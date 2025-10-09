#!/usr/bin/env python3
"""Unit test: hex layout and name-end marker presence for Hierro"""

from pathlib import Path
from pm99_editor.io import FDIFile

def test_hierro_hex_and_marker():
    f = Path("DBDAT/JUG98030.FDI")
    assert f.exists(), "Test fixture missing: DBDAT/JUG98030.FDI"

    fdi = FDIFile(f)
    fdi.load()

    matches = fdi.find_by_name("Hierro")
    assert matches, "Hierro not found in database"

    hierro = matches[0]
    raw = getattr(hierro, "raw_data", None)
    assert raw is not None and len(raw) > 0

    # Verify presence of 'aaaa' marker in expected window
    name_end = None
    for i in range(20, min(60, len(raw) - 20)):
        if i + 3 < len(raw) and raw[i:i+4] == bytes([0x61, 0x61, 0x61, 0x61]):
            name_end = i
            break

    assert name_end is not None, "Name-end marker 'aaaa' not found in Hierro raw_data"

    # Basic sanity checks on metadata offsets
    pos_dec = raw[name_end+7] ^ 0x61 if (name_end+7) < len(raw) else None
    assert pos_dec is not None and 0 <= pos_dec <= 3