"""Build only source-proved placeholder dates and the visible Ferran country."""
from scripts import season_original_secondary_facts_v1 as layer
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.verify_original_secondary_fact_delta_v1 import verify

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/original-secondary-facts-v1'
SOURCE = ROOT.parent / 'stock-club-history-v1'
CASES = {
    '2021-22': dict(base='sourced-original-person-birth-years-20261010-r77a',
        release='sourced-original-secondary-facts-20261010-r79a',
        replay='replayed-original-secondary-facts-20261010-r79b',
        people='remaining-modern-birthday-original-people-v1.json',
        targets={'9166': ['nationality']}, count=1),
    '2025-26': dict(base='sourced-original-person-birth-years-20261010-r78a',
        release='sourced-original-secondary-facts-20261010-r80a',
        replay='replayed-original-secondary-facts-20261010-r80b',
        people='remaining-birthday-original-additional-people-v1.json',
        targets={str(i): ['birth_date'] for i in (10249,10711,18163,18239,26920,26971,27054)}, count=7),
}


def main():
    ROOT.mkdir(exist_ok=True)
    for season, case in CASES.items():
        base = registry.load_registered_release(season, case['base'])
        plan = layer.prepare(base, SOURCE / case['people'], case['targets'])
        if len(plan['updates']) != case['count'] or plan['unresolved']:
            raise ValueError('original secondary-fact target count changed')
        path = ROOT / (season + '-plan.json')
        if path.exists():
            if pipeline.read_json_file(path) != plan:
                raise ValueError('retained secondary-fact source plan differs')
        else:
            pipeline.write_canonical_json(path, plan)
        descriptor = dict(season=season, release_id=base.release_id,
            package_sha256=registry.sha256_file(base.package_path),
            jug_sha256=registry.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[])
        control = ROOT / (season + '-inert.json')
        if control.exists():
            if pipeline.read_json_file(control) != descriptor:
                raise ValueError('secondary-fact baseline descriptor differs')
        else:
            pipeline.write_canonical_json(control, descriptor)
        if not registry.locator_path(season, case['release']).exists():
            publisher.publish(season, control, release_id=case['release'],
                profile_assignment_plan_path=path, source_release_id=base.release_id)
        release = registry.load_registered_release(season, case['release'])
        proof = ROOT / (season + '-independent-proof.json')
        if not proof.exists():
            verify(season, case['release'], path, proof)
        elif pipeline.read_json_file(proof)['package_sha256'] != registry.sha256_file(release.package_path):
            raise ValueError('secondary-fact native proof binds another recipe')
        replay = ROOT / (season + '-complete-replay-proof.json')
        if not replay.exists():
            if registry.locator_path(season, case['replay']).exists():
                raise ValueError('unreceipted secondary-fact replay: inspect rather than repeat')
            pipeline.write_canonical_json(replay, layer.reconstruction(release, case['replay']))
        else:
            rebuilt = registry.load_registered_release(season, case['replay'])
            pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(release.inventory_path))
            if pipeline.read_json_file(rebuilt.package_path) != pipeline.read_json_file(release.package_path):
                raise ValueError('retained full secondary-fact replay differs')
        print(dict(season=season, changes=case['count'], source_native_and_replay_verified=True,
            installed=False, runtime_pending=True), flush=True)


if __name__ == '__main__':
    main()
