import json
from types import SimpleNamespace
import pytest
from scripts import archive_old_crash_probe_assets_20261006 as old


def fixture(tmp_path, monkeypatch):
    probes = tmp_path / 'probes'
    source = probes / old.NAMES[0]
    source.mkdir(parents=True)
    monkeypatch.setattr(old, 'ROOT', tmp_path)
    monkeypatch.setattr(old, 'PROBES', probes)
    monkeypatch.setattr(old.archive, '_active_game', lambda _: False)
    monkeypatch.setattr(old.registry, 'LOCAL_ROOT', tmp_path / 'registry')
    monkeypatch.setattr(old.registry, 'supported_seasons', lambda: [])
    return source


def test_only_exact_unregistered_old_probe_names_are_allowed(tmp_path, monkeypatch):
    source = fixture(tmp_path, monkeypatch)
    assert old.guard_probe(old.NAMES[0]) == source
    with pytest.raises(ValueError, match='exact old crash-probe'):
        old.guard_probe('../current-game')


def test_registered_old_release_is_not_stripped(tmp_path, monkeypatch):
    source = fixture(tmp_path, monkeypatch)
    locator = old.registry.LOCAL_ROOT / 'releases/2004-05/old/locator.json'
    locator.parent.mkdir(parents=True)
    locator.write_text(json.dumps({'game_path': str(source)}))
    with pytest.raises(ValueError, match='registered historical game'):
        old.guard_probe(old.NAMES[0])


def test_running_probe_is_protected(tmp_path, monkeypatch):
    fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(old.archive, '_active_game', lambda _: True)
    with pytest.raises(ValueError, match='currently running'):
        old.guard_probe(old.NAMES[0])


def nested_fixture(tmp_path, monkeypatch):
    fixture(tmp_path, monkeypatch)
    name = '2004-05-stoke-only'
    source = old.PROBES / name / 'ingress/game'
    source.mkdir(parents=True)
    return name, source


def test_exact_nested_installation_is_resolved(tmp_path, monkeypatch):
    name, source = nested_fixture(tmp_path, monkeypatch)
    assert old.guard_probe(name) == source


def test_registered_nested_installation_is_protected(tmp_path, monkeypatch):
    name, source = nested_fixture(tmp_path, monkeypatch)
    locator = old.registry.LOCAL_ROOT / 'releases/2004-05/old/locator.json'
    locator.parent.mkdir(parents=True)
    locator.write_text(json.dumps({'game_path': str(source)}))
    with pytest.raises(ValueError, match='registered historical game'):
        old.guard_probe(name)


def test_running_nested_installation_is_protected(tmp_path, monkeypatch):
    name, source = nested_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(old.archive, '_active_game', lambda path: path == source)
    with pytest.raises(ValueError, match='currently running'):
        old.guard_probe(name)


def test_nested_game_symlink_is_refused(tmp_path, monkeypatch):
    name, source = nested_fixture(tmp_path, monkeypatch)
    source.rmdir()
    source.symlink_to(tmp_path)
    with pytest.raises(ValueError, match='exact non-symlink'):
        old.guard_probe(name)


def test_nested_asset_reference_in_current_recipe_is_protected(tmp_path, monkeypatch):
    name, source = nested_fixture(tmp_path, monkeypatch)
    package = tmp_path / 'package.json'
    package.write_text(json.dumps({'asset': str((source / 'SFX').relative_to(tmp_path))}))
    monkeypatch.setattr(old.registry, 'supported_seasons', lambda: ['2004-05'])
    monkeypatch.setattr(old.registry, 'load_preferred_release', lambda _: SimpleNamespace(
        game_path=tmp_path / 'current-game', package_path=package,
        release_manifest_path=package, compiler_receipt_path=package, build_chain_path=package))
    with pytest.raises(ValueError, match='directly depends'):
        old.guard_probe(name)
