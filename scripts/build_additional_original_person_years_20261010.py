"""Build only ten new corroborated years on R77, retaining its proof layer."""
from scripts import season_original_person_birth_years_v1 as source
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.verify_sourced_birth_years_v1 import verify
from scripts.build_original_person_years_20261010 import RELEASE as BASE

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/additional-original-person-birth-years-v1'
PEOPLE = ROOT.parent / 'stock-club-history-v1/remaining-birthday-original-additional-people-v1.json'
RELEASE = 'sourced-original-person-birth-years-20261010-r78a'
REPLAY = 'replayed-original-person-birth-years-20261010-r78b'
COUNTS = {'2020-21': 1, '2023-24': 3, '2024-25': 1, '2025-26': 5}


def main():
    ROOT.mkdir(exist_ok=True)
    for season, count in COUNTS.items():
        base = registry.load_registered_release(season, BASE)
        path = ROOT / (season + '-plan.json')
        plan = source.prepare(base, PEOPLE, transaction_id=registry.sha256_file(PEOPLE)[:12])
        if len(plan['updates']) != count:
            raise ValueError('bounded additional corroborated year accounting changed')
        if path.exists():
            if pipeline.read_json_file(path) != plan:
                raise ValueError('retained incremental source plan changed')
        else:
            pipeline.write_canonical_json(path, plan)
        control = ROOT / (season + '-inert.json')
        descriptor = dict(season=season, release_id=base.release_id,
            package_sha256=registry.sha256_file(base.package_path),
            jug_sha256=registry.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[])
        if control.exists():
            if pipeline.read_json_file(control) != descriptor:
                raise ValueError('retained incremental baseline descriptor changed')
        else:
            pipeline.write_canonical_json(control, descriptor)
        if not registry.locator_path(season, RELEASE).exists():
            publisher.publish(season, control, release_id=RELEASE,
                birth_year_plan_path=path, source_release_id=base.release_id)
        release = registry.load_registered_release(season, RELEASE)
        native = ROOT / (season + '-independent-proof.json')
        if not native.exists():
            verify(season, RELEASE, path, native)
        elif pipeline.read_json_file(native)['package_sha256'] != registry.sha256_file(release.package_path):
            raise ValueError('incremental native proof binds another recipe')
        replay = ROOT / (season + '-complete-replay-proof.json')
        if not replay.exists():
            if registry.locator_path(season, REPLAY).exists():
                raise ValueError('unreceipted incremental replay: inspect rather than overwrite')
            pipeline.write_canonical_json(replay, source.reconstruction(release, REPLAY))
        else:
            rebuilt = registry.load_registered_release(season, REPLAY)
            pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(release.inventory_path))
            if pipeline.read_json_file(rebuilt.package_path) != pipeline.read_json_file(release.package_path):
                raise ValueError('retained incremental replay recipe differs')
        print(dict(season=season, new_years=count, native_proof=True,
            complete_game_recipe_replay=True, installed=False, runtime_pending=True), flush=True)


if __name__ == '__main__':
    main()
