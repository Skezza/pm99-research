"""Register the private Barnet candidate and prove exact whole SOURCE replay.

Preferred releases stay unchanged until genuine runtime inspection is accepted.
"""
from datetime import UTC, datetime

from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
from scripts import publish_paired_whole_club_delta_v1 as publisher
from scripts import season_paired_whole_club_reconstruction_v1 as source
from scripts import prepare_paired_club_assets_v1 as assets
from scripts import verify_paired_whole_club_native_v1 as readback
from scripts import verify_paired_club_identity_v1 as identity
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/consolidated-audit-20261009'
FOLDER = ROOT / 'Barnet2018-native-delivery-v1'
SEASON = '2018-19'
RELEASE = 'sourced-barnet-original-opening-20261017-r143a'
REPLAY = 'replayed-barnet-original-opening-20261017-r143b'


def resume_completed_native_replay(original, *, folder=FOLDER, season=SEASON, replay_id=REPLAY):
    """Resume only the guard-stopped asset stage, never recompile native work."""
    root = registry.ROOT / '.local/paired-whole-club-replays-v1' / season / replay_id
    if registry.locator_path(season, replay_id).exists() or (root / 'complete').exists():
        raise ValueError('inspect existing completed/partial replay publication')
    bound = source.bound_receipt(original)
    if bound is None:
        raise ValueError('registered actual release lost exact source receipt')
    _, receipt = bound
    old_native = folder / 'native'
    rebuilt_native = root / 'native'
    if (old_native / 'season-package.json').read_bytes() != (rebuilt_native / 'season-package.json').read_bytes():
        raise ValueError('completed native recipe replay differs before assets')
    old_receipt = pipeline.read_json_file(old_native / 'candidate-receipt.json')
    replay_receipt = pipeline.read_json_file(rebuilt_native / 'candidate-receipt.json')
    for key in ('source_pair', 'native_hashes', 'source_release_id', 'corrected_slots', 'new_clubs', 'managers'):
        if old_receipt[key] != replay_receipt[key]:
            raise ValueError('completed native replay receipt differs: ' + key)
    specs = {}
    for ground in receipt['paired_asset_stage']['grounds']:
        carrier = ground['carrier_id']
        specs[carrier] = (ground['club'], ground['ground'], f'ground-original-{carrier}.html',
            ground['url'], ground['dated_match_anchors'])
        assets.ground_source(root / 'assets/source-cache', carrier, specs)
    completed = root / 'complete'
    assets.prepare(rebuilt_native, root / 'assets', completed, ground_specs=specs)
    pipeline.assert_tree_matches_inventory(completed / 'game', pipeline.read_json_file(original.inventory_path))
    if (completed / 'season-package.json').read_bytes() != original.package_path.read_bytes():
        raise ValueError('entire SOURCE recipe differs after resumed asset stage')
    native_proof, identity_proof = root / 'native-proof.json', root / 'identity-proof.json'
    readback.verify(completed, native_proof)
    pair = pipeline.read_json_file(registry.ROOT / receipt['source_pair']['path'])
    proposal = pipeline.read_json_file(registry.ROOT / pair['proposals'][0]['path'])
    persons = proposal['bindings']['published_person_supplement']
    person_input = registry.ROOT / persons['path']
    if registry.sha256_file(person_input) != persons['sha256']:
        raise ValueError('bound original person identities changed')
    identity.verify(completed, person_input, identity_proof)
    publisher.publish(completed, native_proof, identity_proof, replay_id,
        source_release_id=receipt['source_release_id'])
    return dict(season=season, release_id=replay_id, source_release_id=receipt['source_release_id'],
        reused=False, resumed_after_disk_guard=True, completed_native_replay_not_repeated=True,
        complete_game_inventory_identical=True, complete_recipe_identical=True,
        compilation_mode='source-bound-complete-club-reconstruction-not-factory-compile')


def main(*, root=ROOT, folder=FOLDER, season=SEASON, release_id=RELEASE, replay_id=REPLAY,
         candidate_name='Barnet2018-complete-v1', proof_prefix='Barnet2018'):
    ROOT,FOLDER,SEASON,RELEASE,REPLAY=root,folder,season,release_id,replay_id
    if (FOLDER / 'complete-SOURCE-replay.json').exists():
        raise ValueError('completed SOURCE proof must not repeat')
    registered = registry.locator_path(SEASON, RELEASE).exists()
    if not registered:
        result = publisher.publish(ROOT / candidate_name,
            ROOT / (proof_prefix+'-native-readback.json'), ROOT / (proof_prefix+'-identity-readback.json'), RELEASE)
        retained(FOLDER / 'private-registration.json', dict(utc=datetime.now(UTC).isoformat(), **result))
        print(dict(actual_private_release=RELEASE, preferred_changed=False), flush=True)
    original = registry.load_registered_release(SEASON, RELEASE)
    result = resume_completed_native_replay(original,folder=folder,season=season,replay_id=replay_id) if registered else source.reconstruction(original, REPLAY)
    if result is None or not result['complete_game_inventory_identical'] or not result['complete_recipe_identical']:
        raise ValueError('whole SOURCE reconstruction failed')
    rebuilt = registry.load_registered_release(SEASON, REPLAY)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(original.inventory_path))
    if rebuilt.package_path.read_bytes() != original.package_path.read_bytes():
        raise ValueError('whole SOURCE recipe bytes differ')
    retained(FOLDER / 'complete-SOURCE-replay.json', dict(utc=datetime.now(UTC).isoformat(), **result))
    print(dict(SOURCE_complete=True, preferred_changed=False, runner_pending=True), flush=True)


if __name__ == '__main__':
    main()
