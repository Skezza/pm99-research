"""Resume the prepared Exeter source plan after verified space recovery.

No new source proposal, rescrape, unaffected regeneration or catalogue write.
The earlier stopped attempt remains recorded instead of being overwritten.
"""
from datetime import UTC,datetime
import shutil
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_frozen_fixture_reserve_v2 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.closeout_duplicate_ownership_batch_v1 import verify_native_batch
from scripts.build_public_fixture_batches_20261017 import ROOT,RELEASE,REPLAY,share_verified
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def main():
    season='2024-25';folder=ROOT/season
    failure=folder/'build-failure.json';stopped=pipeline.read_json_file(failure)
    if 'before crossing unchanged8GiB reserve' not in stopped['error']:
        raise ValueError('this explicit resume only covers the inspected space preflight refusal')
    completed=registry.ROOT/'.local/cleanup-20261017/shared-completed-fact-SOURCE-copies/completed.json'
    cleanup=pipeline.read_json_file(completed)
    if cleanup['removed_paths'] or not cleanup['current26_unchanged']:
        raise ValueError('space recovery did not preserve all current games and paths')
    if shutil.disk_usage(registry.ROOT).free<8.15*1024**3:raise ValueError('unchanged8GiB reserve still at risk')
    if registry.locator_path(season,RELEASE).exists() or (folder/'complete-SOURCE-replay.json').exists():
        raise ValueError('partial/completed native candidate exists; inspect, never recreate')
    path=folder/'ownership-plan.json';plan=pipeline.read_json_file(path)
    base=registry.load_registered_release(season,plan['release_id'])
    descriptor=folder/'inert.json'
    if pipeline.read_json_file(descriptor)!=dict(season=season,release_id=base.release_id,
            package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]):
        raise ValueError('already prepared original native inputs changed')
    retained(folder/'resume-after-sharing.json',dict(utc=datetime.now(UTC).isoformat(),
        previous_failure=source.binding(failure),retained_source_plan=source.binding(path),
        verified_space_recovery=source.binding(completed),source_rescraped=False,source_proposal_regenerated=False,
        source_parent=base.release_id,preferred_changed=False))
    publisher.publish(season,descriptor,release_id=RELEASE,source_release_id=base.release_id,ownership_plan_path=path)
    print(dict(actual_private_Exeter_game_built=True,source_plan_reused=True),flush=True)
    native_proof=folder/'native-byte-proof.json';verify_native_batch(ROOT,RELEASE,native_proof,seasons=[season])
    actual=registry.load_registered_release(season,RELEASE);result=source.reconstruction(actual,REPLAY)
    rebuilt=registry.load_registered_release(season,REPLAY)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(actual.inventory_path))
    if rebuilt.package_path.read_bytes()!=actual.package_path.read_bytes():raise ValueError('whole SOURCE recipe differs')
    share_verified(actual,rebuilt,folder)
    retained(folder/'complete-SOURCE-replay.json',dict(result,actual_release_id=RELEASE,replay_release_id=REPLAY,
        source_release_id=base.release_id,manifest_sha256=actual.manifest_sha256,
        native_proof_sha256=registry.sha256_file(native_proof),source_plan_sha256=registry.sha256_file(path)))
    retained(folder/'build-summary-resumed.json',dict(utc=datetime.now(UTC).isoformat(),season=season,
        status='actual-private-native-and-whole-SOURCE-complete-after-verified-space-recovery',
        original_stopped_attempt_retained=True,source_plan_reused=True,preferred_changed=False,runtime_pending=True))
    print(dict(actual_native_verified=True,whole_SOURCE_complete=True,preferred_changed=False),flush=True)


if __name__=='__main__':main()
