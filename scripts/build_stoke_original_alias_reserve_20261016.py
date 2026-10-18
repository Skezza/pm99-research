"""Build the exact2001 native alias correction on the finished manager game.

Private only; never changes preferred bindings or counts a case as delivered.
"""
import os
import shutil
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_stoke_original_alias_reserve_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import build_remaining_manager_tenures_20261016 as managers
from scripts.closeout_duplicate_ownership_batch_v1 import verify_native_batch
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/Stoke-original-alias-delivery-v1'
SEASON = '2001-02'
RELEASE = 'sourced-stoke-original-alias-reserve-20261016-r117a'
REPLAY = 'replayed-stoke-original-alias-reserve-20261016-r117b'


def main():
    if (ROOT / 'complete-SOURCE-replay.json').exists():
        raise ValueError('completed alias build must not repeat')
    if not (managers.ROOT / SEASON / 'complete-SOURCE-replay.json').exists():
        raise ValueError('exact manager parent is not SOURCE-complete')
    if shutil.disk_usage(registry.ROOT).free < 8.3 * 1024**3:
        raise ValueError('alias build refuses to threaten8GiB reserve')
    base = registry.load_registered_release(SEASON, managers.RELEASE)
    plan = source.prepare(base)
    folder = ROOT / SEASON; folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'ownership-plan.json'; retained(path, plan)
    descriptor = folder / 'inert.json'
    retained(descriptor, dict(season=SEASON, release_id=base.release_id,
        package_sha256=plan['package_sha256'], jug_sha256=plan['jug_sha256'], updates=[], unresolved=[]))
    if not registry.locator_path(SEASON, RELEASE).exists():
        publisher.publish(SEASON, descriptor, release_id=RELEASE, source_release_id=base.release_id,
            ownership_plan_path=path)
    actual = registry.load_registered_release(SEASON, RELEASE)
    proof = ROOT / 'native-byte-proof.json'
    if not proof.exists():
        verify_native_batch(ROOT, RELEASE, proof, seasons=[SEASON])
    if registry.locator_path(SEASON, REPLAY).exists():
        raise ValueError('unreceipted alias SOURCE game exists; inspect rather than rerun')
    result = source.reconstruction(actual, REPLAY)
    rebuilt = registry.load_registered_release(SEASON, REPLAY)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(actual.inventory_path))
    if pipeline.read_json_file(actual.package_path) != pipeline.read_json_file(rebuilt.package_path):
        raise ValueError('entire alias recipe SOURCE replay differs')
    retained(ROOT / 'complete-SOURCE-replay.json', dict(result, season=SEASON,
        release_id=RELEASE, replay_release_id=REPLAY, manifest_sha256=actual.manifest_sha256,
        native_proof_sha256=registry.sha256_file(proof), ownership_plan_sha256=registry.sha256_file(path)))
    for a, b in ((actual.package_path, rebuilt.package_path),
            (actual.game_path / 'DBDAT/JUG98030.FDI', rebuilt.game_path / 'DBDAT/JUG98030.FDI')):
        if registry.sha256_file(a) != registry.sha256_file(b):
            raise ValueError('new SOURCE copy differs before verified content sharing')
        if a.stat().st_ino != b.stat().st_ino:
            temporary = b.with_name(b.name + '.verified-link')
            if temporary.exists():
                raise ValueError('unreceipted sharing temporary')
            os.link(a, temporary); os.replace(temporary, b)
    print(dict(actual_game_built=True, entire_SOURCE_replay=True, season=SEASON,
        native_replacement='Kris Commons', retained_defender='Sergey Shtanyuk',
        preferred_unchanged=True, runtime_review_pending=True, cases_closed=0), flush=True)


if __name__ == '__main__':
    main()
