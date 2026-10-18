"""Serial targeted final-game evidence; retain failed diagnostics unchanged."""
import os
import subprocess
import time
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.build_savio_bobb_alias_reserve_20261011 import ROOT,SEASON,RELEASE


def main():
    barrier=ROOT.parent/'savio-original-country-v1/savio_verified-profile-transport.json'
    deadline=time.monotonic()+900
    while not barrier.exists():
        if time.monotonic()>deadline:raise ValueError('preceding exact country profile wait expired')
        time.sleep(10)
    if pipeline.read_json_file(barrier)['exit_code']!=0:raise ValueError('preceding country profile failed')
    if not (ROOT/'native-byte-proof.json').exists() or not (ROOT/'complete-SOURCE-replay.json').exists():
        raise ValueError('alias native and exact SOURCE proofs missing')
    release=registry.load_registered_release(SEASON,RELEASE)
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    tag='savio_bobb_2024_r96a_20261011'
    command,evidence=capture.capture_command(season=SEASON,worker='default',run_tag=tag,
        compact_evidence=True,release_id=RELEASE)
    transport=ROOT/'startup-transport.json'
    if not transport.exists():
        if evidence.exists():raise ValueError('unreceipted alias startup exists; inspect rather than overwrite')
        completed=subprocess.run(command,env=env,check=False)
        pipeline.write_canonical_json(transport,dict(exit_code=completed.returncode,evidence=registry.relative_workspace_path(evidence),
            release_manifest_sha256=release.manifest_sha256,visually_approved=False))
    if pipeline.read_json_file(transport)['exit_code']!=0:raise ValueError('alias startup failed')
    transport=ROOT/'bobb-profile-transport.json';target=ROOT/'runtime'/tag
    if not transport.exists():
        if target.exists():raise ValueError('unreceipted Bobb profile exists; inspect rather than overwrite')
        completed=subprocess.run([str(registry.ROOT/'scripts/run_stars_player_offer_probe_direct.sh'),
            '--worker','default','--run-tag',tag+'_bobb','--local-game-dir',str(release.game_path),
            '--local-artifact-dir',str(target),'--player-search','Oscar Bobb','--player-label','bobb',
            '--profile-name-token','Bobb','--profile-only','--provenance-file',str(release.compiler_receipt_path)],env=env,check=False)
        pipeline.write_canonical_json(transport,dict(exit_code=completed.returncode,evidence=registry.relative_workspace_path(target),
            release_manifest_sha256=release.manifest_sha256,visually_approved=False))
    if pipeline.read_json_file(transport)['exit_code']!=0:raise ValueError('exact Bobb profile failed')
    print(dict(final_alias_startup_and_profile_captured=True,visually_approved=False,installed=False),flush=True)


if __name__=='__main__':main()
