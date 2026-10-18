import json
from types import SimpleNamespace

import pytest

from scripts import archive_superseded_ingress_games_20261004 as archive


@pytest.fixture
def sample(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, 'ROOT', tmp_path)
    monkeypatch.setattr(archive, 'OUTPUT', tmp_path / '.local/receipts')
    monkeypatch.setattr(archive.registry, 'LOCAL_ROOT', tmp_path / '.local/registry')
    monkeypatch.setattr(archive.registry, 'supported_seasons', lambda: ['2000-01'])
    source = tmp_path / '.local/season-static-ingress-v1/old/game'
    source.mkdir(parents=True)
    (source / 'MANAGPRE.EXE').write_bytes(b'test fixture')
    (source.parent / 'season-package.json').write_text('{}')
    release = SimpleNamespace(locator={'game_path': '.local/current/game'},
                              package_path=source.parent / 'season-package.json')
    monkeypatch.setattr(archive.registry, 'load_preferred_release', lambda s: release)
    monkeypatch.setattr(archive.transport, 'command', lambda args, stdin=None: '')
    def remote(shell, stdin=None):
        if shell.startswith('findmnt'):
            return archive.transport.DISK_UUID
        if shell.startswith('sha256sum '):
            return archive.compact.digest(archive.receipt_path(source)) + '  receipt.json'
        return ''
    monkeypatch.setattr(archive.transport, 'remote', remote)
    return source, release


@pytest.mark.parametrize('name', ['.local', '.local/season-static-ingress-v1',
                                 '.local/season-identity-repairs-v1/x/game',
                                 '.local/season-static-ingress-v1/x/DBDAT'])
def test_refuse_broad_or_current_roots(sample, name):
    assert not archive.selected_shape(archive.ROOT / name)


def test_keeps_recipe_and_sibling(sample):
    source, _ = sample
    sibling = source.parent / 'another-game'
    sibling.mkdir()
    result = archive.archive(source)
    assert result['local_removed'] and result['archive_verified']
    assert not source.exists() and sibling.exists()
    assert (source.parent / 'season-package.json').exists()
    assert (source.parent / 'game.pi-archive.json').exists()


def test_current_nested_dependency_protected(sample):
    source, release = sample
    release.locator['extra'] = {'path': source.relative_to(archive.ROOT).as_posix() + '/DBDAT/file'}
    with pytest.raises(ValueError, match='current release'):
        archive.archive(source)
    assert source.exists()


def test_recipe_dependency_protected(sample):
    source, release = sample
    release.package_path.write_text(json.dumps({'input': str(source / 'DBDAT/file')}))
    with pytest.raises(ValueError, match='current recipe'):
        archive.archive(source)


def test_bad_mount_stops_removal(sample, monkeypatch):
    source, _ = sample
    monkeypatch.setattr(archive.transport, 'remote', lambda shell, stdin=None: 'wrong disk')
    with pytest.raises(ValueError, match='expected UUID'):
        archive.archive(source)
    assert source.exists()


def test_archive_difference_stops_removal(sample, monkeypatch):
    source, _ = sample
    monkeypatch.setattr(archive.transport, 'command',
                        lambda args, stdin=None: 'changed file' if '-rcni' in args else '')
    with pytest.raises(ValueError, match='comparison differs'):
        archive.archive(source)
    assert source.exists()


def test_local_change_stops_removal(sample, monkeypatch):
    source, _ = sample
    def command(args, stdin=None):
        if '-rcni' in args:
            (source / 'MANAGPRE.EXE').write_bytes(b'changed fixture')
        return ''
    monkeypatch.setattr(archive.transport, 'command', command)
    with pytest.raises(ValueError, match='source changed'):
        archive.archive(source)
    assert source.exists()


def test_symlink_stops_removal(sample):
    source, _ = sample
    original = source.rename(source.parent / 'original')
    source.symlink_to(original, target_is_directory=True)
    with pytest.raises(ValueError, match='permitted game child'):
        archive.archive(source)
    assert original.exists()


def test_final_receipt_check_requires_completed_archive(sample, monkeypatch):
    source, _ = sample
    archive.save(archive.OUTPUT / 'plan.json',
                 {'targets': [source.relative_to(archive.ROOT).as_posix()]})
    archive.archive(source)
    monkeypatch.setattr(archive.sys, 'argv', ['archive', '--verify-receipts'])
    archive.main()
    report = json.loads((archive.OUTPUT / 'final-receipt-verification.json').read_text())
    assert report['completed_archives'] == 1
    assert report['all_completed_remote_receipt_sha256s_match']


def test_current_validation_detects_catalogue_change(sample, monkeypatch):
    monkeypatch.setattr(archive.registry, 'validate_preferred_release', lambda s, level: {'valid': True})
    catalog = archive.ROOT / 'catalog.json'
    catalog.write_text('{}')
    monkeypatch.setattr(archive.registry, 'CATALOG_PATH', catalog)
    archive.save(archive.OUTPUT / 'plan.json', {'catalogue_sha256': 'not the current hash'})
    monkeypatch.setattr(archive.sys, 'argv', ['archive', '--verify-current'])
    with pytest.raises(ValueError, match='current release validation failed'):
        archive.main()
    report = json.loads((archive.OUTPUT / 'post-cleanup-current-release-validation.json').read_text())
    assert not report['valid'] and not report['catalogue_unchanged']
