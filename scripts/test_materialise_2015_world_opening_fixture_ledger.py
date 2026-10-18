from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import materialise_2015_world_opening_fixture_ledger as materialise  # noqa: E402
from scripts import world_fixed_carrier_ledger_v2 as ledger  # noqa: E402


HASH = "a" * 64


def _registry() -> dict[str, object]:
    return {
        "schema_version": ledger.REGISTRY_SCHEMA,
        "registry_id": "synthetic-world-fixed-carriers",
        "baseline": {"database_files": {
            name: {"relative_path": f"DBDAT/{name}", "sha256": HASH, "size": 100}
            for name in ("ENT98030.FDI", "EQ98030.FDI", "JUG98030.FDI")
        }},
        "topology_policy": "preserve-existing-carriers-no-country-division-or-membership-claims",
        "carriers": [{
            "carrier_id": 1, "record_mode": 1,
            "baseline_club": {"name": "Baseline", "full_name": "Baseline FC", "ground_name": "Baseline Ground", "seated_capacity": 1, "active_manager_carrier_id": 10},
            "roster_slots": [{"slot_index": 0, "player_carrier_id": 100, "flag": 0, "family": "dd6360", "baseline_name": "Baseline Player"}],
            "topology_policy": "preserve-existing-carrier-and-roster-slots",
        }],
        "known_baseline_duplicate_player_carriers": [],
    }


def _inputs(*, include_ratings: bool = True) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    registry = _registry()
    base = ledger.initialise_ledger(registry=registry, ledger_id="world-2015-16", start_year=2015)
    values = {
        "rating": 70, "sprint_speed": 71, "stamina": 72, "aggression": 73, "short_pass": 74,
        "stand_tackle": 75, "heading": 76, "finishing": 77, "dribbling": 78, "gk_handling": 10,
    } if include_ratings else {}
    reconciliation = {
        "schema_version": materialise.RECONCILIATION_SCHEMA,
        "carrier_plans": [{"carrier_id": 1, "rows": [{
            "slot_index": 0, "player_carrier_id": 100, "source_squad_index": 4,
            "source_player": {"name": "José Fixture", "birth_date": "1990-01-02", "nationality": "ESP", "height_cm": 180, "weight_kg": 75, "position": "M"},
            "fifa16": {"fifa16_player_id": 55, "fifa16_values": values},
        }]}],
    }
    join = {
        "schema_version": materialise.JOIN_SCHEMA,
        "sources": {
            "footballsquads_capture_sha256": "b" * 64,
            "strict_player_reconciliation_sha256": hashlib.sha256(materialise.canonical_json_bytes(reconciliation)).hexdigest(),
            "transfermarkt_opening_fixture_receipt_sha256": "c" * 64,
        },
        "coverage": {"lineup_player_reconciliation_status_counts": {"strict-normalised-source-name-unique": 1}},
        "clubs": [{
            "transfermarkt_source_club": {"id": 5, "name": "Fixture FC"},
            "strict_club_identity": {"status": "strict-footballsquads-club-identity-match"},
            "source_draft_reference": {"status": "source-draft-and-strict-player-reconciliation-linked", "draft_carrier_id": 1},
            "opening_fixture_facts": {
                "source_status": "source-qualified", "declared_manager": "Fixture Manager",
                "starting_lineup": [{"name": "Jose Fixture", "shirt_number": "8", "player_reconciliation": {
                    "status": "strict-normalised-source-name-unique", "player_reconciliation_row": {"slot_index": 0, "player_carrier_id": 100},
                }}],
                "substitutes": [],
            },
        }],
    }
    return registry, base, join, reconciliation


def test_materialisation_creates_valid_blocked_ledger_rows_only() -> None:
    registry, base, join, reconciliation = _inputs()
    output, report = materialise.build_materialised_ledger(
        registry=registry, base_ledger=base, source_join=join, reconciliation=reconciliation
    )

    ledger.validate_ledger(registry=registry, ledger=output)
    update = output["carrier_updates"][0]
    assert update["status"] == "blocked"
    assert update["manager"]["name"] == "Fixture Manager"
    assert update["club"]["ground_name"] == "Unresolved 2015 ground"
    assert update["club"]["seated_capacity"] == 0
    assert update["players"][0]["facts"]["shirt_number"] == 8
    assert update["players"][0]["portrait"] == {"status": "unresolved"}
    assert report["coverage"]["ledger_ready_fixed_slot_count"] == 1
    assert "not write authorisations" in report["write_policy"]


def test_materialisation_defers_a_strict_player_without_complete_ratings() -> None:
    registry, base, join, reconciliation = _inputs(include_ratings=False)
    output, report = materialise.build_materialised_ledger(
        registry=registry, base_ledger=base, source_join=join, reconciliation=reconciliation
    )

    assert output["carrier_updates"][0]["players"] == []
    assert report["deferred_player_rows_by_reason"] == {"missing-complete-fifa16-rating-candidate": 1}


def test_materialisation_rejects_a_join_with_another_reconciliation_hash() -> None:
    registry, base, join, reconciliation = _inputs()
    join["sources"]["strict_player_reconciliation_sha256"] = "f" * 64
    with pytest.raises(materialise.MaterialisationError, match="not bound"):
        materialise.build_materialised_ledger(
            registry=registry, base_ledger=base, source_join=join, reconciliation=reconciliation
        )
