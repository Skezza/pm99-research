import copy
import json
from pathlib import Path
import pytest
from scripts import capture_opening_club_identity_gaps_v1 as gap


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(gap, 'ROOT', tmp_path)
    monkeypatch.setattr(gap.registry, 'relative_workspace_path', lambda p: str(Path(p).relative_to(tmp_path)))
    pin = {'path': 'snapshot', 'pinned_receipt_path': 'pin'}
    entities = tmp_path / 'entities.json'
    entities.write_text(json.dumps({'batches': [], 'schema_version': 'pm99-original-public-club-entity-discovery-v1'}))
    plan = {'bindings': {'snapshot': pin, 'soccerbase_opening_sources': {'club_entities': {
        'path': 'entities.json', 'sha256': gap.registry.sha256_file(entities), 'policy': 'discovery-only'}}},
        'updates': ['must not authorise']}
    path = tmp_path / 'plan.json'
    path.write_text(json.dumps(plan))
    monkeypatch.setattr(gap.context, 'load_snapshot', lambda *a: ({}, {}, pin))
    monkeypatch.setattr(gap.whole.public, 'merge_bound', lambda p, e, b: (p, e, None))
    monkeypatch.setattr(gap.entities, 'read_entities', lambda p: {})
    monkeypatch.setattr(gap.whole.roster, 'load_sources', lambda s: ([{
        'source_path': 'soccerbase/team/2779/august', 'club_name': 'Weymouth'}], None))
    opening = {'fixture': {'date': '2021-08-21'}, 'source_capture': {'original': 'bound'},
        'identity_bridges': {'starting_xi': [
            {'transfermarkt_person': {'source_player_id': 1}},
            {'transfermarkt_person': None}]}}
    monkeypatch.setattr(gap.whole.replay, 'replay_club', lambda *a: copy.deepcopy(opening))
    monkeypatch.setattr(gap.whole.transfer, 'transfer_interval', lambda *a: {
        'status': 'recorded-entry-and-exit-bracket-fixture', 'source_owner_club_id': 3822})
    def capture(discovery, cache, output):
        result = {'batches': [], 'discovery': {'sha256': gap.registry.sha256_file(discovery)}}
        gap.pipeline.write_canonical_json(output, result)
        return result
    monkeypatch.setattr(gap.capture, 'run', capture)
    return path, tmp_path / 'out'


def test_only_original_dated_starter_ids_are_queried_and_no_game_plan_is_authorised(tmp_path, monkeypatch):
    path, output = fixture(tmp_path, monkeypatch)
    result = gap.run(path, '2021-22', ['Weymouth'], output)
    discovery = json.loads((output / 'query-discovery.json').read_text())
    assert discovery['query_club_ids'] == [3822]
    assert len(discovery['witnesses']) == 1
    assert result['updates'] == [] and result['native_writes'] == 0
    assert result['publication_authorised'] is False
    assert result['schema_version'] != json.loads(path.read_text()).get('schema_version')
    with pytest.raises(ValueError, match='immutable'):
        gap.run(path, '2021-22', ['Weymouth'], output)


@pytest.mark.parametrize('problem', ['missing-history', 'known-id', 'changed-entity-book', 'changed-pin'])
def test_discovery_does_not_guess_ids_or_accept_changed_bound_inputs(tmp_path, monkeypatch, problem):
    path, output = fixture(tmp_path, monkeypatch)
    if problem == 'missing-history':
        monkeypatch.setattr(gap.whole.transfer, 'transfer_interval', lambda *a: {'status': 'missing'})
    if problem == 'known-id':
        monkeypatch.setattr(gap.entities, 'read_entities', lambda p: {3822: {}})
    if problem == 'changed-entity-book':
        (tmp_path / 'entities.json').write_text('{}')
    if problem == 'changed-pin':
        monkeypatch.setattr(gap.context, 'load_snapshot', lambda *a: ({}, {}, {'path': 'other'}))
    with pytest.raises(ValueError):
        gap.run(path, '2021-22', ['Weymouth'], output)
    assert not output.exists()
