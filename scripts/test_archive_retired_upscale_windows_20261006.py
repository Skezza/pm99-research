import json
from types import SimpleNamespace
import pytest
from scripts import archive_retired_upscale_windows_20261006 as archive


def setup(tmp_path, monkeypatch):
    prefix = tmp_path / 'old-test-prefix'
    source = prefix / 'drive_c/windows'
    source.mkdir(parents=True)
    monkeypatch.setattr(archive, 'PREFIX', prefix)
    monkeypatch.setattr(archive, 'SOURCE', source)
    monkeypatch.setattr(archive.registry, 'supported_seasons', lambda: [])
    monkeypatch.setattr(archive.transport, '_active_game', lambda _: False)
    return prefix, source


def test_exact_unused_child_only(tmp_path, monkeypatch):
    _, source = setup(tmp_path, monkeypatch)
    archive.guard(source)
    with pytest.raises(ValueError, match='exact retired'):
        archive.guard(tmp_path)


def test_child_symlink_refused(tmp_path, monkeypatch):
    _, source = setup(tmp_path, monkeypatch)
    source.rmdir()
    source.symlink_to(tmp_path)
    with pytest.raises(ValueError, match='exact retired'):
        archive.guard(source)


def test_active_prefix_refused(tmp_path, monkeypatch):
    _, source = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(archive.transport, '_active_game', lambda _: True)
    with pytest.raises(ValueError, match='active'):
        archive.guard(source)


@pytest.mark.parametrize('inside', [False, True])
def test_current_game_and_recipe_are_protected(tmp_path, monkeypatch, inside):
    prefix, source = setup(tmp_path, monkeypatch)
    doc = tmp_path / 'recipe.json'
    doc.write_text(json.dumps({'artifact': 'wineprefix-enhanced/drive_c/windows/kernel32.dll'}))
    release = SimpleNamespace(game_path=prefix / 'current-game' if inside else tmp_path / 'current-game',
        locator={}, package_path=doc, release_manifest_path=doc,
        compiler_receipt_path=doc, build_chain_path=doc)
    monkeypatch.setattr(archive.registry, 'supported_seasons', lambda: ['2004-05'])
    monkeypatch.setattr(archive.registry, 'load_preferred_release', lambda _: release)
    with pytest.raises(ValueError, match='current game|current recipe'):
        archive.guard(source)
