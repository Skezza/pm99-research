import json
from types import SimpleNamespace

import pytest

from scripts import pm99_season_play_v1 as play
from scripts import season_pipeline_v2 as pipeline


def test_original_session_never_mutates_or_hardlinks_backup(tmp_path, monkeypatch):
    monkeypatch.setattr(play, 'ROOT', tmp_path)
    source = tmp_path / 'original'
    source.mkdir()
    (source / 'MANAGPRE.EXE').write_bytes(b'original game')
    (source / 'manager.ini').write_bytes(b'original settings')
    inventory = tmp_path / 'inventory.json'
    pipeline.write_canonical_json(inventory, pipeline.build_tree_inventory(source))
    release = SimpleNamespace(game_path=source, inventory_path=inventory,
        locator={'required_file_hashes': {'MANAGPRE.EXE': play.registry.sha256_file(source / 'MANAGPRE.EXE')}})
    target = play.original_session_game(release)
    assert (target / 'MANAGPRE.EXE').read_bytes() == b'original game'
    assert (target / 'MANAGPRE.EXE').stat().st_ino != (source / 'MANAGPRE.EXE').stat().st_ino
    (target / 'manager.ini').write_bytes(b'played settings')
    assert (source / 'manager.ini').read_bytes() == b'original settings'
    assert play.original_session_game(release) == target
    (target / 'MANAGPRE.EXE').write_bytes(b'changed')
    with pytest.raises(ValueError, match='changed'):
        play.original_session_game(release)


def test_print_original_command_does_not_change_catalog_or_launch(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(play, 'ROOT', tmp_path)
    monkeypatch.setattr(play.sys, 'argv', ['pm99-season', '2015-16', '--original', '--print-command'])
    release = SimpleNamespace(game_path=tmp_path, inventory_path=tmp_path / 'inventory.json')
    pipeline.write_canonical_json(release.inventory_path, {})
    monkeypatch.setattr(play, 'load_original_release', lambda: release)
    monkeypatch.setattr(play.registry, 'validate_preferred_release', lambda *args, **kwargs: {'valid': True})
    monkeypatch.setattr(play.pipeline, 'assert_tree_matches_inventory', lambda *args: None)
    assert play.main() == 0
    assert '--original' in capsys.readouterr().out
    assert not (tmp_path / '.local').exists()


def test_original_flag_is_not_applied_to_other_seasons(monkeypatch):
    monkeypatch.setattr(play.sys, 'argv', ['pm99-season', '2014-15', '--original'])
    with pytest.raises(SystemExit) as raised:
        play.main()
    assert raised.value.code == 2


def test_original_backup_locator_is_locked_to_retention_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(play, 'ROOT', tmp_path)
    monkeypatch.setattr(play.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(play.registry, 'LOCAL_ROOT', tmp_path / 'registry')
    locator = play.registry.locator_path('2015-16', play.ORIGINAL_RELEASE)
    locator.parent.mkdir(parents=True); locator.write_text('{}')
    inventory = tmp_path / 'inventory.json'; inventory.write_text('{}')
    release = SimpleNamespace(inventory_path=inventory)
    monkeypatch.setattr(play.registry, 'load_registered_release', lambda *args: release)
    row = {'season': '2015-16', 'release_id': play.ORIGINAL_RELEASE,
           'locator_path': play.registry.relative_workspace_path(locator),
           'locator_sha256': play.registry.sha256_file(locator),
           'inventory_sha256': play.registry.sha256_file(inventory)}
    ledger = tmp_path / 'data/retained-season-releases-v1.json'
    ledger.parent.mkdir(); ledger.write_text(json.dumps({'releases': [row]}))
    assert play.load_original_release() == release
    locator.write_text('{"changed":true}')
    with pytest.raises(ValueError, match='locator differs'):
        play.load_original_release()
