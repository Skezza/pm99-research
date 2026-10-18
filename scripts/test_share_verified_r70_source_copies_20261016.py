from pathlib import Path
import pytest
from scripts import share_verified_r70_source_copies_20261016 as share


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(share.registry, 'ROOT', tmp_path)
    a = tmp_path / 'actual.json'; b = tmp_path / 'source.json'
    a.write_bytes(b'exact original'); b.write_bytes(b'exact original')
    return a, b


def test_sharing_keeps_both_paths_and_exact_original_bytes(tmp_path, monkeypatch):
    a, b = fixture(tmp_path, monkeypatch)
    proof = share.share_identical(a, b)
    assert a.exists() and b.exists() and a.read_bytes() == b.read_bytes() == b'exact original'
    assert a.stat().st_ino == b.stat().st_ino
    assert proof['both_paths_retained'] and not proof['already_shared']


def test_distinct_source_bytes_cannot_be_silently_dropped(tmp_path, monkeypatch):
    a, b = fixture(tmp_path, monkeypatch); b.write_bytes(b'edited recipe')
    with pytest.raises(ValueError, match='bytes differ'):
        share.share_identical(a, b)
    assert b.read_bytes() == b'edited recipe' and a.stat().st_ino != b.stat().st_ino


def test_symlink_cannot_escape_exact_copy_scope(tmp_path, monkeypatch):
    a, b = fixture(tmp_path, monkeypatch); b.unlink(); b.symlink_to(a)
    with pytest.raises(ValueError, match='symlink'):
        share.share_identical(a, b)


def test_unreceipted_temporary_is_not_overwritten(tmp_path, monkeypatch):
    a, b = fixture(tmp_path, monkeypatch)
    temporary = b.with_name(b.name + '.verified-r70-link'); temporary.write_bytes(b'unknown')
    with pytest.raises(ValueError, match='unreceipted'):
        share.share_identical(a, b)
    assert temporary.read_bytes() == b'unknown'


def test_already_shared_bytes_are_not_counted_twice(tmp_path, monkeypatch):
    a, b = fixture(tmp_path, monkeypatch)
    share.share_identical(a, b)
    proof = share.share_identical(a, b)
    assert proof['already_shared'] and proof['former_unique_allocated_bytes'] == 0
