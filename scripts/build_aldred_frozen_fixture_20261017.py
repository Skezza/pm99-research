"""Build only the sourced unused Blackpool slot; retain actual Accrington XI."""
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_frozen_fixture_reserve_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.closeout_duplicate_ownership_batch_v1 import verify_native_batch
from scripts.prepare_aldred_frozen_fixture_20261017 import ROOT,BASE
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

SEASON='2014-15'
RELEASE='sourced-original-fixture-reserve-20261017-r122a'
REPLAY='replayed-original-fixture-reserve-20261017-r122b'


def main():
    if registry.locator_path(SEASON,RELEASE).exists() or (ROOT/'native-byte-proof.json').exists():
        raise ValueError('existing partial/completed native repair must be inspected, not overwritten')
    base=registry.load_registered_release(SEASON,BASE)
    plan=pipeline.read_json_file(ROOT/'ownership-plan.json')
    source.verify_plan(base,plan)
    folder=ROOT/SEASON;folder.mkdir(exist_ok=True)
    path=folder/'ownership-plan.json';retained(path,plan)
    descriptor=folder/'inert.json';retained(descriptor,dict(season=SEASON,release_id=BASE,
        package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]))
    publisher.publish(SEASON,descriptor,release_id=RELEASE,source_release_id=BASE,ownership_plan_path=path)
    print(dict(actual_private_game_built=True,changed_native_player=9520,retained_native_player=9580),flush=True)
    verify_native_batch(ROOT,RELEASE,ROOT/'native-byte-proof.json',seasons=[SEASON])
    actual=registry.load_registered_release(SEASON,RELEASE)
    result=source.reconstruction(actual,REPLAY)
    rebuilt=registry.load_registered_release(SEASON,REPLAY)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(actual.inventory_path))
    if rebuilt.package_path.read_bytes()!=actual.package_path.read_bytes():raise ValueError('entire SOURCE recipe differs')
    retained(ROOT/'complete-SOURCE-replay.json',dict(result,source_release_id=BASE,actual_release_id=RELEASE,
        replay_release_id=REPLAY,manifest_sha256=actual.manifest_sha256,
        native_proof_sha256=registry.sha256_file(ROOT/'native-byte-proof.json'),ownership_plan_sha256=registry.sha256_file(path)))
    print(dict(complete_SOURCE=True,actual_native_proof=True,preferred_changed=False,runtime_pending=True),flush=True)


if __name__=='__main__':main()
