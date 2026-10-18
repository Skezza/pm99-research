#!/usr/bin/env python3
"""Create a version-checked PM99 calendar EXE copy for a historical season.

This is deliberately independent of the database editor.  It never changes an
input executable: the caller supplies an output path and receives a JSON
receipt containing the original and generated SHA-256 hashes.

The profile is deliberately independent of the database editor.  It rebases
the *two* calendar years represented by PM99's opening season: 1998 becomes
the requested start year and 1999 becomes the following year.  PM99 stores
hundreds of fixture dates as instruction operands, so changing just the
visible start date makes the schedule internally inconsistent.

This is a fingerprinted research profile for one known No-CD MANAGPRE.EXE.
Every changed value must be a recognised 16- or 32-bit x86 immediate in the
executable's code section, and the exact expected operand counts must match.
It therefore fails closed for a different executable or unexpected code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


IMAGE_BASE = 0x00400000
BASE_YEAR = 1998
ROLLOVER_YEAR = 1999
SUPPORTED_YEARS = range(1900, 2027)
KNOWN_INPUT_SHA256 = "01b845f7dc728e3813968bed51ff24810fde556fab395e97ca7649c57ee53158"
TEXT_START_VA = 0x00401000
TEXT_END_VA = 0x006E5092
EXPECTED_YEAR_OPERAND_COUNTS = {BASE_YEAR: 50, ROLLOVER_YEAR: 803}


@dataclass(frozen=True)
class CalendarDayOverride:
    """One verified day correction for a weekly hard-coded calendar event."""

    year_operand_va: int
    source_year: int
    month: int
    before_day: int
    after_day: int
    description: str


# Retained legacy Saturday alignment for the 8-May-1999 event. The earlier
# claim that this date change fixed 2004/05 setup was not established: that
# crash was intermittent and also occurred with this exception installed.
# Fixed-seed controls on 2026-10-03 instead isolated cloned player self-IDs.
# Keep this calendar byte unchanged during the identity repair; revisiting
# the event date needs a separate controlled test, not a crash-fix claim.
TARGET_DAY_OVERRIDES = {
    2004: (
        CalendarDayOverride(
            year_operand_va=0x004EFE73,
            source_year=1999,
            month=5,
            before_day=8,
            after_day=7,
            description="weekly-calendar Saturday alignment for the 8-May-1999 event",
        ),
    ),
}


@dataclass(frozen=True)
class Section:
    virtual_address: int
    virtual_size: int
    raw_pointer: int
    raw_size: int


@dataclass(frozen=True)
class YearPatch:
    instruction_va: int
    prefix: bytes
    year_offset: int
    year_size: int
    description: str

    @property
    def expected_instruction(self) -> bytes:
        return self.prefix + BASE_YEAR.to_bytes(self.year_size, "little")


def _word_write(va: int, destination_va: int, description: str) -> YearPatch:
    return YearPatch(va, b"\x66\xc7\x05" + struct.pack("<I", destination_va), 7, 2, description)


# These six points are the easiest human-readable anchors in the profile and
# are also used by the synthetic unit test. The complete set is discovered
# below from recognised instruction forms: PM99 has 803 explicit 1999 fixture
# operands as well as 1998 initialisers.
CORE_YEAR_PATCHES = (
    _word_write(0x0040A098, 0x00759794, "new-game current date seed A"),
    _word_write(0x0040A9A1, 0x00759794, "new-game current date seed B"),
    _word_write(0x0040AA6F, 0x00759794, "new-game calendar reset seed"),
    YearPatch(0x004B02BD, b"\xb8", 1, 4, "legacy player age seed"),
    YearPatch(0x004B2B00, b"\xb8", 1, 4, "legacy player age fallback"),
    _word_write(0x005AE0E2, 0x00759794, "shared current-date reset"),
)


@dataclass(frozen=True)
class YearOperand:
    instruction_va: int
    file_offset: int
    source_year: int
    year_size: int

    @property
    def expected(self) -> bytes:
        return self.source_year.to_bytes(self.year_size, "little")


def _is_recognised_year_operand(blob: bytes | bytearray, offset: int, year: int) -> int | None:
    """Return immediate size for one safe x86 year operand, otherwise ``None``.

    The accepted forms cover every 1998/1999 operand in the known executable:
    ``push/mov/cmp/or`` style 32-bit immediates, and the 16-bit date writes and
    comparisons used by PM99's packed date structure. This is intentionally
    tighter than searching for raw ``ce 07``/``cf 07`` byte pairs; those pairs
    also occur inside unrelated CALL displacements.
    """
    marker16 = year.to_bytes(2, "little")
    if blob[offset : offset + 2] != marker16:
        return None

    marker32 = marker16 + b"\x00\x00"
    if blob[offset : offset + 4] == marker32:
        previous = blob[offset - 1] if offset >= 1 else -1
        if previous in {0x68, 0x3D, *range(0xB8, 0xC0)}:
            return 4
        if offset >= 2 and blob[offset - 2] == 0x81 and 0xC0 <= previous <= 0xFF:
            return 4

    if offset >= 2 and blob[offset - 2 : offset] == b"\x66\x3d":
        return 2
    if offset >= 7 and bytes(blob[offset - 7 : offset - 5]) in {b"\x66\xc7", b"\x66\x81"}:
        return 2
    return None


class PatchError(ValueError):
    """The requested executable is not a supported, safe patch target."""


class PEImage:
    def __init__(self, blob: bytearray) -> None:
        if blob[:2] != b"MZ":
            raise PatchError("input is not a PE executable (missing MZ header)")
        pe_offset = struct.unpack_from("<I", blob, 0x3C)[0]
        if blob[pe_offset : pe_offset + 4] != b"PE\0\0":
            raise PatchError("input is not a PE executable (missing PE header)")
        section_count = struct.unpack_from("<H", blob, pe_offset + 6)[0]
        optional_header_size = struct.unpack_from("<H", blob, pe_offset + 20)[0]
        section_table = pe_offset + 24 + optional_header_size
        self.blob = blob
        self.sections = []
        for index in range(section_count):
            offset = section_table + index * 40
            virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from(
                "<IIII", blob, offset + 8
            )
            self.sections.append(Section(virtual_address, virtual_size, raw_pointer, raw_size))

    def va_to_offset(self, va: int) -> int:
        rva = va - IMAGE_BASE
        for section in self.sections:
            size = max(section.virtual_size, section.raw_size)
            if section.virtual_address <= rva < section.virtual_address + size:
                return section.raw_pointer + rva - section.virtual_address
        raise PatchError(f"VA 0x{va:08X} is not mapped by this executable")

    def read(self, va: int, size: int) -> bytes:
        offset = self.va_to_offset(va)
        return bytes(self.blob[offset : offset + size])

    def write(self, va: int, payload: bytes) -> None:
        offset = self.va_to_offset(va)
        self.blob[offset : offset + len(payload)] = payload


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def instruction_for_year(patch: YearPatch, year: int) -> bytes:
    instruction = bytearray(patch.expected_instruction)
    instruction[patch.year_offset : patch.year_offset + patch.year_size] = year.to_bytes(
        patch.year_size, "little"
    )
    return bytes(instruction)


def find_year_operands(image: PEImage) -> list[YearOperand]:
    """Find the profile's explicit 1998/1999 code operands.

    The byte form of a year alone is not a contract: it can be a relative
    address, data, or part of an unrelated instruction.  ``_is_recognised``
    only accepts the immediate forms observed in this build, and this caller
    confines the search to the executable code section.
    """
    start_offset = image.va_to_offset(TEXT_START_VA)
    end_offset = image.va_to_offset(TEXT_END_VA - 1) + 1
    if end_offset > len(image.blob):
        raise PatchError("known .text range is not fully present in this executable")

    operands: list[YearOperand] = []
    seen_offsets: set[int] = set()
    for source_year in (BASE_YEAR, ROLLOVER_YEAR):
        marker = source_year.to_bytes(2, "little")
        offset = start_offset
        while True:
            offset = image.blob.find(marker, offset, end_offset)
            if offset < 0:
                break
            immediate_size = _is_recognised_year_operand(image.blob, offset, source_year)
            if immediate_size is not None:
                if offset in seen_offsets:
                    raise PatchError(f"ambiguous year operand at file offset 0x{offset:X}")
                seen_offsets.add(offset)
                operands.append(
                    YearOperand(
                        instruction_va=TEXT_START_VA + offset - start_offset,
                        file_offset=offset,
                        source_year=source_year,
                        year_size=immediate_size,
                    )
                )
            offset += 1
    return sorted(operands, key=lambda operand: operand.file_offset)


def _validate_core_anchors(image: PEImage) -> None:
    """Give failures a human-readable reason before the full profile scan."""
    for patch in CORE_YEAR_PATCHES:
        actual = image.read(patch.instruction_va, len(patch.expected_instruction))
        if actual != patch.expected_instruction:
            raise PatchError(
                f"unsupported EXE at 0x{patch.instruction_va:08X}: expected "
                f"{patch.expected_instruction.hex(' ')}, found {actual.hex(' ')}"
            )


def patch_calendar(
    input_path: Path,
    output_path: Path,
    target_year: int,
    *,
    strict_profile: bool = True,
) -> dict[str, object]:
    if target_year not in SUPPORTED_YEARS:
        raise PatchError("target year must be in the supported 1900..2026 range")
    if input_path.resolve() == output_path.resolve():
        raise PatchError("input and output must differ; this patcher never modifies the input EXE")
    if not input_path.is_file():
        raise PatchError(f"missing input EXE: {input_path}")
    if output_path.exists():
        raise PatchError(f"refusing to overwrite existing output: {output_path}")

    source = input_path.read_bytes()
    source_hash = sha256(source)
    if strict_profile and source_hash != KNOWN_INPUT_SHA256:
        raise PatchError(
            "unsupported EXE SHA-256: this calendar profile only accepts "
            f"{KNOWN_INPUT_SHA256}, found {source_hash}"
        )
    image = PEImage(bytearray(source))
    _validate_core_anchors(image)
    operands = find_year_operands(image)
    counts = {
        source_year: sum(operand.source_year == source_year for operand in operands)
        for source_year in (BASE_YEAR, ROLLOVER_YEAR)
    }
    if strict_profile and counts != EXPECTED_YEAR_OPERAND_COUNTS:
        raise PatchError(
            "unsupported EXE calendar operand count: expected "
            f"{EXPECTED_YEAR_OPERAND_COUNTS}, found {counts}"
        )

    changes: list[dict[str, object]] = []
    for operand in operands:
        actual = image.read(operand.instruction_va, operand.year_size)
        if actual != operand.expected:
            raise PatchError(
                f"calendar operand changed at 0x{operand.instruction_va:08X}: expected "
                f"{operand.expected.hex(' ')}, found {actual.hex(' ')}"
            )
        replacement_year = target_year + (operand.source_year - BASE_YEAR)
        replacement = replacement_year.to_bytes(operand.year_size, "little")
        image.write(operand.instruction_va, replacement)
        changes.append(
            {
                "instruction_va": f"0x{operand.instruction_va:08X}",
                "file_offset": f"0x{operand.file_offset:X}",
                "description": (
                    "opening-season start-year operand"
                    if operand.source_year == BASE_YEAR
                    else "opening-season rollover-year operand"
                ),
                "before": actual.hex(" "),
                "after": replacement.hex(" "),
            }
        )

    day_changes: list[dict[str, object]] = []
    # These overrides apply only when the strict profile has already proved
    # that every recognised operand belongs to the known executable.  A
    # synthetic test fixture or a future executable must not receive an
    # offset-based day write merely because its requested year is 2004.
    if strict_profile:
        for override in TARGET_DAY_OVERRIDES.get(target_year, ()):
            operand = next(
                (
                    candidate for candidate in operands
                    if candidate.instruction_va == override.year_operand_va
                    and candidate.source_year == override.source_year
                    and candidate.year_size == 4
                ),
                None,
            )
            if operand is None:
                raise PatchError(
                    f"target-day override has no verified year operand at "
                    f"0x{override.year_operand_va:08X}"
                )
            date_suffix = image.read(operand.instruction_va + 4, 4)
            expected_suffix = bytes((0x6A, override.month, 0x6A, override.before_day))
            if date_suffix != expected_suffix:
                raise PatchError(
                    f"target-day override has an unexpected date literal at "
                    f"0x{override.year_operand_va:08X}"
                )
            image.write(operand.instruction_va + 7, bytes((override.after_day,)))
            day_changes.append({
                "instruction_va": f"0x{override.year_operand_va:08X}",
                "source_year": override.source_year,
                "target_year": target_year + (override.source_year - BASE_YEAR),
                "month": override.month,
                "before_day": override.before_day,
                "after_day": override.after_day,
                "description": override.description,
            })

    patched = bytes(image.blob)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(patched)
    readback = output_path.read_bytes()
    if readback != patched:
        raise PatchError("output readback mismatch")

    return {
        "schema_version": "pm99-calendar-patch-v1",
        "profile": "managpre-calendar-1998-99-to-target-v1",
        "input": str(input_path.resolve()),
        "output": str(output_path.resolve()),
        "base_year": BASE_YEAR,
        "rollover_year": ROLLOVER_YEAR,
        "target_year": target_year,
        "target_rollover_year": target_year + 1,
        "before_sha256": source_hash,
        "after_sha256": sha256(readback),
        "patch_count": len(changes) + len(day_changes),
        "source_operand_counts": counts,
        "patches": changes,
        "day_overrides": day_changes,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Unmodified supported MANAGPRE.EXE")
    parser.add_argument("--year", type=int, required=True, help="Historical start year (1900..2026)")
    parser.add_argument("--output", type=Path, required=True, help="New EXE output path")
    parser.add_argument("--receipt", type=Path, help="Optional JSON receipt path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        receipt = patch_calendar(args.input, args.output, args.year)
    except PatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
