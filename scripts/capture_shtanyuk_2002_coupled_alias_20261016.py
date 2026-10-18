"""Capture both actual repaired people after the manager sweep's normal FIFO."""
import argparse
import os
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.capture_stoke_original_alias_reserve_20261016 import wait_for_sweep
from scripts.capture_arsenal_owned_opening_20261016 import bound_capture
from scripts.build_shtanyuk_2002_coupled_alias_20261016 import ROOT,SEASON,RELEASE

TAG='shtanyuk_coupled_2002_03_r119a_20261016'


def main(pid=None):
    if not all((ROOT/n).exists() for n in ('native-byte-proof.json','complete-SOURCE-replay.json')):
        raise ValueError('actual coupled native and full SOURCE proofs required')
    if pid is not None:wait_for_sweep(pid)
    release=registry.load_registered_release(SEASON,RELEASE)
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    command,evidence=capture.capture_command(season=SEASON,worker='default',run_tag=TAG,
        compact_evidence=True,release_id=RELEASE)
    bound_capture(command,evidence,ROOT/'startup-transport.json',release,env)
    people={p['carrier_id']:p for p in pipeline.read_json_file(release.package_path)['players']}
    for carrier,label,token in ((10580,'vandeurzen','Vandeurzen'),(7972,'khomukha','Khomukha')):
        target=ROOT/'runtime'/label
        command=[str(registry.ROOT/'scripts/run_stars_player_offer_probe_direct.sh'),
            '--worker','default','--run-tag',TAG+'_'+label,'--local-game-dir',str(release.game_path),
            '--local-artifact-dir',str(target),'--player-search',people[carrier]['name'],'--player-label',label,
            '--profile-name-token',token,'--profile-only','--provenance-file',str(release.compiler_receipt_path)]
        bound_capture(command,target,ROOT/(label+'-profile-transport.json'),release,env)
    print(dict(actual_startup_and_both_club_profiles_captured=True,original_visual_reviews_pending=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--wait-manager-sweep-pid',type=int)
    args=parser.parse_args();main(args.wait_manager_sweep_pid)
