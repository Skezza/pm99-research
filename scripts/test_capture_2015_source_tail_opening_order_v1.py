"""Focused tests for strict opening ordering of source-tail squads."""

from scripts.capture_2015_source_tail_opening_order_v1 import _capacity_roster, _source_number_order_exception


def _player(name: str) -> dict:
    return {"name": name, "nationality": "ENG", "position": "M", "unresolved_fields": []}


def _lineup(date: str, starters: list[str], bench: list[str]) -> dict:
    return {
        "first_league_fixture_date": date, "lineup_source_url": f"https://example.test/{date}",
        "source_match_id": date, "starting_xi": [{"display_name": name, "source_player_id": name, "source_url": "x"} for name in starters],
        "substitutes": [{"display_name": name, "source_player_id": name, "source_url": "x"} for name in bench],
    }


def test_capacity_roster_prioritises_first_xi_then_bench_then_later_fixture() -> None:
    selected, remainder = _capacity_roster(
        source_players=[_player(name) for name in ("A", "B", "C", "D", "E")],
        lineups=[_lineup("2015-08-01", ["A", "B"], ["C"]), _lineup("2015-08-08", ["D"], ["E"])],
        capacity=5,
    )
    assert [player["name"] for player in selected] == ["A", "B", "C", "D", "E"]
    assert remainder == 0


def test_capacity_roster_labels_only_the_needed_pinned_season_remainder() -> None:
    selected, remainder = _capacity_roster(
        source_players=[_player(name) for name in ("A", "B", "C")],
        lineups=[_lineup("2015-08-01", ["A"], [])], capacity=3,
    )
    assert [player["opening_source"]["selection_role"] for player in selected] == [
        "starting-xi", "pinned-season-capacity-remainder", "pinned-season-capacity-remainder",
    ]
    assert remainder == 2


def test_source_number_exception_is_explicit_and_deterministic() -> None:
    club = {
        "candidate_carrier_id": 2601, "fixed_roster_slot_count": 2, "country_catalog": "bolivia",
        "club_name": "Bolívar", "target_article_title": "Club Bolívar", "target_article_path": "/wiki/Bolívar",
        "source_season_label": "2015-calendar", "source_url": "https://example.test", "source_sha256": "x",
        "source_identity": {"transfermarkt_saison_id": 2014},
        "players": [_player("No Number") | {"shirt_number": None, "source_player_id": "3"},
                    _player("Number Two") | {"shirt_number": 2, "source_player_id": "2"},
                    _player("Number One") | {"shirt_number": 1, "source_player_id": "1"}],
    }
    result = _source_number_order_exception(club=club, reason="no domestic fixture")
    assert [player["name"] for player in result["players"]] == ["Number One", "Number Two"]
    assert result["selection"]["published_opening_lineup_player_count"] == 0
