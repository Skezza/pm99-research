"""Focused tests for 2015 source-tail opening-window squad capture."""

from scripts.capture_2015_source_tail_opening_squads_v1 import (
    _broad_position,
    _combined_capacity_players,
    _ordered_lineup_players,
)


def test_broad_position_accepts_profile_and_classic_lineup_labels() -> None:
    assert [_broad_position(value) for value in ("Goalkeeper", "Centre-Back", "Central Midfield", "Centre-Forward", "D")] == [
        "G", "D", "M", "F", "D",
    ]


def test_opening_order_keeps_first_xi_before_bench_and_later_fixture() -> None:
    lineups = [
        {
            "first_league_fixture_date": "2015-08-01",
            "lineup_source_url": "https://example.test/one",
            "source_match_id": "1",
            "starting_xi": [{"source_player_id": "a", "display_name": "A", "source_url": "https://example.test/a"}],
            "substitutes": [{"source_player_id": "b", "display_name": "B", "source_url": "https://example.test/b"}],
        },
        {
            "first_league_fixture_date": "2015-08-08",
            "lineup_source_url": "https://example.test/two",
            "source_match_id": "2",
            "starting_xi": [
                {"source_player_id": "b", "display_name": "B", "source_url": "https://example.test/b"},
                {"source_player_id": "c", "display_name": "C", "source_url": "https://example.test/c"},
            ],
            "substitutes": [],
        },
    ]
    assert [row["source_player_id"] for row in _ordered_lineup_players(lineups)] == ["a", "b", "c"]


def test_capacity_keeps_opening_players_before_same_club_pinned_roster() -> None:
    selected = _combined_capacity_players(
        opening_players=[{"name": "First XI"}, {"name": "Early Bench"}],
        pinned_players=[{"name": "First XI"}, {"name": "Pinned Extra"}],
        capacity=3,
    )
    assert [row["name"] for row in selected] == ["First XI", "Early Bench", "Pinned Extra"]
