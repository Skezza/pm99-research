"""Small deterministic tests for the dated missing-family source capture."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.capture_2015_missing_family_squads import (
    parse_league_links,
    parse_squad_page,
)


def test_split_year_player_row_is_canonicalised() -> None:
    payload = b"""
    <table><tr itemprop='athlete'><td></td><td><span>Doe</span> , <span>Jane</span></td>
    <td>1994-01-02</td><td>Serbia</td><td>Centre Midfielder</td>
    <td>2015/16</td><td>10</td><td>2</td></tr></table>
    """
    players = parse_squad_page(payload, country_name="Serbia")
    assert len(players) == 1
    assert players[0]["name"] == "Doe, Jane"
    assert players[0]["nationality"] == "SRB"
    assert players[0]["position"] == "M"
    assert players[0]["unresolved_fields"] == ["shirt_number", "height_cm", "weight_kg"]


def test_calendar_year_row_requires_calendar_label() -> None:
    payload = b"""
    <table><tr itemprop='athlete'><td></td><td>Player, One</td>
    <td>1994-01-02</td><td>Finland</td><td>Goalkeeper</td>
    <td>2015</td><td>10</td><td>0</td></tr></table>
    """
    assert parse_squad_page(payload, country_name="Finland") == []
    assert len(parse_squad_page(payload, country_name="Finland", season_label="2015")) == 1


def test_league_links_do_not_fuzzy_join_clubs() -> None:
    payload = b"""
    <a href='/club/1/2015_1/Partizan_Beograd.html'>Partizan Beograd</a>
    <a href='/club/2/2015_1/Partizan_Beograd_B.html'>Partizan Beograd B</a>
    """
    links = parse_league_links(payload)
    assert ("Partizan Beograd", "/club/1/2015_1/Partizan_Beograd.html") in links
    assert ("Partizan Beograd B", "/club/2/2015_1/Partizan_Beograd_B.html") in links


if __name__ == "__main__":
    test_split_year_player_row_is_canonicalised()
    test_calendar_year_row_requires_calendar_label()
    test_league_links_do_not_fuzzy_join_clubs()
    print("manual fixture tests: ok")
