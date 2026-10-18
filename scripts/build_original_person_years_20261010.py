"""Resume bounded year-only corrections; never promote without runtime proof."""
from scripts import season_original_person_birth_years_v1 as source
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.verify_sourced_birth_years_v1 import verify

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/original-person-birth-years-v1'
PEOPLE = ROOT.parent / 'stock-club-history-v1/remaining-modern-birthday-original-people-v1.json'
RELEASE = 'sourced-original-person-birth-years-20261010-r77a'
REPLAY = 'replayed-original-person-birth-years-20261010-r77b'
SEASONS = ('2020-21', '2021-22', '2023-24', '2024-25', '2025-26')


def main():
    ROOT.mkdir(exist_ok=True)
    for season in SEASONS:
        path = ROOT / (season + '-plan.json')
        if path.exists():
            plan = pipeline.read_json_file(path)
            base = registry.load_registered_release(season, plan['release_id'])
            source.verify(base, plan)
        else:
            base = registry.load_preferred_release(season)
            plan = source.prepare(base, PEOPLE)
            pipeline.write_canonical_json(path, plan)
        print(dict(season=season, source_confirmed=len(plan['updates']),
            remaining=len(plan['unresolved']), installed=False), flush=True)
        if not plan['updates']:
            continue
        control = ROOT / (season + '-inert.json')
        descriptor = dict(season=season, release_id=base.release_id,
            package_sha256=registry.sha256_file(base.package_path),
            jug_sha256=registry.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[])
        if control.exists():
            if pipeline.read_json_file(control) != descriptor:
                raise ValueError('retained original-person descriptor changed')
        else:
            pipeline.write_canonical_json(control, descriptor)
        if not registry.locator_path(season, RELEASE).exists():
            publisher.publish(season, control, release_id=RELEASE,
                birth_year_plan_path=path, source_release_id=base.release_id)
        release = registry.load_registered_release(season, RELEASE)
        native_path = ROOT / (season + '-independent-proof.json')
        if not native_path.exists():
            verify(season, RELEASE, path, native_path)
        elif pipeline.read_json_file(native_path)['package_sha256'] != registry.sha256_file(release.package_path):
            raise ValueError('retained independent proof binds another recipe')
        replay_path = ROOT / (season + '-complete-replay-proof.json')
        if not replay_path.exists():
            if registry.locator_path(season, REPLAY).exists():
                raise ValueError('unreceipted replay exists; inspect instead of rerun')
            pipeline.write_canonical_json(replay_path, source.reconstruction(release, REPLAY))
        else:
            replay = registry.load_registered_release(season, REPLAY)
            pipeline.assert_tree_matches_inventory(replay.game_path, pipeline.read_json_file(release.inventory_path))
            if pipeline.read_json_file(replay.package_path) != pipeline.read_json_file(release.package_path):
                raise ValueError('retained complete replay recipe differs')
        print(dict(season=season, native_proof=True, other_bytes_and_files_unchanged=True,
            full_game_recipe_replay=True, installed=False, runtime_pending=True), flush=True)


if __name__ == '__main__':
    main()
