"""Synthetic safety tests for the native no-photo asset stage."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import encode_obfuscated_bitmap_name  # noqa: E402
from scripts.materialise_native_no_photo_v2 import _active_offsets_for_player  # noqa: E402


def test_active_offsets_match_only_exact_player_filename() -> None:
    archive = bytearray(b"\x00" * 120)
    archive[7] = 0x02
    archive[8:28] = encode_obfuscated_bitmap_name("J9600042.BMP")
    archive[50] = 0x02
    archive[51:71] = encode_obfuscated_bitmap_name("J9600043.BMP")
    assert _active_offsets_for_player(archive, 42) == [7]
    archive[7] = 0
    assert _active_offsets_for_player(archive, 42) == []
