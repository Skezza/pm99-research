"""Small discovery safeguards; no proprietary corpus or game mutations."""
import json
from types import SimpleNamespace
import pytest
from scripts import consolidated_season_discovery_v1 as discovery


def test_completed_evidence_cannot_be_overwritten(tmp_path):
    path = tmp_path / 'evidence.json'
    discovery.write_new(path, {'value': 'first'})
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        discovery.write_new(path, {'value': 'second'})
    assert path.read_bytes() == before


def test_evidence_preserves_unicode_and_is_parseable(tmp_path):
    path = tmp_path / 'nested' / 'evidence.json'
    value = {'name': 'Júlio César', 'scope': 'candidate, not confirmed error'}
    discovery.write_new(path, value)
    assert json.loads(path.read_text()) == value


def test_snapshot_binds_manifest_inventory_and_each_layer(tmp_path, monkeypatch):
    files = [tmp_path / name for name in ('recipe', 'manifest', 'inventory', 'english')]
    for i, path in enumerate(files):
        path.write_text(str(i))
    release = SimpleNamespace(release_id='known-good', package_path=files[0],
                              release_manifest_path=files[1], inventory_path=files[2])
    monkeypatch.setattr(discovery.registry, 'supported_seasons', lambda: ['2015-16'])
    monkeypatch.setattr(discovery.registry, 'load_preferred_release', lambda season: release)
    monkeypatch.setattr(discovery.layers, 'package_layers', lambda release:
                        [('main', {}, files[0]), ('english', {}, files[3])])
    before = discovery.bindings()
    files[3].write_text('changed secondary layer')
    after = discovery.bindings()
    assert before[0]['package_sha256'] == after[0]['package_sha256']
    assert before != after
    assert before[0]['manifest_sha256'] == discovery.registry.sha256_file(files[1])
    assert before[0]['inventory_sha256'] == discovery.registry.sha256_file(files[2])
