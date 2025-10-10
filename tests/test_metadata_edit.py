#!/usr/bin/env python3
"""Unit test for metadata field editing (position, nationality, DOB, height, attributes)."""

from pm99_editor.io import FDIFile
from pm99_editor.models import PlayerRecord

def test_metadata_edit_roundtrip(players_fdi_path):
    """Load the FDI fixture, find 'Hierro', modify metadata, serialize and re-parse, assert changes persisted."""
    fdi = FDIFile(players_fdi_path)
    fdi.load()

    matches = fdi.find_by_name("Hierro")
    assert matches, "Hierro not found in database"

    hierro = matches[0]

    # Modify fields
    hierro.position_primary = 1  # Defender
    hierro.nationality = 10
    hierro.birth_day = 23
    hierro.birth_month = 3
    hierro.birth_year = 1968
    hierro.height = 183
    hierro.skills[0] = 95
    hierro.skills[1] = 90

    # Serialize and re-parse
    serialized = hierro.to_bytes()
    assert isinstance(serialized, (bytes, bytearray)) and len(serialized) > 0

    reparsed = PlayerRecord.from_bytes(serialized, 0, 700)

    # Assert important metadata fields persisted
    assert reparsed.position_primary == 1
    assert reparsed.nationality == 10
    assert (reparsed.birth_day, reparsed.birth_month, reparsed.birth_year) == (23, 3, 1968)
    assert reparsed.height == 183
    assert reparsed.skills[0] == 95
    assert reparsed.skills[1] == 90