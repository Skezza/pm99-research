#!/usr/bin/env python3
"""Snapshot and normalise an attributed FootballSquads web season.

The historical cache used by the earlier seasons ends at 2023/24.  This tool
provides the same source-only boundary for a later, user-authorised
non-commercial FootballSquads web snapshot:

* ``snapshot`` discovers the archive's dated league pages, stores the exact
  index and club HTML locally, and creates one canonical manifest;
* ``capture`` turns one retained source catalogue (for example ``2024-2025``
  or calendar-year ``2024``) into the existing FootballSquads capture schema;
* ``verify`` recomputes that capture from the retained local snapshot.

It does not infer facts, choose PM99 carriers, or write a game database.
Online fetching is only performed by ``snapshot``.  A completed snapshot can
therefore be replayed and audited offline even after FootballSquads changes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_footballsquads_season as local_capture  # noqa: E402


SNAPSHOT_SCHEMA = "pm99-footballsquads-web-snapshot-v1"
CAPTURE_SCHEMA = local_capture.SCHEMA
DEFAULT_ARCHIVE_URL = "https://footballsquads.co.uk/archive.htm"
TERMS_URL = "https://www.footballsquads.co.uk/tou.htm"
ALLOWED_HOSTS = {"footballsquads.co.uk", "www.footballsquads.co.uk"}
ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,79}$")
ISO_DATE_RE = re.compile(r"^20\d{2}-\d{2}-\d{2}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class WebCaptureError(ValueError):
    """The web source, retained snapshot, or requested output is unsafe."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise WebCaptureError(f"{label} must be a stable lower-case ID")
    return value


def _safe_relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise WebCaptureError(f"{label} must be a non-empty POSIX relative path")
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or ".." in candidate.parts or "." in candidate.parts:
        raise WebCaptureError(f"{label} must be a safe relative path")
    return value


def _normalise_url(value: str, *, label: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.netloc.casefold() not in ALLOWED_HOSTS or not parsed.path:
        raise WebCaptureError(f"{label} must be an HTTPS FootballSquads URL")
    if parsed.params or parsed.query or parsed.fragment:
        raise WebCaptureError(f"{label} must not contain parameters, query text, or a fragment")
    return f"https://footballsquads.co.uk{parsed.path}"


def _html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value, flags=re.S)
    return " ".join(html.unescape(text).split())


def _html_links(payload: bytes, *, base_url: str) -> list[tuple[str, str]]:
    text = payload.decode("utf-8", errors="replace")
    result: list[tuple[str, str]] = []
    for href, label in re.findall(
        r"<a\b[^>]*\bhref\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
        text,
        flags=re.S | re.I,
    ):
        candidate = urljoin(base_url, html.unescape(href).strip())
        try:
            result.append((_html_text(label), _normalise_url(candidate, label="source link")))
        except WebCaptureError:
            continue
    return result


def season_catalogues(season: str) -> tuple[int, int, str, set[str]]:
    matched = re.fullmatch(r"(20\d{2})-(20\d{2})", season)
    if matched is None:
        raise WebCaptureError("season must be a consecutive split year such as 2024-2025")
    start_year, end_year = (int(item) for item in matched.groups())
    if end_year != start_year + 1:
        raise WebCaptureError("season must contain consecutive years")
    return start_year, end_year, f"{start_year}/{str(end_year)[-2:]}", {season, str(start_year)}


def discover_index_pages(*, archive_payload: bytes, archive_url: str, season: str) -> list[dict[str, str]]:
    """Discover dated league pages without guessing country or competition IDs."""

    _start, _end, _label, accepted_catalogues = season_catalogues(season)
    rows: dict[str, dict[str, str]] = {}
    for anchor_label, url in _html_links(archive_payload, base_url=archive_url):
        parsed = urlparse(url)
        parts = [part for part in PurePosixPath(parsed.path).parts if part != "/"]
        if len(parts) != 3 or not parts[-1].endswith(".htm"):
            continue
        country, source_catalog, filename = parts
        if source_catalog not in accepted_catalogues:
            continue
        if filename == "archive.htm":
            continue
        row = {
            "country_catalog": country,
            "source_catalog": source_catalog,
            "competition_catalog": Path(filename).stem,
            "url": url,
            "archive_label": anchor_label,
        }
        previous = rows.get(url)
        if previous is not None and previous != row:
            raise WebCaptureError(f"archive has conflicting metadata for {url}")
        rows[url] = row
    if not rows:
        raise WebCaptureError(f"archive has no dated league pages for {season}")
    return sorted(
        rows.values(),
        key=lambda row: (row["source_catalog"], row["country_catalog"], row["competition_catalog"]),
    )


def discover_club_pages(*, index_payload: bytes, index: Mapping[str, str]) -> list[dict[str, str]]:
    """Retain only club links below this exact dated league directory."""

    index_url = _normalise_url(str(index["url"]), label="index URL")
    index_path = urlparse(index_url).path
    prefix = index_path.rsplit("/", 1)[0] + "/"
    rows: dict[str, dict[str, str]] = {}
    for anchor_label, url in _html_links(index_payload, base_url=index_url):
        path = urlparse(url).path
        if not path.startswith(prefix) or not path.endswith(".htm"):
            continue
        relative_tail = path[len(prefix) :]
        # FootballSquads has stable dated country/season directories, but its
        # page-list filename is not always the club-page subdirectory (for
        # example ``argprim.htm`` lists ``primera/*.htm``).  Retain exactly
        # one child directory and one club page; this still excludes global
        # navigation and other dated season indexes.
        if len(PurePosixPath(relative_tail).parts) != 2:
            continue
        row = {"url": url, "archive_label": anchor_label}
        previous = rows.get(url)
        if previous is not None and previous != row:
            raise WebCaptureError(f"index {index_url} has conflicting club labels for {url}")
        rows[url] = row
    if not rows:
        raise WebCaptureError(f"index {index_url} has no club links below its dated competition directory")
    return [rows[url] for url in sorted(rows)]


def _table_rows(payload: bytes) -> list[list[str]]:
    document = payload.decode("utf-8", errors="replace")
    rows: list[list[str]] = []
    for row_html in re.findall(r"<tr\b[^>]*>(.*?)</tr>", document, flags=re.S | re.I):
        cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row_html, flags=re.S | re.I)
        if cells:
            rows.append([_html_text(cell) for cell in cells])
    return rows


def _club_name(payload: bytes, *, label: str) -> str:
    document = payload.decode("utf-8", errors="replace")
    matched = re.search(r"<h2\b[^>]*>(.*?)</h2>", document, flags=re.S | re.I)
    name = _html_text(matched.group(1)) if matched is not None else ""
    if not name:
        raise WebCaptureError(f"{label}: missing club h2 heading")
    return name


def _player_row(*, cells: list[str], source_year: int, label: str) -> dict[str, Any] | None:
    if len(cells) < 9:
        return None
    name = cells[1].strip()
    if not name:
        return None
    unresolved: list[str] = []
    nationality = cells[2].strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", nationality):
        nationality = None
        unresolved.append("nationality")
    position = cells[3].strip().upper()
    if position not in {"G", "D", "M", "F"}:
        position = None
        unresolved.append("primary_position")
    try:
        shirt_number = local_capture._positive_int(cells[0], label=label, lower=1, upper=99)
    except local_capture.CaptureError:
        shirt_number = None
        unresolved.append("shirt_number")
    try:
        height_cm = local_capture._height_cm(cells[4], label=label)
    except local_capture.CaptureError:
        height_cm = None
        unresolved.append("height_cm")
    try:
        weight_kg = local_capture._weight_kg(cells[5], label=label)
    except local_capture.CaptureError:
        weight_kg = None
        unresolved.append("weight_kg")
    try:
        birth_date = local_capture._birth_date(cells[6], season_start=source_year, label=label)
    except local_capture.CaptureError:
        birth_date = None
        unresolved.append("birth_date")
    return {
        "shirt_number": shirt_number,
        "name": name,
        "nationality": nationality,
        "position": position,
        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "birth_date": birth_date,
        "unresolved_fields": unresolved,
    }


def parse_club_page(*, payload: bytes, source_year: int, label: str) -> tuple[str, list[dict[str, Any]]]:
    """Read only the current-squad table; past-player tables are excluded."""

    name = _club_name(payload, label=label)
    players: list[dict[str, Any]] = []
    in_current_squad = False
    for row_index, cells in enumerate(_table_rows(payload), start=1):
        if len(cells) == 1 and "players no longer" in cells[0].casefold():
            break
        if cells and cells[0].casefold() == "number" and len(cells) >= 9:
            in_current_squad = True
            continue
        if not in_current_squad:
            continue
        player = _player_row(cells=cells, source_year=source_year, label=f"{label}:row {row_index}")
        if player is not None:
            players.append(player)
    if not players:
        raise WebCaptureError(f"{label}: no current-squad player rows")
    known_numbers = [player["shirt_number"] for player in players if player["shirt_number"] is not None]
    if len(known_numbers) != len(set(known_numbers)):
        raise WebCaptureError(f"{label}: duplicate current-squad shirt numbers")
    return name, sorted(
        players,
        key=lambda player: (
            int(player["shirt_number"]) if player["shirt_number"] is not None else 1000,
            str(player["name"]),
        ),
    )


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
    except FileExistsError as exc:
        raise WebCaptureError(f"refusing to overwrite existing output: {path}") from exc


def _cache_path(*, kind: str, parsed_url: str) -> str:
    path = urlparse(parsed_url).path.lstrip("/")
    return f"{kind}/{path}"


def _fetch_url(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "PM99RE attributed historical source snapshot/1.0"})
    with urlopen(request, timeout=45) as response:
        return response.read()


def snapshot_season(
    *,
    archive_url: str,
    season: str,
    snapshot_id: str,
    retrieved_on: str,
    cache_root: Path,
    fetch: Callable[[str], bytes] = _fetch_url,
    delay_seconds: float = 0.1,
) -> dict[str, Any]:
    """Fetch each required page once into a new, immutable local snapshot."""

    archive_url = _normalise_url(archive_url, label="archive URL")
    _require_id(snapshot_id, "snapshot_id")
    if not isinstance(retrieved_on, str) or not ISO_DATE_RE.fullmatch(retrieved_on):
        raise WebCaptureError("retrieved_on must be an ISO date")
    start_year, end_year, season_label, _catalogues = season_catalogues(season)
    if cache_root.exists():
        raise WebCaptureError(f"cache root already exists; choose a new snapshot path: {cache_root}")
    if delay_seconds < 0:
        raise WebCaptureError("delay_seconds must be non-negative")
    cache_root.mkdir(parents=True)

    def get(url: str) -> bytes:
        payload = fetch(url)
        if not isinstance(payload, bytes) or not payload:
            raise WebCaptureError(f"source fetch returned no bytes: {url}")
        if delay_seconds:
            time.sleep(delay_seconds)
        return payload

    archive_payload = get(archive_url)
    archive_cache_path = "archive.html"
    _write_new(cache_root / archive_cache_path, archive_payload)
    indexes: list[dict[str, Any]] = []
    for index in discover_index_pages(archive_payload=archive_payload, archive_url=archive_url, season=season):
        index_payload = get(index["url"])
        index_cache_path = _cache_path(kind="indexes", parsed_url=index["url"])
        _write_new(cache_root / index_cache_path, index_payload)
        clubs: list[dict[str, str]] = []
        for club in discover_club_pages(index_payload=index_payload, index=index):
            club_payload = get(club["url"])
            club_cache_path = _cache_path(kind="clubs", parsed_url=club["url"])
            _write_new(cache_root / club_cache_path, club_payload)
            clubs.append(
                {
                    "archive_label": club["archive_label"],
                    "cache_path": club_cache_path,
                    "sha256": sha256_bytes(club_payload),
                    "url": club["url"],
                }
            )
        indexes.append(
            {
                **index,
                "cache_path": index_cache_path,
                "sha256": sha256_bytes(index_payload),
                "clubs": clubs,
            }
        )
    return {
        "schema_version": SNAPSHOT_SCHEMA,
        "snapshot_id": snapshot_id,
        "retrieved_on": retrieved_on,
        "source": {
            "archive_url": archive_url,
            "terms_url": TERMS_URL,
            "attribution": "FootballSquads.com — non-commercial use with attribution, user-authorised",
        },
        "season": {
            "start_year": start_year,
            "end_year": end_year,
            "label": season_label,
            "split_catalog": season,
            "calendar_catalog": str(start_year),
        },
        "archive": {"cache_path": archive_cache_path, "sha256": sha256_bytes(archive_payload)},
        "indexes": indexes,
        "summary": {
            "index_count": len(indexes),
            "club_page_count": sum(len(index["clubs"]) for index in indexes),
            "source_catalogs": sorted({str(index["source_catalog"]) for index in indexes}),
        },
    }


def _read_canonical(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WebCaptureError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise WebCaptureError(f"{label} must use canonical JSON bytes")
    return value, sha256_bytes(raw)


def _read_snapshot(path: Path) -> tuple[dict[str, Any], str]:
    snapshot, digest = _read_canonical(path, label="web snapshot manifest")
    expected = {"schema_version", "snapshot_id", "retrieved_on", "source", "season", "archive", "indexes", "summary"}
    if set(snapshot) != expected or snapshot.get("schema_version") != SNAPSHOT_SCHEMA:
        raise WebCaptureError(f"web snapshot manifest must use {SNAPSHOT_SCHEMA}")
    _require_id(snapshot.get("snapshot_id"), "snapshot_id")
    if not isinstance(snapshot.get("retrieved_on"), str) or not ISO_DATE_RE.fullmatch(snapshot["retrieved_on"]):
        raise WebCaptureError("snapshot retrieved_on is invalid")
    season = snapshot.get("season")
    if not isinstance(season, Mapping) or set(season) != {
        "start_year", "end_year", "label", "split_catalog", "calendar_catalog"
    }:
        raise WebCaptureError("snapshot season is malformed")
    if not isinstance(season["start_year"], int) or not isinstance(season["end_year"], int):
        raise WebCaptureError("snapshot season years are invalid")
    if season["end_year"] != season["start_year"] + 1:
        raise WebCaptureError("snapshot season years are not consecutive")
    if not isinstance(snapshot.get("indexes"), list) or not snapshot["indexes"]:
        raise WebCaptureError("snapshot has no index pages")
    return snapshot, digest


def _snapshot_bytes(*, cache_root: Path, relative_path: Any, digest: Any, label: str) -> bytes:
    relative = _safe_relative_path(relative_path, f"{label}.cache_path")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise WebCaptureError(f"{label}.sha256 is invalid")
    path = (cache_root / relative).resolve()
    try:
        path.relative_to(cache_root.resolve())
    except ValueError as exc:
        raise WebCaptureError(f"{label}.cache_path escapes the snapshot root") from exc
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise WebCaptureError(f"cannot read retained source {relative}") from exc
    if sha256_bytes(payload) != digest:
        raise WebCaptureError(f"retained source hash does not match snapshot: {relative}")
    return payload


def capture_from_snapshot(*, snapshot: Mapping[str, Any], snapshot_sha256: str, cache_root: Path, catalog: str) -> dict[str, Any]:
    """Create one canonical raw capture from an immutable local snapshot."""

    if not isinstance(catalog, str) or not catalog:
        raise WebCaptureError("catalog must be non-blank")
    season = snapshot["season"]
    source_year = int(season["start_year"])
    if catalog == season["split_catalog"]:
        season_label = str(season["label"])
    elif catalog == season["calendar_catalog"]:
        season_label = catalog
    else:
        raise WebCaptureError("catalog is not declared by this snapshot")
    clubs: list[dict[str, Any]] = []
    blocked_sources: list[dict[str, str]] = []
    for index in snapshot["indexes"]:
        if not isinstance(index, Mapping) or index.get("source_catalog") != catalog:
            continue
        required = {"country_catalog", "source_catalog", "competition_catalog", "url", "archive_label", "cache_path", "sha256", "clubs"}
        if set(index) != required or not isinstance(index.get("clubs"), list):
            raise WebCaptureError("snapshot index row is malformed")
        _snapshot_bytes(
            cache_root=cache_root,
            relative_path=index["cache_path"],
            digest=index["sha256"],
            label="snapshot index",
        )
        for club in index["clubs"]:
            if not isinstance(club, Mapping) or set(club) != {"archive_label", "cache_path", "sha256", "url"}:
                raise WebCaptureError("snapshot club row is malformed")
            relative_path = _safe_relative_path(club["cache_path"], "snapshot club.cache_path")
            payload = _snapshot_bytes(
                cache_root=cache_root,
                relative_path=relative_path,
                digest=club["sha256"],
                label="snapshot club",
            )
            try:
                name, players = parse_club_page(
                    payload=payload,
                    source_year=source_year,
                    label=relative_path,
                )
            except WebCaptureError as exc:
                blocked_sources.append(
                    {"source_path": relative_path, "source_sha256": str(club["sha256"]), "reason": str(exc)}
                )
                continue
            clubs.append(
                {
                    "country_catalog": str(index["country_catalog"]),
                    "competition_catalog": str(index["competition_catalog"]),
                    "club_name": name,
                    "competition_name": str(index["archive_label"]),
                    "source_path": relative_path,
                    "source_sha256": str(club["sha256"]),
                    "players": players,
                }
            )
    if not clubs:
        raise WebCaptureError(f"snapshot has no usable club pages for catalog {catalog}")
    clubs.sort(key=lambda club: (club["country_catalog"], club["competition_catalog"], club["club_name"]))
    selectors = [(club["country_catalog"], club["competition_catalog"], club["club_name"]) for club in clubs]
    if len(selectors) != len(set(selectors)):
        raise WebCaptureError("snapshot has duplicate country/competition/club source selectors")
    result: dict[str, Any] = {
        "schema_version": CAPTURE_SCHEMA,
        "source": {
            "title": "FootballSquads attributed web snapshot",
            "repository": "https://footballsquads.co.uk/",
            "revision": str(snapshot["snapshot_id"]),
            "license": "FootballSquads non-commercial use with attribution",
            "terms_url": TERMS_URL,
            "snapshot_manifest_sha256": snapshot_sha256,
        },
        "season": {"catalog": catalog, "label": season_label},
        "clubs": clubs,
        "summary": {
            "club_count": len(clubs),
            "player_count": sum(len(club["players"]) for club in clubs),
            "player_rows_with_unresolved_facts": sum(
                1
                for club in clubs
                for player in club["players"]
                if player["unresolved_fields"]
            ),
            "country_catalogs": sorted({str(club["country_catalog"]) for club in clubs}),
            "competition_catalogs": sorted(
                {f"{club['country_catalog']}/{club['competition_catalog']}" for club in clubs}
            ),
        },
    }
    if blocked_sources:
        result["blocked_sources"] = sorted(blocked_sources, key=lambda row: row["source_path"])
        result["summary"]["blocked_source_count"] = len(blocked_sources)
    return result


def _snapshot_command(args: argparse.Namespace) -> None:
    cache_root = args.cache_root.resolve()
    manifest_path = args.manifest.resolve()
    if manifest_path.exists():
        raise WebCaptureError(f"refusing to overwrite existing output: {manifest_path}")
    snapshot = snapshot_season(
        archive_url=args.archive_url,
        season=args.season,
        snapshot_id=args.snapshot_id,
        retrieved_on=args.retrieved_on,
        cache_root=cache_root,
        delay_seconds=args.delay_seconds,
    )
    _write_new(manifest_path, canonical_json_bytes(snapshot))
    print(json.dumps({"manifest": str(manifest_path), **snapshot["summary"]}, sort_keys=True))


def _capture_command(args: argparse.Namespace, *, verify: bool) -> None:
    snapshot, digest = _read_snapshot(args.snapshot.resolve())
    capture = capture_from_snapshot(
        snapshot=snapshot,
        snapshot_sha256=digest,
        cache_root=args.cache_root.resolve(),
        catalog=args.catalog,
    )
    if verify:
        actual, _actual_digest = _read_canonical(args.capture.resolve(), label="web source capture")
        if actual != capture:
            raise WebCaptureError("web source capture does not exactly match the retained snapshot")
        print(json.dumps({"capture": str(args.capture), "status": "validated", **capture["summary"]}, sort_keys=True))
        return
    output = args.output.resolve()
    _write_new(output, canonical_json_bytes(capture))
    print(json.dumps({"output": str(output), **capture["summary"]}, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot = subparsers.add_parser("snapshot", help="Fetch a new immutable local web snapshot")
    snapshot.add_argument("--archive-url", default=DEFAULT_ARCHIVE_URL)
    snapshot.add_argument("--season", required=True, help="Split year, for example 2024-2025")
    snapshot.add_argument("--snapshot-id", required=True)
    snapshot.add_argument("--retrieved-on", required=True, help="Explicit YYYY-MM-DD acquisition date")
    snapshot.add_argument("--cache-root", required=True, type=Path)
    snapshot.add_argument("--manifest", required=True, type=Path)
    snapshot.add_argument("--delay-seconds", type=float, default=0.1)
    capture = subparsers.add_parser("capture", help="Build one source capture from a retained snapshot")
    capture.add_argument("--snapshot", required=True, type=Path)
    capture.add_argument("--cache-root", required=True, type=Path)
    capture.add_argument("--catalog", required=True, help="Declared split or calendar source catalogue")
    capture.add_argument("--output", required=True, type=Path)
    verify = subparsers.add_parser("verify", help="Verify one source capture against a retained snapshot")
    verify.add_argument("--snapshot", required=True, type=Path)
    verify.add_argument("--cache-root", required=True, type=Path)
    verify.add_argument("--catalog", required=True, help="Declared split or calendar source catalogue")
    verify.add_argument("--capture", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "snapshot":
            _snapshot_command(args)
        elif args.command == "capture":
            _capture_command(args, verify=False)
        else:
            _capture_command(args, verify=True)
    except (OSError, WebCaptureError) as exc:
        raise SystemExit(f"web capture failed: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
