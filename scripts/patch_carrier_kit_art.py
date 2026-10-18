#!/usr/bin/env python3
"""Copy one PM99 club's carrier kit art to another carrier safely.

The game resolves a club kit by the EQ record id in its bitmap file name:
``EQ96<eq-id>.BMP``.  This utility is deliberately limited to copying the
pixel region of an existing, same-sized source bitmap into an existing target
record in the explicitly selected stock archive set.  It never rewrites
archive directories, bitmap names, offsets or payload lengths.  The default
five-archive set is for an English carrier; the foreign compact-UI set is the
three archives that actually contain every modern carrier.

It is intended for a controlled identity migration such as Stoke's original
EQ 341 art onto its 2015/16 Premier League carrier EQ 314.  It is not a
general artwork importer and it does not alter database strings or rosters.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EDITOR_ROOT = ROOT / "upstream" / "pm99-skezmod-db-editor"
if str(EDITOR_ROOT) not in sys.path:
    sys.path.insert(0, str(EDITOR_ROOT))

from app.minifoto_bitmap_archive import BitmapArchiveRecord, iter_obfuscated_bmp_records  # noqa: E402


# The two large archives are an English-only surface in the stock corpus.
# Modern carriers in the compact UI archives are wider in scope: F.C.
# Barcelona, for example, has EQ960001 records in these three archives but no
# record in either BIG*.PKF.  Keep that distinction explicit so a foreign-kit
# research patch never invents a missing large-archive record.
KIT_ARCHIVE_SETS: dict[str, tuple[str, ...]] = {
    "all": ("BIGCAMP.PKF", "BIGESC.PKF", "MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF"),
    "foreign-ui": ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF"),
}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def kit_name(team_id: int) -> str:
    if not 1 <= team_id <= 9999:
        raise ValueError("EQ record ids must fit the four-digit kit filename contract.")
    return f"EQ96{team_id:04d}.BMP"


def record_by_name(path: Path, name: str) -> BitmapArchiveRecord:
    records = iter_obfuscated_bmp_records(path, file_name_pattern=rf"^{re.escape(name)}$")
    if len(records) != 1:
        raise ValueError(f"{path.name}: expected exactly one {name}, found {len(records)}.")
    return records[0]


def copy_art(
    *,
    source_dir: Path,
    target_dir: Path,
    source_team_id: int,
    target_team_id: int,
    archive_set: str,
) -> dict[str, Any]:
    archives = KIT_ARCHIVE_SETS[archive_set]
    source_name = kit_name(source_team_id)
    target_name = kit_name(target_team_id)
    events: list[dict[str, Any]] = []

    for archive_name in archives:
        source_path = source_dir / archive_name
        target_path = target_dir / archive_name
        if not source_path.is_file():
            raise FileNotFoundError(f"Missing source kit archive: {source_path}")
        if not target_path.is_file():
            raise FileNotFoundError(f"Missing target kit archive: {target_path}")

        source_record = record_by_name(source_path, source_name)
        target_record = record_by_name(target_path, target_name)
        if source_record.bitmap_length != target_record.bitmap_length:
            raise ValueError(
                f"{archive_name}: source {source_name} is {source_record.bitmap_length} bytes, "
                f"target {target_name} is {target_record.bitmap_length}; refusing to resize an archive record."
            )
        if (source_record.width, source_record.height, source_record.bits_per_pixel) != (
            target_record.width,
            target_record.height,
            target_record.bits_per_pixel,
        ):
            raise ValueError(f"{archive_name}: source/target bitmap shapes differ; refusing to reinterpret pixels.")

        before_archive = target_path.read_bytes()
        patched = bytearray(before_archive)
        start = target_record.bitmap_offset
        end = start + target_record.bitmap_length
        patched[start:end] = source_record.raw_bitmap
        target_path.write_bytes(bytes(patched))

        reread = record_by_name(target_path, target_name)
        if reread.raw_bitmap != source_record.raw_bitmap:
            raise RuntimeError(f"{archive_name}: target bitmap did not survive post-write read-back.")
        changed = [index for index, (before, after) in enumerate(zip(before_archive, patched)) if before != after]
        if changed and (min(changed) < start or max(changed) >= end):
            raise RuntimeError(f"{archive_name}: bytes outside the target bitmap changed.")
        events.append(
            {
                "archive_name": archive_name,
                "source_file_name": source_name,
                "target_file_name": target_name,
                "target_bitmap_offset": start,
                "target_bitmap_length": target_record.bitmap_length,
                "shape": {"width": target_record.width, "height": target_record.height, "bits_per_pixel": target_record.bits_per_pixel},
                "changed_byte_count": len(changed),
                "source_bitmap_sha256": sha256(source_record.raw_bitmap),
                "target_bitmap_sha256_before": sha256(target_record.raw_bitmap),
                "target_bitmap_sha256_after": sha256(reread.raw_bitmap),
                "archive_sha256_before": sha256(before_archive),
                "archive_sha256_after": sha256(bytes(patched)),
            }
        )

    return {
        "schema": "pm99-carrier-kit-art-copy-v1",
        "source_team_id": source_team_id,
        "target_team_id": target_team_id,
        "source_file_name": source_name,
        "target_file_name": target_name,
        "archive_set": archive_set,
        "archives": events,
        "checks": {
            "all_expected_archives_patched": len(events) == len(archives),
            "all_target_bitmaps_equal_source": all(event["source_bitmap_sha256"] == event["target_bitmap_sha256_after"] for event in events),
            "no_archive_resize": all(event["target_bitmap_length"] > 0 for event in events),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path, help="Directory containing the original five kit archives.")
    parser.add_argument("--target-dir", required=True, type=Path, help="Existing disposable DBDAT override directory to patch.")
    parser.add_argument("--source-team-id", type=int, default=341)
    parser.add_argument("--target-team-id", type=int, default=314)
    parser.add_argument(
        "--archive-set",
        choices=tuple(KIT_ARCHIVE_SETS),
        default="all",
        help="all for an English carrier; foreign-ui for a non-English carrier's compact UI assets only.",
    )
    parser.add_argument("--copy-source-archives", action="store_true", help="Initialise missing target archives by copying from source before patching.")
    parser.add_argument("--summary", type=Path, help="Write the JSON proof here.")
    args = parser.parse_args()

    source_dir = args.source_dir.resolve()
    target_dir = args.target_dir.resolve()
    if source_dir == target_dir:
        raise SystemExit("--source-dir and --target-dir must be different; preserve the original archives.")
    if args.copy_source_archives:
        target_dir.mkdir(parents=True, exist_ok=True)
        for archive_name in KIT_ARCHIVES:
            source = source_dir / archive_name
            target = target_dir / archive_name
            if not source.is_file():
                raise SystemExit(f"Missing source kit archive: {source}")
            if not target.exists():
                shutil.copy2(source, target)

    result = copy_art(
        source_dir=source_dir,
        target_dir=target_dir,
        source_team_id=args.source_team_id,
        target_team_id=args.target_team_id,
        archive_set=args.archive_set,
    )
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
