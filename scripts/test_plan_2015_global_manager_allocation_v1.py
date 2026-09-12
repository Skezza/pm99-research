from __future__ import annotations

from scripts import plan_2015_global_manager_allocation_v1 as allocation


def test_shared_manager_keeps_english_mode_zero_and_relinks_foreign() -> None:
    teams = {
        10: {"baseline_manager_carrier_id": 50, "record_mode": 1},
        20: {"baseline_manager_carrier_id": 50, "record_mode": 0},
        30: {"baseline_manager_carrier_id": 60, "record_mode": 1},
    }

    result, displaced = allocation._allocate(teams, [50, 60, 70, 80])

    assert result == {10: 70, 20: 50, 30: 60}
    assert displaced == {50: [10]}


def test_fails_when_the_clean_base_has_insufficient_unlinked_manager_records() -> None:
    teams = {
        10: {"baseline_manager_carrier_id": 50, "record_mode": 1},
        20: {"baseline_manager_carrier_id": 50, "record_mode": 0},
    }

    try:
        allocation._allocate(teams, [50])
    except allocation.AllocationError as error:
        assert "lacks enough unlinked" in str(error)
    else:
        raise AssertionError("expected allocation to fail")
