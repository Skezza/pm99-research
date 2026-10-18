"""Tests for first-fixture duplicate-player reconciliation."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from scripts.reconcile_opening_date_identities_v1 import (
    ReconciliationError,
    _normalise,
    apply_decisions,
    build_reconciliation,
)


def _package() -> dict:
    return {
        "package_id": "pm99-2015-16-fixture",
        "clubs": [{"id": "club-a", "name": "Club A"}, {"id": "club-b", "name": "Club B"}],
        "players": [
            {"id": "player-a", "carrier_id": 1, "club_id": "club-a", "name": "Same Player", "facts": {"birth_date": "1990-01-01", "nationality": "ENG", "shirt_number": 7}},
            {"id": "player-b", "carrier_id": 2, "club_id": "club-b", "name": "Same Player", "facts": {"birth_date": "1990-01-01", "nationality": "ENG", "shirt_number": 8}},
            {"id": "player-c", "carrier_id": 3, "club_id": "club-a", "name": "Unseen Player", "facts": {"birth_date": "1991-01-01", "nationality": "ENG", "shirt_number": 9}},
            {"id": "player-d", "carrier_id": 4, "club_id": "club-b", "name": "Unseen Player", "facts": {"birth_date": "1991-01-01", "nationality": "ENG", "shirt_number": 10}},
        ],
    }


def _opening() -> dict:
    return {
        "schema_version": "pm99-2015-16-opening-lineup-reconciliation-v1",
        "failures": [],
        "clubs": [
            {"club": "Club A", "reconciled": True, "first_league_fixture_date": "08/08/2015", "starting_xi": [{"source_name": "Same Player"}], "substitutes": []},
            {"club": "Club B", "reconciled": True, "first_league_fixture_date": "08/08/2015", "starting_xi": [], "substitutes": []},
        ],
    }


def test_first_fixture_recommends_only_one_evidence_backed_owner() -> None:
    result = build_reconciliation(_package(), _opening())
    assert result["summary"] == {
        "duplicate_candidate_groups": 2,
        "first_fixture_proven_groups": 1,
        "manual_membership_groups": 1,
        "replacement_carriers_required": 1,
    }
    assert result["rows"][0]["recommendation"] == {
        "retain_player_id": "player-a", "replace_player_ids": ["player-b"],
    }
    assert result["rows"][1]["disposition"] == "manual-opening-date-membership-required"


def test_pm99_transliteration_matches_source_name_with_polish_l_stroke() -> None:
    # PM99's CP1252 package has to store Bialkowski, while a match source may
    # correctly spell Białkowski.  This must remain one identity when judging
    # whether an opening-XI player is already on a club roster.
    assert _normalise("Bartosz Białkowski") == _normalise("Bartosz Bialkowski")


def test_dated_decision_resolves_manual_candidate_and_requires_replacements() -> None:
    queue = build_reconciliation(_package(), _opening())
    decisions = {
        "schema_version": "pm99-opening-date-identity-decisions-v1",
        "reconciliation_canonical_sha256": "",
        "decisions": [{
            "id": "candidate-002",
            "action": "replace-all",
            "retain_player_id": None,
            "replace_player_ids": ["player-c", "player-d"],
            "snapshot_date": "2015-08-08",
            "reason": "The player was outside the selected English scope on the opening date.",
            "sources": [{"title": "Dated transfer record", "uri": "https://example.invalid/record"}],
        }],
    }
    from scripts import season_package_v2 as package_v2
    import hashlib

    decisions["reconciliation_canonical_sha256"] = hashlib.sha256(package_v2.canonical_json_bytes(queue)).hexdigest()
    result = apply_decisions(queue, decisions)
    assert result["summary"] == {
        "duplicate_candidate_groups": 2,
        "first_fixture_resolutions": 1,
        "dated_editorial_resolutions": 1,
        "replacement_carriers_required": 3,
        "unresolved_membership_groups": 0,
    }
    assert result["rows"][1]["resolution"]["action"] == "replace-all"


def test_dated_decision_cannot_retain_an_unrelated_carrier() -> None:
    queue = build_reconciliation(_package(), _opening())
    decisions = {
        "schema_version": "pm99-opening-date-identity-decisions-v1",
        "reconciliation_canonical_sha256": "not-a-real-hash",
        "decisions": [],
    }
    with pytest.raises(ReconciliationError, match="different reconciliation queue"):
        apply_decisions(queue, decisions)
