from types import SimpleNamespace
import copy
import pytest
from scripts import capture_exact_position_batch_20261017 as batch
from scripts import capture_shinnie_country_20261017 as shared


def test_two_changed_players_capture_startup_once_not_twice(monkeypatch, tmp_path):
    season = '2016-17'; folder = tmp_path / season; folder.mkdir()
    (folder / 'complete-SOURCE-replay.json').touch()
    monkeypatch.setattr(batch.build, 'ROOT', tmp_path)
    monkeypatch.setattr(batch.build.registry, 'load_registered_release',
        lambda *args: SimpleNamespace(manifest_sha256='actual-game'))
    monkeypatch.setattr(batch.build.pipeline, 'read_json_file', lambda path: dict(updates=[
        dict(carrier_id=1, before_player=dict(name='First Player')),
        dict(carrier_id=2, before_player=dict(name='Second Player'))]))
    monkeypatch.setattr(batch.build.source.fifa, 'names', lambda p: {p['name']})
    monkeypatch.setattr(batch, 'retained', lambda *args: None)
    calls = []
    monkeypatch.setattr(batch, 'capture', lambda *args, **kwargs: calls.append(kwargs))
    batch.main(season, 0)
    assert [c['capture_startup'] for c in calls] == [True, False]
    assert [c['profile']['carrier_id'] for c in calls] == [1, 2]
    assert len({c['run_tag'] for c in calls}) == 1


@pytest.mark.parametrize('problem', [None, 'failed', 'manifest', 'evidence', 'summary', 'crash', 'fingerprint'])
def test_startup_reuse_requires_exact_successful_same_game(monkeypatch, tmp_path, problem):
    transport = dict(exit_code=0, evidence='exact-evidence', release_manifest_sha256='actual')
    summary = dict(success=True, release_manifest_sha256='actual', output_inventory_fingerprint='files')
    if problem == 'failed': transport['exit_code'] = 3
    if problem == 'manifest': transport['release_manifest_sha256'] = 'other'
    if problem == 'evidence': transport['evidence'] = 'other'
    if problem == 'summary': summary['success'] = False
    if problem == 'crash': summary['crash_detected'] = True
    if problem == 'fingerprint': summary['output_inventory_fingerprint'] = 'other'
    monkeypatch.setattr(shared.registry, 'relative_workspace_path', lambda p: 'exact-evidence')
    monkeypatch.setattr(shared.pipeline, 'read_json_file',
        lambda p: copy.deepcopy(transport if p.name == 'startup-transport.json' else summary))
    release = SimpleNamespace(manifest_sha256='actual', locator=dict(game_inventory_fingerprint='files'))
    if problem is None:
        shared.verify_existing_startup(tmp_path, tmp_path, release)
    else:
        with pytest.raises(ValueError, match='cannot reuse'):
            shared.verify_existing_startup(tmp_path, tmp_path, release)
