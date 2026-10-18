"""Replace only the positively proved unused Savinho copy with Oscar Bobb."""
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_within_club_reserve_repair_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.closeout_duplicate_ownership_batch_v1 import verify_native_batch

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/savio-alias-reserve-v1'
BASE='sourced-savio-period-country-20261011-r95a'
RELEASE='sourced-savio-bobb-reserve-20261011-r96a'
REPLAY='replayed-savio-bobb-reserve-20261011-r96b'
SEASON='2024-25'


def retained(path,data):
    if path.exists():
        if pipeline.read_json_file(path)!=data:raise ValueError('immutable alias reserve stage differs')
    else:pipeline.write_canonical_json(path,data)


def main():
    ROOT.mkdir(exist_ok=True)
    base=registry.load_registered_release(SEASON,BASE)
    plan=source.make_plan(base,9246,9232,'Oscar Bobb','Oscar_Bobb',ROOT,
        duplicate_provider_id=743591,biography_provider='original-savio-bobb-2024')
    folder=ROOT/SEASON;folder.mkdir(exist_ok=True)
    path=folder/'ownership-plan.json';retained(path,plan)
    descriptor=folder/'inert.json'
    retained(descriptor,dict(season=SEASON,release_id=BASE,
        package_sha256=registry.sha256_file(base.package_path),jug_sha256=registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),updates=[],unresolved=[]))
    if not registry.locator_path(SEASON,RELEASE).exists():
        publisher.publish(SEASON,descriptor,release_id=RELEASE,source_release_id=BASE,ownership_plan_path=path)
    proof=ROOT/'native-byte-proof.json'
    if not proof.exists():verify_native_batch(ROOT,RELEASE,proof,seasons=[SEASON])
    replay_proof=ROOT/'complete-SOURCE-replay.json'
    if not replay_proof.exists():
        if registry.locator_path(SEASON,REPLAY).exists():raise ValueError('unreceipted alias replay needs inspection')
        publisher.publish(SEASON,descriptor,release_id=REPLAY,source_release_id=BASE,ownership_plan_path=path)
        release=registry.load_registered_release(SEASON,RELEASE)
        rebuilt=registry.load_registered_release(SEASON,REPLAY)
        pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(release.inventory_path))
        if pipeline.read_json_file(rebuilt.package_path)!=pipeline.read_json_file(release.package_path):raise ValueError('complete alias recipe replay differs')
        retained(replay_proof,dict(season=SEASON,release_id=RELEASE,replay_release_id=REPLAY,
            complete_game_inventory_identical=True,complete_recipe_identical=True,
            native_proof_sha256=registry.sha256_file(proof),ownership_plan_sha256=registry.sha256_file(path)))
    print(dict(built=True,SOURCE_replay_verified=True,installed=False,runtime_pending=True),flush=True)


if __name__=='__main__':main()
