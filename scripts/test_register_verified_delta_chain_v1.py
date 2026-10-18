from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts import register_verified_delta_chain_v1 as subject


def setup(monkeypatch):
    releases = {}
    docs = {}
    for name, previous in (('base', None), ('private', 'base'), ('final', 'private')):
        obj = SimpleNamespace(release_id=name, manifest_sha256=name+'-manifest',
            package_path=Path(name+'-recipe'), compiler_receipt_path=Path(name+'-receipt'),
            build_chain_path=Path(name+'-chain'), inventory_path=Path(name+'-inventory'),
            release_manifest_path=Path(name+'-manifest'), game_path=Path(name+'-game'),
            locator=dict(package_canonical_sha256=name+'-recipe', required_file_hashes={}))
        releases[name] = obj
        docs[obj.compiler_receipt_path] = dict(source_season_package_sha256=str(previous)+'-recipe',
            source_compiler_receipt_sha256=str(previous)+'-receipt',
            source_build_chain_sha256=str(previous)+'-chain')
    current = [releases['base']]
    monkeypatch.setattr(subject.registry, 'load_preferred_release', lambda s: current[0])
    monkeypatch.setattr(subject.registry, 'load_registered_release', lambda s, r: releases[r])
    monkeypatch.setattr(subject.registry, 'canonical_document_sha256', lambda p: str(p))
    monkeypatch.setattr(subject.registry, 'sha256_file', lambda p: str(p))
    monkeypatch.setattr(subject.pipeline, 'read_json_file', lambda p: docs.get(p, {}))
    monkeypatch.setattr(subject.pipeline, 'assert_tree_matches_inventory', lambda *a: None)
    monkeypatch.setattr(subject.pipeline, 'validate_release_manifest', lambda *a: None)
    monkeypatch.setattr(subject.registry, 'load_catalog', lambda: {'other': {'release_id': 'untouched'}})
    writes = []
    monkeypatch.setattr(subject, '_atomic_replace_json', lambda p, d: writes.append(d))
    return releases, docs, current, writes


def test_private_intermediate_never_becomes_preferred(monkeypatch):
    releases, docs, current, writes = setup(monkeypatch)
    result = subject.register_chain('season', ['private', 'final'])
    assert result['catalog_writes'] == 1
    assert not result['intermediate_releases_promoted']
    assert len(writes) == 1
    assert writes[0]['seasons'] == [{'release_id': 'untouched'}, dict(season='season',
        release_id='final', release_manifest_sha256='final-manifest')]


@pytest.mark.parametrize('ids', [[], ['private', 'private'], ['final'], ['base'], ['final', 'private']])
def test_bad_or_skipped_ancestry_never_writes(monkeypatch, ids):
    *_, writes = setup(monkeypatch)
    with pytest.raises(ValueError):
        subject.register_chain('season', ids)
    assert writes == []


@pytest.mark.parametrize('field', ['source_season_package_sha256',
    'source_compiler_receipt_sha256', 'source_build_chain_sha256'])
def test_changed_ancestry_hash_never_writes(monkeypatch, field):
    releases, docs, current, writes = setup(monkeypatch)
    docs[releases['final'].compiler_receipt_path][field] = 'tampered'
    with pytest.raises(ValueError, match='parent'):
        subject.register_chain('season', ['private', 'final'])
    assert writes == []


def test_changed_preferred_during_check_never_writes(monkeypatch):
    releases, docs, current, writes = setup(monkeypatch)
    def checked(*args):
        current[0] = releases['private']
        return releases['base'], releases['final']
    monkeypatch.setattr(subject, 'check_chain', checked)
    with pytest.raises(ValueError, match='moved'):
        subject.register_chain('season', ['private', 'final'])
    assert writes == []


@pytest.mark.parametrize('kind', ['inventory', 'recipe', 'native', 'manifest'])
def test_changed_child_evidence_never_writes(monkeypatch, kind):
    releases, docs, current, writes = setup(monkeypatch)
    if kind == 'inventory':
        def fail(*args): raise ValueError('changed inventory')
        monkeypatch.setattr(subject.pipeline, 'assert_tree_matches_inventory', fail)
    elif kind == 'recipe':
        releases['final'].locator['package_canonical_sha256'] = 'changed'
    elif kind == 'native':
        releases['final'].locator['required_file_hashes'] = {'DBDAT/JUG98030.FDI': 'changed'}
    else:
        releases['final'].manifest_sha256 = 'changed'
    with pytest.raises(ValueError):
        subject.register_chain('season', ['private', 'final'])
    assert writes == []
