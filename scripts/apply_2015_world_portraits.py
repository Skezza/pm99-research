#!/usr/bin/env python3
"""Apply reviewed 2015/16 portrait outcomes to an isolated PM99 game tree.

This is the binary-writing boundary for the world portrait lane.  Successful
identity-bound conversions replace the matching MINIFOTO payload when one
exists, or use PM99's supported loose ``DBDAT/MINIFOTO/J96xxxxx.BMP`` lookup.
Every other selected player is forced to native no-photo unless the reviewed
ownership receipt explicitly preserves the native player row and portrait.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import (  # noqa: E402
    iter_minifoto_records_from_bytes,
    validate_minifoto_bitmap,
)
from scripts.materialise_native_no_photo_v2 import _active_offsets_for_players  # noqa: E402

SCHEMA = "pm99-world-2015-portrait-application-v1"
MANIFEST_SCHEMA = "pm99-world-2015-asset-candidate-manifest-v1"
MATERIALISATION_SCHEMA = "pm99-world-2015-portrait-materialisation-v1"


class PortraitApplicationError(ValueError):
    pass


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _selected_players(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise PortraitApplicationError("asset manifest schema is unsupported")
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for club in manifest.get("clubs", []):
        if not isinstance(club, dict) or club.get("source_status") != "source-squad-ready":
            continue
        for player in club.get("players", []):
            if not isinstance(player, dict):
                raise PortraitApplicationError("asset manifest contains a malformed player")
            player_id = int(player.get("player_carrier_id") or 0)
            if player_id <= 0 or player_id in seen:
                raise PortraitApplicationError(f"final player carrier is absent or shared: {player_id}")
            seen.add(player_id)
            rows.append({
                "carrier_id": int(club["carrier_id"]),
                "slot_index": int(player["slot_index"]),
                "player_carrier_id": player_id,
                "name": str(player.get("name") or ""),
                "candidate_status": str((player.get("portrait") or {}).get("status") or ""),
                "recycle_clone_carrier_id": int((player.get("recycle_allocation") or {}).get("appended_mode0_clone_carrier_id") or 0),
            })
    return sorted(rows, key=lambda row: (row["carrier_id"], row["slot_index"], row["player_carrier_id"]))


def apply_portraits(*, manifest: Mapping[str, Any], materialisation: Mapping[str, Any], game_tree: Path) -> dict[str, Any]:
    if materialisation.get("schema_version") != MATERIALISATION_SCHEMA:
        raise PortraitApplicationError("portrait materialisation schema is unsupported")
    if int((materialisation.get("coverage") or {}).get("pending_count", -1)) != 0:
        raise PortraitApplicationError("portrait materialisation still has pending rows")
    players = _selected_players(manifest)
    expected_candidates = [row for row in players if row["candidate_status"] == "fifa16-url-candidate"]
    outcome_by_key: dict[tuple[int, int, int], Mapping[str, Any]] = {}
    for row in materialisation.get("rows", []):
        if not isinstance(row, dict):
            raise PortraitApplicationError("portrait materialisation contains a malformed row")
        key = (int(row.get("carrier_id") or 0), int(row.get("slot_index") or 0), int(row.get("player_carrier_id") or 0))
        if key in outcome_by_key:
            raise PortraitApplicationError(f"duplicate portrait outcome {key}")
        outcome_by_key[key] = row
    expected_keys = {(row["carrier_id"], row["slot_index"], row["player_carrier_id"]) for row in expected_candidates}
    if set(outcome_by_key) != expected_keys:
        raise PortraitApplicationError("portrait outcomes do not exactly cover every URL candidate")

    game_tree = game_tree.resolve()
    archive_path = game_tree / "DBDAT" / "MINIFOTO.PKF"
    if not archive_path.is_file() or archive_path.is_symlink():
        raise PortraitApplicationError(f"missing regular MINIFOTO.PKF: {archive_path}")
    original = archive_path.read_bytes()
    archive = bytearray(original)
    records = {record.player_record_id: record for record in iter_minifoto_records_from_bytes(archive_path.name, original)}
    if not records:
        raise PortraitApplicationError("MINIFOTO.PKF has no parseable records")

    # A recycle transaction moves the original mode-0 player to a fresh clone
    # ID and reuses the old carrier for the dated foreign player. Preserve the
    # original face on that clone before the old ID is overwritten/disabled.
    loose_root = game_tree / "DBDAT" / "MINIFOTO"
    clone_payloads: dict[int, bytes] = {}
    clone_operations: list[dict[str, Any]] = []
    clone_ids: set[int] = set()
    for row in players:
        clone_id = int(row.get("recycle_clone_carrier_id") or 0)
        if clone_id <= 0:
            continue
        if clone_id in clone_ids or clone_id in records:
            raise PortraitApplicationError(f"recycle portrait clone ID is shared or already active: {clone_id}")
        clone_ids.add(clone_id)
        source_id = row["player_carrier_id"]
        source_loose = loose_root / f"J96{source_id:05d}.BMP"
        payload = source_loose.read_bytes() if source_loose.is_file() else records[source_id].raw_bitmap if source_id in records else None
        if payload is None:
            clone_operations.append({"mode0_source_player_carrier_id": source_id, "appended_mode0_clone_carrier_id": clone_id, "resulting_state": "native-no-photo"})
        else:
            validate_minifoto_bitmap(payload)
            clone_payloads[clone_id] = payload
            clone_operations.append({"mode0_source_player_carrier_id": source_id, "appended_mode0_clone_carrier_id": clone_id, "resulting_state": "preserved-original-portrait", "bitmap_sha256": _sha256_bytes(payload)})

    prepared: dict[int, bytes] = {}
    for row in players:
        key = (row["carrier_id"], row["slot_index"], row["player_carrier_id"])
        outcome = outcome_by_key.get(key)
        if outcome is None or outcome.get("status") != "approved-crop-conversion-candidate":
            continue
        path = Path(str(outcome.get("converted_path") or ""))
        if not path.is_file() or _sha256_file(path) != outcome.get("converted_sha256"):
            raise PortraitApplicationError(f"converted portrait hash mismatch for {key}")
        payload = path.read_bytes()
        validate_minifoto_bitmap(payload)
        prepared[row["player_carrier_id"]] = payload

    preserved_native_ids = {row["player_carrier_id"] for row in players if row["candidate_status"] == "preserve-native-carrier-portrait"}
    no_photo_ids = {row["player_carrier_id"] for row in players if row["player_carrier_id"] not in prepared and row["player_carrier_id"] not in preserved_native_ids}
    active = _active_offsets_for_players(archive, no_photo_ids)
    for offsets in active.values():
        for offset in offsets:
            archive[offset] = 0

    operations: list[dict[str, Any]] = []
    loose_writes: dict[Path, bytes] = {}
    loose_removals: set[Path] = set()
    for row in players:
        player_id = row["player_carrier_id"]
        loose_path = loose_root / f"J96{player_id:05d}.BMP"
        payload = prepared.get(player_id)
        record = records.get(player_id)
        if player_id in preserved_native_ids:
            operations.append({**row, "resulting_state": "preserved-native-portrait", "storage": "unchanged"})
            continue
        if payload is None:
            loose_removals.add(loose_path)
            operations.append({**row, "resulting_state": "native-no-photo", "disabled_archive_directory_offsets": active.get(player_id, [])})
            continue
        if record is not None and len(payload) == record.bitmap_length:
            shape = validate_minifoto_bitmap(payload)
            if (shape.width, shape.height, shape.bits_per_pixel) == (record.width, record.height, record.bits_per_pixel):
                archive[record.bitmap_offset : record.bitmap_offset + record.bitmap_length] = payload
                loose_removals.add(loose_path)
                operations.append({**row, "resulting_state": "applied", "storage": "MINIFOTO.PKF", "bitmap_sha256": _sha256_bytes(payload)})
                continue
        loose_writes[loose_path] = payload
        operations.append({**row, "resulting_state": "applied", "storage": "loose-DBDAT/MINIFOTO", "bitmap_sha256": _sha256_bytes(payload)})

    verified = bytes(archive)
    reread = {record.player_record_id: record for record in iter_minifoto_records_from_bytes(archive_path.name, verified)}
    residual = sorted(no_photo_ids.intersection(reread))
    if residual:
        raise PortraitApplicationError(f"native no-photo archive rows remain active: {residual[:10]}")

    archive_path.write_bytes(verified)
    loose_root.mkdir(parents=True, exist_ok=True)
    for path in sorted(loose_removals):
        path.unlink(missing_ok=True)
    for path, payload in sorted(loose_writes.items(), key=lambda item: str(item[0])):
        path.write_bytes(payload)
    for clone_id, payload in sorted(clone_payloads.items()):
        clone_path = loose_root / f"J96{clone_id:05d}.BMP"
        clone_path.write_bytes(payload)
    for path, payload in loose_writes.items():
        if path.read_bytes() != payload:
            raise PortraitApplicationError(f"loose portrait verification failed: {path}")

    applied = sum(row["resulting_state"] == "applied" for row in operations)
    preserved_native = sum(row["resulting_state"] == "preserved-native-portrait" for row in operations)
    no_photo = len(operations) - applied - preserved_native
    return {
        "schema_version": SCHEMA,
        "result": "complete" if len(operations) == len(players) else "incomplete",
        "coverage": {
            "selected_player_count": len(players),
            "applied_portrait_count": applied,
            "preserved_native_portrait_count": preserved_native,
            "native_no_photo_count": no_photo,
            "pending_count": 0,
            "recycle_portrait_clone_count": len(clone_operations),
            "recycle_portrait_clone_with_photo_count": len(clone_payloads),
        },
        "archive": {
            "path": str(archive_path),
            "sha256_before": _sha256_bytes(original),
            "sha256_after": _sha256_bytes(verified),
        },
        "operations": operations,
        "recycle_portrait_clone_operations": clone_operations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-manifest", type=Path, required=True)
    parser.add_argument("--portrait-materialisation", type=Path, required=True)
    parser.add_argument("--game-tree", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest_raw = args.asset_manifest.read_bytes()
    materialisation_raw = args.portrait_materialisation.read_bytes()
    manifest = json.loads(manifest_raw)
    materialisation = json.loads(materialisation_raw)
    expected_hash = str((materialisation.get("source") or {}).get("candidate_manifest_file_sha256") or "")
    if expected_hash != _sha256_bytes(manifest_raw):
        parser.error("portrait materialisation targets a different asset manifest")
    try:
        result = apply_portraits(manifest=manifest, materialisation=materialisation, game_tree=args.game_tree)
    except PortraitApplicationError as exc:
        parser.error(str(exc))
    result["sources"] = {
        "asset_manifest_sha256": _sha256_bytes(manifest_raw),
        "portrait_materialisation_sha256": _sha256_bytes(materialisation_raw),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps(result["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
