#!/usr/bin/env python3
"""Unit test: verify name-end marker and decoded metadata for Hierro."""

from app.io import FDIFile

def test_hierro_name_end_and_metadata(players_fdi_path):
    fdi = FDIFile(players_fdi_path)
    fdi.load()

    matches = fdi.find_by_name("Hierro")
    assert matches, "Hierro not found in database"

    hierro = matches[0]
    raw = getattr(hierro, "raw_data", None)
    assert raw is not None and len(raw) > 0

    name_end = None
    for i in range(20, min(60, len(raw) - 20)):
        if i + 3 < len(raw) and raw[i:i+4] == bytes([0x61, 0x61, 0x61, 0x61]):
            name_end = i
            break

    assert name_end is not None, "Name-end marker 'aaaa' not found in Hierro raw_data"

    pos_dec = raw[name_end + 7] ^ 0x61 if (name_end + 7) < len(raw) else None
    nat_dec = raw[name_end + 8] ^ 0x61 if (name_end + 8) < len(raw) else None
    day_dec = raw[name_end + 9] ^ 0x61 if (name_end + 9) < len(raw) else None
    month_dec = raw[name_end + 10] ^ 0x61 if (name_end + 10) < len(raw) else None
    height_dec = raw[name_end + 13] ^ 0x61 if (name_end + 13) < len(raw) else None

    assert pos_dec is not None and 0 <= pos_dec <= 3
    assert nat_dec is not None and 0 <= nat_dec <= 255
    assert day_dec is not None and 1 <= day_dec <= 31
    assert month_dec is not None and 1 <= month_dec <= 12
    assert height_dec is not None and 50 <= height_dec <= 250
