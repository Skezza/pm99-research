from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.prepare_2015_english92_native_manifest import (  # noqa: E402
    HIDDEN_CARRIERS_BY_DIVISION,
    build_native92_manifest,
)


def _club(club: str, division: str) -> dict[str, str]:
    return {"club": club, "division": division}


def _source() -> dict[str, object]:
    shape = {"Premier League": 20, "Championship": 24, "League One": 24, "League Two": 24}
    return {"clubs": [_club(f"{division} {index:02d}", division) for division, count in shape.items() for index in range(count)]}


def _selector_map() -> dict[str, object]:
    panels = []
    carrier = 1000
    for panel_index, panel_key in enumerate(("division_01", "division_02", "division_03", "division_04"), start=1):
        teams = []
        for row in range(1, 21):
            teams.append({"eq_record_id": carrier, "row_index": row, "team_select_x": row, "team_select_y": panel_index, "eq_short_name": f"Carrier {carrier}"})
            carrier += 1
        panels.append({"division_key": panel_key, "teams": teams})
    return {"divisions": panels}


def test_native92_assigns_every_source_club_and_marks_hidden_carriers():
    selector = _selector_map()
    # Replace the synthetic final twelve slots with the fixed hidden registry;
    # visible slots remain intentionally synthetic for this unit-level test.
    registry, ledger = build_native92_manifest(source_ledger=_source(), selector_map=selector)

    assert len(ledger["clubs"]) == 92
    assert len({club["carrier_eq_record_id"] for club in ledger["clubs"]}) == 92
    assert registry["picker_carrier_count"] == 80
    assert registry["hidden_game_used_carrier_count"] == 12
    assert registry["picker_availability_contract"] == "must-be-captured-from-the-built-database"
    hidden = [row for row in registry["assignments"] if not row["picker_visible"]]
    assert len(hidden) == 12
    assert {row["picker_visibility_basis"] for row in registry["assignments"]} == {"vanilla-1998-baseline-only"}
    assert {row["carrier_eq_record_id"] for row in hidden} == {carrier for ids in HIDDEN_CARRIERS_BY_DIVISION.values() for carrier in ids}


def test_native92_rejects_an_incomplete_season_shape():
    source = _source()
    source["clubs"].pop()
    try:
        build_native92_manifest(source_ledger=source, selector_map=_selector_map())
    except ValueError as exc:
        assert "20/24/24/24" in str(exc)
    else:
        raise AssertionError("incomplete source shape was accepted")
