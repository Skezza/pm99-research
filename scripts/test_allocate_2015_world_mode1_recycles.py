from __future__ import annotations

import json

from scripts.allocate_2015_world_mode1_recycles import allocate
from scripts.test_season_package_compiler_v2 import _indexed_fdi


def _write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_allocates_distinct_role_compatible_sources_and_clone_ids(tmp_path):
    jug = tmp_path / "JUG98030.FDI"
    jug.write_bytes(_indexed_fdi([(1, "", b"one"), (50, "", b"fifty")]))
    capacity = _write(tmp_path / "capacity.json", {
        "eligible_mode0_dd6361_sources_by_primary_role": {
            "0": [
                {"carrier_id": 10, "mode0_team_carrier_id": 300, "baseline_name": "A", "role_candidates": [0]},
                {"carrier_id": 11, "mode0_team_carrier_id": 301, "baseline_name": "B", "role_candidates": [0, 9]},
            ]
        }
    })
    demand = _write(tmp_path / "demand.json", {
        "runtime_unqualified_required_role_codes": [],
        "recycle_demand_count": 2,
        "unresolved_duplicate_slot_count": 1,
        "demands": [
            {"recycle_team_carrier_id": 2, "slot_index": 0, "historical_player_name": "P1", "player_carrier_id": 1, "required_primary_fine_role_code": 0},
            {"recycle_team_carrier_id": 3, "slot_index": 1, "historical_player_name": "P2", "player_carrier_id": 2, "required_primary_fine_role_code": 0},
        ],
    })

    result = allocate(capacity_path=capacity, demand_path=demand, jug_path=jug)

    assert result["allocation_count"] == 2
    assert [row["new_foreign_player_carrier_id"] for row in result["allocations"]] == [10, 11]
    assert [row["appended_mode0_clone_carrier_id"] for row in result["allocations"]] == [51, 52]
    assert result["unallocated_duplicate_slot_count"] == 1
