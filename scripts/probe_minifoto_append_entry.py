#!/usr/bin/env python3
"""Build a disposable MINIFOTO.PKF append-entry probe.

This is deliberately a research probe, not a public asset writer.  It adds a
new directory record and a donor-sized bitmap at the archive tail so the game
can decide whether PKF lookup accepts appended entries without a catalogue
repack.  The input archive is never modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

EDITOR_ROOT = Path(__file__).resolve().parents[1] / "upstream" / "pm99-skezmod-db-editor"
if str(EDITOR_ROOT) not in sys.path:
    sys.path.insert(0, str(EDITOR_ROOT))

from app.minifoto_bitmap_archive import (
    encode_obfuscated_bitmap_name,
    iter_minifoto_records_from_bytes,
)


def append_entry(source: bytes, *, target_id: int, donor_id: int, disabled_ids: tuple[int, ...] = ()) -> tuple[bytes, dict[str, object]]:
    records = iter_minifoto_records_from_bytes("MINIFOTO.PKF", source)
    disabled = tuple(sorted(set(disabled_ids)))
    if disabled:
        mutable = bytearray(source)
        for record in records:
            if record.player_record_id in disabled:
                mutable[record.record_offset] = 0
        source = bytes(mutable)
        records = iter_minifoto_records_from_bytes("MINIFOTO.PKF", source)
    if any(record.player_record_id == target_id for record in records):
        raise ValueError(f"target player {target_id} already has a MINIFOTO record")
    donor = next((record for record in records if record.player_record_id == donor_id), None)
    if donor is None:
        raise ValueError(f"donor player {donor_id} has no MINIFOTO record")

    directory = bytearray(source[donor.record_offset : donor.record_offset + 38])
    bitmap_offset = len(source) + len(directory)
    directory[1:21] = encode_obfuscated_bitmap_name(f"J96{target_id:05d}.BMP")
    directory[26:30] = bitmap_offset.to_bytes(4, "little")
    directory[30:34] = donor.bitmap_length.to_bytes(4, "little")
    output = source + bytes(directory) + donor.raw_bitmap
    parsed = iter_minifoto_records_from_bytes("MINIFOTO.PKF", output)
    inserted = next((record for record in parsed if record.player_record_id == target_id), None)
    if inserted is None or inserted.raw_bitmap != donor.raw_bitmap:
        raise RuntimeError("appended entry was not readable by the archive parser")
    return output, {
        "target_player_id": target_id,
        "target_file_name": inserted.file_name,
        "donor_player_id": donor_id,
        "donor_file_name": donor.file_name,
        "archive_length_before": len(source),
        "archive_length_after": len(output),
        "directory_offset": len(source),
        "bitmap_offset": bitmap_offset,
        "bitmap_length": donor.bitmap_length,
        "archive_sha256_before": hashlib.sha256(source).hexdigest(),
        "archive_sha256_after": hashlib.sha256(output).hexdigest(),
        "disabled_player_ids": list(disabled),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a disposable MINIFOTO append-entry probe")
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--target-player-id", type=int, required=True)
    parser.add_argument("--donor-player-id", type=int, default=15578)
    parser.add_argument("--disable-player-id", action="append", type=int, default=[], help="Temporarily hide an existing entry before the append probe")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--loose-bitmap-output", type=Path, help="Also write the donor bitmap as J96xxxxx.BMP for the loose-file probe")
    args = parser.parse_args()

    output, report = append_entry(
        args.archive.read_bytes(),
        target_id=args.target_player_id,
        donor_id=args.donor_player_id,
        disabled_ids=tuple(args.disable_player_id),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    if args.loose_bitmap_output:
        record = next(record for record in iter_minifoto_records_from_bytes("MINIFOTO.PKF", output) if record.player_record_id == args.target_player_id)
        args.loose_bitmap_output.parent.mkdir(parents=True, exist_ok=True)
        args.loose_bitmap_output.write_bytes(record.raw_bitmap)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
