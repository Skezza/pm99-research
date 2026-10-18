#!/usr/bin/env python3
"""Materialise a declared calendar-patch group for bounded runtime diagnosis.

This is intentionally a probe, not a season release builder.  It writes a
separate executable containing only selected, profile-recognised year operand
groups so a runner test can distinguish a start-date seed fault from a
fixture-rollover fault.  Its receipt makes the incomplete calendar explicit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import pm99_calendar_patcher as calendar


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def materialise(
    *, input_path: Path, output_path: Path, target_year: int, source_years: set[int], prefix_count: int | None,
    day_overrides: dict[int, int],
) -> dict[str, object]:
    if prefix_count is None and (not source_years or not source_years <= {calendar.BASE_YEAR, calendar.ROLLOVER_YEAR}):
        raise calendar.PatchError("--source-year must select 1998 and/or 1999")
    if input_path.resolve() == output_path.resolve() or output_path.exists():
        raise calendar.PatchError("probe output must be a new path")
    source = input_path.read_bytes()
    if _sha256(source) != calendar.KNOWN_INPUT_SHA256:
        raise calendar.PatchError("probe requires the known clean calendar executable")
    image = calendar.PEImage(bytearray(source))
    calendar._validate_core_anchors(image)
    operands = calendar.find_year_operands(image)
    expected_counts = {
        year: sum(operand.source_year == year for operand in operands)
        for year in (calendar.BASE_YEAR, calendar.ROLLOVER_YEAR)
    }
    if expected_counts != calendar.EXPECTED_YEAR_OPERAND_COUNTS:
        raise calendar.PatchError("calendar operand profile does not match the known executable")
    changes: list[dict[str, object]] = []
    if prefix_count is not None and not 1 <= prefix_count <= len(operands):
        raise calendar.PatchError(f"--prefix-count must be in 1..{len(operands)}")
    selected_offsets = (
        {operand.file_offset for operand in operands[:prefix_count]}
        if prefix_count is not None
        else {operand.file_offset for operand in operands if operand.source_year in source_years}
    )
    for index, operand in enumerate(operands, start=1):
        if operand.file_offset not in selected_offsets:
            continue
        replacement_year = target_year + (operand.source_year - calendar.BASE_YEAR)
        replacement = replacement_year.to_bytes(operand.year_size, "little")
        image.write(operand.instruction_va, replacement)
        changes.append({
            "instruction_va": f"0x{operand.instruction_va:08X}",
            "source_year": operand.source_year,
            "replacement_year": replacement_year,
        })
        if index not in day_overrides:
            continue
        replacement_day = day_overrides[index]
        # A recognised ``push yyyy; push month; push day`` literal is the
        # only permitted day-level probe.  Do not treat arbitrary bytes after
        # a year operand as a date.
        if operand.year_size != 4 or image.read(operand.instruction_va - 1, 8)[:1] != b"\x68":
            raise calendar.PatchError(f"operand {index} is not a 32-bit pushed calendar date")
        date_suffix = image.read(operand.instruction_va + 4, 4)
        if date_suffix[:3] != b"\x6a\x05\x6a":
            raise calendar.PatchError(f"operand {index} is not the expected May date literal")
        image.write(operand.instruction_va + 7, bytes([replacement_day]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(bytes(image.blob))
    result = {
        "schema_version": "pm99-calendar-patch-group-probe-v1",
        "state": "diagnostic-incomplete-calendar-not-for-release",
        "input_sha256": _sha256(source),
        "output_sha256": _sha256(output_path.read_bytes()),
        "target_year": target_year,
        "included_source_years": sorted(source_years),
        "prefix_count": prefix_count,
        "day_overrides": {str(index): day for index, day in sorted(day_overrides.items())},
        "changed_operand_count": len(changes),
        "source_operand_counts": expected_counts,
        "changes": changes,
    }
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--year", type=int, required=True)
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--source-year", type=int, action="append")
    selector.add_argument("--prefix-count", type=int)
    parser.add_argument("--day-override", action="append", default=[], metavar="OPERAND:DAY",
                        help="bounded date probe, e.g. 817:7")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        day_overrides: dict[int, int] = {}
        for value in args.day_override:
            index_text, separator, day_text = value.partition(":")
            if not separator or not index_text.isdecimal() or not day_text.isdecimal():
                raise calendar.PatchError("--day-override must have the form OPERAND:DAY")
            index, day = int(index_text), int(day_text)
            if index in day_overrides or not 1 <= day <= 31:
                raise calendar.PatchError("--day-override contains a duplicate or invalid day")
            day_overrides[index] = day
        result = materialise(
            input_path=args.input, output_path=args.output, target_year=args.year,
            source_years=set(args.source_year or ()), prefix_count=args.prefix_count,
            day_overrides=day_overrides,
        )
    except (OSError, calendar.PatchError) as exc:
        parser.exit(2, f"calendar-patch-group-probe: {exc}\n")
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("state", "target_year", "included_source_years", "prefix_count", "changed_operand_count")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
