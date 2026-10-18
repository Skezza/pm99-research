"""Resume new bounded name/year candidates; never regenerate existing stages."""
from scripts import season_number_label_names_v2 as names
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.verify_number_label_names_v2 import verify

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/original-number-labels-v3'
RELEASE = 'sourced-original-number-labels-20261010-r69a'
REPLAY = 'replayed-original-number-labels-20261010-r69b'


def main():
    ROOT.mkdir(exist_ok=True)
    for year in range(2018, 2026):
        season = f'{year}-{str(year+1)[-2:]}'
        plan_path = ROOT / (season + '-plan.json')
        if plan_path.exists():
            plan = pipeline.read_json_file(plan_path)
            base = registry.load_registered_release(season, plan['release_id'])
            if plan['release_id'] != base.release_id or plan['package_sha256'] != registry.sha256_file(base.package_path):
                raise ValueError('retained name plan belongs to another immutable source')
        else:
            base = (registry.load_preferred_release(season) if year == 2018 else
                    registry.load_registered_release(season, 'sourced-biographic-birth-years-20261010-r67a'))
            plan = names.prepare(base)
            pipeline.write_canonical_json(plan_path, plan)
        print(dict(season=season, original_names=len(plan['updates']),
            year_omissions=sum(u['repair_birth_year'] for u in plan['updates']),
            unresolved=len(plan['unresolved']), installed=False), flush=True)
        if not plan['updates']:
            continue
        control = ROOT / (season + '-inert.json')
        expected = dict(season=season, release_id=base.release_id,
            package_sha256=registry.sha256_file(base.package_path),
            jug_sha256=registry.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[])
        if control.exists():
            if pipeline.read_json_file(control) != expected:
                raise ValueError('retained descriptor differs')
        else:
            pipeline.write_canonical_json(control, expected)
        if not registry.locator_path(season, RELEASE).exists():
            publisher.publish(season, control, release_id=RELEASE,
                name_only_plan_path=plan_path, source_release_id=base.release_id)
        release = registry.load_registered_release(season, RELEASE)
        proof_path = ROOT / (season + '-independent-proof.json')
        if not proof_path.exists():
            proof = verify(season, RELEASE, plan_path, proof_path)
        else:
            proof = pipeline.read_json_file(proof_path)
            if proof['package_sha256'] != registry.sha256_file(release.package_path):
                raise ValueError('retained independent proof belongs to another recipe')
            pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
        replay_path = ROOT / (season + '-complete-replay-proof.json')
        if not replay_path.exists():
            if registry.locator_path(season, REPLAY).exists():
                raise ValueError('unreceipted completed replay exists; inspect instead of rerun')
            pipeline.write_canonical_json(replay_path, names.reconstruction(release, REPLAY))
        else:
            replay = registry.load_registered_release(season, REPLAY)
            pipeline.assert_tree_matches_inventory(replay.game_path, pipeline.read_json_file(release.inventory_path))
            if pipeline.read_json_file(replay.package_path) != pipeline.read_json_file(release.package_path):
                raise ValueError('retained complete replay recipe differs')
        print(dict(season=season, native_proof=True, complete_game_recipe_replay=True,
            remaining_birthdays=proof['after_birthday_disagreements'], installed=False), flush=True)


if __name__ == '__main__':
    main()
