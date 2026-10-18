import json
from types import SimpleNamespace

import pytest

from scripts import archive_retired_season_tests_20261004 as archive


@pytest.fixture
def setup_archive(tmp_path, monkeypatch):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    source = workspace / archive.TARGETS[0]
    source.mkdir()
    (source / 'original.bin').write_bytes(b'original test data')
    monkeypatch.setattr(archive, 'WORKSPACE', workspace)
    monkeypatch.setattr(archive, 'RECEIPTS', tmp_path / 'receipts')
    monkeypatch.setattr(archive.registry, 'LOCAL_ROOT', tmp_path / 'registry')
    monkeypatch.setattr(archive.registry, 'supported_seasons', lambda: ['2000-01'])
    monkeypatch.setattr(archive.registry, 'load_preferred_release',
                        lambda season: SimpleNamespace(game_path=tmp_path / 'current'))
    monkeypatch.setattr(archive, '_active_game', lambda path: False)
    calls = []

    def fake_command(args, stdin=None):
        calls.append(args)
        return ''

    def fake_remote(shell, stdin=None):
        calls.append(shell)
        return archive.DISK_UUID + '\n' if shell.startswith('findmnt') else ''

    monkeypatch.setattr(archive, 'command', fake_command)
    monkeypatch.setattr(archive, 'remote', fake_remote)
    return source, calls


def test_read_only_default(setup_archive):
    source, calls = setup_archive
    assert archive.archive(source.name)['status'] == 'eligible'
    assert source.exists() and not calls


def test_verified_archive_removes_only_exact_target(setup_archive):
    source, calls = setup_archive
    sibling = source.parent / 'keep-current-game'
    sibling.mkdir()
    assert archive.archive(source.name, True)['local_removed']
    assert not source.exists() and sibling.exists()
    receipt = json.loads((archive.RECEIPTS / source.name / 'receipt.json').read_text())
    assert receipt['archive_verified'] and receipt['file_count'] == 1
    assert any(isinstance(c, str) and 'sha256sum --check --quiet' in c for c in calls)
    assert any(isinstance(c, list) and c[:2] == ['rsync', '-rcni'] for c in calls)


@pytest.mark.parametrize('kind', ['unknown', 'preferred', 'active', 'registered', 'symlink'])
def test_unsafe_target_is_never_removed(setup_archive, monkeypatch, kind):
    source, calls = setup_archive
    if kind == 'unknown':
        source = source.rename(source.parent / 'not-allowlisted')
    elif kind == 'preferred':
        monkeypatch.setattr(archive.registry, 'load_preferred_release',
                            lambda season: SimpleNamespace(game_path=source))
    elif kind == 'active':
        monkeypatch.setattr(archive, '_active_game', lambda path: True)
    elif kind == 'registered':
        locator = archive.registry.LOCAL_ROOT / 'releases/2000-01/old/locator.json'
        locator.parent.mkdir(parents=True)
        locator.write_text(json.dumps({'game_path': str(source)}))
    else:
        actual = source.rename(source.parent / 'keep-original')
        source.symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError):
        archive.archive(source.name, True)
    assert source.exists() and not calls


def test_remote_difference_prevents_removal(setup_archive, monkeypatch):
    source, _ = setup_archive
    monkeypatch.setattr(archive, 'command',
                        lambda args, stdin=None: 'changed file\n' if '-rcni' in args else '')
    with pytest.raises(ValueError, match='dry-run'):
        archive.archive(source.name, True)
    assert source.exists()


def test_wrong_disk_prevents_removal(setup_archive, monkeypatch):
    source, _ = setup_archive
    monkeypatch.setattr(archive, 'remote', lambda shell, stdin=None: 'wrong-disk')
    with pytest.raises(ValueError, match='expected mounted disk'):
        archive.archive(source.name, True)
    assert source.exists()


def test_changed_source_prevents_removal(setup_archive, monkeypatch):
    source, _ = setup_archive

    def mutate(args, stdin=None):
        if '-rcni' in args:
            (source / 'original.bin').write_bytes(b'changed after the backup')
        return ''

    monkeypatch.setattr(archive, 'command', mutate)
    with pytest.raises(ValueError, match='changed during backup'):
        archive.archive(source.name, True)
    assert source.exists()


def test_only_completed_archive_can_seed_common_files(setup_archive):
    source, calls = setup_archive
    receipt = archive.RECEIPTS / source.name / 'receipt.json'
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({'remote': archive.REMOTE + '/' + source.name,
                                   'archive_verified': True, 'local_removed': False}))
    with pytest.raises(ValueError, match='not complete'):
        archive.seed_common_archive_files()
    assert not calls
    archive.archive(source.name, True)
    calls.clear()
    archive.seed_common_archive_files()
    seeds = [c for c in calls if isinstance(c, str) and 'cp -al' in c]
    assert len(seeds) == 14
    assert not any('2015-16' in c for c in seeds)
