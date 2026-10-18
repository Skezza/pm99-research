"""Tests for the bounded opening-date replacement-source audit."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_opening_date_replacement_sources_v1 import build_readiness
from scripts.reconcile_opening_date_identities_v1 import RESOLVED_SCHEMA


def test_only_fixture_proven_absent_identity_becomes_a_candidate() -> None:
    package = {
        "package_id": "pm99-2015-16-fixture",
        "clubs": [
            {"id": "club-a", "name": "Club A", "full_name": "Club A"},
            {"id": "club-b", "name": "Club B", "full_name": "Club B"},
        ],
        "players": [
            {"id": "player-existing", "carrier_id": 1, "club_id": "club-a", "name": "Bartosz Bialkowski"},
            {"id": "player-out-a", "carrier_id": 2, "club_id": "club-a", "name": "Outgoing A"},
            {"id": "player-out-b", "carrier_id": 3, "club_id": "club-b", "name": "Outgoing B"},
        ],
    }
    resolution = {
        "schema_version": RESOLVED_SCHEMA,
        "package_id": "pm99-2015-16-fixture",
        "rows": [{
            "id": "candidate-001",
            "resolution": {"replace_player_ids": ["player-out-a", "player-out-b"]},
        }],
    }
    opening = {
        "schema_version": "pm99-2015-16-opening-lineup-reconciliation-v1",
        "failures": [],
        "clubs": [
            {"club": "Club A", "reconciled": True, "starting_xi": [{"source_name": "Bartosz Białkowski"}], "substitutes": []},
            {"club": "Club B", "reconciled": True, "starting_xi": [{"source_name": "New Player", "shirt_number": 19, "source_url": "https://example.invalid/new"}], "substitutes": []},
        ],
    }
    source_ledger = {
        "clubs": [
            {"club": "Club A", "players": [{"name": "Bartosz Białkowski"}]},
            {"club": "Club B", "players": [{
                "name": "New Player", "birth_date_ddmmyy": "01-01-90", "nationality": "ENG",
                "position": "M", "height_cm": 180, "weight_kg": 75,
            }]},
        ],
    }

    receipt = build_readiness(package, resolution, opening, source_ledger)

    assert receipt["summary"] == {
        "replacement_carriers_required": 2,
        "slots_with_retained_first_fixture_identity_candidates": 1,
        "unique_retained_first_fixture_identity_candidates": 1,
        "slots_needing_dated_opening_roster_source": 1,
        "strict_native_rebuild_ready": False,
    }
    by_id = {row["replacement_player_id"]: row for row in receipt["rows"]}
    assert by_id["player-out-a"]["opening_fixture_identity_candidates"] == []
    assert by_id["player-out-b"]["opening_fixture_identity_candidates"] == [{
        "name": "New Player", "source_name": "New Player", "birth_date_ddmmyy": "01-01-90",
        "nationality": "ENG", "position": "M", "height_cm": 180, "weight_kg": 75,
        "shirt_number": 19, "first_fixture_source_url": "https://example.invalid/new",
    }]
