#!/usr/bin/env python3
"""Unit test for PlayerRecord serialization round-trip (converted from script)."""

from app.io import FDIFile
from app.models import PlayerRecord

def test_hierro_serialization_roundtrip(players_fdi_path):
    """Load the FDI fixture, find 'Hierro', serialize and re-parse, assert key fields preserved."""
    fdi = FDIFile(players_fdi_path)
    fdi.load()

    matches = fdi.find_by_name("Hierro")
    assert matches, "Hierro not found in database"

    hierro = matches[0]

    # Serialize (to_bytes returns decoded payload according to current contract)
    serialized = hierro.to_bytes()
    assert isinstance(serialized, (bytes, bytearray)) and len(serialized) > 0

    # Re-parse using the package parser (expects decoded payload)
    reparsed = PlayerRecord.from_bytes(serialized, 0, 700)

    # Assert important metadata fields round-trip unchanged
    assert hierro.position_primary == reparsed.position_primary
    assert hierro.nationality == reparsed.nationality
    assert hierro.birth_day == reparsed.birth_day
    assert hierro.birth_month == reparsed.birth_month
    assert hierro.birth_year == reparsed.birth_year
    assert hierro.height == reparsed.height

    # Optionally assert sizes are consistent (decoded payload length preserved)
    if getattr(hierro, "raw_data", None) is not None:
        assert len(serialized) == len(hierro.raw_data)
