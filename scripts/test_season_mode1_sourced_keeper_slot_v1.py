import copy
from pathlib import Path

import pytest

from scripts import season_mode1_sourced_keeper_slot_v1 as module

URL = 'https://www.skysports.com/football/club-vs-opponent/teams/12345'


def fixture():
    def person(given, surname):
        return ('<dd class="sdc-site-team-lineup__player-name">'
                f'<span class="sdc-site-team-lineup__player-initial" title="{given}">{given[0]}</span>'
                f'<span class="sdc-site-team-lineup__player-surname">{surname}</span></dd>')
    xi = person('Real', 'Keeper') + ''.join(person('Full', f'Player{i}') for i in range(10))
    bench = person('Real', 'Defender')
    return ('<html><head><title>Starting Lineups - Club vs Opponent | 10.09.2006</title></head>'
            '<body><svg><title>Goal scored</title></svg><div>'
            '<div><h4 class="sdc-site-team-lineup__team-name">Club</h4></div>'
            f'<dl class="sdc-site-team-lineup__players">{xi}</dl>'
            '<dl class="sdc-site-team-lineup__players sdc-site-team-lineup__players--subs">'
            f'{bench}</dl></div></body></html>').encode()


def test_original_full_given_name_not_guessed_from_initials_and_SVG_titles_ignored():
    result = module.report(fixture(), URL, 'Club', 'Opponent', '2006-09-10')
    assert result['starting_xi_names'][0] == 'Real Keeper'
    assert result['bench_names'] == ['Real Defender']
    assert result['complete_native_XI_repair_claimed'] is False


@pytest.mark.parametrize('problem', ['date', 'club', 'opponent', 'host', 'query', 'http',
    'missing-title-name', 'initial-mismatch', 'missing-XI', 'missing-bench', 'duplicate-name',
    'XI-bench-overlap', 'duplicate-column'])
def test_ambiguous_or_wrong_original_source_refuses(problem):
    raw, url, day, club, opponent = fixture(), URL, '2006-09-10', 'Club', 'Opponent'
    if problem == 'date': day = '2006-09-11'
    if problem == 'club': club = 'Other Club'
    if problem == 'opponent': opponent = 'Other Opponent'
    if problem == 'host': url = url.replace('www.skysports.com', 'mirror.example')
    if problem == 'query': url += '?other=1'
    if problem == 'http': url = url.replace('https:', 'http:')
    if problem == 'missing-title-name': raw = raw.replace(b'title="Real"', b'')
    if problem == 'initial-mismatch': raw = raw.replace(b'title="Real">R', b'title="Real">Q')
    if problem == 'missing-XI': raw = raw.replace(b'<dl class="sdc-site-team-lineup__players">', b'<div>')
    if problem == 'missing-bench': raw = raw.replace(b'sdc-site-team-lineup__players--subs', b'wrong')
    if problem == 'duplicate-name': raw = raw.replace(b'Player1</span>', b'Player0</span>')
    if problem == 'XI-bench-overlap': raw = raw.replace(b'Defender</span>', b'Keeper</span>')
    if problem == 'duplicate-column': raw = raw.replace(b'</body>', raw[raw.index(b'<div>'):raw.index(b'</body>')] + b'</body>')
    with pytest.raises(ValueError): module.report(raw, url, club, opponent, day)


def test_changed_original_binding_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(module.registry, 'ROOT', tmp_path)
    path = tmp_path / 'source.html'
    path.write_bytes(fixture())
    binding = {'path': 'source.html', 'sha256': module.registry.sha256_file(path)}
    assert module.original(binding) == path
    path.write_bytes(b'changed')
    with pytest.raises(ValueError, match='bytes changed'): module.original(binding)


def test_apply_requires_exact_source_schema_and_pair(monkeypatch):
    calls = []
    monkeypatch.setattr(module, 'patch_owned_mode1_reserve_keeper_slot',
                        lambda jug, eq, rows: calls.append(rows) or b'output')
    monkeypatch.setattr(module, 'target_members', lambda eq, carrier: {1, 13})
    plan = {'schema_version': module.SCHEMA, 'club_carrier_id': 223, 'players': [
        {'carrier_id': 1, 'native_name': 'Defender', 'before': 1, 'after': 13},
        {'carrier_id': 13, 'native_name': 'Keeper', 'before': 13, 'after': 1}]}
    assert module.apply(b'JUG', b'EQ', plan) == b'output'
    assert [(r.before, r.after) for r in calls[0]] == [(1, 13), (13, 1)]
    bad = copy.deepcopy(plan); bad['schema_version'] = 'unbound'
    with pytest.raises(ValueError): module.apply(b'JUG', b'EQ', bad)
    bad = copy.deepcopy(plan); bad['players'].pop()
    with pytest.raises(ValueError): module.apply(b'JUG', b'EQ', bad)


def test_a_pair_in_another_native_club_cannot_replay(monkeypatch):
    monkeypatch.setattr(module, 'target_members', lambda eq, carrier: {2, 3})
    plan = {'schema_version': module.SCHEMA, 'club_carrier_id': 223,
            'players': [{'carrier_id': 1}, {'carrier_id': 13}]}
    with pytest.raises(ValueError, match='target native club'):
        module.apply(b'JUG', b'EQ', plan)


@pytest.mark.parametrize('problem', ['club', 'carrier', 'name', 'DOB', 'roster', 'person-club'])
def test_recipe_source_identity_cannot_drift(problem):
    row = {'player_id': 'p1', 'carrier_id': 1, 'source_name': 'Source Person', 'birth_date': '1980-01-01'}
    plan = {'club_id': 'c1', 'club_carrier_id': 223, 'club': 'Club', 'players': [row]}
    package = {'clubs': [{'id': 'c1', 'carrier_id': 223, 'name': 'Club', 'roster_player_ids': ['p1']}],
               'players': [{'id': 'p1', 'carrier_id': 1, 'club_id': 'c1', 'name': 'Display',
                            'source_name': 'Source Person', 'facts': {'birth_date': '1980-01-01'}}]}
    module.validate_recipe_scope(package, plan)
    if problem == 'club': package['clubs'][0]['name'] = 'Other'
    if problem == 'carrier': package['players'][0]['carrier_id'] = 2
    if problem == 'name': package['players'][0]['source_name'] = 'Other'
    if problem == 'DOB': package['players'][0]['facts']['birth_date'] = '1981-01-01'
    if problem == 'roster': package['clubs'][0]['roster_player_ids'] = []
    if problem == 'person-club': package['players'][0]['club_id'] = 'c2'
    with pytest.raises(ValueError): module.validate_recipe_scope(package, plan)
