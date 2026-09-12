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


def test_pinned_transfermarkt_snapshot_is_a_dated_manager_source() -> None:
    package = {
        "managers": [],
        "clubs": [{"carrier_id": 7, "manager_id": "manager-7"}],
    }
    source = {
        "schema_version": allocation.TRANSFERMARKT_SNAPSHOT_HISTORY_SCHEMA,
        "rows": [{"carrier_id": 7, "manager_name": "Historical Manager"}],
    }

    result = allocation._foreign_manager_sources(package, [source])

    assert result == {
        7: {
            "status": "dated-transfermarkt-pinned-2015-squad-manager-history-source",
            "name": "Historical Manager",
        }
    }


def test_exact_search_transfermarkt_snapshot_is_a_dated_manager_source() -> None:
    package = {"managers": [], "clubs": [{"carrier_id": 7, "manager_id": "manager-7"}]}
    source = {
        "schema_version": allocation.TRANSFERMARKT_EXACT_SEARCH_HISTORY_SCHEMA,
        "rows": [{"carrier_id": 7, "manager_name": "Historical Manager"}],
    }

    result = allocation._foreign_manager_sources(package, [source])

    assert result[7]["status"] == "dated-transfermarkt-exact-search-manager-history-source"


def test_source_tail_manager_history_is_a_dated_manager_source() -> None:
    package = {"managers": [], "clubs": [{"carrier_id": 706, "manager_id": "manager-706"}]}
    source = {
        "schema_version": allocation.SOURCE_TAIL_MANAGER_HISTORY_SCHEMA,
        "rows": [{"carrier_id": 706, "manager_name": "Historical Manager"}],
    }

    result = allocation._foreign_manager_sources(package, [source])

    assert result[706] == {
        "status": "dated-transfermarkt-source-tail-manager-history-source",
        "name": "Historical Manager",
    }
