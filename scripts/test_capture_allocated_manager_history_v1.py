"""Tests for fixed-carrier manager-history capture."""

from __future__ import annotations

from pathlib import Path

from scripts import capture_allocated_manager_history_v1 as allocated


def test_capture_scopes_manager_history_to_the_current_fixed_carrier(monkeypatch, tmp_path: Path) -> None:
    selector = {"country_catalog": "eng", "competition_catalog": "prem", "club_name": "Example Town"}
    ref = allocated.opening.TeamRef("Example Town", "Example Town", 42, "/example/startseite/verein/42", "test")
    monkeypatch.setattr(allocated.opening, "_competition_teams", lambda **_kwargs: [ref])
    monkeypatch.setattr(allocated.opening, "_first_fixture", lambda *_args, **_kwargs: {"date": "2000-08-12"})
    monkeypatch.setattr(allocated.history, "manager_at_date", lambda *_args: ("Historical Manager", "99"))

    class Cache:
        used = {"manager-history/42.html": {"sha256": "a" * 64, "url": "https://example.test"}}

        def get(self, *_args):
            return b"manager history"

    result = allocated.capture(
        source_capture={"clubs": [selector]}, source_capture_sha256="source-sha",
        allocation={
            "schema_version": allocated.ALLOCATION_SCHEMA,
            "season": {"start_year": 2000},
            "assignments": [{"carrier_id": 7, "club_name": "Example Town", "source_selector": selector}],
        }, allocation_sha256="allocation-sha",
        competition_map={("eng", "prem"): "GB1"}, competition_map_sha256="map-sha",
        aliases={}, aliases_sha256=None, cache=Cache(),
    )

    assert result["summary"] == {
        "allocated_carrier_count": 1,
        "retained_known_manager_count": 0,
        "manager_capture_candidate_count": 1,
        "supplemented_manager_count": 1,
        "unresolved_manager_count": 0,
    }
    assert result["managers"][0]["manager_name"] == "Historical Manager"


def test_capture_keeps_valid_known_manager_without_refetching(monkeypatch, tmp_path: Path) -> None:
    selector = {"country_catalog": "eng", "competition_catalog": "prem", "club_name": "Example Town"}

    class Cache:
        used = {}

        def get(self, *_args):
            raise AssertionError("a retained manager must not be fetched")

    result = allocated.capture(
        source_capture={"clubs": [selector]}, source_capture_sha256="source-sha",
        allocation={
            "schema_version": allocated.ALLOCATION_SCHEMA,
            "season": {"start_year": 2000},
            "assignments": [{"carrier_id": 7, "club_name": "Example Town", "source_selector": selector}],
        }, allocation_sha256="allocation-sha",
        competition_map={("eng", "prem"): "GB1"}, competition_map_sha256="map-sha",
        aliases={}, aliases_sha256=None, cache=Cache(),
        known_manager_ledger={
            "sources": {"squad_source_capture_sha256": "source-sha"},
            "managers": [{
                "source_selector": selector,
                "manager_name": "Existing Manager",
                "opening_fixture_date": "2000-08-12",
                "evidence": {"source_url": "https://example.test", "source_snapshot_sha256": "b" * 64},
            }],
        }, known_manager_ledger_sha256="ledger-sha",
    )

    assert result["summary"] == {
        "allocated_carrier_count": 1,
        "retained_known_manager_count": 1,
        "manager_capture_candidate_count": 0,
        "supplemented_manager_count": 0,
        "unresolved_manager_count": 0,
    }


def test_capture_uses_frozen_historic_source_path_without_competition_map(monkeypatch, tmp_path: Path) -> None:
    selector = {"country_catalog": "albania", "competition_catalog": "superiore", "club_name": "Example Town"}
    monkeypatch.setattr(allocated.opening, "_first_fixture", lambda *_args, **_kwargs: {"date": "2000-08-12"})
    monkeypatch.setattr(allocated.history, "manager_at_date", lambda *_args: ("Historical Manager", "99"))

    class Cache:
        used = {"manager-history/42.html": {"sha256": "a" * 64, "url": "https://example.test"}}

        def get(self, *_args):
            return b"manager history"

    result = allocated.capture(
        source_capture={"clubs": [{**selector, "source_path": "squad/2000/ALB1/42.html"}]}, source_capture_sha256="source-sha",
        allocation={
            "schema_version": allocated.ALLOCATION_SCHEMA,
            "season": {"start_year": 2000},
            "assignments": [{"carrier_id": 7, "club_name": "Example Town", "source_selector": selector}],
        }, allocation_sha256="allocation-sha",
        competition_map={}, competition_map_sha256="map-sha", aliases={}, aliases_sha256=None, cache=Cache(),
    )

    assert result["summary"]["supplemented_manager_count"] == 1
    assert "frozen-historic-source-path" in result["managers"][0]["reason"]


def test_capture_retries_only_explicit_hash_bound_prior_gaps(monkeypatch) -> None:
    wanted = {"country_catalog": "eng", "competition_catalog": "prem", "club_name": "Wanted Town"}
    untouched = {"country_catalog": "eng", "competition_catalog": "prem", "club_name": "Untouched Town"}
    ref = allocated.opening.TeamRef("Wanted Town", "Wanted Town", 42, "/wanted/startseite/verein/42", "test")
    monkeypatch.setattr(allocated.opening, "_competition_teams", lambda **_kwargs: [ref])
    monkeypatch.setattr(allocated.opening, "_first_fixture", lambda *_args, **_kwargs: {"date": "2000-08-12"})
    monkeypatch.setattr(allocated.history, "manager_at_date", lambda *_args: ("Historical Manager", "99"))

    class Cache:
        used = {"manager-history/42.html": {"sha256": "a" * 64, "url": "https://example.test"}}

        def get(self, *_args):
            return b"manager history"

    allocation = {
        "schema_version": allocated.ALLOCATION_SCHEMA,
        "season": {"start_year": 2000},
        "assignments": [
            {"carrier_id": 7, "club_name": "Wanted Town", "source_selector": wanted},
            {"carrier_id": 8, "club_name": "Untouched Town", "source_selector": untouched},
        ],
    }
    result = allocated.capture(
        source_capture={"clubs": [wanted, untouched]}, source_capture_sha256="source-sha",
        allocation=allocation, allocation_sha256="allocation-sha",
        competition_map={("eng", "prem"): "GB1"}, competition_map_sha256="map-sha",
        aliases={}, aliases_sha256=None, cache=Cache(),
        gap_scope_supplement={
            "schema_version": allocated.SCHEMA,
            "sources": {"full_source_capture_sha256": "source-sha", "carrier_allocation_sha256": "allocation-sha"},
            "gaps": [{"source_selector": wanted, "carrier_id": 7, "reason": "prior gap"}],
        }, gap_scope_supplement_sha256="prior-gap-sha",
    )

    assert result["summary"] == {
        "allocated_carrier_count": 1,
        "retained_known_manager_count": 0,
        "manager_capture_candidate_count": 1,
        "supplemented_manager_count": 1,
        "unresolved_manager_count": 0,
    }
    assert result["sources"]["gap_scope_supplement_sha256"] == "prior-gap-sha"
