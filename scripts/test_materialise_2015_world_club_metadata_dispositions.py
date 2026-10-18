"""Tests for 2015 club metadata source dispositions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.materialise_2015_world_club_metadata_dispositions import build


def test_fixture_stadium_is_not_promoted_to_permanent_capacity() -> None:
    draft = {"proposals": [{"carrier_id": 1, "status": "source-squad-ready", "source_club_name": "Club"}]}
    fixture = {"clubs": [{"source_club": {"id": 9}, "opening_fixture": {"declared_manager": "Manager", "source_url": "match"}, "first_home_fixture_ground_evidence": {"reported_stadium": "Ground", "source_url": "home"}}]}
    identity = {"mappings": [{"transfermarkt_source_club": {"id": 9}, "selected_source_draft_carrier_ids": [1]}]}
    result = build(draft=draft, fixture_receipt=fixture, identity_receipt=identity)
    row = result["rows"][0]
    assert row["manager"]["value"] == "Manager"
    assert row["stadium"]["status"] == "fixture-stadium-evidence-only"
    assert row["capacity"]["value"] is None
    assert row["capacity"]["status"].startswith("preserve-existing")
