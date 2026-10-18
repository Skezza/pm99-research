#!/usr/bin/env python3
"""Make a disposable, same-length native-dd6360 metadata probe.

This is research tooling, not an editor write path. It only changes named
native-cursor bytes in one indexed JUG record and proves all other bytes in
the FDI are unchanged. It refuses the two known legacy birth-year encodings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.editor_actions import (  # type: ignore[import-not-found]
    _indexed_variable_name_compact_segments,
    _native_dd6360_fine_role_window_start,
    _native_dd6360_role_start,
    _read_native_dd6360_fields,
)
from app.fdi_indexed import IndexedFDIFile  # type: ignore[import-not-found]
from app.xor import xor_encode  # type: ignore[import-not-found]


_BIRTH_YEAR_PRESERVE_ONLY_IDS = {28453, 29678}
_FIELD_OFFSETS = {
    "nationality": 8,
    "birth_day": 12,
    "birth_month": 13,
    "height": 16,
    "weight": 17,
}
_POSITION_CODES = {"G": 0, "D": 1, "M": 2, "F": 3}


def _bounded(value: int, *, minimum: int, maximum: int, label: str) -> int:
    if not minimum <= value <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}; got {value}")
    return value


def _parse_skills(value: str | None) -> list[int] | None:
    if value is None:
        return None
    values = [_bounded(int(item.strip()), minimum=0, maximum=100, label="skill") for item in value.split(",")]
    if len(values) != 9:
        raise ValueError("--skills requires exactly nine comma-separated values")
    return values


def _parse_role_set(value: str | None) -> list[int] | None:
    if value is None:
        return None
    values = [item.strip() for item in value.split(",")]
    if len(values) != 6:
        raise ValueError("--role-set requires exactly six comma-separated role codes")
    parsed = [_bounded(int(item), minimum=0, maximum=98, label="role-set code") for item in values]
    if any(code not in {*range(18), 98} for code in parsed):
        raise ValueError("--role-set supports PM99 tactical codes 0..17 and 98 (unassigned) only")
    return parsed


def patch(
    source: Path,
    destination: Path,
    *,
    record_id: int,
    updates: dict[str, int],
    skills: list[int] | None,
    role: int | None,
    role_set: list[int] | None = None,
    position: int | None = None,
    handling: int | None = None,
) -> dict[str, object]:
    if source.resolve() == destination.resolve():
        raise ValueError("source and destination must differ; use a disposable output path")

    source_bytes = source.read_bytes()
    indexed = IndexedFDIFile.from_bytes(source_bytes)
    entry = next((item for item in indexed.entries if int(item.record_id) == record_id), None)
    if entry is None:
        raise ValueError(f"JUG record id {record_id} is not indexed")
    decoded = bytearray(entry.decode_payload(source_bytes))
    if decoded[2:5] != b"\xdd\x63\x60":
        raise ValueError(f"JUG id {record_id} is not dd6360 ({decoded[2:5].hex()})")

    segments = _indexed_variable_name_compact_segments(decoded)
    if segments is None:
        raise ValueError("dd6360 compact string cursor could not be resolved")
    role_start = _native_dd6360_role_start(decoded)
    if role_start != int(segments["full_name_end"]):
        raise ValueError("native role cursor does not agree with compact string end")
    before = _read_native_dd6360_fields(decoded, role_start)

    if "birth_year" in updates and record_id in _BIRTH_YEAR_PRESERVE_ONLY_IDS:
        raise ValueError(f"JUG id {record_id} has a preserve-only legacy birth-year encoding")

    changed_payload_offsets: list[int] = []
    for field, value in updates.items():
        if field == "birth_year":
            _bounded(value, minimum=1850, maximum=2050, label=field)
            for delta, byte in enumerate(value.to_bytes(2, "little")):
                offset = role_start + 14 + delta
                decoded[offset] = byte ^ 0x61
                changed_payload_offsets.append(offset)
            continue
        offset = role_start + _FIELD_OFFSETS[field]
        decoded[offset] = value ^ 0x61
        changed_payload_offsets.append(offset)

    if skills is not None:
        for index, value in enumerate(skills):
            offset = role_start + 18 + index
            decoded[offset] = value ^ 0x61
            changed_payload_offsets.append(offset)
    if handling is not None:
        # MANAGPRE's compact loader copies the byte immediately after the
        # nine generic skills into player+0xd3.  The player profile renders
        # that member as HANDLING.  Keep this named and separate from the
        # generic window: other player families do not share this location.
        offset = role_start + 27
        if offset >= len(decoded):
            raise ValueError("dd6360 compact handling byte is outside this payload")
        decoded[offset] = handling ^ 0x61
        changed_payload_offsets.append(offset)

    # This is deliberately a research-only write of fine-role window slot 0.
    # Ghidra shows the six bytes form a tactical candidate set: this does not
    # claim that slot 0 is a primary role, nor that the other five can be
    # safely edited as independent "secondary" roles.
    if role is not None:
        encoded_role = (role + 1) ^ 0x61
        offset = _native_dd6360_fine_role_window_start(decoded)
        decoded[offset] = encoded_role
        changed_payload_offsets.append(offset)
    if role_set is not None:
        window_start = _native_dd6360_fine_role_window_start(decoded)
        for index, value in enumerate(role_set):
            # A native decoded zero is PM99's unassigned candidate (reported
            # as 98); active codes are stored one-based.
            stored = 0 if value == 98 else value + 1
            offset = window_start + index
            decoded[offset] = stored ^ 0x61
            changed_payload_offsets.append(offset)
    if position is not None:
        for offset in (role_start + 10, role_start + 11):
            decoded[offset] = position ^ 0x61
            changed_payload_offsets.append(offset)

    after = _read_native_dd6360_fields(decoded, role_start)
    output = bytearray(source_bytes)
    encoded = xor_encode(bytes(decoded))
    start = int(entry.payload_offset)
    end = start + int(entry.payload_length)
    if len(encoded) != int(entry.payload_length):
        raise AssertionError("same-length probe unexpectedly changed indexed payload length")
    output[start:end] = encoded
    IndexedFDIFile.from_bytes(bytes(output))

    changed_file_offsets = [start + offset for offset in changed_payload_offsets]
    unchanged_elsewhere = all(
        old == new
        for index, (old, new) in enumerate(zip(source_bytes, output))
        if index not in set(changed_file_offsets)
    )
    if not unchanged_elsewhere:
        raise AssertionError("bytes outside approved native metadata spans changed")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(bytes(output))
    return {
        "schema_version": 1,
        "purpose": "Disposable same-length dd6360 native-metadata runtime probe",
        "source": str(source),
        "destination": str(destination),
        "record_id": record_id,
        "payload_offset": start,
        "payload_length": int(entry.payload_length),
        "pre_marker_gap_bytes": int(segments["pre_marker_gap_bytes"]),
        "role_start": role_start,
        "before": before,
        "after": after,
        "requested_updates": updates,
        "requested_skills": skills,
        "requested_handling": handling,
        "requested_fine_role_slot_0": role,
        "requested_fine_role_set": role_set,
        "requested_broad_position": position,
        "changed_payload_offsets": changed_payload_offsets,
        "changed_file_offsets": changed_file_offsets,
        "unchanged_elsewhere": unchanged_elsewhere,
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "destination_sha256": hashlib.sha256(bytes(output)).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--record-id", required=True, type=int)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--nationality", type=int)
    parser.add_argument("--birth-day", type=int)
    parser.add_argument("--birth-month", type=int)
    parser.add_argument("--birth-year", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--weight", type=int)
    parser.add_argument("--skills", help="Nine comma-separated values")
    parser.add_argument("--handling", type=int, help="Compact dd6360 native Handling value (0..100)")
    parser.add_argument(
        "--role",
        type=int,
        help="Research-only write to compact fine-role slot 0 (0..17; not a primary-role claim)",
    )
    parser.add_argument(
        "--role-set",
        help="Research-only exact six-slot compact tactical candidate set; values are 0..17 or 98 for unassigned",
    )
    parser.add_argument("--position", choices=sorted(_POSITION_CODES), help="Research-only broad position")
    args = parser.parse_args()

    updates: dict[str, int] = {}
    ranges = {
        "nationality": (0, 255),
        "birth_day": (1, 31),
        "birth_month": (1, 12),
        "birth_year": (1850, 2050),
        "height": (100, 240),
        "weight": (30, 180),
    }
    for field, (minimum, maximum) in ranges.items():
        value = getattr(args, field)
        if value is not None:
            updates[field] = _bounded(value, minimum=minimum, maximum=maximum, label=field)
    skills = _parse_skills(args.skills)
    handling = None if args.handling is None else _bounded(args.handling, minimum=0, maximum=100, label="handling")
    role = args.role
    if role is not None:
        role = _bounded(role, minimum=0, maximum=17, label="role")
    role_set = _parse_role_set(args.role_set)
    if role is not None and role_set is not None:
        raise ValueError("--role and --role-set are mutually exclusive")
    position = _POSITION_CODES.get(args.position) if args.position is not None else None
    if not updates and skills is None and handling is None and role is None and role_set is None and position is None:
        raise ValueError("supply at least one metadata update, --skills, --handling, --role, --role-set or --position")

    result = patch(
        args.source,
        args.destination,
        record_id=args.record_id,
        updates=updates,
        skills=skills,
        handling=handling,
        role=role,
        role_set=role_set,
        position=position,
    )
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
