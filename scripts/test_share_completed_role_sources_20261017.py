from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import share_completed_role_sources_20261017 as subject


@pytest.fixture
def registry_fixture(tmp_path, monkeypatch):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    catalog = workspace / 'catalog.json'
    catalog.write_text('{}', encoding='utf-8')
    folder = workspace / '.local' / 'registry' / '2000-01'
    replay_id = 'replayed-sample-r101b'
    actual_id = 'sourced-sample-r101a'
    for release_id in ('unused', replay_id, actual_id):
        locator = folder / release_id / 'locator.json'
        locator.parent.mkdir(parents=True, exist_ok=True)
        locator.write_text('{}', encoding='utf-8')
    actual_game = workspace / 'old-actual-game'
    replay_game = workspace / '.local' / 'historical-role-deltas-v1' / '2000-01' / replay_id / 'game'
    actual_game.mkdir(parents=True)
    replay_game.mkdir(parents=True)
    base_package = actual_game / 'package.json'
    replay_package = replay_game / 'package.json'
    base_jug = actual_game / 'DBDAT' / 'JUG98030.FDI'
    replay_jug = replay_game / 'DBDAT' / 'JUG98030.FDI'
    for path in (base_package, replay_package, base_jug, replay_jug):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(path.name.encode())
    base = SimpleNamespace(package_path=base_package, game_path=actual_game)
    replay = SimpleNamespace(package_path=replay_package, game_path=replay_game)
    monkeypatch.setattr(subject.registry, 'ROOT', workspace)
    monkeypatch.setattr(subject.registry, 'CATALOG_PATH', catalog)
    monkeypatch.setattr(subject.registry, 'supported_seasons', lambda: ['2000-01'])
    monkeypatch.setattr(subject.registry, 'locator_path',
        lambda season, release_id: folder / release_id / 'locator.json')
    real_sha256_file = subject.registry.sha256_file
    monkeypatch.setattr(subject.registry, 'sha256_file',
        lambda path: real_sha256_file(path) if Path(path).is_file() else 'f' * 64)
    monkeypatch.setattr(subject.registry, 'relative_workspace_path',
        lambda path: Path(path).resolve().relative_to(workspace.resolve()).as_posix())
    monkeypatch.setattr(subject.registry, 'load_preferred_release',
        lambda season: SimpleNamespace(release_id='sourced-preferred-r1a'))
    monkeypatch.setattr(subject.registry, 'load_registered_release',
        lambda season, release_id: base if release_id == actual_id else replay)
    monkeypatch.setattr(subject, 'ROOT', workspace / '.local' / 'share-output')
    monkeypatch.setattr(subject, 'active', lambda path: False)
    monkeypatch.setattr(subject, 'assert_equal_games', lambda *args: None)
    monkeypatch.setattr(subject.shutil, 'disk_usage', lambda path: SimpleNamespace(free=1000))
    retained_calls = []
    monkeypatch.setattr(subject, 'retained', lambda path, value: retained_calls.append((path, value)))
    shares = []
    monkeypatch.setattr(subject, 'share_identical',
        lambda source, dest: shares.append((source, dest)) or {'former_unique_allocated_bytes': 10})
    return dict(workspace=workspace, folder=folder, replay_id=replay_id, actual_id=actual_id,
                base=base, replay=replay, retained=retained_calls, shares=shares)


def test_default_range_still_selects_and_shares_every_eligible_replay(registry_fixture):
    state = registry_fixture
    subject.main(min_revision=100, max_revision=116)
    assert len(state['shares']) == 2
    analysis = next(value for path, value in state['retained'] if path.name == 'analysis.json')
    assert analysis['selected_replays'] is None
    assert analysis['targets'] == [dict(season='2000-01', actual_release=state['actual_id'],
                                        replay_release=state['replay_id'])]
    completed = next(value for path, value in state['retained'] if path.name == 'completed.json')
    assert completed['rows']


def test_missing_selected_replay_fails_before_analysis_or_file_sharing(registry_fixture):
    state = registry_fixture
    with pytest.raises(ValueError, match='registrations absent or out of range'):
        subject.main(min_revision=100, max_revision=116,
                     selected_replays={('2001-02', 'replayed-missing-r101b')})
    assert state['shares'] == []
    assert state['retained'] == []


def test_selected_already_shared_replay_cannot_end_as_empty_success(registry_fixture):
    state = registry_fixture
    replay = state['replay']
    base = state['base']
    # Same file paths model package/JUG pairs already sharing one inode.
    replay.package_path.unlink()
    replay.package_path.hardlink_to(base.package_path)
    replay_jug = replay.game_path / 'DBDAT/JUG98030.FDI'
    base_jug = base.game_path / 'DBDAT/JUG98030.FDI'
    replay_jug.unlink()
    replay_jug.hardlink_to(base_jug)
    with pytest.raises(ValueError, match='already shared|no eligible selected replay'):
        subject.main(min_revision=100, max_revision=116,
                     selected_replays={('2000-01', state['replay_id'])})
    assert state['shares'] == []
    assert not any(path.name == 'completed.json' for path, _ in state['retained'])
