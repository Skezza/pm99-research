"""Recover space from exact old SOURCE duplicates without removing any path."""
import shutil
from datetime import UTC, datetime
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.archive_completed_arsenal_replays_20261016 import assert_equal_games, active
from scripts.share_verified_r70_source_copies_20261016 import share_identical
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/cleanup-20261016/shared-old-number-SOURCE-copies'
PAIRS = (
    ('sourced-original-number-labels-20261010-r68a', 'replayed-original-number-labels-20261010-r68b'),
    ('sourced-original-number-labels-20261010-r69a', 'replayed-original-number-labels-20261010-r69b'),
)


def main():
    if (ROOT / 'completed.json').exists():
        raise ValueError('completed cleanup must not repeat')
    ROOT.mkdir(parents=True, exist_ok=True)
    catalog = registry.sha256_file(registry.CATALOG_PATH)
    free = shutil.disk_usage(registry.ROOT).free
    proofs = []
    for season in registry.supported_seasons():
        for actual_id, replay_id in PAIRS:
            if not registry.locator_path(season, replay_id).exists():
                continue
            ledger = ROOT / (season + '-' + replay_id + '.json')
            if ledger.exists():
                proof = pipeline.read_json_file(ledger)
                for row in proof['shared_files']:
                    a, b = registry.ROOT / row['original'], registry.ROOT / row['shared_copy']
                    if (a.stat().st_ino != b.stat().st_ino
                            or registry.sha256_file(a) != row['sha256']
                            or registry.sha256_file(b) != row['sha256']):
                        raise ValueError('previous shared bytes changed')
            else:
                base = registry.load_registered_release(season, actual_id)
                replay = registry.load_registered_release(season, replay_id)
                expected = registry.ROOT / '.local/historical-role-deltas-v1' / season / replay_id
                if (replay.game_path != expected / 'game' or active(expected)
                        or active(base.game_path.parent)
                        or registry.load_preferred_release(season).release_id in (actual_id, replay_id)):
                    raise ValueError('unexpected, active or preferred immutable sharing scope')
                assert_equal_games(base, replay)
                shared = [share_identical(a, b) for a, b in (
                    (base.package_path, replay.package_path),
                    (base.game_path / 'DBDAT/JUG98030.FDI', replay.game_path / 'DBDAT/JUG98030.FDI'))]
                assert_equal_games(base, replay)
                if registry.sha256_file(registry.CATALOG_PATH) != catalog:
                    raise ValueError('preferred catalog changed')
                retained(ledger, dict(season=season, actual_release=actual_id, replay_release=replay_id,
                    shared_files=shared, complete_games_and_recipes_equal_before_and_after=True,
                    removed_paths=[], recovery='Both paths remain; future immutable-artifact edits must use atomic replacement, never in-place mutation.'))
            proofs.append(dict(path=registry.relative_workspace_path(ledger), sha256=registry.sha256_file(ledger)))
            print(dict(season=season, replay=replay_id, former_unique_allocated_bytes=sum(
                r['former_unique_allocated_bytes'] for r in pipeline.read_json_file(ledger)['shared_files'])), flush=True)
    retained(ROOT / 'completed.json', dict(utc=datetime.now(UTC).isoformat(), machine='joe-Vostro-3350',
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4', rows=proofs,
        preferred_catalog_sha256=catalog, before_free_bytes=free,
        after_free_bytes=shutil.disk_usage(registry.ROOT).free, removed_paths=[], current26_unchanged=True))


if __name__ == '__main__':
    main()
