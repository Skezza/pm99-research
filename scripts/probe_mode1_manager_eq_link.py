#!/usr/bin/env python3
"""Make one bounded mode-1 EQ -> ENT manager-link mutation in a test DBDAT root.

This is deliberately a research probe, not a bulk manager writer.  It changes
only the existing final four-byte manager id in one large mode-1 EQ carrier,
keeps the ENT-link count and all roster rows intact, and emits a receipt that
can be paired with a fresh-game dashboard capture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from app.xor import xor_decode


_MODE1_MANAGER_DELTA = 0x6E7


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbdat", required=True, type=Path)
    parser.add_argument("--eq-record-id", required=True, type=int)
    parser.add_argument("--expected-manager-id", required=True, type=int)
    parser.add_argument("--new-manager-id", required=True, type=int)
    parser.add_argument("--receipt", required=True, type=Path)
    return parser.parse_args()


def _read_xor_string_cursor(raw: bytes, cursor: int, label: str) -> int:
    if cursor + 2 > len(raw):
        raise ValueError(f"truncated {label} length")
    # The outer EQ payload is XOR encoded, but its inline string length word
    # remains stored plain.  Only the following text bytes are XOR encoded.
    length = int.from_bytes(raw[cursor : cursor + 2], "little")
    if length <= 0 or cursor + 2 + length > len(raw):
        raise ValueError(f"invalid {label} length")
    # Decode only as a structural check.  The resulting text is irrelevant to
    # this bounded link mutation.
    xor_decode(raw[cursor + 2 : cursor + 2 + length]).decode("cp1252")
    return cursor + 2 + length


def _mode1_final_manager_offset(raw: bytes) -> tuple[int, tuple[int, ...]]:
    if len(raw) < 0x2A:
        raise ValueError("EQ payload is too short")
    size = int.from_bytes(raw[0x26:0x28], "little")
    mode = raw[0x29]
    if size != 700 or mode != 1:
        raise ValueError(f"requires a 700-byte mode-1 EQ record, got size={size} mode={mode}")
    cursor = 0x2A
    cursor = _read_xor_string_cursor(raw, cursor, "short club name")
    cursor = _read_xor_string_cursor(raw, cursor, "stadium name")
    cursor += 1 + (1 if size > 0x20C else 0)
    cursor = _read_xor_string_cursor(raw, cursor, "full club name")
    cursor += 4 + (4 if size >= 0x1FE else 0) + 6
    count_offset = cursor + _MODE1_MANAGER_DELTA
    if count_offset >= len(raw):
        raise ValueError("manager-link count lies outside EQ payload")
    count = raw[count_offset]
    if count <= 0 or count_offset + 1 + count * 4 > len(raw):
        raise ValueError("EQ carrier has no structurally valid existing manager link")
    offsets = tuple(count_offset + 1 + index * 4 for index in range(count))
    return offsets[-1], offsets


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
    args = _args()
    if not 1 <= args.new_manager_id <= 0xFFFF_FFFF:
        raise SystemExit("new manager id must be a non-zero u32")
    dbdat = args.dbdat.resolve()
    eq_path = dbdat / "EQ98030.FDI"
    ent_path = dbdat / "ENT98030.FDI"
    if not eq_path.is_file() or not ent_path.is_file():
        raise SystemExit("both EQ98030.FDI and ENT98030.FDI are required")

    before_file = eq_path.read_bytes()
    eq_index = IndexedFDIFile.from_bytes(before_file)
    entry = next((row for row in eq_index.entries if row.record_id == args.eq_record_id), None)
    if entry is None:
        raise SystemExit(f"EQ record id not found: {args.eq_record_id}")
    raw_before = before_file[entry.payload_offset : entry.payload_offset + entry.payload_length]
    final_offset, all_offsets = _mode1_final_manager_offset(raw_before)
    before_id = int.from_bytes(raw_before[final_offset : final_offset + 4], "little")
    if before_id != args.expected_manager_id:
        raise SystemExit(f"EQ record {args.eq_record_id} points to {before_id}, not expected {args.expected_manager_id}")
    ent_ids = {row.record_id for row in IndexedFDIFile.from_path(ent_path).entries}
    if args.new_manager_id not in ent_ids:
        raise SystemExit(f"new manager id is not an indexed ENT record: {args.new_manager_id}")

    raw_after = bytearray(raw_before)
    raw_after[final_offset : final_offset + 4] = args.new_manager_id.to_bytes(4, "little")
    reparsed_offset, reparsed_offsets = _mode1_final_manager_offset(bytes(raw_after))
    after_id = int.from_bytes(raw_after[reparsed_offset : reparsed_offset + 4], "little")
    if reparsed_offset != final_offset or reparsed_offsets != all_offsets or after_id != args.new_manager_id:
        raise SystemExit("manager link did not reparse after bounded mutation")

    after_file = bytearray(before_file)
    start = entry.payload_offset + final_offset
    after_file[start : start + 4] = raw_after[final_offset : final_offset + 4]
    IndexedFDIFile.from_bytes(bytes(after_file))
    eq_path.write_bytes(after_file)
    receipt = {
        "schema": "pm99-mode1-manager-eq-link-probe/v1",
        "eq_path": str(eq_path),
        "eq_record_id": args.eq_record_id,
        "manager_link_count": len(all_offsets),
        "write_span": {"offset": start, "length": 4},
        "before_manager_id": before_id,
        "after_manager_id": after_id,
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
