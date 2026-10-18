"""Focused safety tests for the standalone PM99 calendar patcher."""

from __future__ import annotations

import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("pm99_calendar_patcher.py")
SPEC = importlib.util.spec_from_file_location("pm99_calendar_patcher", MODULE_PATH)
assert SPEC and SPEC.loader
calendar = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = calendar
SPEC.loader.exec_module(calendar)


def make_test_pe(path: Path) -> None:
    # A minimal PE32 image with a single .text-like section at VA 0x1000.
    blob = bytearray(0x500000)
    blob[:2] = b"MZ"
    struct.pack_into("<I", blob, 0x3C, 0x80)
    blob[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", blob, 0x80 + 6, 1)
    struct.pack_into("<H", blob, 0x80 + 20, 0xE0)
    section = 0x80 + 24 + 0xE0
    blob[section:section + 5] = b".text"
    struct.pack_into("<IIII", blob, section + 8, 0x400000, 0x1000, 0x400000, 0x400)
    image = calendar.PEImage(blob)
    for patch in calendar.CORE_YEAR_PATCHES:
        image.write(patch.instruction_va, patch.expected_instruction)
    # A real recognised 1999 ``push imm32`` rollover fixture entry.  The
    # synthetic fixture deliberately does not contain the production count.
    image.write(0x00402100, b"\x68\xcf\x07\x00\x00")
    path.write_bytes(bytes(image.blob))


class CalendarPatcherTests(unittest.TestCase):
    def test_patches_only_known_complete_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            source = tmp_path / "source.exe"
            output = tmp_path / "patched.exe"
            make_test_pe(source)

            receipt = calendar.patch_calendar(source, output, 2015, strict_profile=False)

            self.assertNotEqual(source.read_bytes(), output.read_bytes())
            self.assertEqual(receipt["target_year"], 2015)
            image = calendar.PEImage(bytearray(output.read_bytes()))
            for patch in calendar.CORE_YEAR_PATCHES:
                self.assertEqual(
                    image.read(patch.instruction_va, len(patch.expected_instruction)),
                    calendar.instruction_for_year(patch, 2015),
                )
            self.assertEqual(image.read(0x00402100, 5), b"\x68\xe0\x07\x00\x00")
            self.assertEqual(receipt["target_rollover_year"], 2016)
            self.assertEqual(receipt["patch_count"], 7)

    def test_accepts_the_first_post_base_season(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            source = tmp_path / "source.exe"
            output = tmp_path / "patched.exe"
            make_test_pe(source)

            receipt = calendar.patch_calendar(source, output, 1999, strict_profile=False)

            self.assertEqual(receipt["target_year"], 1999)
            self.assertEqual(receipt["target_rollover_year"], 2000)

    def test_accepts_a_pre_pm99_historical_season(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            source = tmp_path / "source.exe"
            output = tmp_path / "patched.exe"
            make_test_pe(source)

            receipt = calendar.patch_calendar(source, output, 1990, strict_profile=False)

            self.assertEqual(receipt["target_year"], 1990)
            self.assertEqual(receipt["target_rollover_year"], 1991)

    def test_refuses_an_unknown_instruction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            source = tmp_path / "source.exe"
            output = tmp_path / "patched.exe"
            make_test_pe(source)
            image = calendar.PEImage(bytearray(source.read_bytes()))
            image.write(calendar.CORE_YEAR_PATCHES[0].instruction_va, b"\x90" * 5)
            source.write_bytes(bytes(image.blob))

            with self.assertRaisesRegex(calendar.PatchError, "unsupported EXE"):
                calendar.patch_calendar(source, output, 2015, strict_profile=False)

    def test_refuses_to_overwrite_or_patch_input_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            source = tmp_path / "source.exe"
            make_test_pe(source)

            with self.assertRaisesRegex(calendar.PatchError, "input and output must differ"):
                calendar.patch_calendar(source, source, 2015)
            output = tmp_path / "already.exe"
            output.write_bytes(b"keep")
            with self.assertRaisesRegex(calendar.PatchError, "refusing to overwrite"):
                calendar.patch_calendar(source, output, 2015)

    def test_production_profile_requires_the_known_input_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.exe"
            output = Path(directory) / "patched.exe"
            make_test_pe(source)

            with self.assertRaisesRegex(calendar.PatchError, "SHA-256"):
                calendar.patch_calendar(source, output, 2015)
