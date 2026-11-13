#!/usr/bin/env python3
"""Apply certified English and identity-bound foreign 2015 kit art safely."""

from __future__ import annotations

try:
    from scripts import json_storage_io_v1 as storage_io
except ModuleNotFoundError:
    import sys as _storage_sys
    from pathlib import Path as _StoragePath
    _storage_sys.path.insert(0, str(next(p for p in _StoragePath(__file__).resolve().parents if (p / 'scripts/json_storage_io_v1.py').is_file())))
    from scripts import json_storage_io_v1 as storage_io

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = storage_io.resolve(Path(__file__)).parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
if str(EDITOR) not in sys.path:
    sys.path.insert(0, str(EDITOR))

from app.minifoto_bitmap_archive import iter_obfuscated_bmp_records  # noqa: E402

SCHEMA = "pm99-world-2015-kit-application-v1"
MATERIALISATION_SCHEMAS = {"pm99-world-2015-fifaindex-kit-materialisation-v1", "pm99-world-2015-combined-kit-materialisation-v1"}
APPROVED_STATUSES = {"release-eligible-fifa16-identity-bound", "release-eligible-reviewed-2015-geometry"}
ENGLISH_RECEIPT_SCHEMA = "pm99-english-2015-16-home-kit-render-v2"
ALL_ARCHIVES = ("BIGCAMP.PKF", "BIGESC.PKF", "MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")
FOREIGN_ARCHIVES = ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")


class KitApplicationError(ValueError):
    pass


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(storage_io.read_bytes(path))


def records_by_carrier(path: Path) -> dict[int, Any]:
    return {
        int(re.fullmatch(r"EQ96(\d{4})\.BMP", str(record.file_name), re.I).group(1)): record
        for record in iter_obfuscated_bmp_records(path, file_name_pattern=r"^EQ96\d{4}\.BMP$")
    }


def verify_english_source(dbdat: Path, receipt: Mapping[str, Any]) -> dict[str, Any]:
    if receipt.get("schema") != ENGLISH_RECEIPT_SCHEMA or int(receipt.get("team_count") or 0) != 92:
        raise KitApplicationError("English kit receipt is not the certified 92-club 2015 render")
    expected_counts = {str(key): int(value) for key, value in (receipt.get("patched_counts_by_archive") or {}).items()}
    if expected_counts != {"BIGCAMP.PKF": 80, "BIGESC.PKF": 91, "MINIESC.PKF": 92, "NANOESC.PKF": 92, "RIDIESC.PKF": 92}:
        raise KitApplicationError("English kit receipt has unexpected archive coverage")
    verified = 0
    by_archive = {archive: records_by_carrier(dbdat / archive) for archive in ALL_ARCHIVES}
    for event in receipt.get("patched", []):
        archive = str(event.get("archive_name") or "")
        carrier = int(event.get("team_id") or 0)
        record = by_archive.get(archive, {}).get(carrier)
        if record is None or sha256_bytes(record.raw_bitmap) != event.get("bitmap_sha256_after"):
            raise KitApplicationError(f"English kit receipt/readback mismatch: {archive} carrier {carrier}")
        verified += 1
    if verified != 447 or int(receipt.get("patched_record_count") or 0) != 447:
        raise KitApplicationError("English kit receipt does not prove all 447 expected records")
    return {"team_count": 92, "verified_record_count": verified, "archive_sha256": {archive: sha256_file(dbdat / archive) for archive in ALL_ARCHIVES}}


def apply_world_kits(*, materialisation: Mapping[str, Any], english_dbdat: Path, english_receipt: Mapping[str, Any], target_game_tree: Path) -> dict[str, Any]:
    if materialisation.get("schema_version") not in MATERIALISATION_SCHEMAS:
        raise KitApplicationError("foreign kit materialisation schema is unsupported")
    english_dbdat, target_dbdat = storage_io.resolve(english_dbdat), (storage_io.resolve(target_game_tree) / "DBDAT")
    if english_dbdat == target_dbdat:
        raise KitApplicationError("English source and target DBDAT must be different")
    if not target_dbdat.is_dir():
        raise KitApplicationError(f"target DBDAT is missing: {target_dbdat}")
    english_proof = verify_english_source(english_dbdat, english_receipt)
    target_before = {archive: sha256_file(target_dbdat / archive) for archive in ALL_ARCHIVES}
    for archive in ALL_ARCHIVES:
        source, target = english_dbdat / archive, target_dbdat / archive
        if source.is_symlink() or target.is_symlink() or not storage_io.is_file(source) or not storage_io.is_file(target):
            raise KitApplicationError(f"kit archive must be a regular existing file: {archive}")
        storage_io.copy_file(source, target, metadata=True)

    approved = [row for row in materialisation.get("rows", []) if row.get("status") in APPROVED_STATUSES]
    approved_ids = [int(row["carrier_id"]) for row in approved]
    if len(approved_ids) != len(set(approved_ids)):
        raise KitApplicationError("foreign materialisation repeats a carrier")
    events: list[dict[str, Any]] = []
    native_fallbacks: list[dict[str, Any]] = []
    for archive in FOREIGN_ARCHIVES:
        path = target_dbdat / archive
        baseline = storage_io.read_bytes(path)
        before_records = records_by_carrier(path)
        patched = bytearray(baseline)
        allowed_ranges: list[tuple[int, int]] = []
        for row in approved:
            carrier = int(row["carrier_id"])
            record = before_records.get(carrier)
            asset = (row.get("assets") or {}).get(archive) or {}
            candidate = Path(str(asset.get("path") or ""))
            if record is None or not storage_io.is_file(candidate) or sha256_file(candidate) != asset.get("sha256"):
                raise KitApplicationError(f"candidate/record missing or hash mismatch: {archive} carrier {carrier}")
            payload = storage_io.read_bytes(candidate)
            if len(payload) != record.bitmap_length or payload[:26] != record.raw_bitmap[:26]:
                raise KitApplicationError(f"candidate shape/header mismatch: {archive} carrier {carrier}")
            start, end = int(record.bitmap_offset), int(record.bitmap_offset + record.bitmap_length)
            patched[start:end] = payload
            allowed_ranges.append((start, end))
            team = row.get("binding", {}).get("team", {})
            reviewed = row.get("reviewed_source", {})
            events.append({"archive": archive, "carrier_id": carrier, "file_name": str(record.file_name), "bitmap_offset": start, "bitmap_length": record.bitmap_length, "bitmap_sha256_before": sha256_bytes(record.raw_bitmap), "bitmap_sha256_after": sha256_bytes(payload), "source_kind": row["status"], "source_team_id": team.get("fifa_team_id"), "source_team_name": team.get("fifa_team_name") or reviewed.get("source_team_name"), "source_image_sha256": (row.get("source_image") or {}).get("sha256"), "source_url": reviewed.get("source_url")})
        changed = [index for index, (before, after) in enumerate(zip(baseline, patched)) if before != after]
        if any(not any(start <= index < end for start, end in allowed_ranges) for index in changed):
            raise KitApplicationError(f"bytes outside approved {archive} record extents changed")
        storage_io.write_bytes(path, bytes(patched))
        after_records = records_by_carrier(path)
        for row in approved:
            carrier = int(row["carrier_id"])
            if sha256_bytes(after_records[carrier].raw_bitmap) != row["assets"][archive]["sha256"]:
                raise KitApplicationError(f"post-write readback failed: {archive} carrier {carrier}")
        for carrier, record in before_records.items():
            if carrier not in set(approved_ids) and after_records[carrier].raw_bitmap != record.raw_bitmap:
                raise KitApplicationError(f"unapproved native fallback changed: {archive} carrier {carrier}")

    for row in materialisation.get("rows", []):
        if row.get("source_status") == "source-squad-ready" and row.get("status") not in APPROVED_STATUSES:
            native_fallbacks.append({"carrier_id": int(row["carrier_id"]), "source_club_name": row.get("source_club_name"), "reason": row.get("status"), "resulting_state": "certified-English-tree native PM99 compact kit retained; historical kit unresolved"})
    return {"schema_version": SCHEMA, "result": "complete-for-approved-kits", "coverage": {"english_club_count": 92, "english_verified_record_count": english_proof["verified_record_count"], "foreign_approved_carrier_count": len(approved), "foreign_patched_record_count": len(events), "foreign_native_fallback_count": len(native_fallbacks)}, "english_source": english_proof, "target": {"game_tree": str(storage_io.resolve(target_game_tree)), "archive_sha256_before": target_before, "archive_sha256_after": {archive: sha256_file(target_dbdat / archive) for archive in ALL_ARCHIVES}}, "foreign_events": events, "native_fallbacks": native_fallbacks}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--materialisation", type=Path, required=True)
    parser.add_argument("--english-kit-dbdat", type=Path, required=True)
    parser.add_argument("--english-kit-receipt", type=Path, required=True)
    parser.add_argument("--target-game-tree", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        materialisation = json.loads(storage_io.read_text(args.materialisation, encoding='utf-8'))
        english_receipt = json.loads(storage_io.read_text(args.english_kit_receipt, encoding='utf-8'))
        result = apply_world_kits(materialisation=materialisation, english_dbdat=args.english_kit_dbdat, english_receipt=english_receipt, target_game_tree=args.target_game_tree)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KitApplicationError) as exc:
        parser.error(str(exc))
    result["sources"] = {"materialisation_sha256": sha256_file(args.materialisation), "english_receipt_sha256": sha256_file(args.english_kit_receipt)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    storage_io.write_text(args.output, json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
    print(json.dumps(result["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
