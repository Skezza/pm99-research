#!/usr/bin/env python3
"""Era-aware, deterministic PM99 season portrait pipeline.

The lane is deliberately independent from database compilation.  It plans
identity matches from a canonical season package and a dated SoFIFA/FIFA CSV,
downloads only edition-specific player-ID URLs, converts them to the native
PM99 minifoto bitmap shape, and applies the complete set to a copy-on-write
game tree.  Every unresolved or failed source becomes native no-photo so a
recycled carrier can never retain an unrelated 1998 face.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import fcntl
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

import requests
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream/pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR, ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import (  # noqa: E402
    discover_riff_palette_resource,
    iter_minifoto_records,
    iter_minifoto_records_from_bytes,
    load_riff_palette,
    validate_minifoto_bitmap,
)
from prepare_stoke_2015_face_dbdat import (  # noqa: E402
    _build_palette_image,
    _build_replacement_bitmap,
)
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_pipeline_v2 as pipeline_v2  # noqa: E402
from scripts.materialise_native_no_photo_v2 import _active_offsets_for_players  # noqa: E402


PLAN_SCHEMA = "pm99-season-portrait-plan-v1"
MATERIALISATION_SCHEMA = "pm99-season-portrait-materialisation-v1"
APPLICATION_SCHEMA = "pm99-season-portrait-application-v1"
VALIDATION_SCHEMA = "pm99-season-portrait-validation-v1"
USER_AGENT = "playpm99-era-portrait-pipeline/1.0 (+local historical game mod)"
DEFAULT_CACHE = ROOT / ".local/season-portrait-cache-v1"
DEFAULT_OUTPUT = ROOT / ".local/season-portrait-pilots-v1"


class PortraitPipelineError(ValueError):
    """The portrait lane cannot safely continue."""


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PortraitPipelineError(f"cannot read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise PortraitPipelineError(f"JSON must be an object: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pipeline_v2.write_canonical_json(path, dict(value))


def _normalise_name(value: str) -> str:
    # These letters do not decompose under NFKD; silently dropping them turns
    # Łukasz into Ukasz and invalidates an otherwise exact identity join.
    value = value.translate(str.maketrans({'ł': 'l', 'Ł': 'L', 'ð': 'd', 'Ð': 'D',
                                          'þ': 'th', 'Þ': 'Th', 'ø': 'o', 'Ø': 'O'}))
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"['’`]", "", text)
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def _name_score(target: str, short_name: str, long_name: str) -> tuple[int, str]:
    target_norm = _normalise_name(target)
    short_norm = _normalise_name(short_name)
    long_norm = _normalise_name(long_name)
    if target_norm and target_norm in {short_norm, long_norm}:
        return 100, "exact-normalised-name"
    target_tokens = target_norm.split()
    long_tokens = long_norm.split()
    aliases = {"phil": "phillip", "steve": "steven", "mike": "michael", "matt": "matthew", "chris": "christopher",
               "rob": "robert", "nick": "nicholas", "andy": "andrew", "joe": "joseph", "dan": "daniel",
               "tom": "thomas", "tony": "anthony", "jim": "james", "ben": "benjamin"}
    target_alias_tokens = [aliases.get(token, token) for token in target_tokens]
    long_alias_tokens = [aliases.get(token, token) for token in long_tokens]
    if target_alias_tokens and target_alias_tokens == long_alias_tokens:
        return 95, "normalised-given-name-alias"
    target_tokens, long_tokens = target_alias_tokens, long_alias_tokens
    if len(target_tokens) >= 2 and set(target_tokens).issubset(set(long_tokens)):
        return 85, "target-name-tokens-contained-in-long-name"
    if len(target_tokens) >= 2 and target_tokens[-1] in long_tokens:
        overlap = len(set(target_tokens).intersection(long_tokens))
        if overlap >= 2:
            return 70, "surname-and-given-token-match"
    return 0, "name-mismatch"


def _season_label(package: Mapping[str, Any]) -> str:
    season = package.get("season")
    if not isinstance(season, Mapping) or not isinstance(season.get("label"), str):
        raise PortraitPipelineError("package has no season.label")
    return str(season["label"]).replace("/", "-")


def _club_by_player(package: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for club in package.get("clubs", []):
        if not isinstance(club, Mapping):
            continue
        for player_id in club.get("roster_player_ids", []):
            if isinstance(player_id, str):
                result[player_id] = str(club.get("name") or "")
    return result


def _load_edition_rows(path: Path) -> tuple[list[dict[str, str]], str]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
        rows = [dict(row) for row in csv.DictReader(io.StringIO(text))]
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise PortraitPipelineError(f"cannot read edition CSV: {path}") from exc
    required = {"sofifa_id", "short_name", "long_name", "dob", "club", "player_url"}
    if not rows or not required.issubset(rows[0]):
        raise PortraitPipelineError(f"edition CSV lacks required columns: {sorted(required)}")
    return rows, _sha_bytes(raw)


def build_plan(*, package_path: Path, edition_csv: Path, edition: int) -> dict[str, Any]:
    package = package_v2.read_canonical_package(package_path)
    rows, csv_hash = _load_edition_rows(edition_csv)
    season = _season_label(package)
    package_hash = package_v2.sha256_bytes(package_v2.canonical_json_bytes(package))
    by_dob: dict[str, list[dict[str, str]]] = defaultdict(list)
    by_exact_name: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row.get("dob"):
            by_dob[row["dob"]].append(row)
        for value in (row.get("short_name", ""), row.get("long_name", "")):
            if _normalise_name(value):
                by_exact_name[_normalise_name(value)].append(row)
    club_names = _club_by_player(package)
    planned: list[dict[str, Any]] = []
    used_source_ids: set[int] = set()
    for player in sorted(package["players"], key=lambda row: (int(row["carrier_id"]), str(row["id"]))):
        facts = player.get("facts") if isinstance(player.get("facts"), Mapping) else {}
        dob = facts.get("birth_date") if isinstance(facts.get("birth_date"), str) else None
        candidates = by_dob.get(dob, []) if dob else by_exact_name.get(_normalise_name(str(player["name"])), [])
        scored: list[tuple[int, str, dict[str, str]]] = []
        for candidate in candidates:
            score, method = _name_score(str(player["name"]), candidate.get("short_name", ""), candidate.get("long_name", ""))
            if score:
                scored.append((score, method, candidate))
        scored.sort(key=lambda item: (-item[0], int(item[2]["sofifa_id"])))
        accepted: tuple[int, str, dict[str, str]] | None = None
        if scored and scored[0][0] >= 85 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
            accepted = scored[0]
        base = {
            "player_id": str(player["id"]),
            "person_id": player.get("person_id"),
            "carrier_id": int(player["carrier_id"]),
            "name": str(player["name"]),
            "birth_date": dob,
            "target_club": club_names.get(str(player["id"]), ""),
            "target_season": season,
        }
        if accepted is None:
            planned.append({
                **base,
                "status": "native-no-photo",
                "reason": "no-unique-exact-era-identity",
                "candidate_count": len(scored),
                "era_grade": "unresolved",
            })
            continue
        score, method, source = accepted
        source_id = int(source["sofifa_id"])
        # A source identity may map to only one final PM99 carrier in a season.
        if source_id in used_source_ids:
            planned.append({
                **base,
                "status": "native-no-photo",
                "reason": "edition-identity-already-assigned",
                "sofifa_id": source_id,
                "era_grade": "unresolved",
            })
            continue
        used_source_ids.add(source_id)
        source_url = f"https://cdn.sofifa.net/players/{source_id // 1000}/{source_id % 1000:03d}/{edition}_120.png"
        planned.append({
            **base,
            "status": "era-source-candidate",
            "identity_match": method,
            "identity_score": score,
            "source_name": source.get("long_name") or source.get("short_name"),
            "source_birth_date": source.get("dob"),
            "source_club": source.get("club"),
            "sofifa_id": source_id,
            "source_profile_url": source.get("player_url"),
            "source_image_url": source_url,
            "source_edition": edition,
            "era_grade": "exact-target-edition",
            "era_distance_seasons": 0,
        })
    counts: dict[str, int] = defaultdict(int)
    for row in planned:
        counts[str(row["status"])] += 1
    return {
        "schema_version": PLAN_SCHEMA,
        "season": season,
        "result": "complete",
        "policy": {
            "identity": "unique dated identity match; ambiguous names are rejected",
            "era": "exact target-edition image only in v1 pilot",
            "fallback": "native-no-photo; never retain an inherited carrier face",
        },
        "inputs": {
            "package_path": str(package_path.resolve()),
            "package_canonical_sha256": package_hash,
            "edition_csv_path": str(edition_csv.resolve()),
            "edition_csv_sha256": csv_hash,
            "edition": edition,
        },
        "coverage": {
            "player_count": len(planned),
            "candidate_count": counts["era-source-candidate"],
            "native_no_photo_count": counts["native-no-photo"],
        },
        "players": planned,
    }


def _validate_source_image(payload: bytes) -> dict[str, Any]:
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.verify()
        with Image.open(io.BytesIO(payload)) as image:
            width, height = image.size
            if width < 24 or height < 24:
                raise ValueError("image is too small")
            return {"width": int(width), "height": int(height), "format": str(image.format or "unknown")}
    except Exception as exc:
        raise PortraitPipelineError(f"invalid source image: {type(exc).__name__}: {exc}") from exc


def _cache_paths(cache_root: Path, url: str) -> tuple[Path, Path]:
    key = _sha_bytes(url.encode("utf-8"))
    return cache_root / "urls" / key[:2] / f"{key}.json", cache_root / "url-payloads" / key[:2] / f"{key}.bin"


def _logical_size(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _fetch(row: Mapping[str, Any], *, cache_root: Path, timeout: int) -> dict[str, Any]:
    if row.get("status") != "era-source-candidate":
        return dict(row)
    url = str(row["source_image_url"])
    meta_path, payload_path = _cache_paths(cache_root, url)
    lock_path = meta_path.with_suffix('.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # Loans/duplicate roster references can ask for the same URL in parallel.
    # Serialize by URL across threads AND processes; retain immutable receipts.
    with lock_path.open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        return _fetch_locked(row, url, meta_path, payload_path, timeout)


def _fetch_locked(row, url, meta_path, payload_path, timeout):
    if meta_path.is_file() and payload_path.is_file():
        meta = _read_json(meta_path)
        payload = payload_path.read_bytes()
        if meta.get("url") == url and meta.get("source_sha256") == _sha_bytes(payload):
            return {**row, "fetch_status": "cache-hit", "payload": payload, "source_sha256": meta["source_sha256"], "source_dimensions": meta["source_dimensions"]}
    headers = {"User-Agent": USER_AGENT, "Accept": "image/png,image/*;q=0.9", "Referer": "https://sofifa.com/"}
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        if response.status_code != 200:
            raise PortraitPipelineError(f"HTTP {response.status_code}")
        payload = bytes(response.content)
        dimensions = _validate_source_image(payload)
    except Exception as exc:
        return {**row, "status": "native-no-photo", "reason": f"era-source-fetch-failed: {type(exc).__name__}: {exc}", "attempted_url": url}
    digest = _sha_bytes(payload)
    if meta_path.exists():
        meta = _read_json(meta_path)
        if meta.get('url') != url or meta.get('source_sha256') != digest:
            return {**row, 'status': 'native-no-photo',
                    'reason': 'recovered-source-does-not-match-retained-cache-receipt', 'attempted_url': url}
        if payload_path.exists() and _sha_bytes(payload_path.read_bytes()) != digest:
            return {**row, 'status': 'native-no-photo',
                    'reason': 'retained-cache-payload-is-corrupt', 'attempted_url': url}
        if not payload_path.exists():
            payload_path.parent.mkdir(parents=True, exist_ok=True)
            payload_path.write_bytes(payload)
        return {**row, 'fetch_status': 'recovered-hash-matching-payload', 'payload': payload,
                'source_sha256': digest, 'source_dimensions': meta['source_dimensions']}
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    if payload_path.exists() and _sha_bytes(payload_path.read_bytes()) != digest:
        return {**row, 'status': 'native-no-photo',
                'reason': 'orphan-cache-payload-conflicts-with-downloaded-source', 'attempted_url': url}
    if not payload_path.exists():
        payload_path.write_bytes(payload)
    _write_json(meta_path, {"url": url, "source_sha256": digest, "source_dimensions": dimensions})
    return {**row, "fetch_status": "downloaded", "payload": payload, "source_sha256": digest, "source_dimensions": dimensions}


def materialise(*, plan_path: Path, minifoto_path: Path, cache_root: Path, output_root: Path, workers: int, timeout: int, write_previews: bool, max_local_bytes: int) -> dict[str, Any]:
    plan = _read_json(plan_path)
    if plan.get("schema_version") != PLAN_SCHEMA:
        raise PortraitPipelineError("portrait plan schema is unsupported")
    if not minifoto_path.is_file():
        raise PortraitPipelineError(f"missing MINIFOTO.PKF: {minifoto_path}")
    records = list(iter_minifoto_records(minifoto_path))
    if not records:
        raise PortraitPipelineError("MINIFOTO.PKF contains no parseable template")
    palette_path, _palette_source = discover_riff_palette_resource(minifoto_path, extra_roots=[minifoto_path.parent, minifoto_path.parent.parent])
    if palette_path is None:
        raise PortraitPipelineError("could not resolve PM99 portrait palette")
    palette_rgb = load_riff_palette(palette_path)
    palette_image = _build_palette_image(palette_rgb)
    template = records[0]
    candidates = [row for row in plan["players"] if row.get("status") == "era-source-candidate"]
    if shutil.disk_usage(output_root.parent if output_root.parent.exists() else ROOT).free < max_local_bytes:
        raise PortraitPipelineError("free disk space is below the requested portrait working budget")
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        fetched = list(pool.map(lambda row: _fetch(row, cache_root=cache_root, timeout=timeout), candidates))
    logical_usage = _logical_size(cache_root) + _logical_size(output_root)
    if logical_usage > max_local_bytes:
        raise PortraitPipelineError("portrait cache exceeded --max-local-bytes")
    fetched_by_player = {row["player_id"]: row for row in fetched}
    result_rows: list[dict[str, Any]] = []
    output_root.mkdir(parents=True, exist_ok=True)
    for planned in plan["players"]:
        row = fetched_by_player.get(planned["player_id"], planned)
        payload = row.get("payload")
        if row.get("status") != "era-source-candidate" or not isinstance(payload, bytes):
            result_rows.append({key: value for key, value in row.items() if key != "payload"})
            continue
        try:
            with Image.open(io.BytesIO(payload)) as source:
                bitmap, crop, preview = _build_replacement_bitmap(
                    raw_bitmap_template=template.raw_bitmap,
                    pixel_offset=template.pixel_offset,
                    width=template.width,
                    height=template.height,
                    source_image=source,
                    palette_image=palette_image,
                    palette_rgb=palette_rgb,
                    allowed_indices=list(range(len(palette_rgb))),
                )
            validate_minifoto_bitmap(bitmap)
        except Exception as exc:
            result_rows.append({key: value for key, value in row.items() if key != "payload"} | {
                "status": "native-no-photo",
                "reason": f"conversion-failed: {type(exc).__name__}: {exc}",
            })
            continue
        converted = output_root / "converted" / f"J96{int(row['carrier_id']):05d}.BMP"
        preview_path = output_root / "previews" / f"J96{int(row['carrier_id']):05d}.png"
        converted.parent.mkdir(parents=True, exist_ok=True)
        converted.write_bytes(bitmap)
        if write_previews:
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            preview.save(preview_path, format="PNG", optimize=False, compress_level=9)
        logical_usage += len(bitmap) + (preview_path.stat().st_size if write_previews else 0)
        if logical_usage > max_local_bytes:
            raise PortraitPipelineError("portrait output exceeded --max-local-bytes")
        result_rows.append({key: value for key, value in row.items() if key != "payload"} | {
            "status": "applied",
            "converted_path": str(converted.resolve()),
            "converted_sha256": _sha_file(converted),
            "preview_path": str(preview_path.resolve()) if write_previews else None,
            "preview_sha256": _sha_file(preview_path) if write_previews else None,
            "crop_dimensions": {"width": int(crop.width), "height": int(crop.height)},
        })
    status_counts: dict[str, int] = defaultdict(int)
    era_counts: dict[str, int] = defaultdict(int)
    for row in result_rows:
        status_counts[str(row["status"])] += 1
        era_counts[str(row.get("era_grade") or "unresolved")] += 1
    return {
        "schema_version": MATERIALISATION_SCHEMA,
        "season": plan["season"],
        "result": "complete",
        "inputs": {
            "plan_path": str(plan_path.resolve()),
            "plan_sha256": _sha_file(plan_path),
            "package_canonical_sha256": plan["inputs"]["package_canonical_sha256"],
            "minifoto_path": str(minifoto_path.resolve()),
            "minifoto_sha256": _sha_file(minifoto_path),
            "palette_path": str(palette_path.resolve()),
            "palette_sha256": _sha_file(palette_path),
        },
        "policy": plan["policy"],
        "coverage": {
            "player_count": len(result_rows),
            "applied_count": status_counts["applied"],
            "native_no_photo_count": status_counts["native-no-photo"],
            "pending_count": len(result_rows) - status_counts["applied"] - status_counts["native-no-photo"],
            "status_counts": dict(sorted(status_counts.items())),
            "era_grade_counts": dict(sorted(era_counts.items())),
        },
        "players": result_rows,
    }


def _copy_game_cow(source: Path, target: Path) -> None:
    if target.exists() or target.is_symlink():
        raise PortraitPipelineError(f"output game already exists: {target}")
    # Hard links are NOT copy-on-write: launching the game can mutate shared
    # configuration/save files, and later asset writes can corrupt the base.
    # Reserve space for the regular-copy fallback, even on reflink filesystems.
    inventory = pipeline_v2.build_tree_inventory(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(target.parent).free < inventory["total_bytes"] + 1024 ** 3:
        raise PortraitPipelineError("game copy would leave less than 1 GiB free")
    target.mkdir()
    subprocess.run(["cp", "-a", "--reflink=auto", str(source) + "/.", str(target)], check=True)
    pipeline_v2.assert_tree_matches_inventory(target, inventory)


def apply(*, materialisation_path: Path, base_game: Path, output_game: Path) -> dict[str, Any]:
    materialisation = _read_json(materialisation_path)
    if materialisation.get("schema_version") != MATERIALISATION_SCHEMA or materialisation.get("result") != "complete":
        raise PortraitPipelineError("portrait materialisation is incomplete or unsupported")
    coverage = materialisation.get("coverage") if isinstance(materialisation.get("coverage"), Mapping) else {}
    if coverage.get("pending_count") != 0:
        raise PortraitPipelineError("portrait materialisation still has pending players")
    # All identity and bitmap checks happen BEFORE allocating a game copy.
    # Otherwise a malformed receipt can waste hundreds of MB before failing.
    rows = materialisation["players"]
    carrier_ids = [int(row["carrier_id"]) for row in rows]
    if len(carrier_ids) != len(set(carrier_ids)):
        raise PortraitPipelineError("portrait materialisation reuses a PM99 carrier")
    expected_counts = {state: sum(row["status"] == state for row in rows)
                       for state in ("applied", "native-no-photo")}
    if any(row["status"] not in expected_counts for row in rows) or (
        coverage.get("player_count") != len(rows) or
        coverage.get("applied_count") != expected_counts["applied"] or
        coverage.get("native_no_photo_count") != expected_counts["native-no-photo"]
    ):
        raise PortraitPipelineError("portrait materialisation coverage is inconsistent")
    for row in rows:
        if row["status"] != "applied":
            continue
        if row.get("identity_score", 0) < 85:
            raise PortraitPipelineError("portrait identity score is below 85: " + row["name"])
        converted = Path(str(row.get("converted_path") or ""))
        if not converted.is_file() or _sha_file(converted) != row.get("converted_sha256"):
            raise PortraitPipelineError("converted portrait is missing or changed: " + row["name"])
        validate_minifoto_bitmap(converted.read_bytes())
    _copy_game_cow(base_game.resolve(), output_game.resolve())
    archive_path = output_game.resolve() / "DBDAT/MINIFOTO.PKF"
    original = archive_path.read_bytes()
    archive = bytearray(original)
    loose_root = output_game.resolve() / "DBDAT/MINIFOTO"
    loose_root.mkdir(parents=True, exist_ok=True)
    no_photo_ids = [int(row["carrier_id"]) for row in rows if row["status"] == "native-no-photo"]
    active = _active_offsets_for_players(archive, no_photo_ids)
    for offsets in active.values():
        for offset in offsets:
            archive[offset] = 0
    operations: list[dict[str, Any]] = []
    for row in rows:
        carrier_id = int(row["carrier_id"])
        loose = loose_root / f"J96{carrier_id:05d}.BMP"
        if row["status"] == "native-no-photo":
            loose.unlink(missing_ok=True)
            operations.append({"player_id": row["player_id"], "carrier_id": carrier_id, "status": "native-no-photo", "disabled_archive_records": active.get(carrier_id, [])})
            continue
        converted = Path(str(row.get("converted_path") or ""))
        if not converted.is_file() or _sha_file(converted) != row.get("converted_sha256"):
            raise PortraitPipelineError(f"converted portrait is missing or changed: {row['player_id']}")
        payload = converted.read_bytes()
        validate_minifoto_bitmap(payload)
        temporary = loose.with_suffix(".BMP.tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, loose)
        operations.append({"player_id": row["player_id"], "carrier_id": carrier_id, "status": "applied", "storage": "loose-DBDAT/MINIFOTO", "bitmap_sha256": _sha_bytes(payload), "era_grade": row.get("era_grade")})
    archive_path.write_bytes(bytes(archive))
    reread = {record.player_record_id for record in iter_minifoto_records_from_bytes(archive_path.name, archive_path.read_bytes())}
    residual = sorted(set(no_photo_ids).intersection(reread))
    if residual:
        raise PortraitPipelineError(f"native no-photo carriers remain active: {residual[:10]}")
    return {
        "schema_version": APPLICATION_SCHEMA,
        "season": materialisation["season"],
        "result": "complete",
        "inputs": {
            "materialisation_path": str(materialisation_path.resolve()),
            "materialisation_sha256": _sha_file(materialisation_path),
            "base_game": str(base_game.resolve()),
            "base_inventory_fingerprint": pipeline_v2.build_tree_inventory(base_game.resolve())["files_fingerprint"],
        },
        "output": {
            "game": str(output_game.resolve()),
            "minifoto_sha256_before": _sha_bytes(original),
            "minifoto_sha256_after": _sha_file(archive_path),
            "applied_count": sum(row["status"] == "applied" for row in operations),
            "native_no_photo_count": sum(row["status"] == "native-no-photo" for row in operations),
        },
        "operations": operations,
    }


def validate(*, materialisation_path: Path, application_path: Path, game: Path) -> dict[str, Any]:
    materialisation = _read_json(materialisation_path)
    application = _read_json(application_path)
    issues: list[dict[str, Any]] = []
    if application.get("schema_version") != APPLICATION_SCHEMA or application.get("result") != "complete":
        issues.append({"code": "application-invalid"})
    if application.get("inputs", {}).get("materialisation_sha256") != _sha_file(materialisation_path):
        issues.append({"code": "materialisation-hash-mismatch"})
    archive_path = game.resolve() / "DBDAT/MINIFOTO.PKF"
    if not archive_path.is_file() or application.get("output", {}).get("minifoto_sha256_after") != _sha_file(archive_path):
        issues.append({"code": "minifoto-archive-mismatch"})
        active_ids: set[int] = set()
    else:
        active_ids = {record.player_record_id for record in iter_minifoto_records(archive_path)}
    by_player = {row["player_id"]: row for row in materialisation.get("players", [])}
    for operation in application.get("operations", []):
        row = by_player.get(operation.get("player_id"))
        carrier_id = int(operation.get("carrier_id") or 0)
        loose = game.resolve() / "DBDAT/MINIFOTO" / f"J96{carrier_id:05d}.BMP"
        if not isinstance(row, Mapping):
            issues.append({"code": "operation-player-missing", "player_id": operation.get("player_id")})
        elif operation.get("status") == "applied":
            if not loose.is_file() or _sha_file(loose) != row.get("converted_sha256"):
                issues.append({"code": "applied-bitmap-mismatch", "player_id": row["player_id"]})
            else:
                try:
                    validate_minifoto_bitmap(loose.read_bytes())
                except Exception as exc:
                    issues.append({"code": "applied-bitmap-invalid", "player_id": row["player_id"], "detail": str(exc)})
        elif loose.exists() or carrier_id in active_ids:
            issues.append({"code": "native-no-photo-not-clean", "player_id": operation.get("player_id")})
    return {
        "schema_version": VALIDATION_SCHEMA,
        "season": materialisation.get("season"),
        "result": "pass" if not issues else "fail",
        "checked_player_count": len(application.get("operations", [])),
        "issue_count": len(issues),
        "issues": issues,
    }


def _registered_paths(season: str) -> tuple[Path, Path]:
    from scripts import season_release_registry_v1 as registry
    release = registry.load_preferred_release(season)
    return release.package_path, release.game_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan_parser = sub.add_parser("plan")
    plan_parser.add_argument("season")
    plan_parser.add_argument("--edition-csv", type=Path, required=True)
    plan_parser.add_argument("--edition", type=int, required=True)
    plan_parser.add_argument("--output", type=Path)
    fetch_parser = sub.add_parser("fetch")
    fetch_parser.add_argument("--plan", type=Path, required=True)
    fetch_parser.add_argument("--minifoto", type=Path, required=True)
    fetch_parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE)
    fetch_parser.add_argument("--output-root", type=Path, required=True)
    fetch_parser.add_argument("--receipt", type=Path, required=True)
    fetch_parser.add_argument("--workers", type=int, default=12)
    fetch_parser.add_argument("--timeout", type=int, default=12)
    fetch_parser.add_argument("--write-previews", action="store_true")
    fetch_parser.add_argument("--max-local-bytes", type=int, default=1024 * 1024 * 1024)
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("season")
    apply_parser.add_argument("--materialisation", type=Path, required=True)
    apply_parser.add_argument("--output-game", type=Path, required=True)
    apply_parser.add_argument("--receipt", type=Path, required=True)
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--materialisation", type=Path, required=True)
    validate_parser.add_argument("--application", type=Path, required=True)
    validate_parser.add_argument("--game", type=Path, required=True)
    validate_parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            package, _game = _registered_paths(args.season)
            output = args.output or DEFAULT_OUTPUT / args.season / "portrait-plan.json"
            result = build_plan(package_path=package, edition_csv=args.edition_csv, edition=args.edition)
            _write_json(output, result)
        elif args.command == "fetch":
            result = materialise(plan_path=args.plan, minifoto_path=args.minifoto, cache_root=args.cache_root, output_root=args.output_root, workers=args.workers, timeout=args.timeout, write_previews=args.write_previews, max_local_bytes=args.max_local_bytes)
            output = args.receipt
            _write_json(output, result)
        elif args.command == "apply":
            _package, game = _registered_paths(args.season)
            result = apply(materialisation_path=args.materialisation, base_game=game, output_game=args.output_game)
            output = args.receipt
            _write_json(output, result)
        else:
            result = validate(materialisation_path=args.materialisation, application_path=args.application, game=args.game)
            output = args.output
            if output:
                _write_json(output, result)
        print(json.dumps({"output": str(output) if output else None, "result": result.get("result"), "coverage": result.get("coverage"), "issue_count": result.get("issue_count")}, sort_keys=True))
        return 0 if result.get("result") in {"complete", "pass"} else 1
    except (OSError, requests.RequestException, package_v2.PackageValidationError, pipeline_v2.PipelineError, PortraitPipelineError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
