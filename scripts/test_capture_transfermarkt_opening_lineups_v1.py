from __future__ import annotations

import sys
from pathlib import Path

import pytest
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_transfermarkt_opening_lineups_v1 as capture


def _classic_box(player_count: int = 11) -> BeautifulSoup:
    players = "".join(
        f'<a href="/player-{number}/profil/spieler/{number}">Player {number}</a>'
        + (", " if number != player_count else "")
        for number in range(1, player_count + 1)
    )
    html = f'''<div class="aufstellung-box">
      <a href="/example/startseite/verein/12">Example</a>
      <table><tr><td><b>Goalkeeper</b></td><td>{players}</td></tr>
      <tr><td><b>Manager</b></td><td><a href="/manager/profil/trainer/1">Manager Name</a></td></tr></table>
    </div>'''
    return BeautifulSoup(html, "html.parser")


def test_classic_report_preserves_xi_and_explicitly_leaves_formation_unreported() -> None:
    players, manager = capture._classic_lineup(_classic_box().select_one(".aufstellung-box"))
    assert len(players) == 11
    assert players[0]["source_position_group"] == "Goalkeeper"
    assert manager == "Manager Name"


def test_classic_report_does_not_accept_a_short_xi() -> None:
    with pytest.raises(capture.CaptureError, match="not eleven"):
        capture._classic_lineup(_classic_box(10).select_one(".aufstellung-box"))


def test_modern_report_uses_position_table_when_pitch_markers_have_no_links() -> None:
    players = "".join(
        f'<a href="/player-{index}/profil/spieler/{index}">Player {index}</a>'
        for index in range(1, 12)
    )
    page = BeautifulSoup(
        '<div class="aufstellung-box">'
        '<div class="formation-subtitle">Starting Line-up: 4-4-2</div>'
        '<div class="formation-player-container"><img src="marker.png"></div>'
        f'<table><tr><td>Players</td><td>{players}</td></tr>'
        '<tr><td>Manager</td><td>Historical Manager</td></tr></table>'
        '</div>',
        "html.parser",
    )

    starters, bench, formation, manager = capture._modern_lineup(
        page.select_one(".aufstellung-box")
    )

    assert len(starters) == 11
    assert bench == []
    assert formation == "4-4-2"
    assert manager == "Historical Manager"


def test_team_identity_resolution_is_scoped_to_the_season_competition() -> None:
    teams = [
        capture.TeamRef("", "Arsenal FC", 11, "/arsenal/startseite/verein/11", "competition-season-roster"),
        capture.TeamRef("", "Manchester United", 985, "/man-utd/startseite/verein/985", "competition-season-roster"),
    ]
    result = capture._team_ref("Arsenal", teams)
    assert result.club_id == 11
    assert result.identity_match_method == "normalised-season-competition-club-name"


def test_team_identity_resolution_accepts_only_structural_label_variants() -> None:
    teams = [
        capture.TeamRef("", "FC Barcelona", 131, "/barcelona/startseite/verein/131", "competition-season-roster"),
        capture.TeamRef("", "RCD Espanyol Barcelona", 714, "/espanyol/startseite/verein/714", "competition-season-roster"),
    ]
    result = capture._team_ref("Barcelona", teams)
    assert result.club_id == 131
    assert result.identity_match_method == "normalised-season-competition-club-name"


def test_explicit_team_identity_alias_must_stay_inside_the_declared_competition() -> None:
    teams = [capture.TeamRef("", "Inter Milan", 46, "/inter/startseite/verein/46", "competition-season-roster")]
    result = capture._team_ref_alias("Internazionale", {"club_id": 46, "reason": "published season roster label"}, teams)
    assert result.club_id == 46
    with pytest.raises(capture.CaptureError, match="absent"):
        capture._team_ref_alias("Internazionale", {"club_id": 99, "reason": "wrong"}, teams)


def test_snapshot_validator_rejects_large_access_control_pages() -> None:
    payload = (b"<html><title>Just a moment...</title>"
               b"Performing security verification cf-chl-" + b"x" * 2_000)
    with pytest.raises(capture.CaptureError, match="access-control"):
        capture._validate_snapshot_payload(payload, "https://example.invalid/source")


def test_first_fixture_uses_numeric_source_match_id_for_same_day_ties() -> None:
    ref = capture.TeamRef("Example", "Example", 12, "/example/startseite/verein/12", "fixture")
    html = '''<table>
      <tr><td>12/08/2000</td><td><a href="/x/test/spieltag/wettbewerb/TEST">League</a></td>
        <td><a href="/x/spielbericht/index/spielbericht/100">Report</a></td></tr>
      <tr><td>12/08/2000</td><td><a href="/x/test/spieltag/wettbewerb/TEST">League</a></td>
        <td><a href="/x/spielbericht/index/spielbericht/99">Report</a></td></tr>
    </table>'''.encode()

    class Cache:
        def get(self, _url: str, _key: str) -> bytes:
            return html

    fixture = capture._first_fixture(ref, season_start_year=2000, competition_code="TEST", cache=Cache())
    assert fixture["match_id"] == "99"


@pytest.mark.parametrize('requested,opponent', [(11, 1148), (1, 14), (16, 167)])
def test_report_selection_matches_whole_numeric_club_id_not_its_prefix(requested, opponent):
    def box(id, base, cls):
        players = ''.join(f'<a href="/player-{n}/profil/spieler/{n}">Player {n}</a>' for n in range(base, base + 11))
        return (f'<div class="{cls}"><a href="/club/startseite/verein/{id}/">Club</a>'
                f'<table><tr><td>Players</td><td>{players}</td></tr></table></div>')
    # The opponent has the preferred layout class. Falling back to large-6
    # is required for the requested club; never accept its numeric prefix.
    raw = (box(opponent, 100, 'aufstellung-box') + box(requested, 200, 'large-6')).encode()
    class Cache:
        def get(self, *_): return raw
    ref = capture.TeamRef('Requested', 'Requested', requested, '/club', 'fixture')
    result = capture._lineup_from_report(ref, {'report_url': 'report', 'match_id': '1',
        'date': '2000-08-01', 'schedule_url': 'schedule'}, Cache())
    assert {p['source_player_id'] for p in result['starting_xi']} == {str(n) for n in range(200, 211)}


def test_eleven_person_bench_cannot_become_an_anonymous_pitch_fallback_xi():
    rows = ''.join(f'<tr><td>Reserve</td><td><a href="/reserve-{n}/profil/spieler/{n}">Reserve</a></td></tr>' for n in range(11))
    page = BeautifulSoup('<div class="aufstellung-box"><div class="formation-subtitle">Starting Line-up: 4-4-2</div>'
        '<div class="formation-player-container"><img src="marker.png"></div>'
        '<div class="aufstellung-ersatzbank-box"><table class="ersatzbank">' + rows + '</table></div></div>', 'html.parser')
    with pytest.raises(capture.CaptureError, match='no lineup table'):
        capture._modern_lineup(page.select_one('.aufstellung-box'))


def test_distinct_clubs_cannot_share_a_provider_identity():
    def row(name, provider_id, country='greece'):
        return {'source_selector': {'country_catalog': country,
                'competition_catalog': 'greekprm', 'club_name': name,
                'transfermarkt_club_id': provider_id}}
    good = row('AEK Athens', 244)
    accepted, failures = capture._reject_duplicate_club_identities([
        row('Olympiakos', 4602), good, row('Olympiakos Volos', 4602)])
    assert accepted == [good]
    assert {x['club_name'] for x in failures} == {'Olympiakos', 'Olympiakos Volos'}
    assert all(x['reason'].startswith('duplicate-provider-club-identity:') for x in failures)
    # Distinct provider IDs are accepted; numeric provider identity is global.
    accepted, failures = capture._reject_duplicate_club_identities([
        row('Example', 1), row('Other', 2, 'other')])
    assert len(accepted) == 2 and not failures

    accepted, failures = capture._reject_duplicate_club_identities([
        row('Example', 1), row('Other', 1, 'other')])
    assert not accepted and len(failures) == 2
