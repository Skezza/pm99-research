#!/usr/bin/env python3
"""Capture one season of the local FootballSquads CC0 cache as canonical facts.

The cache is deliberately an *input capture*, not a PM99 writer.  It records
the historic club squad rows, physical facts and shirt numbers used by a
season package, retaining a hash for every source file.  Carrier assignment,
ratings, managers, kits and portraits remain separate reviewed decisions.

Example:

    python3 scripts/capture_footballsquads_season.py \
      --source-root .local/external-sources/cache.footballsquads \
      --season 2015-2016 \
      --output .local/season-sources/footballsquads-2015-16.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


SCHEMA = "pm99-footballsquads-season-capture-v1"
# FootballSquads uses both European split-year (``2015/16``) and calendar-year
# (``2015``) competition titles.  Both are historical season facts; treating
# the latter as invalid silently discarded South American and summer-league
# carriers from a worldwide package.
_TITLE = re.compile(r"^=\s+(.+?)\s+-\s+(.+?)\s+(\d{4}(?:/(?:\d{2}|\d{4}))?)(?:\s+(.+?))?\s*$")
# ``Nat`` was added to the FootballSquads cache after the early PM99-era
# seasons. It is useful when present, but refusing an otherwise precise 1999
# roster because that column did not yet exist loses source facts. Keep the
# missing nationality explicit in ``unresolved_fields`` instead.
_REQUIRED_COLUMNS = (
    "Number", "Pos", "Height", "Weight", "Date of Birth", "Birth Place",
)


class CaptureError(ValueError):
    """The cached source cannot be converted into a clear historical fact."""


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_revision(source_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = result.stdout.strip()
    return value if re.fullmatch(r"[0-9a-f]{40}", value) else None


def _height_cm(value: str, *, label: str) -> int:
    cleaned = value.strip()
    imperial = re.fullmatch(r"(\d+)\s*'\s*(\d+)(?:\s*(?:\"|''))?", cleaned)
    if imperial is not None:
        feet, inches = (int(part) for part in imperial.groups())
        if not 0 <= inches < 12:
            raise CaptureError(f"{label}: invalid imperial height {value!r}")
        centimetres = round((feet * 12 + inches) * 2.54)
    else:
        try:
            metres = float(cleaned)
        except ValueError as exc:
            raise CaptureError(f"{label}: invalid height {value!r}") from exc
        centimetres = round(metres * 100)
    if not 120 <= centimetres <= 230:
        raise CaptureError(f"{label}: implausible height {value!r}")
    return centimetres


def _positive_int(value: str, *, label: str, lower: int, upper: int) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise CaptureError(f"{label}: invalid integer {value!r}") from exc
    if not lower <= result <= upper:
        raise CaptureError(f"{label}: value outside {lower}..{upper}: {result}")
    return result


def _weight_kg(value: str, *, label: str) -> int:
    """Read metric kilograms or the historic stone/pound source notation."""

    cleaned = value.strip()
    try:
        return _positive_int(cleaned, label=label, lower=40, upper=140)
    except CaptureError:
        pass
    imperial = re.fullmatch(r"(\d{1,2})\s+(?:st\s*)?(\d{1,2})(?:\s*lb)?", cleaned, re.IGNORECASE)
    if imperial is None:
        raise CaptureError(f"{label}: invalid weight {value!r}")
    stone, pounds = (int(part) for part in imperial.groups())
    if not 0 <= pounds < 14:
        raise CaptureError(f"{label}: invalid stone/pound weight {value!r}")
    kilograms = round(stone * 6.35029318 + pounds * 0.45359237)
    if not 40 <= kilograms <= 140:
        raise CaptureError(f"{label}: implausible weight {value!r}")
    return kilograms


def _birth_date(value: str, *, season_start: int, label: str) -> str:
    parts = value.split("-")
    if len(parts) != 3:
        raise CaptureError(f"{label}: invalid date of birth {value!r}")
    day = _positive_int(parts[0], label=label, lower=1, upper=31)
    month = _positive_int(parts[1], label=label, lower=1, upper=12)
    year_short = _positive_int(parts[2], label=label, lower=0, upper=99)
    # The early 1999/00 cache stores every two-digit birth year in the 1900s.
    # In later source seasons, a year later than the season suffix is a 1900s
    # birth; the remainder is a 2000s birth. The result is still audited by
    # the package validator.
    season_suffix = season_start % 100
    year = 1900 + year_short if season_start < 2000 or year_short > season_suffix else 2000 + year_short
    return f"{year:04d}-{month:02d}-{day:02d}"


def _read_club_file(path: Path, *, root: Path, season_start: int, season_label: str) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    title = next((line for line in lines if line.strip()), "")
    matched = _TITLE.fullmatch(title)
    if matched is None:
        raise CaptureError(f"{path}: unsupported club-title line {title!r}")
    club_name, competition, source_season, phase = matched.groups()
    split_phase = (phase or "").strip()
    source_is_split_phase = (
        bool(split_phase)
        and source_season in {str(season_start), str(season_start + 1)}
    )
    source_is_full_split_label = source_season == f"{season_start}/{season_start + 1}"
    if source_season != season_label and not source_is_split_phase and not source_is_full_split_label:
        raise CaptureError(
            f"{path}: title season {source_season} does not match {season_label} "
            "or a dated phase in that split season"
        )
    try:
        header_index = next(index for index, line in enumerate(lines) if line.startswith("Number,"))
    except StopIteration as exc:
        raise CaptureError(f"{path}: missing squad CSV header") from exc
    if any(line.startswith("==") for line in lines[:header_index]):
        raise CaptureError(f"{path}: contains no current-squad CSV section")
    data_lines: list[str] = []
    for line in lines[header_index:]:
        if line.startswith("=="):
            break
        if line.strip():
            data_lines.append(line)
    reader = csv.DictReader(data_lines, skipinitialspace=True)
    headers = set(reader.fieldnames or [])
    name_column = "Name" if "Name" in headers else "Namea" if "Namea" in headers else None
    required_columns = set(_REQUIRED_COLUMNS)
    if reader.fieldnames is None or name_column is None or not required_columns <= headers:
        raise CaptureError(f"{path}: unsupported squad CSV columns {reader.fieldnames!r}")
    players: list[dict[str, Any]] = []
    for row_index, row in enumerate(reader, start=1):
        label = f"{path}:{row_index}"
        name = str(row.get(name_column) or "").strip()
        nationality = str(row.get("Nat") or "").strip().upper()
        position = str(row.get("Pos") or "").strip().upper()
        if not name:
            raise CaptureError(f"{label}: missing player name")
        unresolved_fields: list[str] = []
        if not re.fullmatch(r"[A-Z]{3}", nationality):
            nationality = None
            unresolved_fields.append("nationality")
        if position not in {"G", "D", "M", "F"}:
            position = None
            unresolved_fields.append("primary_position")
        try:
            shirt_number = _positive_int(str(row.get("Number") or ""), label=label, lower=1, upper=99)
        except CaptureError:
            shirt_number = None
            unresolved_fields.append("shirt_number")
        try:
            height_cm = _height_cm(str(row.get("Height") or ""), label=label)
        except CaptureError:
            height_cm = None
            unresolved_fields.append("height_cm")
        try:
            weight_kg = _weight_kg(str(row.get("Weight") or ""), label=label)
        except CaptureError:
            weight_kg = None
            unresolved_fields.append("weight_kg")
        try:
            birth_date = _birth_date(str(row.get("Date of Birth") or ""), season_start=season_start, label=label)
        except CaptureError:
            birth_date = None
            unresolved_fields.append("birth_date")
        players.append({
            "shirt_number": shirt_number,
            "name": name,
            "nationality": nationality,
            "position": position,
            "height_cm": height_cm,
            "weight_kg": weight_kg,
            "birth_date": birth_date,
            "unresolved_fields": unresolved_fields,
        })
    if not players:
        raise CaptureError(f"{path}: no current-squad players")
    known_shirt_numbers = [player["shirt_number"] for player in players if player["shirt_number"] is not None]
    if len(set(known_shirt_numbers)) != len(known_shirt_numbers):
        raise CaptureError(f"{path}: duplicate current-squad shirt numbers")
    relative = path.relative_to(root)
    return {
        "country_catalog": relative.parts[0],
        "competition_catalog": relative.parts[2],
        "club_name": club_name,
        "competition_name": " ".join(part for part in (competition, phase) if part),
        "source_path": relative.as_posix(),
        "source_sha256": _sha256_file(path),
        "players": sorted(
            players,
            key=lambda player: (
                int(player["shirt_number"]) if player["shirt_number"] is not None else 1000,
                str(player["name"]),
            ),
        ),
    }


def _season_spec(season: str) -> tuple[int, str, str]:
    """Return ``(start_year, source-title-label, catalog-folder)``.

    The cache names a European campaign ``2015-2016`` but names a
    calendar-year competition simply ``2015``.  Do not coerce the latter to a
    fictional ``2015/16`` label: the source-title check is what stops an
    accidental cross-season roster from entering a release.
    """

    split = re.fullmatch(r"((?:19|20)\d{2})-((?:19|20)\d{2})", season)
    if split is not None:
        start, end = int(split.group(1)), int(split.group(2))
        if end != start + 1:
            raise CaptureError("split-year season must contain consecutive years")
        return start, f"{start}/{str(end)[-2:]}", season
    calendar = re.fullmatch(r"20\d{2}", season)
    if calendar is not None:
        return int(season), season, season
    raise CaptureError("season must be YYYY-YYYY for a split season or YYYY for a calendar-year league")


def capture_season(
    *, source_root: Path, season: str, countries: set[str] | None = None
) -> dict[str, Any]:
    source_root = source_root.expanduser().resolve()
    if not source_root.is_dir():
        raise CaptureError(f"source root does not exist: {source_root}")
    season_start, season_label, catalog_folder = _season_spec(season)
    country_filter = None if countries is None else {str(value).strip() for value in countries if str(value).strip()}
    if country_filter is not None and not country_filter:
        raise CaptureError("country filter must contain at least one non-blank catalog id")
    club_files = sorted(
        path for path in source_root.glob(f"*/{catalog_folder}/*/*.txt") if path.name != "README.md"
    )
    if country_filter is not None:
        club_files = [path for path in club_files if path.relative_to(source_root).parts[0] in country_filter]
        observed = {path.relative_to(source_root).parts[0] for path in club_files}
        missing = sorted(country_filter - observed)
        if missing:
            raise CaptureError("country filter has no matching source files: " + ", ".join(missing))
    clubs: list[dict[str, Any]] = []
    blocked_sources: list[dict[str, str]] = []
    for path in club_files:
        try:
            clubs.append(
                _read_club_file(path, root=source_root, season_start=season_start, season_label=season_label)
            )
        except CaptureError as exc:
            relative_path = path.relative_to(source_root).as_posix()
            message = str(exc)
            prefix = f"{path}: "
            blocked_sources.append({
                "source_path": relative_path,
                "source_sha256": _sha256_file(path),
                "reason": message[len(prefix):] if message.startswith(prefix) else message,
            })
    if not clubs:
        raise CaptureError("no usable current-squad source files matched the requested season")
    clubs.sort(key=lambda club: (str(club["country_catalog"]), str(club["competition_catalog"]), str(club["club_name"])))
    duplicate_keys = [
        (club["country_catalog"], club["competition_catalog"], club["club_name"])
        for club in clubs
    ]
    if len(duplicate_keys) != len(set(duplicate_keys)):
        raise CaptureError("source cache contains duplicate country/competition/club captures")
    result = {
        "schema_version": SCHEMA,
        "source": {
            "title": "footballcsv/cache.footballsquads",
            "repository": "https://github.com/footballcsv/cache.footballsquads",
            "revision": _repo_revision(source_root),
            "license": "CC0-1.0",
        },
        "season": {"catalog": catalog_folder, "label": season_label},
        "clubs": clubs,
        "summary": {
            "club_count": len(clubs),
            "player_count": sum(len(club["players"]) for club in clubs),
            "player_rows_with_unresolved_facts": sum(
                1 for club in clubs for player in club["players"] if player["unresolved_fields"]
            ),
            "country_catalogs": sorted({str(club["country_catalog"]) for club in clubs}),
            "competition_catalogs": sorted({
                f"{club['country_catalog']}/{club['competition_catalog']}" for club in clubs
            }),
        },
    }
    if blocked_sources:
        result["blocked_sources"] = blocked_sources
        result["summary"]["blocked_source_count"] = len(blocked_sources)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--season", required=True)
    parser.add_argument(
        "--country",
        action="append",
        default=[],
        help="Restrict to one source-country catalog; repeatable. Useful where a cache folder has a different calendar label.",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        capture = capture_season(
            source_root=args.source_root,
            season=args.season,
            countries=set(args.country) if args.country else None,
        )
    except CaptureError as exc:
        raise SystemExit(f"capture failed: {exc}") from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical_json_bytes(capture))
    print(json.dumps({"output": str(args.output), **capture["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
