#!/usr/bin/env python3
"""Rebuild one full-profile ENT name pair while preserving its prose tail.

The probe is intentionally limited to the established two CP1252 name
segments of a `dd6361` ENT manager profile. It changes neither biography nor
career text, rebuilds the indexed container, and checks every other payload is
byte-for-byte unchanged before a disposable game run is attempted.
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
    parser.add_argument("--expected-surname", required=True)
    parser.add_argument("--expected-display-name", required=True)
    parser.add_argument("--new-surname", required=True)
    parser.add_argument("--new-display-name", required=True)
    parser.add_argument("--receipt", required=True, type=Path)
    return parser.parse_args()


def _xor_u16(value: int) -> bytes:
    if not 1 <= value <= 0xFFFF:
        raise ValueError(f"invalid xored u16: {value}")
    return bytes(((value & 0xFF) ^ 0x61, ((value >> 8) & 0xFF) ^ 0x61))


def _read_xor_u16(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise ValueError("xored u16 falls outside ENT payload")
    return (data[offset] ^ 0x61) | ((data[offset + 1] ^ 0x61) << 8)


def _rebuild(original: bytes, indexed: IndexedFDIFile, target_id: int, target_raw: bytes) -> bytes:
    ordered = sorted(indexed.entries, key=lambda entry: entry.payload_offset)
    rebuilt = bytearray(original[: ordered[0].payload_offset])
    positions: dict[int, tuple[int, int]] = {}
    for index, entry in enumerate(ordered):
        old_end = entry.payload_offset + entry.payload_length
        raw = target_raw if entry.record_id == target_id else original[entry.payload_offset:old_end]
        positions[entry.record_id] = (len(rebuilt), len(raw))
        rebuilt.extend(raw)
        next_entry = ordered[index + 1] if index + 1 < len(ordered) else None
        rebuilt.extend(original[old_end : next_entry.payload_offset if next_entry else len(original)])
    for entry in indexed.entries:
        key_length = rebuilt[entry.index_offset + 4]
        offset_at = entry.index_offset + 5 + key_length
        offset, length = positions[entry.record_id]
        struct.pack_into("<I", rebuilt, offset_at, offset)
        struct.pack_into("<I", rebuilt, offset_at + 4, length)
    return bytes(rebuilt)


def main() -> int:
    args = _args()
    try:
        expected_surname = args.expected_surname.encode("cp1252")
        expected_display = args.expected_display_name.encode("cp1252")
        new_surname = args.new_surname.encode("cp1252")
        new_display = args.new_display_name.encode("cp1252")
    except UnicodeEncodeError as exc:
        raise SystemExit(f"name is not CP1252 encodable: {exc}") from exc
    if not new_surname or not new_display:
        raise SystemExit("full-profile names must not be empty")
    ent_path = args.dbdat.resolve() / "ENT98030.FDI"
    before_file = ent_path.read_bytes()
    indexed = IndexedFDIFile.from_bytes(before_file)
    entry = next((item for item in indexed.entries if item.record_id == args.manager_record_id), None)
    if entry is None:
        raise SystemExit(f"ENT record not found: {args.manager_record_id}")
    raw_before = before_file[entry.payload_offset : entry.payload_offset + entry.payload_length]
    profile_before = parse_indexed_ent_manager_profile(raw_before, record_id=entry.record_id)
    if profile_before.format != "full_profile" or profile_before.surname != args.expected_surname or profile_before.display_name != args.expected_display_name:
        raise SystemExit("probe does not match expected full-profile ENT fields")
    decoded_before = xor_decode(raw_before)
    surname_length = _read_xor_u16(decoded_before, 7)
    surname_start = 9
    surname_end = surname_start + surname_length
    display_length = _read_xor_u16(decoded_before, surname_end)
    display_start = surname_end + 2
    display_end = display_start + display_length
    if (
        decoded_before[surname_start:surname_end] != expected_surname
        or decoded_before[display_start:display_end] != expected_display
        or _read_xor_u16(decoded_before, 0) != surname_length + display_length + 2
    ):
        raise SystemExit("unexpected full-profile ENT name grammar")
    prose_tail = decoded_before[display_end:]
    decoded_after = (
        _xor_u16(len(new_surname) + len(new_display) + 2)
        + decoded_before[2:7]
        + _xor_u16(len(new_surname))
        + new_surname
        + _xor_u16(len(new_display))
        + new_display
        + prose_tail
    )
    raw_after = xor_encode(decoded_after)
    profile_after = parse_indexed_ent_manager_profile(raw_after, record_id=entry.record_id)
    if profile_after.surname != args.new_surname or profile_after.display_name != args.new_display_name:
        raise SystemExit("full-profile name did not reparse after rebuild")
    if xor_decode(raw_after)[len(decoded_after) - len(prose_tail) :] != prose_tail:
        raise SystemExit("full-profile prose tail changed during name rebuild")

    after_file = _rebuild(before_file, indexed, entry.record_id, raw_after)
    reparsed = IndexedFDIFile.from_bytes(after_file)
    if len(reparsed.entries) != len(indexed.entries):
        raise SystemExit("indexed directory count changed")
    unchanged = 0
    for old_entry in indexed.entries:
        new_entry = next(item for item in reparsed.entries if item.record_id == old_entry.record_id)
        old_raw = before_file[old_entry.payload_offset : old_entry.payload_offset + old_entry.payload_length]
        new_raw = after_file[new_entry.payload_offset : new_entry.payload_offset + new_entry.payload_length]
        if old_entry.record_id == entry.record_id:
            if new_raw != raw_after:
                raise SystemExit("target full-profile payload did not survive container rebuild")
        elif old_raw != new_raw:
            raise SystemExit(f"unrelated ENT payload changed: {old_entry.record_id}")
        else:
            unchanged += 1
    ent_path.write_bytes(after_file)
    receipt = {
        "schema": "pm99-manager-ent-variable-profile-name-probe/v1",
        "ent_path": str(ent_path),
        "manager_record_id": entry.record_id,
        "before": {"surname": profile_before.surname, "display_name": profile_before.display_name, "payload_length": len(raw_before)},
        "after": {"surname": profile_after.surname, "display_name": profile_after.display_name, "payload_length": len(raw_after)},
        "prose_tail_length": len(prose_tail),
        "directory_entry_count": len(reparsed.entries),
        "unrelated_payloads_preserved": unchanged,
        "before_sha256": hashlib.sha256(before_file).hexdigest(),
        "after_sha256": hashlib.sha256(after_file).hexdigest(),
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
