"""Share identical immutable old SOURCE recipe/JUG copies, keeping all paths.

No release/workspace/source is removed. Both complete games and recipes must
independently match before and after, as in the existing manager replay builder.
"""
import os
import shutil
from datetime import UTC, datetime
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.archive_completed_arsenal_replays_20261016 import assert_equal_games, active
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/cleanup-20261016/shared-r70-SOURCE-copies'
SEASONS = ('2020-21', '2021-22', '2022-23', '2023-24', '2024-25', '2025-26')
ACTUAL = 'sourced-cross-period-birth-years-20261010-r70a'
REPLAY = 'replayed-cross-period-birth-years-20261010-r70b'


def share_identical(original, duplicate):
    if original.is_symlink() or duplicate.is_symlink() or original.resolve() == duplicate.resolve():
        raise ValueError('unexpected or symlink sharing target')
    before = registry.sha256_file(original)
    if before != registry.sha256_file(duplicate):
        raise ValueError('SOURCE bytes differ; sharing forbidden')
    if original.stat().st_dev != duplicate.stat().st_dev:
        raise ValueError('different filesystems cannot share this proof')
    temporary = duplicate.with_name(duplicate.name + '.verified-r70-link')
    if temporary.exists():
        raise ValueError('unreceipted old sharing temporary')
    already = original.stat().st_ino == duplicate.stat().st_ino
    recoverable = duplicate.stat().st_blocks * 512 if duplicate.stat().st_nlink == 1 and not already else 0
    if not already:
        os.link(original, temporary)
        os.replace(temporary, duplicate)
    if original.stat().st_ino != duplicate.stat().st_ino or registry.sha256_file(duplicate) != before:
        raise ValueError('shared SOURCE inode or original bytes differ')
    return dict(original=registry.relative_workspace_path(original), shared_copy=registry.relative_workspace_path(duplicate),
        sha256=before, already_shared=already, former_unique_allocated_bytes=recoverable,
        both_paths_retained=True)


def main():
    if (ROOT / 'completed.json').exists():
        raise ValueError('completed sharing must not repeat')
    ROOT.mkdir(parents=True, exist_ok=True)
    catalog = registry.sha256_file(registry.CATALOG_PATH)
    free = shutil.disk_usage(registry.ROOT).free; rows = []
    for season in SEASONS:
        path = ROOT / (season + '.json')
        if path.exists():
            proof = pipeline.read_json_file(path)
            for row in proof['shared_files']:
                a, b = registry.ROOT / row['original'], registry.ROOT / row['shared_copy']
                if a.stat().st_ino != b.stat().st_ino or registry.sha256_file(a) != row['sha256'] or registry.sha256_file(b) != row['sha256']:
                    raise ValueError('recorded shared source changed')
            rows.append(dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path)))
            continue
        base = registry.load_registered_release(season, ACTUAL)
        replay = registry.load_registered_release(season, REPLAY)
        expected = registry.ROOT / '.local/historical-role-deltas-v1' / season / REPLAY
        if replay.game_path != expected / 'game' or active(expected) or active(base.game_path.parent):
            raise ValueError('wrong or active immutable SOURCE/actual target')
        if registry.load_preferred_release(season).release_id in (ACTUAL, REPLAY):
            raise ValueError('only completed old nonpreferred copies may be shared')
        assert_equal_games(base, replay)
        shared = [share_identical(a, b) for a, b in ((base.package_path, replay.package_path),
            (base.game_path / 'DBDAT/JUG98030.FDI', replay.game_path / 'DBDAT/JUG98030.FDI'))]
        assert_equal_games(base, replay)
        if registry.sha256_file(registry.CATALOG_PATH) != catalog:
            raise ValueError('preferred catalog changed')
        retained(path, dict(season=season, actual_release=ACTUAL, replay_release=REPLAY,
            shared_files=shared, complete_game_inventory_identical_before_and_after=True,
            complete_recipe_identical_before_and_after=True, removed_paths=[],
            recovery='No restoration needed: both original paths retain exact bytes; copy-on-write via atomic replacement is required for future edits to these immutable artifacts.'))
        rows.append(dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path)))
        print(dict(season=season, verified_shared_files=2, removed_paths=0), flush=True)
    retained(ROOT / 'completed.json', dict(utc=datetime.now(UTC).isoformat(), machine='joe-Vostro-3350',
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4', rows=rows,
        preferred_catalog_sha256=catalog, before_free_bytes=free, after_free_bytes=shutil.disk_usage(registry.ROOT).free,
        concurrent_builder_allocations_make_free_space_delta_nonexclusive=True, current26_unchanged=True,
        removed_paths=[]))


if __name__ == '__main__':
    main()
