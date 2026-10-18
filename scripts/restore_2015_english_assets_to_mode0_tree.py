#!/usr/bin/env python3
"""Restore signed English 2015 assets onto the mode-0 append carrier map.

The mode-0 append build preserves all 2,300 `(club, player)` identities but
changes many player carrier IDs.  This stage remaps the signed clean-release
portrait for each identity to the target carrier, copies the five reviewed
English kit archives, and restores the independently-qualified 2015 calendar
executable.  It never assigns an image by carrier number alone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import iter_minifoto_records, iter_minifoto_records_from_bytes, validate_minifoto_bitmap
from scripts.materialise_native_no_photo_v2 import _active_offsets_for_players

SCHEMA = "pm99-2015-english-assets-mode0-restoration-v1"
KIT_ARCHIVES = ("BIGCAMP.PKF", "BIGESC.PKF", "MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _identity(row: dict[str, Any]) -> tuple[str, str]:
    return (" ".join(str(row.get("club") or "").split()), " ".join(str(row.get("name") or "").split()))


def build_plan(*, signed_tree: Path, signed_ledger: list[dict[str, Any]], target_ledger: list[dict[str, Any]]) -> dict[str, Any]:
    source = {_identity(row): row for row in signed_ledger}
    target = {_identity(row): row for row in target_ledger}
    if len(source) != 2300 or len(target) != 2300 or set(source) != set(target):
        raise ValueError("signed and mode-0 ledgers do not contain the same 2,300 unique identities")
    archive_path = signed_tree / "DBDAT" / "MINIFOTO.PKF"
    archive = {row.player_record_id: row for row in iter_minifoto_records(archive_path)}
    loose_root = signed_tree / "DBDAT" / "MINIFOTO"
    rows: list[dict[str, Any]] = []
    for identity in sorted(source):
        old_id, new_id = int(source[identity]["record_id"]), int(target[identity]["record_id"])
        loose = loose_root / f"J96{old_id:05d}.BMP"
        if loose.is_file():
            payload, origin = loose.read_bytes(), "signed-clean-loose"
        elif old_id in archive:
            payload, origin = archive[old_id].raw_bitmap, "signed-clean-archive"
        else:
            payload, origin = None, "signed-clean-native-no-photo"
        if payload is not None:
            validate_minifoto_bitmap(payload)
        rows.append({"club": identity[0], "player": identity[1], "signed_player_carrier_id": old_id, "target_player_carrier_id": new_id, "carrier_disposition": "unchanged" if old_id == new_id else "identity-remapped", "portrait_disposition": "restore-loose-override" if payload is not None else "native-no-photo", "portrait_origin": origin, "portrait_sha256": hashlib.sha256(payload).hexdigest() if payload is not None else None})
    portraits = sum(row["portrait_disposition"] == "restore-loose-override" for row in rows)
    no_photo = len(rows) - portraits
    if (portraits, no_photo) != (2294, 6):
        raise ValueError(f"signed portrait coverage changed: {portraits} portraits, {no_photo} no-photo")
    for name in KIT_ARCHIVES:
        if not (signed_tree / "DBDAT" / name).is_file():
            raise ValueError(f"signed kit archive is missing: {name}")
    calendar = signed_tree / "MANAGPRE.EXE"
    if not calendar.is_file():
        raise ValueError("signed calendar executable is missing")
    return {"schema_version": SCHEMA, "result": "restoration-plan-ready", "policy": "identity-bound English portrait remap; signed kit archives; independently-qualified calendar; no carrier-number-only face copy", "sources": {"signed_tree": str(signed_tree.resolve()), "signed_minifoto_sha256": sha(archive_path), "signed_calendar_sha256": sha(calendar), "signed_ledger_sha256": hashlib.sha256(canonical_bytes(signed_ledger)).hexdigest(), "target_ledger_sha256": hashlib.sha256(canonical_bytes(target_ledger)).hexdigest(), "signed_kit_sha256": {name: sha(signed_tree / "DBDAT" / name) for name in KIT_ARCHIVES}}, "coverage": {"identity_count": len(rows), "unchanged_carrier_count": sum(row["carrier_disposition"] == "unchanged" for row in rows), "remapped_carrier_count": sum(row["carrier_disposition"] == "identity-remapped" for row in rows), "approved_portrait_count": portraits, "native_no_photo_count": no_photo, "kit_archive_count": len(KIT_ARCHIVES), "calendar_restoration_count": 1}, "rows": rows}


def apply_plan(*, plan: dict[str, Any], signed_tree: Path, game_tree: Path) -> dict[str, Any]:
    dbdat = game_tree / "DBDAT"
    archive_path = dbdat / "MINIFOTO.PKF"
    if not archive_path.is_file():
        raise ValueError("target tree has no MINIFOTO.PKF")
    # Start with the signed archive; identity-remapped portraits are then
    # emitted as loose overrides, which is PM99's proven append-safe path.
    signed_archive = signed_tree / "DBDAT" / "MINIFOTO.PKF"
    archive = bytearray(signed_archive.read_bytes())
    no_photo_ids = {int(row["target_player_carrier_id"]) for row in plan["rows"] if row["portrait_disposition"] == "native-no-photo"}
    active = _active_offsets_for_players(archive, no_photo_ids)
    for offsets in active.values():
        for offset in offsets:
            archive[offset] = 0
    archive_path.write_bytes(bytes(archive))
    target_loose = dbdat / "MINIFOTO"
    target_loose.mkdir(parents=True, exist_ok=True)
    signed_loose = signed_tree / "DBDAT" / "MINIFOTO"
    signed_records = {row.player_record_id: row for row in iter_minifoto_records(signed_archive)}
    # Remove only files named by the signed and target English ledgers; foreign
    # loose files outside this identity set are untouched.
    cleanup_ids = {int(row["signed_player_carrier_id"]) for row in plan["rows"]} | {int(row["target_player_carrier_id"]) for row in plan["rows"]}
    for player_id in cleanup_ids:
        (target_loose / f"J96{player_id:05d}.BMP").unlink(missing_ok=True)
    written = 0
    for row in plan["rows"]:
        if row["portrait_disposition"] != "restore-loose-override":
            continue
        old_id, new_id = int(row["signed_player_carrier_id"]), int(row["target_player_carrier_id"])
        source_loose = signed_loose / f"J96{old_id:05d}.BMP"
        payload = source_loose.read_bytes() if source_loose.is_file() else signed_records[old_id].raw_bitmap
        if hashlib.sha256(payload).hexdigest() != row["portrait_sha256"]:
            raise ValueError(f"signed portrait hash changed for {old_id}")
        (target_loose / f"J96{new_id:05d}.BMP").write_bytes(payload)
        written += 1
    for name in KIT_ARCHIVES:
        shutil.copy2(signed_tree / "DBDAT" / name, dbdat / name)
    shutil.copy2(signed_tree / "MANAGPRE.EXE", game_tree / "MANAGPRE.EXE")
    active_after = {row.player_record_id for row in iter_minifoto_records_from_bytes(archive_path.name, archive_path.read_bytes())}
    if active_after.intersection(no_photo_ids):
        raise ValueError("restored English no-photo IDs remain active in archive")
    result = dict(plan)
    result["result"] = "restoration-applied"
    result["target"] = {"game_tree": str(game_tree.resolve()), "loose_portrait_write_count": written, "minifoto_sha256": sha(archive_path), "calendar_sha256": sha(game_tree / "MANAGPRE.EXE"), "kit_sha256": {name: sha(dbdat / name) for name in KIT_ARCHIVES}}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signed-tree", required=True, type=Path)
    parser.add_argument("--signed-ledger", type=Path)
    parser.add_argument("--target-ledger", type=Path)
    parser.add_argument("--plan", type=Path, help="previously reviewed canonical restoration plan")
    parser.add_argument("--game-tree", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.plan:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        if plan.get("schema_version") != SCHEMA or plan.get("result") != "restoration-plan-ready":
            parser.error("--plan is not a reviewed restoration-plan-ready receipt")
        if Path(plan["sources"]["signed_tree"]).resolve() != args.signed_tree.resolve():
            parser.error("--plan signed tree does not match --signed-tree")
        for relative, expected in (("DBDAT/MINIFOTO.PKF", plan["sources"]["signed_minifoto_sha256"]), ("MANAGPRE.EXE", plan["sources"]["signed_calendar_sha256"])):
            if sha(args.signed_tree / relative) != expected:
                parser.error(f"--plan signed input changed: {relative}")
    else:
        if not args.signed_ledger or not args.target_ledger:
            parser.error("provide --plan or both --signed-ledger and --target-ledger")
        plan = build_plan(signed_tree=args.signed_tree, signed_ledger=json.loads(args.signed_ledger.read_text(encoding="utf-8")), target_ledger=json.loads(args.target_ledger.read_text(encoding="utf-8")))
    result = apply_plan(plan=plan, signed_tree=args.signed_tree, game_tree=args.game_tree) if args.game_tree else plan
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps({"result": result["result"], **result["coverage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
