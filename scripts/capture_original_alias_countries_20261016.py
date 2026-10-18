"""Only final country-complete games get new startup/named profile captures."""
import argparse
import os
from pathlib import Path
import time
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.capture_arsenal_owned_opening_20261016 import bound_capture
from scripts.capture_stoke_original_alias_reserve_20261016 import wait_for_sweep
from scripts.build_original_alias_countries_20261016 import ROOT,RELEASE


def wait_build(season,pid):
    deadline=time.monotonic()+3600
    while not (ROOT/season/'complete-SOURCE-replay.json').is_file():
        try:command=(Path('/proc')/str(pid)/'cmdline').read_bytes()
        except FileNotFoundError:raise ValueError('owned country builder stopped before SOURCE proof; inspect rather than rerun')
        if b'scripts.build_original_alias_countries_20261016' not in command:raise ValueError('country builder PID identity changed')
        if time.monotonic()>deadline:raise ValueError('bounded country build wait expired; inspect live process')
        time.sleep(10)


def run(season):
    root=ROOT/season
    if not all((root/n).is_file() for n in ('native-byte-proof.json','complete-SOURCE-replay.json')):
        raise ValueError('actual country-complete native/SOURCE proofs required')
    release=registry.load_registered_release(season,RELEASE)
    tag='original_alias_countries_'+season.replace('-','_')+'_r120a_20261016'
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    command,evidence=capture.capture_command(season=season,worker='default',run_tag=tag,
        compact_evidence=True,release_id=RELEASE)
    bound_capture(command,evidence,root/'startup-transport.json',release,env)
    people={p['carrier_id']:p for p in pipeline.read_json_file(release.package_path)['players']}
    wanted=((27013,'commons','Commons'),) if season=='2001-02' else ((10580,'vandeurzen','Vandeurzen'),(7972,'khomukha','Khomukha'))
    for carrier,label,token in wanted:
        target=root/'runtime'/label
        command=[str(registry.ROOT/'scripts/run_stars_player_offer_probe_direct.sh'),
            '--worker','default','--run-tag',tag+'_'+label,'--local-game-dir',str(release.game_path),
            '--local-artifact-dir',str(target),'--player-search',people[carrier]['name'],'--player-label',label,
            '--profile-name-token',token,'--profile-only','--provenance-file',str(release.compiler_receipt_path)]
        bound_capture(command,target,root/(label+'-profile-transport.json'),release,env)
        print(dict(season=season,actual_country_complete_profile_captured=people[carrier]['name'],original_visual_review_pending=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wait-manager-sweep-pid',type=int);parser.add_argument('--wait-build-pid',type=int)
    args=parser.parse_args()
    if args.wait_manager_sweep_pid is not None:wait_for_sweep(args.wait_manager_sweep_pid)
    for season in ('2001-02','2002-03'):
        if args.wait_build_pid is not None:wait_build(season,args.wait_build_pid)
        run(season)
