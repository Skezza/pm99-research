"""Resume additional source-bound private year-only deltas from R69 games."""
from scripts import season_cross_period_birth_years_v1 as source
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.verify_sourced_birth_years_v1 import verify
from scripts import probe_dd6361_skill_patch as skills

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/cross-period-birth-years-v1'
BASE = 'sourced-original-number-labels-20261010-r69a'
RELEASE = 'sourced-cross-period-birth-years-20261010-r70a'
REPLAY = 'replayed-cross-period-birth-years-20261010-r70b'


def main():
    ROOT.mkdir(exist_ok=True)
    for year in range(2020, 2026):
        season = f'{year}-{str(year+1)[-2:]}'
        base = registry.load_registered_release(season, BASE)
        plan_path = ROOT / (season + '-plan.json')
        if plan_path.exists():
            plan = pipeline.read_json_file(plan_path)
            if plan['release_id'] != BASE or plan['package_sha256'] != registry.sha256_file(base.package_path):
                raise ValueError('retained cross-period plan belongs to another baseline')
        else:
            plan = source.prepare(base)
            pipeline.write_canonical_json(plan_path, plan)
        print(dict(season=season, original_year_omissions=len(plan['updates']), unresolved=len(plan['unresolved']), installed=False), flush=True)
        if not plan['updates']:
            continue
        control = ROOT / (season + '-inert.json')
        descriptor = dict(season=season, release_id=BASE,
            package_sha256=registry.sha256_file(base.package_path),
            jug_sha256=registry.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[])
        if control.exists():
            if pipeline.read_json_file(control) != descriptor:
                raise ValueError('retained cross-period descriptor differs')
        else:
            pipeline.write_canonical_json(control, descriptor)
        if not registry.locator_path(season, RELEASE).exists():
            publisher.publish(season, control, release_id=RELEASE,
                birth_year_plan_path=plan_path, source_release_id=BASE)
        release = registry.load_registered_release(season, RELEASE)
        native_path = ROOT / (season + '-independent-proof.json')
        if not native_path.exists():
            verify(season, RELEASE, plan_path, native_path)
        else:
            native = pipeline.read_json_file(native_path)
            if native['package_sha256'] != registry.sha256_file(release.package_path):
                raise ValueError('retained cross-period proof belongs to another recipe')
        semantic_path = ROOT / (season + '-skill-and-all-file-proof.json')
        if not semantic_path.exists():
            old_inventory, inventory = pipeline.read_json_file(base.inventory_path), pipeline.read_json_file(release.inventory_path)
            for game, inv in ((base.game_path, old_inventory), (release.game_path, inventory)):
                pipeline.assert_tree_matches_inventory(game, inv)
            old_files = {r['path']: r['sha256'] for r in old_inventory['files'] if r['path'] != 'DBDAT/JUG98030.FDI'}
            new_files = {r['path']: r['sha256'] for r in inventory['files'] if r['path'] != 'DBDAT/JUG98030.FDI'}
            if old_files != new_files:
                raise ValueError('cross-period birthday changed another game file')
            before = skills.build_dd6361_pid_stats_index(player_file=base.game_path / 'DBDAT/JUG98030.FDI')
            after = skills.build_dd6361_pid_stats_index(player_file=release.game_path / 'DBDAT/JUG98030.FDI')
            if set(before) != set(after) or any(any(before[p][key] != after[p][key] for key in
                    ('mapped10', 'decoded18', 'role_ratings5', 'unknown_byte16_candidate')) for p in before):
                raise ValueError('cross-period birthday changed global skill/role semantics')
            pipeline.write_canonical_json(semantic_path, dict(season=season, release_id=RELEASE,
                package_sha256=registry.sha256_file(release.package_path),
                all_other_game_files_identical=True, all_visible_skills_and_role_ratings_identical=True,
                all_biographic_stat_ids_preserved=True, biographic_stat_records_checked=len(before)))
        replay_path = ROOT / (season + '-complete-replay-proof.json')
        if not replay_path.exists():
            if registry.locator_path(season, REPLAY).exists():
                raise ValueError('unreceipted cross-period replay exists; inspect instead of rerun')
            pipeline.write_canonical_json(replay_path, source.reconstruction(release, REPLAY))
        else:
            replay = registry.load_registered_release(season, REPLAY)
            pipeline.assert_tree_matches_inventory(replay.game_path, pipeline.read_json_file(release.inventory_path))
            if pipeline.read_json_file(replay.package_path) != pipeline.read_json_file(release.package_path):
                raise ValueError('retained complete cross-period replay recipe differs')
        print(dict(season=season, native_proof=True, semantic_proof=True, full_game_recipe_replay=True, installed=False), flush=True)


if __name__ == '__main__':
    main()
