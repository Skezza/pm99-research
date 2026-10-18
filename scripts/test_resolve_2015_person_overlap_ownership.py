"""Tests for strict 2015 opening-date ownership decisions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.resolve_2015_person_overlap_ownership import OPENING_OWNER, build


def test_every_reviewed_overlap_retains_one_and_preserves_the_other() -> None:
    overlaps = []
    for index, (name, owner) in enumerate(OPENING_OWNER.items()):
        other = owner + 100000
        overlaps.append({"strict_identity": {"normalised_name": name, "birth_date": "1990-01-01", "nationality": "TST"}, "candidates": [
            {"team_carrier_id": owner, "slot_index": 1, "player_carrier_id": index * 2 + 1, "club_name": "Owner", "source_player_name": name, "source_selector": {"source_path": "owner"}},
            {"team_carrier_id": other, "slot_index": 2, "player_carrier_id": index * 2 + 2, "club_name": "Other", "source_player_name": name, "source_selector": {"source_path": "other"}},
        ]})
    result = build({"overlaps": overlaps})
    assert result["coverage"] == {"decision_count": 36, "retained_identity_count": 36, "displaced_slot_count": 36}
    assert all(row["displaced"][0]["disposition"] == "preserve-native-carrier-row" for row in result["decisions"])
