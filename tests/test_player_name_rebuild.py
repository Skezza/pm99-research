#!/usr/bin/env python3
"""Regression tests for rebuilding player name regions during renames."""

from app.models import PlayerRecord
from app.xor import decode_entry


def test_player_name_growth_preserves_metadata_and_attributes():
    """Renaming a player to a longer name should keep metadata intact and remain parseable."""

    base = PlayerRecord(
        given_name="Mikel",
        surname="Lasa",
        team_id=42,
        squad_number=7,
        nationality=34,
        position_primary=1,
        birth_day=9,
        birth_month=9,
        birth_year=1971,
        height=178,
        skills=[80, 75, 70, 65, 60, 55, 50, 45, 40, 35],
        version=700,
    )

    # Build an encoded record, decode to raw payload, then reparse to simulate loader behaviour.
    encoded = base.to_bytes()
    decoded_payload, _ = decode_entry(encoded, 0)
    original = PlayerRecord.from_bytes(decoded_payload, 0, 700)

    original.set_position(1)
    original.set_nationality(97)
    original.set_dob(9, 9, 1971)
    original.set_height(178)
    baseline_skills = [80, 75, 70, 65, 60, 55, 50, 45, 40, 35]
    for idx, value in enumerate(baseline_skills):
        original.set_attribute(idx, value)

    orig_meta = (
        original.position_primary,
        original.nationality,
        original.birth_day,
        original.birth_month,
        original.birth_year,
        original.height,
        list(original.skills[:10]),
    )

    # Rename to a longer first name (Mikel -> Manuel) which requires rebuilding the name region.
    original.set_name("Manuel Lasa")

    updated_payload = original.to_bytes()
    reparsed = PlayerRecord.from_bytes(updated_payload, 0, 700)

    assert "Manuel Lasa" in updated_payload.decode("latin-1")
    assert reparsed.given_name.upper() == "MANUEL"
    assert reparsed.surname.upper() == "LASA"

    # Metadata and attributes must remain identical after the rename.
    assert (
        reparsed.position_primary,
        reparsed.nationality,
        reparsed.birth_day,
        reparsed.birth_month,
        reparsed.birth_year,
        reparsed.height,
        list(reparsed.skills[:10]),
    ) == orig_meta
