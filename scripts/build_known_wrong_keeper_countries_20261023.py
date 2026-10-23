"""Serial, exact-parent country-only builds; never promote or run the game."""
import argparse
import shutil

from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_source_verified_player_changes_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.build_public_fixture_batches_20261017 import share_verified

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/parallel-rc-20261023'
OUTPUT = ROOT / 'keeper-country-delivery-v1'
SEASONS = ('2000-01', '2001-02', '2002-03', '2003-04',
           '2004-05', '2005-06', '2006-07')


def native_proof(base, actual, plan):
    source.verify(base, plan)
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    expected, expected_eq = source.apply(jug, eq, plan)
    if ((actual.game_path / 'DBDAT/JUG98030.FDI').read_bytes() != expected
            or (actual.game_path / 'DBDAT/EQ98030.FDI').read_bytes() != expected_eq
            or source.apply(expected, expected_eq, plan) != (expected, expected_eq)):
        raise ValueError('actual country native readback or idempotence differs')
    left = {r['path']: r['sha256'] for r in pipeline.read_json_file(base.inventory_path)['files']}
    right = {r['path']: r['sha256'] for r in pipeline.read_json_file(actual.inventory_path)['files']}
    changed = sorted(k for k in left.keys() & right.keys() if left[k] != right[k])
    if left.keys() != right.keys() or changed != ['DBDAT/JUG98030.FDI']:
        raise ValueError('country-only release changed another file or inventory path')
    package = pipeline.read_json_file(base.package_path)
    if source.bind(package, plan) != pipeline.read_json_file(actual.package_path):
        raise ValueError('actual recipe differs from exact nationality-only binding')
    allowed = {row['native_mask']['file_offset'] for row in plan['updates']}
    if len(jug) != len(expected) or {i for i, (a, b) in enumerate(zip(jug, expected)) if a != b} != allowed:
        raise ValueError('country-only native scope differs')
    return dict(season=base.season, parent=base.release_id, release_id=actual.release_id,
        manifest_sha256=actual.manifest_sha256, changed_native_bytes=len(allowed),
        changed_files=changed, carriers=[r['carrier_id'] for r in plan['updates']],
        all_other_bytes_and_files_exact=True, recipe_exact_binding=True,
        complete_postimage_idempotent=True, historical_ownership_certified=False,
        preferred_changed=False, runtime_verified=False)


def build_one(season):
    number = 181 + SEASONS.index(season)
    release_id = f'sourced-keeper-profile-countries-20261023-r{number}a'
    replay_id = f'replayed-keeper-profile-countries-20261023-r{number}b'
    folder = OUTPUT / season
    if folder.exists() or registry.locator_path(season, release_id).exists():
        raise ValueError('existing stage must be inspected, never silently regenerated')
    input_path = ROOT / 'horne' / f'known-wrong-input-{season}-v2.json'
    request = pipeline.read_json_file(input_path)
    base = registry.load_preferred_release(season)
    if base.release_id != request['release_id']:
        raise ValueError('preferred parent advanced: preserve intervening corrections')
    plan = source.prepare(base, input_path)
    if plan['kind'] != source.KNOWN_WRONG_KIND:
        raise ValueError('only admitted country-only plan supported')
    # Publisher additionally enforces its own projected write reserve.
    if shutil.disk_usage(registry.ROOT).free < 8.2 * 1024**3:
        raise ValueError('country batch would approach unchanged 8 GiB reserve')
    folder.mkdir(parents=True)
    plan_path = folder / 'country-plan.json'
    retained(plan_path, plan)
    descriptor = folder / 'inert.json'
    retained(descriptor, dict(season=season, release_id=base.release_id,
        package_sha256=plan['package_sha256'], jug_sha256=plan['jug_sha256'],
        updates=[], unresolved=[]))
    publisher.publish(season, descriptor, release_id=release_id,
        source_release_id=base.release_id, profile_assignment_plan_path=plan_path)
    actual = registry.load_registered_release(season, release_id)
    proof = native_proof(base, actual, plan)
    retained(folder / 'native-and-unchanged-proof.json', proof)
    replay = source.reconstruction(actual, replay_id)
    if not replay or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
        raise ValueError('whole SOURCE replay not proven')
    rebuilt = registry.load_registered_release(season, replay_id)
    share_verified(actual, rebuilt, folder)
    retained(folder / 'complete-SOURCE-replay.json', dict(replay,
        release_id=release_id, replay_release_id=replay_id,
        source_plan_sha256=registry.sha256_file(plan_path)))
    retained(folder / 'build-complete.json', proof)
    print(proof, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('seasons', nargs='+', choices=SEASONS)
    for season in parser.parse_args().seasons:
        build_one(season)
