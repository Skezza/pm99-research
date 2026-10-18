from types import SimpleNamespace
import pytest

from scripts import archive_completed_arsenal_replays_20261016 as archive


def fixture(tmp_path, monkeypatch):
    a = tmp_path / 'actual.json'; b = tmp_path / 'replay.json'
    a.write_bytes(b'original'); b.write_bytes(b'original')
    base = SimpleNamespace(package_path=a, inventory_path='actual-inventory', game_path='actual-game')
    replay = SimpleNamespace(package_path=b, inventory_path='replay-inventory', game_path='replay-game')
    docs = {'actual-inventory': {'files': ['exact']}, 'replay-inventory': {'files': ['exact']}}
    monkeypatch.setattr(archive.pipeline, 'read_json_file', lambda p: docs[p])
    monkeypatch.setattr(archive.pipeline, 'assert_tree_matches_inventory', lambda *a: None)
    return base, replay, docs


def test_equal_game_and_recipe_are_required(tmp_path, monkeypatch):
    base, replay, _ = fixture(tmp_path, monkeypatch)
    assert archive.assert_equal_games(base, replay) == {'files': ['exact']}


def test_different_inventory_cannot_be_retired_as_duplicate(tmp_path, monkeypatch):
    base, replay, docs = fixture(tmp_path, monkeypatch)
    docs['replay-inventory'] = {'files': ['unique']}
    with pytest.raises(ValueError, match='inventory differs'):
        archive.assert_equal_games(base, replay)


def test_different_recipe_cannot_be_retired_as_duplicate(tmp_path, monkeypatch):
    base, replay, _ = fixture(tmp_path, monkeypatch)
    replay.package_path.write_bytes(b'unique edits')
    with pytest.raises(ValueError, match='recipe differs'):
        archive.assert_equal_games(base, replay)


def test_physical_game_verification_failure_is_not_ignored(tmp_path, monkeypatch):
    base, replay, _ = fixture(tmp_path, monkeypatch)
    def fail(*args):
        raise ValueError('actual bytes changed')
    monkeypatch.setattr(archive.pipeline, 'assert_tree_matches_inventory', fail)
    with pytest.raises(ValueError, match='bytes changed'):
        archive.assert_equal_games(base, replay)
