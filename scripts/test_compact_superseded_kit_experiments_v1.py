"""Compaction may remove only exact targets after preserving their unique bytes."""
import json

import pytest

from scripts import compact_superseded_kit_experiments_v1 as compact


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / 'workspace'
    root.mkdir()
    base = root / 'retained'
    base.mkdir()
    (base / 'shared.dat').write_bytes(b'same')
    (base / 'kit.dat').write_bytes(b'new kit')
    old = root / 'old'
    old.mkdir()
    (old / 'shared.dat').write_bytes(b'same')
    (old / 'kit.dat').write_bytes(b'old kit')
    (old / 'extra.dat').write_bytes(b'only in old')
    monkeypatch.setattr(compact, 'WORKSPACE', root)
    monkeypatch.setattr(compact, 'BASE', base)
    monkeypatch.setattr(compact, 'OUTPUT', tmp_path / 'deltas')
    monkeypatch.setattr(compact, 'TARGETS', ('old',))
    return old, base


def test_default_keeps_original_and_saves_only_changed_files(workspace):
    old, base = workspace
    result = compact.run()
    assert old.is_dir()
    assert sorted(result[0]['delta_files']) == ['extra.dat', 'kit.dat']
    assert not (compact.OUTPUT / 'old/files/shared.dat').exists()
    compact.verify_retained()


def test_verified_deletion_leaves_base_and_recoverable_deltas(workspace):
    old, base = workspace
    compact.run(delete=True)
    assert not old.exists()
    assert base.is_dir()
    compact.verify_retained()
    assert (compact.OUTPUT / 'old/files/kit.dat').read_bytes() == b'old kit'


def test_symlink_target_is_never_deleted(workspace):
    old, base = workspace
    (old / 'link').symlink_to(base / 'shared.dat')
    with pytest.raises(ValueError, match='symlink'):
        compact.run(delete=True)
    assert old.exists()


def test_changed_base_invalidates_recoverability(workspace):
    old, base = workspace
    compact.run(delete=True)
    (base / 'shared.dat').write_bytes(b'changed')
    with pytest.raises(ValueError, match='Reconstruction input mismatch'):
        compact.verify_retained()


def test_copy_hash_mismatch_preserves_original(workspace, monkeypatch):
    old, _ = workspace
    def corrupt_copy(source, destination):
        destination.write_bytes(b'corrupt')
    monkeypatch.setattr(compact.shutil, 'copy2', corrupt_copy)
    with pytest.raises(ValueError, match='verification failed'):
        compact.run(delete=True)
    assert old.exists()
