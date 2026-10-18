from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import materialise_opening_manager_ledger_v1 as ledger


def _source(*names: str) -> dict:
    return {"clubs": [{"country_catalog": "eng", "competition_catalog": "prem", "club_name": name} for name in names]}


def _lineup(manager: str | None = "Opening Manager") -> dict:
    return {
        "schema_version": ledger.LINEUP_SCHEMA,
        "season_start_year": 2000,
        "source": {"cache_files": [{"url": "https://example.test/report/1", "cache_path": "report/1.html", "sha256": "a" * 64}]},
        "clubs": [{
            "source_selector": {"country_catalog": "eng", "competition_catalog": "prem", "club_name": "Example"},
            "first_league_fixture_date": "2000-08-12", "declared_manager": manager,
            "lineup_source_url": "https://example.test/report/1", "source_match_id": "1",
        }],
    }


def test_materialises_hash_bound_match_report_manager_and_explicit_missing_club() -> None:
    result = ledger.materialise(
        source_capture=_source("Example", "Missing"), source_capture_sha256="b" * 64,
        lineup=_lineup(), lineup_sha256="c" * 64,
    )
    assert result["summary"] == {
        "source_club_count": 2, "resolved_manager_count": 1, "unresolved_manager_count": 1,
        "resolution_method_counts": {"first-league-match-report-declared-manager": 1},
    }
    assert result["managers"][0]["manager_name"] == "Opening Manager"
    assert result["managers"][0]["evidence"]["source_snapshot_sha256"] == "a" * 64
    assert result["gaps"][0]["reason"] == "no-first-league-match-report-capture"


def test_dated_supplement_resolves_missing_published_manager_without_native_fallback() -> None:
    supplement = {
        "schema_version": ledger.SUPPLEMENT_SCHEMA, "season_start_year": 2000,
        "managers": [{
            "source_selector": {"country_catalog": "eng", "competition_catalog": "prem", "club_name": "Example"},
            "opening_fixture_date": "2000-08-12", "manager_name": "Supplemented Manager",
            "source_name": "Archived season report", "source_url": "https://example.test/season",
            "source_snapshot_sha256": "d" * 64, "reason": "match report omitted its manager field",
        }],
    }
    result = ledger.materialise(
        source_capture=_source("Example"), source_capture_sha256="b" * 64,
        lineup=_lineup(None), lineup_sha256="c" * 64,
        supplement=supplement, supplement_sha256="e" * 64,
    )
    assert result["summary"]["unresolved_manager_count"] == 0
    assert result["managers"][0]["manager_name"] == "Supplemented Manager"
    assert result["managers"][0]["resolution_method"] == "dated-source-supplement"


def test_rejects_supplement_without_real_snapshot_hash() -> None:
    supplement = {
        "schema_version": ledger.SUPPLEMENT_SCHEMA, "season_start_year": 2000,
        "managers": [{
            "source_selector": {"country_catalog": "eng", "competition_catalog": "prem", "club_name": "Example"},
            "opening_fixture_date": "2000-08-12", "manager_name": "Manager", "source_name": "Source",
            "source_url": "https://example.test/source", "source_snapshot_sha256": "not-a-hash", "reason": "omitted",
        }],
    }
    with pytest.raises(ledger.ManagerLedgerError, match="invalid source snapshot hash"):
        ledger.materialise(
            source_capture=_source("Example"), source_capture_sha256="b" * 64,
            lineup=_lineup(None), lineup_sha256="c" * 64, supplement=supplement, supplement_sha256="e" * 64,
        )


def test_rejects_manager_report_without_matching_cache_receipt() -> None:
    lineup = _lineup()
    lineup["source"]["cache_files"] = []
    with pytest.raises(ledger.ManagerLedgerError, match="no cache receipt"):
        ledger.materialise(
            source_capture=_source("Example"), source_capture_sha256="b" * 64,
            lineup=lineup, lineup_sha256="c" * 64,
        )


def test_rejects_supplement_for_already_resolved_match_report() -> None:
    supplement = {
        "schema_version": ledger.SUPPLEMENT_SCHEMA, "season_start_year": 2000,
        "managers": [{
            "source_selector": {"country_catalog": "eng", "competition_catalog": "prem", "club_name": "Example"},
            "opening_fixture_date": "2000-08-12", "manager_name": "Conflicting Manager",
            "source_name": "Second source", "source_url": "https://example.test/second",
            "source_snapshot_sha256": "d" * 64, "reason": "unnecessary override",
        }],
    }
    with pytest.raises(ledger.ManagerLedgerError, match="duplicates published"):
        ledger.materialise(
            source_capture=_source("Example"), source_capture_sha256="b" * 64,
            lineup=_lineup(), lineup_sha256="c" * 64,
            supplement=supplement, supplement_sha256="e" * 64,
        )
