"""Tests for exact-historic-ID fixed-carrier opening-lineup capture."""

from __future__ import annotations

from scripts import capture_allocated_opening_lineups_v1 as allocated


def test_capture_uses_only_missing_allocated_clubs_with_frozen_historic_ids(monkeypatch) -> None:
    selector = {"country_catalog": "albania", "competition_catalog": "superiore", "club_name": "Example Town"}
    existing = {"country_catalog": "eng", "competition_catalog": "prem", "club_name": "Known Town"}
    ref = allocated.opening.TeamRef("Example Town", "Example Town", 42, "/-/startseite/verein/42", "frozen-historic-source-path")
    monkeypatch.setattr(allocated.opening, "_first_fixture", lambda *_args, **_kwargs: {"date": "2000-08-12", "match_id": "99", "report_url": "https://example.test/report", "schedule_url": "https://example.test/schedule"})
    monkeypatch.setattr(allocated.opening, "_lineup_from_report", lambda *_args, **_kwargs: {
        "source_selector": {"club_name": "Example Town", "transfermarkt_club_id": 42, "transfermarkt_club_name": "Example Town", "transfermarkt_identity_match_method": "frozen-historic-source-path"},
        "starting_xi": [], "source_status": "source-qualified",
    })

    class Cache:
        used = {}

    result = allocated.capture(
        source_capture={"clubs": [{**selector, "source_path": "squad/2000/ALB1/42.html"}, {**existing, "source_path": "squad/2000/GB1/7.html"}]},
        source_capture_sha256="source", allocation={"schema_version": allocated.ALLOCATION_SCHEMA, "season": {"start_year": 2000}, "assignments": [
            {"carrier_id": 1, "club_name": "Example Town", "source_selector": selector},
            {"carrier_id": 2, "club_name": "Known Town", "source_selector": existing},
        ]}, allocation_sha256="allocation",
        known_reconciliation={"schema_version": "pm99-transfermarkt-opening-lineup-reconciliation-v1", "sources": {"source_capture_sha256": "source"}, "clubs": [{"source_selector": existing}]},
        known_reconciliation_sha256="known", cache=Cache(),
    )

    assert result["summary"] == {
        "allocated_carrier_count": 2,
        "retained_existing_reconciliation_count": 1,
        "historic_id_capture_candidate_count": 1,
        "captured_club_count": 1,
        "failed_club_count": 0,
    }
    assert result["clubs"][0]["source_competition_code"] == "ALB1"
