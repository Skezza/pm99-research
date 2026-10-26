from pathlib import Path
import json
import pytest
from scripts import season_annual_literal_broad_position_v1 as annual
from scripts import season_source_verified_player_changes_v1 as common
from scripts import season_release_registry_v1 as registry


def test_generic_request_does_not_require_a_private_audit_file(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, 'ROOT', tmp_path)
    path = tmp_path / 'request.json'
    value = {'schema': 'pm99-annual-literal-broad-position-input-v1',
             'kind': annual.KIND, 'changes': [{'case_id': 'example'}]}
    path.write_text(json.dumps(value))
    assert annual._read_input(path) == value
    value['kind'] = 'infer-position-from-pitch-coordinate'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='schema/kind'):
        annual._read_input(path)


def test_source_binding_rejects_a_symlinked_parent_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, 'ROOT', tmp_path)
    original = tmp_path / 'original'
    original.mkdir()
    source = original / 'source.txt'
    source.write_text('source')
    (tmp_path / 'alias').symlink_to(original, target_is_directory=True)
    with pytest.raises(ValueError, match='symlinks'):
        annual._root_file({'path': 'alias/source.txt', 'sha256': registry.sha256_file(source)})


@pytest.mark.parametrize('name,args', [('verify', ('base',)), ('validate_mask', ()),
                                     ('bind', ('package',)), ('apply', ('jug', 'eq'))])
def test_common_dispatch_preserves_the_typed_annual_lane(monkeypatch, name, args):
    plan = {'kind': annual.KIND}
    calls = []
    monkeypatch.setattr(annual, name, lambda *values: calls.append(values) or 'annual-result')
    values = (*args, plan)
    assert getattr(common, name)(*values) == 'annual-result'
    assert calls == [values]


def test_common_filename_and_artifact_identity_use_the_annual_provider():
    plan = {'kind': annual.KIND, 'transaction_id': 'a' * 24}
    assert common.filename(plan) == annual.filename(plan)
    assert common.artifact_id(plan) == annual.artifact_id(plan)


def test_common_prepare_dispatches_only_an_explicit_annual_request(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, 'ROOT', tmp_path)
    path = tmp_path / 'request.json'
    path.write_text(json.dumps({'kind': annual.KIND}))
    calls = []
    monkeypatch.setattr(annual, 'prepare', lambda *values: calls.append(values) or 'annual-result')
    assert common.prepare('base', path) == 'annual-result'
    assert calls == [('base', path)]
