from __future__ import annotations

import copy

import pytest

from scripts.season_english_fixed_carrier_authoring_v1 import (
    COMPILER_SCHEMA,
    DIVISIONS,
    EnglishAuthoringError,
    NATIVE_DIVISION_CARRIERS,
    RATING_FIELDS,
    build_authoring,
)


def _documents():
    competition = dict(zip(DIVISIONS, ("faprem", "d1", "d2", "d3"), strict=True))
    source_clubs = []
    selector_panels = []
    opening_rows = []
    manager_rows = []
    kit_rows = []
    rating_rows = []
    for panel_number, division in enumerate(DIVISIONS, start=1):
        teams = []
        for club_number in range(20 if division == "Premier League" else 24):
            carrier = NATIVE_DIVISION_CARRIERS[division][club_number]
            club = f"{division} Club {club_number:02d}"
            players = [
                {"name": f"{club} Player {number:02d}", "position": "G" if number in {0, 11} else "D", "birth_date": "1980-01-01", "nationality": None, "height_cm": None, "weight_kg": None, "shirt_number": number + 1, "unresolved_fields": ["nationality", "height_cm", "weight_kg"]}
                for number in range(20)
            ]
            source_clubs.append({"country_catalog": "eng", "competition_catalog": competition[division], "club_name": club, "competition_name": division, "source_path": f"eng/{club_number}.txt", "source_sha256": "a" * 64, "players": players})
            if club_number < 20:
                teams.append({"canonical_team_name": club, "eq_record_id": carrier, "mode_byte": 0, "row_index": club_number + 1, "team_select_x": club_number, "team_select_y": panel_number})
            xi = [player["name"] for player in players[:11]]
            opening_rows.append({"club": club, "first_xi": xi, "opening_squad": [player["name"] for player in players], "squad_snapshot_policy": "at-club-on-first-league-fixture-date-exclude-later-arrivals", "formation": "4-4-2", "formation_method": "source", "fixture_date": "2000-08-12", "source_url": "https://example.test/fixture"})
            manager_rows.append({"club": club, "manager_name": f"Manager {carrier}", "source_url": "https://example.test/manager"})
            kit_rows.append({"club": club, "policy": "historical-target-season", "source_url": "https://example.test/kit", "home": {"shirt": "red"}})
            rating_rows.append({"club": club, "players": [{"player": player["name"], "ratings": {field: 10 for field in RATING_FIELDS}} for player in players]})
        selector_panels.append({"division_key": f"division_{panel_number:02d}", "teams": teams})
    season = {"label": "2000/01", "catalog": "2000-2001"}
    return (
        {"schema_version": "pm99-footballsquads-season-capture-v1", "season": season, "clubs": source_clubs},
        {"schema_version": "pm99-native-english-selector-eq-map-v1", "divisions": selector_panels},
        {"schema_version": "pm99-season-opening-layer-v1", "season": season, "clubs": opening_rows},
        {"schema_version": "pm99-season-manager-layer-v1", "season": season, "rows": manager_rows},
        {"schema_version": "pm99-season-kit-layer-v1", "season": season, "clubs": kit_rows},
        {"schema_version": "pm99-season-rating-layer-v1", "season": season, "rows": rating_rows},
    )


def test_complete_layers_emit_deterministic_compiler_input():
    documents = _documents()
    first_audit, first_input = build_authoring(source=documents[0], selector_map=documents[1], openings=documents[2], managers=documents[3], kits=documents[4], ratings=documents[5])
    second_audit, second_input = build_authoring(source=documents[0], selector_map=documents[1], openings=documents[2], managers=documents[3], kits=documents[4], ratings=documents[5])
    assert first_audit == second_audit
    assert first_input == second_input
    assert first_audit["status"] == "compiler-input-ready"
    assert first_input["schema_version"] == COMPILER_SCHEMA
    assert len(first_input["clubs"]) == 92
    assert first_input["clubs"][0]["players"][0]["opening_xi"] is True
    assert "never-borrow-shared" in first_audit["policies"]["player_carriers"]


def test_missing_manager_and_rating_are_exact_blockers_not_fallbacks():
    source, selector, openings, managers, kits, ratings = _documents()
    club = managers["rows"].pop(0)["club"]
    ratings["rows"][0]["players"].pop(0)
    audit, compiler_input = build_authoring(source=source, selector_map=selector, openings=openings, managers=managers, kits=kits, ratings=ratings)
    assert compiler_input is None
    assert {row["code"] for row in audit["blockers"] if row.get("club") == club} == {"missing-manager-layer-row", "missing-or-invalid-player-ratings"}


def test_binary_scale_rating_values_accept_zero_and_one_hundred():
    source, selector, openings, managers, kits, ratings = _documents()
    ratings["rows"][0]["players"][0]["ratings"]["quality"] = 100
    ratings["rows"][0]["players"][0]["ratings"]["handling"] = 0
    audit, compiler_input = build_authoring(source=source, selector_map=selector, openings=openings, managers=managers, kits=kits, ratings=ratings)
    assert not audit["blockers"]
    assert compiler_input is not None


def test_first_xi_is_first_and_later_source_players_fill_capacity():
    source, selector, openings, managers, kits, ratings = _documents()
    club = source["clubs"][0]["club_name"]
    openings["clubs"][0]["first_xi"] = [source["clubs"][0]["players"][index]["name"] for index in range(10, -1, -1)]
    audit, compiler_input = build_authoring(source=source, selector_map=selector, openings=openings, managers=managers, kits=kits, ratings=ratings)
    assert not audit["blockers"]
    row = next(item for item in compiler_input["clubs"] if item["club"] == club)
    assert [item["facts"]["name"] for item in row["players"][:11]] == openings["clubs"][0]["first_xi"]


def test_complete_preallocation_identity_replaces_lineup_display_spelling():
    source, selector, openings, managers, kits, ratings = _documents()
    source = {
        "schema_version": "pm99-opening-squad-preallocation-v1",
        "season": source["season"],
        "source_clubs": [
            {
                "selector": {
                    "country_catalog": club["country_catalog"],
                    "competition_catalog": club["competition_catalog"],
                    "club_name": club["club_name"],
                    "source_path": club["source_path"],
                    "source_sha256": club["source_sha256"],
                },
                "competition_name": club["competition_name"],
                "opening_xi_complete": True,
                "players": [
                    {
                        "facts": copy.deepcopy(player),
                        **({"opening_xi_order": index + 1} if index < 11 else {}),
                    }
                    for index, player in enumerate(club["players"])
                ],
            }
            for club in source["clubs"]
        ],
    }
    canonical_name = source["source_clubs"][0]["players"][0]["facts"]["name"]
    openings["clubs"][0]["first_xi"][0] = "Source report display spelling"
    openings["clubs"][0]["opening_squad"][0] = "Source report display spelling"

    audit, compiler_input = build_authoring(
        source=source,
        selector_map=selector,
        openings=openings,
        managers=managers,
        kits=kits,
        ratings=ratings,
    )

    assert not audit["blockers"]
    assert compiler_input is not None
    assert compiler_input["clubs"][0]["players"][0]["facts"]["name"] == canonical_name


def test_full_season_source_player_is_excluded_when_not_in_opening_squad():
    source, selector, openings, managers, kits, ratings = _documents()
    late = copy.deepcopy(source["clubs"][0]["players"][0]); late["name"] = "January Arrival"
    source["clubs"][0]["players"].append(late)
    ratings["rows"][0]["players"].append({"player": late["name"], "ratings": {field: 10 for field in RATING_FIELDS}})
    audit, compiler_input = build_authoring(source=source, selector_map=selector, openings=openings, managers=managers, kits=kits, ratings=ratings, squad_limit=25)
    assert not audit["blockers"]
    row = next(item for item in compiler_input["clubs"] if item["club"] == source["clubs"][0]["club_name"])
    assert late["name"] not in {player["facts"]["name"] for player in row["players"]}


def test_exact_xi_is_enough_when_no_more_opening_date_players_are_sourced():
    source, selector, openings, managers, kits, ratings = _documents()
    club = source["clubs"][0]["club_name"]
    source["clubs"][0]["players"] = source["clubs"][0]["players"][:11]
    openings["clubs"][0]["opening_squad"] = openings["clubs"][0]["opening_squad"][:11]
    ratings["rows"][0]["players"] = ratings["rows"][0]["players"][:11]
    audit, compiler_input = build_authoring(
        source=source,
        selector_map=selector,
        openings=openings,
        managers=managers,
        kits=kits,
        ratings=ratings,
    )
    assert not [row for row in audit["blockers"] if row.get("club") == club]
    assert compiler_input is not None
    row = next(item for item in compiler_input["clubs"] if item["club"] == club)
    assert len(row["players"]) == 11


def test_opening_august_window_is_an_accepted_squad_snapshot() -> None:
    source, selector, openings, managers, kits, ratings = _documents()
    openings["clubs"][0]["squad_snapshot_policy"] = (
        "opening-window-through-august-31-exclude-september-and-later-arrivals"
    )
    audit, compiler_input = build_authoring(
        source=source,
        selector_map=selector,
        openings=openings,
        managers=managers,
        kits=kits,
        ratings=ratings,
    )
    assert not audit["blockers"]
    assert compiler_input is not None


def test_rejects_non_mode0_selector_carrier():
    documents = list(_documents())
    documents[1] = copy.deepcopy(documents[1])
    documents[1]["divisions"][0]["teams"][0]["mode_byte"] = 1
    with pytest.raises(EnglishAuthoringError, match="mode-0"):
        build_authoring(source=documents[0], selector_map=documents[1], openings=documents[2], managers=documents[3], kits=documents[4], ratings=documents[5])


def test_surplus_lower_division_clubs_are_explicitly_omitted():
    source, selector, openings, managers, kits, ratings = _documents()
    extra = copy.deepcopy(source["clubs"][-1]); extra["club_name"] = "League Two Surplus"
    source["clubs"].append(extra)
    audit, compiler_input = build_authoring(source=source, selector_map=selector, openings=openings, managers=managers, kits=kits, ratings=ratings)
    assert audit["coverage"]["omitted_rows"] == 1
    assert audit["omissions"][0]["reason"] == "source-club-exceeds-native-panel-capacity"
    assert compiler_input is not None
