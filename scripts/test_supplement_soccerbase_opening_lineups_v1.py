from __future__ import annotations

import pytest

from scripts.supplement_soccerbase_opening_lineups_v1 import (
    Cache, SoccerbaseCaptureError, _first_fixture, _lineup, _team_identity, supplement,
)


class FakeCache:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages

    def get(self, url: str, key: str) -> bytes:
        return self.pages[key].encode()


def test_soccerbase_identity_fixture_and_xi_are_exactly_parsed() -> None:
    players = "".join(
        f'<tr><td class="colA"><a href="/players/player.sd?player_id={number}">P Surname{number}</a></td><td>({"G" if number == 1 else "D" if number < 6 else "M" if number < 10 else "F"})</td></tr>'
        for number in range(1, 12)
    )
    profiles = {f"player/{number}.html": f"<html><h1>Player Surname{number}</h1></html>" for number in range(1, 12)}
    cache = FakeCache({
        "team-search/" + __import__("hashlib").sha256(b"Example City").hexdigest() + ".html": '<html><link rel="canonical" href="https://www.soccerbase.com/teams/team.sd?team_id=7"><h1>Example City Club details</h1></html>',
        "team-season/2001/7.html": '<html><select id="seasonSelect"><option value="131">2001/2002</option></select><table><tr class="match" id="tgc99"><td class="tournament"><a>Football League Div 3</a></td><td class="dateTime"><span class="hide">2001-08-11 15:00</span></td><td class="team"><a href="/teams/team.sd?team_id=7">Example City</a></td><td class="team"><a href="/teams/team.sd?team_id=8">Other</a></td></tr></table></html>',
        "match/99.html": f'<html><table>{players}<tr><td class="separator"></td></tr></table><table>{players}<tr><td class="separator"></td></tr></table></html>',
        **profiles,
    })
    team_id, published = _team_identity("Example City", cache)  # type: ignore[arg-type]
    fixture = _first_fixture("Example City", team_id, "d3", 2001, cache)  # type: ignore[arg-type]
    lineup = _lineup("Example City", team_id, published, fixture, cache)  # type: ignore[arg-type]
    assert fixture == {"date": "2001-08-11", "game_id": "99", "side": 0, "schedule_url": "https://www.soccerbase.com/teams/team.sd?team_id=7&teamTabs=results&season_id=131"}
    assert len(lineup["starting_xi"]) == 11
    assert lineup["starting_xi"][0]["display_name"] == "Player Surname1"
    assert lineup["starting_xi"][0]["source_player_id"] == "soccerbase:1"
    assert lineup["source_blockers"] == ["no-published-formation-grid", "no-published-manager"]


def test_composition_accepts_a_hash_bound_selector_projection_and_scopes_source() -> None:
    selector = {"country_catalog": "eng", "competition_catalog": "d3", "club_name": "Example City"}
    other = {"country_catalog": "spain", "competition_catalog": "laliga", "club_name": "Other"}
    primary = {"schema_version": "pm99-transfermarkt-opening-lineup-source-v1", "source": {"source_capture_sha256": "b" * 64}, "clubs": [{"source_selector": selector}], "failures": []}
    result = supplement(
        source_capture={"clubs": [selector, other]}, source_capture_sha256="a" * 64,
        primary=primary, primary_sha256="c" * 64, season_start_year=2001,
        cache=Cache(__import__("pathlib").Path("unused"), offline=True, delay=0),
        lineup_source_selection={"clubs": [selector], "source_intake_sha256": "d" * 64},
        lineup_source_selection_sha256="b" * 64,
        source_intake={"source_capture_sha256": "a" * 64}, source_intake_sha256="d" * 64,
    )
    assert result["summary"]["source_club_count"] == 1
    assert result["summary"]["captured_club_count"] == 1


def test_composition_rejects_an_unbound_selector_projection() -> None:
    with pytest.raises(SoccerbaseCaptureError, match="different squad source"):
        supplement(source_capture={"clubs": []}, source_capture_sha256="a" * 64,
                   primary={"schema_version": "pm99-transfermarkt-opening-lineup-source-v1", "source": {"source_capture_sha256": "b" * 64}, "clubs": []},
                   primary_sha256="c" * 64, season_start_year=2001,
                   cache=Cache(__import__("pathlib").Path("unused"), offline=True, delay=0))


def test_composition_preserves_selected_non_english_primary_failure() -> None:
    selector = {"country_catalog": "spain", "competition_catalog": "laliga", "club_name": "Missing Club"}
    primary = {
        "schema_version": "pm99-transfermarkt-opening-lineup-source-v1",
        "source": {"source_capture_sha256": "b" * 64},
        "clubs": [],
        "failures": [{**selector, "reason": "exact primary identity unavailable"}],
    }
    result = supplement(
        source_capture={"clubs": [selector]}, source_capture_sha256="a" * 64,
        primary=primary, primary_sha256="c" * 64, season_start_year=2001,
        cache=Cache(__import__("pathlib").Path("unused"), offline=True, delay=0),
        lineup_source_selection={"clubs": [selector], "source_intake_sha256": "d" * 64},
        lineup_source_selection_sha256="b" * 64,
        source_intake={"source_capture_sha256": "a" * 64}, source_intake_sha256="d" * 64,
    )
    assert result["failures"] == [{**selector, "reason": "exact primary identity unavailable"}]
    assert result["summary"]["failed-club-count"] == 1
