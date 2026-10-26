import copy
import json
from types import SimpleNamespace

import pytest

from scripts import season_historical_club_label_review_v1 as review


def fixture(monkeypatch):
    monkeypatch.setattr(review.roster, 'club_group', lambda c: 'germany')
    selector = {'country_catalog': 'ger', 'competition_catalog': 'bundes', 'club_name': 'Werder Bremen',
        'source_path': 'ger/2012-2013/bundes/wbremen.txt', 'source_sha256': 'f' * 64}
    rows = [{'source_row_sha256': f'{i:064x}', 'opening_xi_order': i + 1,
             'facts': {'name': f'Person {i}', 'birth_date': '1989-01-01'}} for i in range(11)]
    source = {'selector': selector, 'opening_xi_complete': True, 'players': rows}
    index, sources = review.indexed_claims({'source_clubs': [source]})
    players = [{'name': r['facts']['name'], 'person_id': review.builder._source_person_id(r),
                'facts': {'birth_date': '1989-01-01'}, 'proof': {'artifact_id': 'original-rows'}} for r in rows]
    return {'name': 'Hannover 96'}, players, index, sources, source


def test_source_row_identity_recovers_club_without_voting_or_player_moves(monkeypatch):
    club, players, index, sources, source = fixture(monkeypatch)
    original = copy.deepcopy(players)
    actual, reason = review.unanimous_claim(club, players, 'original-rows', index, sources)
    assert actual == source and reason is None
    assert players == original and club['name'] == 'Hannover 96'


def test_ten_good_players_cannot_outvote_one_different_authored_club(monkeypatch):
    club, players, index, sources, source = fixture(monkeypatch)
    key = next(iter(sources)); other = (*key[:2], 'Hamburger SV', *key[3:])
    id = players[-1]['person_id']; index[id] = [(other, source['players'][-1])]
    actual, reason = review.unanimous_claim(club, players, 'original-rows', index, sources)
    assert actual is None and 'mixed' in reason


def test_changed_name_or_birth_date_breaks_authoring_binding(monkeypatch):
    club, players, index, sources, _ = fixture(monkeypatch)
    players[0]['facts']['birth_date'] = '1989-01-02'
    actual, reason = review.unanimous_claim(club, players, 'original-rows', index, sources)
    assert actual is None and 'no longer binds' in reason


def test_missing_opening_starter_is_not_a_complete_source_club(monkeypatch):
    club, players, index, sources, _ = fixture(monkeypatch)
    actual, reason = review.unanimous_claim(club, players[:-1], 'original-rows', index, sources)
    assert actual is None and 'eleven' in reason


@pytest.mark.parametrize('country', ['brazil', 'ireland', 'norway', 'sweden'])
def test_next_calendar_year_fixture_cannot_authorize_a_club_rename(tmp_path, monkeypatch, country):
    source_root = tmp_path / 'sources'
    season_root = source_root / '2000-01'
    season_root.mkdir(parents=True)
    pre = season_root / 'opening-squad-preallocation.json'
    selector = {'country_catalog': country, 'competition_catalog': 'league', 'club_name': 'Correct Club'}
    capture = season_root / 'opening-lineups.json'
    capture.write_text(json.dumps({'clubs': [{'source_selector': selector,
        'first_league_fixture_date': '2001-02-14', 'source_match_id': '42'}]}))
    pre.write_text(json.dumps({'source_clubs': [], 'sources': {
        'opening_lineup_sha256': review.registry.sha256_file(capture)}}))
    club = {'id': 'club-1', 'carrier_id': 1, 'name': 'Wrong Club'}
    package = tmp_path / 'package.json'
    package.write_text(json.dumps({'clubs': [club], 'players': [], 'artifacts': [{
        'id': 'opening-squad-preallocation-2000-01', 'sha256': review.registry.sha256_file(pre)}]}))
    game = tmp_path / 'game'
    (game / 'DBDAT').mkdir(parents=True)
    for name in ('EQ98030.FDI', 'ENT98030.FDI'):
        (game / 'DBDAT' / name).write_bytes(b'unchanged fixture input')
    release = SimpleNamespace(release_id='known', package_path=package, game_path=game)
    monkeypatch.setattr(review.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(review.registry, 'load_preferred_release', lambda season: release)
    monkeypatch.setattr(review.roster, 'club_group', lambda club: country)
    monkeypatch.setattr(review, '_manager_graph', lambda **kwargs: ({}, {}))
    source = {'selector': selector, 'opening_fixture_date': '2001-02-14',
        'opening_source_match_id': '42', 'players': [{'opening_xi_order': i + 1,
            'opening_source_player_id': str(i)} for i in range(11)]}
    monkeypatch.setattr(review, 'unanimous_claim', lambda *args: (source, None))
    monkeypatch.setattr(review.opening, 'verify_opening', lambda *args: {
        'date': '2001-02-14', 'starting_xi': {str(i): {} for i in range(11)}})
    result = review.review('2000-01', source_root, source_root, tmp_path / 'none', tmp_path / 'output')
    assert result['supported_label_mismatches'] == 0
    report = json.loads((tmp_path / 'output/2000-01/club-label-review.json').read_text())
    assert report['clubs'][0]['status'] == 'club-label-first-fixture-evidence-gap'
    assert 'outside season start year' in report['clubs'][0]['reason']
