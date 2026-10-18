from __future__ import annotations

import json

from scripts.audit_2015_world_recycle_role_demand import audit


def _write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_demand_uses_only_non_retained_owner_and_checks_actual_role(tmp_path):
    registry = _write(tmp_path / "registry.json", {"carriers": [
        {"carrier_id": 1, "roster_slots": [{"player_carrier_id": 10}]},
        {"carrier_id": 2, "roster_slots": [{"player_carrier_id": 10}]},
    ]})
    plan = _write(tmp_path / "plan.json", {"carrier_plans": [
        {"carrier_id": 1, "rows": [{"slot_index": 0, "player_carrier_id": 10, "source_player": {"name": "Keeper A", "position": "G"}}]},
        {"carrier_id": 2, "rows": [{"slot_index": 0, "player_carrier_id": 10, "source_player": {"name": "Forward B", "position": "F"}}]},
    ]})
    capacity = _write(tmp_path / "capacity.json", {
        "runtime_qualified_primary_fine_role_codes": [0, 12],
        "duplicate_slots": [{"shared_compact_carrier_id": 10, "recycle_required_for_mode1_team_carrier_ids": [2]}],
    })

    result = audit(registry_path=registry, player_plan_path=plan, capacity_path=capacity)

    assert result["recycle_demand_count"] == 1
    assert result["required_role_counts"] == {"12": 1}
    assert result["demands"][0]["historical_player_name"] == "Forward B"
    assert result["runtime_unqualified_required_role_codes"] == []
    assert result["unresolved_duplicate_slot_count"] == 0
    assert result["result"] == "pass-for-selected-carriers"


def test_unselected_duplicate_slot_stays_explicit(tmp_path):
    registry = _write(tmp_path / "registry.json", {"carriers": [
        {"carrier_id": 1, "roster_slots": [{"player_carrier_id": 10}]},
        {"carrier_id": 2, "roster_slots": [{"player_carrier_id": 10}]},
    ]})
    plan = _write(tmp_path / "plan.json", {"carrier_plans": [
        {"carrier_id": 1, "rows": [{"slot_index": 0, "player_carrier_id": 10, "source_player": {"name": "Keeper A", "position": "G"}}]},
    ]})
    capacity = _write(tmp_path / "capacity.json", {
        "runtime_qualified_primary_fine_role_codes": [0],
        "duplicate_slots": [{"shared_compact_carrier_id": 10, "recycle_required_for_mode1_team_carrier_ids": [2]}],
    })

    result = audit(registry_path=registry, player_plan_path=plan, capacity_path=capacity)

    assert result["recycle_demand_count"] == 0
    assert result["unresolved_duplicate_slot_count"] == 1
    assert result["result"] == "pass-for-selected-carriers"
