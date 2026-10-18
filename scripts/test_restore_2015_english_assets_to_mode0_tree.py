"""Tests for identity-safe English asset carrier mapping."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.restore_2015_english_assets_to_mode0_tree import _identity


def test_identity_uses_club_and_player_not_carrier() -> None:
    assert _identity({"club": " Stoke  City ", "name": " Jack  Butland ", "record_id": 1}) == ("Stoke City", "Jack Butland")
