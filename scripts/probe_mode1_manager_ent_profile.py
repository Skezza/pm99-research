#!/usr/bin/env python3
"""Make one same-length ENT surname-only mutation in a disposable PM99 DBDAT root.

This is a narrow ownership probe, not a released manager editor.  It tests
whether a visibly named foreign dashboard manager is loaded from a specific
ENT profile.  The name length is deliberately fixed so the FDI directory and
every unrelated payload byte remain untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.ent_manager_profiles import parse_indexed_ent_manager_profile
from app.fdi_indexed import IndexedFDIFile
from app.xor import xor_decode, xor_encode


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbdat", required=True, type=Path)
    parser.add_argument("--manager-record-id", required=True, type=int)
    parser.add_argument("--expected-name", required=True)
    parser.add_argument("--new-name", required=True)
    parser.add_argument("--receipt", required=True, type=Path)
    return parser.parse_args()


def _xor_u16(payload: bytes, offset: int) -> int:
    return payload[offset] ^ 0x61 | ((payload[offset + 1] ^ 0x61) << 8)


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
    ent_path = args.dbdat.resolve() / "ENT98030.FDI"
    if not ent_path.is_file():
        raise SystemExit(f"missing ENT98030.FDI: {ent_path}")
    try:
        expected_bytes = args.expected_name.encode("cp1252")
        replacement = args.new_name.encode("cp1252")
    except UnicodeEncodeError as exc:
        raise SystemExit(f"name is not CP1252 encodable: {exc}") from exc
    if len(replacement) != len(expected_bytes):
        raise SystemExit(
            f"same-length probe required: expected name is {len(expected_bytes)} bytes, "
            f"replacement is {len(replacement)}"
        )

    before_file = ent_path.read_bytes()
    indexed = IndexedFDIFile.from_bytes(before_file)
    entry = next((row for row in indexed.entries if row.record_id == args.manager_record_id), None)
    if entry is None:
        raise SystemExit(f"ENT record id not found: {args.manager_record_id}")
    raw_before = before_file[entry.payload_offset : entry.payload_offset + entry.payload_length]
    profile_before = parse_indexed_ent_manager_profile(raw_before, record_id=args.manager_record_id)
    if profile_before.display_name != args.expected_name:
        raise SystemExit(
            f"ENT record {args.manager_record_id} is {profile_before.display_name!r}, "
            f"not expected {args.expected_name!r}"
        )
    if profile_before.format != "surname_only":
        raise SystemExit("this probe deliberately supports surname-only ENT records only")

    decoded_before = xor_decode(raw_before)
    name_length = _xor_u16(decoded_before, 7)
    name_start = 9
    name_end = name_start + name_length
    if decoded_before[name_start:name_end] != expected_bytes:
        raise SystemExit("decoded ENT surname span does not match expected text")
    if name_length != len(replacement):
        raise SystemExit("decoded ENT surname length does not match replacement length")

    decoded_after = decoded_before[:name_start] + replacement + decoded_before[name_end:]
    raw_after = xor_encode(decoded_after)
    if len(raw_after) != len(raw_before):
        raise SystemExit("same-length ENT probe unexpectedly changed payload length")
    profile_after = parse_indexed_ent_manager_profile(raw_after, record_id=args.manager_record_id)
    if profile_after.display_name != args.new_name:
        raise SystemExit("patched ENT profile did not reparse as requested name")

    after_file = bytearray(before_file)
    after_file[entry.payload_offset : entry.payload_offset + entry.payload_length] = raw_after
    IndexedFDIFile.from_bytes(bytes(after_file))
    ent_path.write_bytes(after_file)

    receipt = {
        "schema": "pm99-mode1-manager-ent-profile-probe/v1",
        "ent_path": str(ent_path),
        "manager_record_id": args.manager_record_id,
        "before_name": profile_before.display_name,
        "after_name": profile_after.display_name,
        "payload_offset": entry.payload_offset,
        "payload_length": entry.payload_length,
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
