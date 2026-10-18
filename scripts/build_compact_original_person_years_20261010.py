"""Repair two compact player records from original entity and period DOBs."""
from scripts import season_original_secondary_facts_v1 as layer
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.verify_original_secondary_fact_delta_v1 import verify

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/compact-original-person-birth-years-v1'
SOURCE = ROOT.parent / 'stock-club-history-v1/remaining-birthday-original-additional-people-v1.json'
CASES = {
    '2024-25': dict(base='sourced-original-person-birth-years-20261010-r78a',
        release='sourced-original-secondary-facts-20261010-r81a',
        replay='replayed-original-secondary-facts-20261010-r81b', carrier=10958),
    '2025-26': dict(base='sourced-original-secondary-facts-20261010-r80a',
        release='sourced-original-secondary-facts-20261010-r82a',
        replay='replayed-original-secondary-facts-20261010-r82b', carrier=10958),
}


def main(*, root=ROOT, cases=CASES, source=SOURCE, identity_document_path=None):
    root.mkdir(exist_ok=True)
    for season, case in cases.items():
        base = registry.load_registered_release(season, case['base'])
        targets = case.get('targets') or {str(case['carrier']): ['native_birth_year']}
        plan = layer.prepare(base, source, targets, identity_document_path=identity_document_path)
        if len(plan['updates']) != len(targets) or plan['unresolved']:
            raise ValueError('compact original entity and original period DOB not uniquely corroborated: '
                + str(plan['unresolved']))
        path = root / (season + '-plan.json')
        descriptor = dict(season=season, release_id=base.release_id,
            package_sha256=registry.sha256_file(base.package_path),
            jug_sha256=registry.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[])
        control = root / (season + '-inert.json')
        for saved, data in ((path, plan), (control, descriptor)):
            if saved.exists():
                if pipeline.read_json_file(saved) != data:
                    raise ValueError('immutable compact birthday evidence differs')
            else:
                pipeline.write_canonical_json(saved, data)
        if not registry.locator_path(season, case['release']).exists():
            publisher.publish(season, control, release_id=case['release'],
                profile_assignment_plan_path=path, source_release_id=base.release_id)
        release = registry.load_registered_release(season, case['release'])
        proof = root / (season + '-independent-proof.json')
        if not proof.exists():
            verify(season, case['release'], path, proof)
        retained = pipeline.read_json_file(proof)
        limit = sum(2 if fields == ['native_birth_year'] else 4 for fields in targets.values())
        if retained['native_bytes_changed'] > limit or not retained['all_other_recipe_facts_identical']:
            raise ValueError('compact year repair changed anything outside its two-byte scope')
        replay = root / (season + '-complete-replay-proof.json')
        if not replay.exists():
            if registry.locator_path(season, case['replay']).exists():
                raise ValueError('unreceipted compact birthday replay requires inspection')
            pipeline.write_canonical_json(replay, layer.reconstruction(release, case['replay']))
        else:
            rebuilt = registry.load_registered_release(season, case['replay'])
            pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(release.inventory_path))
            if pipeline.read_json_file(rebuilt.package_path) != pipeline.read_json_file(release.package_path):
                raise ValueError('compact year recipe SOURCE replay differs')
        print(dict(season=season, person=plan['updates'][0]['before_player']['name'],
            built=True, full_source_replay_verified=True, installed=False, runtime_pending=True), flush=True)


if __name__ == '__main__':
    main()
