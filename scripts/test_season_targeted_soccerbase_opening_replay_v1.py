import copy
import hashlib
import json
import pytest
from scripts import season_targeted_soccerbase_opening_replay_v1 as targeted
from scripts import season_soccerbase_original_opening_v1 as original
from scripts import season_soccerbase_duplicate_source_policy_v1 as policy
from scripts.test_season_soccerbase_original_opening_v1 import schedule, lineup


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(targeted.registry, 'ROOT', tmp_path)
    proofs = []
    def put(key, raw, url):
        path = tmp_path / key; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw); sha = hashlib.sha256(path.read_bytes()).hexdigest()
        receipt = path.with_suffix(path.suffix+'.source.json')
        receipt.write_text(json.dumps({'url': url, 'sha256': sha}))
        proofs.append({'path': key, 'sha256': sha, 'receipt_path': str(receipt.relative_to(tmp_path)),
            'receipt_sha256': hashlib.sha256(receipt.read_bytes()).hexdigest(), 'url': url})
    discovery = 'https://www.soccerbase.com/teams/team.sd?team_id=364&season_id=0&teamTabs=results'
    team_url = discovery.replace('season_id=0', 'season_id=154')
    put('discovery.html', schedule(), discovery); put('team.html', schedule(), team_url)
    first = original.first_fixture(schedule(), 364, '2021-22', 'National League', 'Boreham W', team_url)
    match_url = 'https://www.soccerbase.com/matches/additional_information.sd?id_game=833593'
    put('match.html', lineup(), match_url)
    sheet = original.match(lineup(), first, 364, match_url, True); biographies = []
    for field in ('starting_xi', 'published_bench'):
        for row in sheet[field]:
            id = row['provider_player_id']
            url = f'https://www.soccerbase.com/players/player.sd?player_id={id}'
            raw = f'<h1>Full Player {id}</h1><table><tr><th>Born</th><td>22 Feb, 1990</td></tr></table>'
            put(f'players/{id}.html', raw, url)
            biographies.append({'membership': field, 'original_match_row': row,
                'original_biography': original.profile(raw, row, url)})
    saved = {'schema_version': targeted.SCHEMA, 'target': {'season': '2021-22', 'club': 'Boreham Wood'},
        'provider_team_id': 364, 'provider_season_id': 154, 'competition': 'National League',
        'published_club_name': 'Boreham W', 'fixture': first, 'original_match': sheet,
        'biographies': biographies, 'raw_sources': proofs,
        'native_writes': 0, 'recipes_modified': 0, 'historical_ownership_approved': False}
    path = tmp_path/'capture.json'
    def save():
        path.write_text(json.dumps(saved))
        return {'path': 'capture.json', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'policy': targeted.POLICY}
    return saved, save, save()


def test_full_original_replay_preserves_namespaces_and_not_ownership(tmp_path, monkeypatch):
    saved, save, binding = fixture(tmp_path, monkeypatch)
    row = targeted.replay_capture(binding, '2021-22', {})
    assert len(row['identity_bridges']['starting_xi']) == 11
    assert len(row['identity_gaps']) == 12
    assert row['identity_bridges']['starting_xi'][0]['soccerbase_person']['source_player_id'] == 'soccerbase:200'
    assert row['approved_for_native_ownership_repair'] is False
    represented = copy.deepcopy(row); represented['represented_native_clubs'] = []
    assert policy.reconstruct(represented, '2021-22', None, {}) == row
    with pytest.raises(ValueError, match='two consistent'):
        policy.confirm_club_mapping(row, {}, {})


@pytest.mark.parametrize('problem', ['season', 'claims', 'raw', 'receipt', 'original-url', 'conflate', 'approval'])
def test_saved_summaries_and_rehashed_tampering_cannot_bypass_original_replay(tmp_path, monkeypatch, problem):
    saved, save, binding = fixture(tmp_path, monkeypatch)
    people = {}; season = '2021-22'
    if problem == 'season': season = '2020-21'
    if problem == 'claims': saved['biographies'][0]['original_biography']['name'] = 'Other Person'
    if problem == 'raw': (tmp_path/'team.html').write_text('changed')
    if problem == 'receipt': (tmp_path/'team.html.source.json').write_text('{}')
    if problem == 'original-url': saved['raw_sources'][1]['url'] += '0'
    if problem == 'conflate':
        for bio in saved['biographies'][:2]:
            person = bio['original_biography']
            people[(targeted.replay.transfer._normalise(person['name']), person['birth_date'])] = {
                7: {'source_player_id': 7, 'name': 'Alias', 'birth_date': person['birth_date']}}
    if problem == 'approval': saved['historical_ownership_approved'] = True
    binding = save()
    with pytest.raises(ValueError): targeted.replay_capture(binding, season, people)
