from __future__ import annotations

import copy

from scripts import season_editorial_rating_input_builder_v1 as builder
from scripts import season_editorial_ratings_v1 as ratings
from scripts import test_season_package_v2 as fixtures


def _inputs():
    draft = fixtures._valid_package()
    for index, row in enumerate(draft["players"], start=1):
        row.update({"person_id": "person-source-" + f"{index:064x}", "source_name": f"Source Player {index}"})
    player = draft["players"][0]
    player["facts"].update({"primary_position": "M", "birth_date": {"policy": "preserve-existing-mode1"}, "height_cm": {"policy": "preserve-existing-mode1"}})
    player["fact_fallbacks"] = [
        {"field": "birth_date", "method": "preserve-existing-mode1", "value": {"policy": "preserve-existing-mode1"}, "reason": "fixture", "proof": fixtures._proof()},
        {"field": "height_cm", "method": "preserve-existing-mode1", "value": {"policy": "preserve-existing-mode1"}, "reason": "fixture", "proof": fixtures._proof()},
    ]
    allocation = {
        "schema_version": "pm99-season-carrier-allocation-v1",
        "season": dict(draft["season"]),
        "assignments": [{"carrier_id": 100, "club_name": "Fixture Town", "country_group": "spain", "source_selector": {"country_catalog": "spain", "competition_catalog": "laliga", "source_path": "x", "source_sha256": "b" * 64}}],
    }
    opening = {"clubs": [{"source_selector": {"country_catalog": "spain", "competition_catalog": "laliga", "club_name": "Fixture Town"}, "first_league_fixture_date": "2015-08-12", "starting_xi": [{"source_name": f"Source Player {index}"} for index in range(1, 12)]}]}
    return draft, allocation, opening


def test_builds_stable_input_and_uses_opening_xi_status() -> None:
    draft, allocation, opening = _inputs()
    payload, audit = builder.build_input(draft=draft, allocation=allocation, opening=opening)
    assert payload["schema_version"] == ratings.INPUT_SCHEMA
    assert payload["snapshot_date"] == "2015-08-12"
    assert payload["players"][0]["squad_status"] == "starting_xi"
    assert payload["players"][0]["birth_date"] is None
    assert audit["coverage"]["starting_xi_player_count"] == 11
    assert builder.build_input(draft=copy.deepcopy(draft), allocation=copy.deepcopy(allocation), opening=copy.deepcopy(opening)) == (payload, audit)


def test_without_opening_uses_explicit_opening_squad_status() -> None:
    draft, allocation, _opening = _inputs()
    payload, audit = builder.build_input(draft=draft, allocation=allocation)
    assert payload["snapshot_date"] == "2015-08-01"
    assert payload["players"][0]["squad_status"] == "opening_squad"
    assert audit["coverage"]["starting_xi_player_count"] == 0


def test_future_birth_date_is_logged_nonblocking_fallback() -> None:
    draft, allocation, opening = _inputs()
    draft["players"][1]["facts"]["birth_date"] = "2016-01-01"

    payload, audit = builder.build_input(
        draft=draft, allocation=allocation, opening=opening
    )

    by_id = {row["player_id"]: row for row in payload["players"]}
    assert by_id[draft["players"][1]["id"]]["birth_date"] is None
    assert audit["coverage"]["invalid_birth_date_fallback_player_count"] == 1
    assert audit["hard_blockers"] == []
    assert audit["non_blocking_warnings"][0]["code"] == (
        "invalid-player-birth-date-fallback-logged"
    )


def test_missing_country_strength_is_an_explicit_partial_coverage_blocker() -> None:
    draft, allocation, _opening = _inputs()
    uncovered = copy.deepcopy(allocation["assignments"][0])
    uncovered["country_group"] = "unreviewed-fixture-country"
    allocation["assignments"].append(uncovered)

    payload, audit = builder.build_input(draft=draft, allocation=allocation)

    assert len(payload["players"]) == len(draft["players"])
    assert audit["coverage"]["country_strength_missing_assignment_count"] == 1
    assert audit["coverage"]["country_strength_missing_player_count"] == len(draft["players"])
    assert audit["hard_blockers"] == [{
        "code": "country-strength-policy-required",
        "count": 1,
        "country_groups": ["unreviewed-fixture-country"],
        "carrier_ids_by_country_group": {"unreviewed-fixture-country": [100]},
        "player_count": len(draft["players"]),
        "message": (
            "Allocated source players were left unrated because their country group "
            "has no reviewed editorial strength in this policy version."
        ),
    }]
