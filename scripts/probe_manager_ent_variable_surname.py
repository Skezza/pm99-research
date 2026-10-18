#!/usr/bin/env python3
"""Rebuild one surname-only ENT payload to test a variable-length manager name.

This is a disposable proof probe. It changes one ENT `dd6360` surname, rebuilds
the indexed DMFI directory, verifies every non-target payload byte survives,
and writes a receipt for a fresh-game dashboard capture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from app.ent_manager_profiles import parse_indexed_ent_manager_profile
from app.fdi_indexed import IndexedFDIFile
from app.xor import xor_decode, xor_encode


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbdat", required=True, type=Path)
    parser.add_argument("--manager-record-id", required=True, type=int)
    parser.add_argument("--expected-name", required=True)
    parser.add_argument("--new-name", required=True)
    parser.add_argument("--receipt", required=True, type=Path)
    return parser.parse_args()


def _xor_u16(value: int) -> bytes:
    if not 1 <= value <= 0xFFFF:
        raise ValueError(f"invalid xored u16: {value}")
    return bytes((value & 0xFF) ^ 0x61 for value in (value, value >> 8))


def _decode_xor_u16(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise ValueError("xored u16 falls outside payload")
    return (data[offset] ^ 0x61) | ((data[offset + 1] ^ 0x61) << 8)


def _rebuild_indexed_fdi(original: bytes, indexed: IndexedFDIFile, replacement_raw: dict[int, bytes]) -> bytes:
    entries_by_id = {entry.record_id: entry for entry in indexed.entries}
    if set(replacement_raw) - set(entries_by_id):
        raise ValueError("replacement id is absent from indexed FDI directory")
    ordered = sorted(indexed.entries, key=lambda entry: entry.payload_offset)
    if not ordered:
        raise ValueError("cannot rebuild an empty indexed container")
    result = bytearray(original[: ordered[0].payload_offset])
    positions: dict[int, tuple[int, int]] = {}
    for index, entry in enumerate(ordered):
        old_end = entry.payload_offset + entry.payload_length
        raw = replacement_raw.get(entry.record_id, original[entry.payload_offset:old_end])
        positions[entry.record_id] = (len(result), len(raw))
        result.extend(raw)
        next_entry = ordered[index + 1] if index + 1 < len(ordered) else None
        if next_entry is None:
            result.extend(original[old_end:])
        else:
            if next_entry.payload_offset < old_end:
                raise ValueError("overlapping indexed payloads")
            result.extend(original[old_end:next_entry.payload_offset])
    for entry in indexed.entries:
        key_length = result[entry.index_offset + 4]
        offset_at = entry.index_offset + 5 + key_length
        new_offset, new_length = positions[entry.record_id]
        struct.pack_into("<I", result, offset_at, new_offset)
        struct.pack_into("<I", result, offset_at + 4, new_length)
    return bytes(result)


def main() -> int:
    args = _args()
    try:
        replacement = args.new_name.encode("cp1252")
        expected = args.expected_name.encode("cp1252")
    except UnicodeEncodeError as exc:
        raise SystemExit(f"name is not CP1252 encodable: {exc}") from exc
    if not replacement:
        raise SystemExit("new manager surname must not be empty")
    ent_path = args.dbdat.resolve() / "ENT98030.FDI"
    before_file = ent_path.read_bytes()
    indexed = IndexedFDIFile.from_bytes(before_file)
    entry = next((item for item in indexed.entries if item.record_id == args.manager_record_id), None)
    if entry is None:
        raise SystemExit(f"ENT record not found: {args.manager_record_id}")
    raw_before = before_file[entry.payload_offset : entry.payload_offset + entry.payload_length]
    profile_before = parse_indexed_ent_manager_profile(raw_before, record_id=entry.record_id)
    if profile_before.format != "surname_only" or profile_before.display_name != args.expected_name:
        raise SystemExit("probe requires the expected surname-only ENT profile")

    decoded_before = xor_decode(raw_before)
    name_len = _decode_xor_u16(decoded_before, 7)
    name_start = 9
    name_end = name_start + name_len
    if decoded_before[name_start:name_end] != expected or _decode_xor_u16(decoded_before, 0) != name_len + 1:
        raise SystemExit("unexpected surname-only ENT payload grammar")
    decoded_after = (
        _xor_u16(len(replacement) + 1)
        + decoded_before[2:7]
        + _xor_u16(len(replacement))
        + replacement
        + decoded_before[name_end:]
    )
    raw_after = xor_encode(decoded_after)
    profile_after = parse_indexed_ent_manager_profile(raw_after, record_id=entry.record_id)
    if profile_after.display_name != args.new_name:
        raise SystemExit("rebuild did not reparse the requested surname")

    after_file = _rebuild_indexed_fdi(before_file, indexed, {entry.record_id: raw_after})
    reparsed = IndexedFDIFile.from_bytes(after_file)
    if len(reparsed.entries) != len(indexed.entries):
        raise SystemExit("indexed directory entry count changed")
    unchanged_payloads = 0
    for old_entry in indexed.entries:
        new_entry = next(item for item in reparsed.entries if item.record_id == old_entry.record_id)
        old_raw = before_file[old_entry.payload_offset : old_entry.payload_offset + old_entry.payload_length]
        new_raw = after_file[new_entry.payload_offset : new_entry.payload_offset + new_entry.payload_length]
        if old_entry.record_id == entry.record_id:
            if new_raw != raw_after:
                raise SystemExit("target payload did not survive directory rebuild")
        elif old_raw != new_raw:
            raise SystemExit(f"unrelated ENT payload changed: {old_entry.record_id}")
        else:
            unchanged_payloads += 1
    ent_path.write_bytes(after_file)
    receipt = {
        "schema": "pm99-manager-ent-variable-surname-probe/v1",
        "ent_path": str(ent_path),
        "manager_record_id": entry.record_id,
        "before_name": profile_before.display_name,
        "after_name": profile_after.display_name,
        "before_payload_length": len(raw_before),
        "after_payload_length": len(raw_after),
        "directory_entry_count": len(reparsed.entries),
        "unrelated_payloads_preserved": unchanged_payloads,
        "before_sha256": hashlib.sha256(before_file).hexdigest(),
        "after_sha256": hashlib.sha256(after_file).hexdigest(),
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
