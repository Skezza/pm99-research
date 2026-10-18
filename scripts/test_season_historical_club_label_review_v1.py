import copy

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
