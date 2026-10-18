#!/usr/bin/env python3
"""Patch one parser-backed mode-1 seated-capacity lane for a runtime probe.

This is deliberately not a released bulk writer.  It creates a reviewable
four-byte mutation in a disposable ``EQ98030.FDI`` and records enough
structural information to pair the mutation with a fresh-game Ground screen.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.eq_team_indexed_metadata import (
    extract_indexed_team_payload_metadata,
    patch_indexed_team_seated_capacity,
)
from app.fdi_indexed import IndexedFDIFile


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbdat", required=True, type=Path)
    parser.add_argument("--eq-record-id", required=True, type=int)
    parser.add_argument("--expected-capacity", required=True, type=int)
    parser.add_argument("--new-capacity", required=True, type=int)
    parser.add_argument("--receipt", required=True, type=Path)
    return parser.parse_args()


def _changed_spans(before: bytes, after: bytes) -> list[dict[str, int]]:
    spans: list[dict[str, int]] = []
    start: int | None = None
    for offset, (left, right) in enumerate(zip(before, after)):
        if left != right and start is None:
            start = offset
        elif left == right and start is not None:
            spans.append({"offset": start, "length": offset - start})
            start = None
    if start is not None:
        spans.append({"offset": start, "length": len(before) - start})
    return spans


def main() -> int:
    args = _parse_args()
    eq_path = args.dbdat.resolve() / "EQ98030.FDI"
    if not eq_path.is_file():
        raise SystemExit(f"missing EQ98030.FDI: {eq_path}")
    if not 0 <= int(args.new_capacity) <= 2_147_483_647:
        raise SystemExit("new capacity must fit a non-negative signed 32-bit lane")

    before_file = eq_path.read_bytes()
    indexed = IndexedFDIFile.from_bytes(before_file)
    entry = next((item for item in indexed.entries if item.record_id == args.eq_record_id), None)
    if entry is None:
        raise SystemExit(f"EQ record id not found: {args.eq_record_id}")
    raw_before = before_file[entry.payload_offset : entry.payload_offset + entry.payload_length]
    metadata_before = extract_indexed_team_payload_metadata(raw_before)
    if int(metadata_before["record_mode"]) != 1 or int(metadata_before["record_size"]) != 700:
        raise SystemExit(
            "requires a modern 700-byte mode-1 carrier, got "
            f"size={metadata_before['record_size']} mode={metadata_before['record_mode']}"
        )
    if int(metadata_before["seated_capacity"]) != int(args.expected_capacity):
        raise SystemExit(
            f"EQ record {args.eq_record_id} capacity is {metadata_before['seated_capacity']}, "
            f"not expected {args.expected_capacity}"
        )

    raw_after = patch_indexed_team_seated_capacity(raw_before, int(args.new_capacity))
    metadata_after = extract_indexed_team_payload_metadata(raw_after)
    if (
        int(metadata_after["seated_capacity"]) != int(args.new_capacity)
        or int(metadata_after["standing_capacity"] or 0) != int(metadata_before["standing_capacity"] or 0)
        or len(raw_after) != len(raw_before)
    ):
        raise SystemExit("capacity patch did not preserve the parsed mode-1 carrier shape")
    raw_spans = _changed_spans(raw_before, raw_after)
    if not raw_spans or any(span["offset"] != int(metadata_before["seated_capacity_offset"]) for span in raw_spans):
        raise SystemExit("capacity patch changed a byte outside the parser-backed seated lane")

    after_file = bytearray(before_file)
    after_file[entry.payload_offset : entry.payload_offset + entry.payload_length] = raw_after
    IndexedFDIFile.from_bytes(bytes(after_file))
    eq_path.write_bytes(after_file)

    receipt = {
        "schema": "pm99-mode1-team-capacity-probe/v1",
        "eq_path": str(eq_path),
        "eq_record_id": int(args.eq_record_id),
        "club": {
            "short_name": metadata_before["short_name"],
            "stadium_name": metadata_before["stadium_name"],
        },
        "record": {
            "size": int(metadata_before["record_size"]),
            "mode": int(metadata_before["record_mode"]),
            "payload_offset": int(entry.payload_offset),
            "payload_length": int(entry.payload_length),
        },
        "before": {
            "seated_capacity": int(metadata_before["seated_capacity"]),
            "standing_capacity": metadata_before["standing_capacity"],
        },
        "after": {
            "seated_capacity": int(metadata_after["seated_capacity"]),
            "standing_capacity": metadata_after["standing_capacity"],
        },
        "payload_changed_spans": raw_spans,
        "file_changed_spans": _changed_spans(before_file, bytes(after_file)),
        "before_sha256": hashlib.sha256(before_file).hexdigest(),
        "after_sha256": hashlib.sha256(after_file).hexdigest(),
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
