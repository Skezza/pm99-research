from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import reconcile_transfermarkt_opening_lineups_v1 as reconcile


def test_reconcile_links_unique_xi_and_keeps_missing_fixture_players_explicit() -> None:
    source = {"clubs": [{"club_name": "Example", "country_catalog": "eng", "competition_catalog": "d1", "players": [
        {"name": f"Player {number}", "position": "M", "shirt_number": number} for number in range(1, 12)
    ]}]}
    source_sha = hashlib.sha256(json.dumps(source).encode()).hexdigest()
    lineup = {"schema_version": reconcile.LINEUP_SCHEMA, "source": {"source_capture_sha256": source_sha}, "clubs": [{
        "source_selector": {"club_name": "Example", "country_catalog": "eng", "competition_catalog": "d1"},
        "starting_xi": [{"display_name": f"Player {number}", "source_slug": f"player-{number}", "source_player_id": str(number)} for number in range(1, 12)],
        "source_blockers": [], "source_status": "source-qualified",
    }]}
    result = reconcile.reconcile(source_capture=source, lineup_capture=lineup, source_capture_sha256=source_sha, lineup_capture_sha256="b" * 64)
    assert result["summary"]["reconciled-xi-club-count"] == 1
    assert result["clubs"][0]["starting_xi"][0]["source_name"] == "Player 1"


def test_reconcile_reports_an_uncaptured_source_club() -> None:
    source = {"clubs": [{"club_name": "Example", "country_catalog": "eng", "competition_catalog": "d1", "players": []}]}
    source_sha = hashlib.sha256(json.dumps(source).encode()).hexdigest()
    lineup = {"schema_version": reconcile.LINEUP_SCHEMA, "source": {"source_capture_sha256": source_sha}, "clubs": []}
    result = reconcile.reconcile(source_capture=source, lineup_capture=lineup, source_capture_sha256=source_sha, lineup_capture_sha256="b" * 64)
    assert result["failures"][0]["reason"] == "no-first-fixture-source-capture"


def test_reconcile_uses_only_a_unique_profile_birth_date_after_name_matching_fails() -> None:
    source = {"clubs": [{"club_name": "Example", "country_catalog": "eng", "competition_catalog": "d1", "players": [
        {"name": "Jorge Paulo Costa", "birth_date": "1980-01-01", "position": "M", "shirt_number": 7},
    ]}]}
    source_sha = hashlib.sha256(json.dumps(source).encode()).hexdigest()
    lineup = {"schema_version": reconcile.LINEUP_SCHEMA, "source": {"source_capture_sha256": source_sha}, "clubs": [{
        "source_selector": {"club_name": "Example", "country_catalog": "eng", "competition_catalog": "d1"},
        "starting_xi": [{"display_name": "Jorge Silva", "source_slug": "jorge-silva", "source_player_id": "99"}],
        "source_blockers": [], "source_status": "source-qualified",
    }]}
    key = (("eng", "d1", "Example"), "99")
    result = reconcile.reconcile(
        source_capture=source, lineup_capture=lineup, source_capture_sha256=source_sha, lineup_capture_sha256="b" * 64,
        person_evidence={key: {"birth_date": "1980-01-01"}},
    )
    player = result["clubs"][0]["starting_xi"][0]
    assert player["source_name"] == "Jorge Paulo Costa"
    assert player["match_method"] == "profile-birth-date-unique"


def test_reconcile_does_not_link_unrelated_players_who_share_a_birth_date() -> None:
    source = {"clubs": [{"club_name": "Example", "country_catalog": "eng", "competition_catalog": "d1", "players": [
        {"name": "John Murphy", "birth_date": "1976-10-18", "position": "F", "shirt_number": 9},
    ]}]}
    source_sha = hashlib.sha256(json.dumps(source).encode()).hexdigest()
    lineup = {"schema_version": reconcile.LINEUP_SCHEMA, "source": {"source_capture_sha256": source_sha}, "clubs": [{
        "source_selector": {"club_name": "Example", "country_catalog": "eng", "competition_catalog": "d1"},
        "starting_xi": [{"display_name": "Brett Ormerod", "source_slug": "brett-ormerod", "source_player_id": "99"}],
        "source_blockers": [], "source_status": "source-qualified",
    }]}
    key = (("eng", "d1", "Example"), "99")

    result = reconcile.reconcile(
        source_capture=source, lineup_capture=lineup, source_capture_sha256=source_sha,
        lineup_capture_sha256="b" * 64, person_evidence={key: {"birth_date": "1976-10-18"}},
    )

    assert result["clubs"][0]["starting_xi"] == []
    assert result["clubs"][0]["unresolved_first_fixture_players"][0]["display_name"] == "Brett Ormerod"


def test_person_evidence_requires_an_iso_birth_date() -> None:
    with pytest.raises(reconcile.ReconciliationError, match="ISO"):
        reconcile._require_iso_date("04/05/1975")


def test_composed_lineup_accepts_full_source_and_exact_selection_bindings() -> None:
    source = {"clubs": []}
    source_sha = "a" * 64
    selection_sha = "b" * 64
    lineup = {
        "schema_version": reconcile.LINEUP_SCHEMA,
        "source": {
            "source_capture_sha256": source_sha,
            "lineup_source_selection_sha256": selection_sha,
        },
        "clubs": [],
    }
    result = reconcile.reconcile(
        source_capture=source,
        lineup_capture=lineup,
        source_capture_sha256=source_sha,
        lineup_capture_sha256="c" * 64,
        lineup_source_selection_sha256=selection_sha,
    )
    assert result["sources"]["lineup_source_selection_sha256"] == selection_sha


def test_composed_lineup_refuses_stale_selection_binding() -> None:
    lineup = {
        "schema_version": reconcile.LINEUP_SCHEMA,
        "source": {
            "source_capture_sha256": "a" * 64,
            "lineup_source_selection_sha256": "d" * 64,
        },
        "clubs": [],
    }
    with pytest.raises(reconcile.ReconciliationError, match="exact source selection"):
        reconcile.reconcile(
            source_capture={"clubs": []}, lineup_capture=lineup,
            source_capture_sha256="a" * 64, lineup_capture_sha256="c" * 64,
            lineup_source_selection_sha256="b" * 64,
        )
