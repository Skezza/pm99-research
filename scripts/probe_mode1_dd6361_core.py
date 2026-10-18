#!/usr/bin/env python3
"""Make one disposable, byte-accounted mode-1 ``dd6361`` core-field probe.

The world registry has one fixed foreign roster slot whose player is the full
``dd6361`` family rather than compact ``dd6360``. This tool proves that the
ordinary full-player codec can update its visible core fields without
normalising the record prefix, its role vector, or unknown tail bytes.

It is research tooling. Source and destination must differ and it refuses to
make a no-op probe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from app.editor_actions import _apply_player_mutations  # type: ignore[import-not-found]
from app.fdi_indexed import IndexedFDIFile  # type: ignore[import-not-found]
from app.models import PlayerRecord  # type: ignore[import-not-found]
from app.xor import xor_encode  # type: ignore[import-not-found]


_POSITIONS = {"G": 0, "D": 1, "M": 2, "F": 3}


def _skills(value: str | None) -> list[int] | None:
    if value is None:
        return None
    result = [int(item.strip()) for item in value.split(",")]
    if len(result) != 9 or any(not 0 <= item <= 100 for item in result):
        raise ValueError("--skills must contain exactly nine values in 0..100")
    return result


def _record_snapshot(record: PlayerRecord) -> dict[str, Any]:
    return {
        "name": str(record.name or ""),
        "position": int(record.position),
        "nationality": int(record.nationality),
        "birth_day": int(record.birth_day),
        "birth_month": int(record.birth_month),
        "birth_year": int(record.birth_year),
        "height_cm": int(record.height),
        "weight_kg": int(record.weight),
        "attributes": [int(value) for value in record.attributes],
    }


def _fine_role_bytes(payload: bytes) -> list[int]:
    """Return the raw six-byte role window from a full-player record.

    This is retained as byte evidence only; it intentionally does not assign
    a primary/secondary meaning to the individual values.
    """

    cursor = 7
    for _ in range(2):
        if cursor + 2 > len(payload):
            raise ValueError("dd6361 compact-name header is truncated")
        length = payload[cursor] ^ 0x61
        cursor += 2 + length
    start = cursor + 2
    if start + 6 > len(payload):
        raise ValueError("dd6361 fine-role window is truncated")
    return [int(payload[start + index]) for index in range(6)]


def patch(
    source: Path,
    destination: Path,
    *,
    record_id: int,
    nationality: int | None,
    birth_day: int | None,
    birth_month: int | None,
    birth_year: int | None,
    height: int | None,
    weight: int | None,
    position: int | None,
    skills: list[int] | None,
) -> dict[str, Any]:
    if source.resolve() == destination.resolve():
        raise ValueError("source and destination must differ")
    if all(value is None for value in (
        nationality, birth_day, birth_month, birth_year, height, weight, position, skills,
    )):
        raise ValueError("supply at least one core-field update")

    source_bytes = source.read_bytes()
    indexed = IndexedFDIFile.from_bytes(source_bytes)
    entry = next((item for item in indexed.entries if int(item.record_id) == record_id), None)
    if entry is None:
        raise ValueError(f"JUG record id {record_id} is not indexed")
    decoded = entry.decode_payload(source_bytes)
    if decoded[2:5] != b"\xdd\x63\x61":
        raise ValueError(f"JUG id {record_id} is not dd6361 ({decoded[2:5].hex()})")

    before = PlayerRecord.from_bytes(decoded, int(entry.payload_offset))
    before_snapshot = _record_snapshot(before)
    before_roles = _fine_role_bytes(decoded)

    # Establish the codec's exact no-op output before authorising mutations.
    pristine = bytearray(before.to_bytes())
    if len(pristine) != len(decoded):
        raise AssertionError("dd6361 codec changed payload length on a no-op round trip")
    pristine[:2] = decoded[:2]
    if bytes(pristine) != decoded:
        changed = [index for index, (old, new) in enumerate(zip(decoded, pristine)) if old != new]
        raise AssertionError(f"dd6361 codec changed unrequested bytes on a no-op round trip: {changed[:16]}")

    _apply_player_mutations(
        before,
        position=position,
        nationality=nationality,
        birth_day=birth_day,
        birth_month=birth_month,
        birth_year=birth_year,
        height=height,
        weight=weight,
        attribute_updates=(None if skills is None else {index + 3: value for index, value in enumerate(skills)}),
        offset=int(entry.payload_offset),
    )
    mutated = bytearray(before.to_bytes())
    if len(mutated) != len(decoded):
        raise AssertionError("dd6361 core mutation changed payload length")
    # The full player codec does not own the indexed payload's two-byte
    # preamble. It must remain the original opaque value.
    mutated[:2] = decoded[:2]
    after_snapshot = _record_snapshot(PlayerRecord.from_bytes(bytes(mutated), int(entry.payload_offset)))
    after_roles = _fine_role_bytes(bytes(mutated))
    if after_roles != before_roles:
        raise AssertionError("dd6361 core mutation changed the tactical role window")

    expected = dict(before_snapshot)
    field_updates = {
        "nationality": nationality,
        "birth_day": birth_day,
        "birth_month": birth_month,
        "birth_year": birth_year,
        "height_cm": height,
        "weight_kg": weight,
        "position": position,
    }
    for field, value in field_updates.items():
        if value is not None:
            expected[field] = int(value)
    if skills is not None:
        expected_attributes = list(expected["attributes"])
        expected_attributes[3:12] = skills
        expected["attributes"] = expected_attributes
    for field, expected_value in expected.items():
        if after_snapshot[field] != expected_value:
            raise AssertionError(
                f"dd6361 read-back mismatch for {field}: {after_snapshot[field]!r} != {expected_value!r}"
            )

    changed_payload_offsets = [
        index for index, (old, new) in enumerate(zip(decoded, mutated)) if old != new
    ]
    if not changed_payload_offsets:
        raise ValueError("requested dd6361 core update is a no-op")
    output = bytearray(source_bytes)
    start = int(entry.payload_offset)
    end = start + int(entry.payload_length)
    output[start:end] = xor_encode(bytes(mutated))
    IndexedFDIFile.from_bytes(bytes(output))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(bytes(output))
    return {
        "schema_version": 1,
        "purpose": "Disposable mode-1 dd6361 core metadata runtime probe",
        "record_id": record_id,
        "payload_offset": start,
        "payload_length": int(entry.payload_length),
        "before": before_snapshot,
        "after": after_snapshot,
        "fine_role_bytes_before": before_roles,
        "fine_role_bytes_after": after_roles,
        "fine_role_bytes_preserved": True,
        "changed_payload_offsets": changed_payload_offsets,
        "changed_file_offsets": [start + offset for offset in changed_payload_offsets],
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
    parser.add_argument("--position", choices=sorted(_POSITIONS))
    parser.add_argument("--skills", help="Nine comma-separated values")
    args = parser.parse_args()

    result = patch(
        args.source,
        args.destination,
        record_id=args.record_id,
        nationality=args.nationality,
        birth_day=args.birth_day,
        birth_month=args.birth_month,
        birth_year=args.birth_year,
        height=args.height,
        weight=args.weight,
        position=None if args.position is None else _POSITIONS[args.position],
        skills=_skills(args.skills),
    )
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
