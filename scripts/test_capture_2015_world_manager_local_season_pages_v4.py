from __future__ import annotations

from scripts import capture_2015_world_manager_local_season_pages_v4 as capture


def test_requires_an_exact_local_club_title_inside_a_2015_season_title() -> None:
    assert capture._season_title_matches("2015–16 SK Rapid Wien season", "SK Rapid Wien")
    assert not capture._season_title_matches("2015–16 Rapid Wien II season", "SK Rapid Wien")
    assert not capture._season_title_matches("2014–15 SK Rapid Wien season", "SK Rapid Wien")


def test_rejects_a_prior_receipt_with_ambiguous_local_titles() -> None:
    row = {
        "carrier_id": 1, "source_club_name": "Example",
        "considered": [{"language": "de", "title": "Example"}, {"language": "fr", "title": "Exemple"}],
    }
    result = capture._one(row, as_of="2015-09-01T00:00:00Z", search=lambda _a, _b: [])
    assert result["status"] == "requires-review-no-single-national-club-title-from-prior-receipt"
