"""Fresh original-game startup and representative corrected Eastleigh actors."""
import argparse
import os
from pathlib import Path
import time
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.capture_arsenal_owned_opening_20261016 import bound_capture
from scripts.publish_eastleigh_private_20261017 import ROOT,RELEASE,SEASON

FOLDER=ROOT/'Eastleigh2014-native-delivery-v1'
TAG='eastleigh_original_opening_2014_15_r121a_20261017'
PROFILES=((11157,'flitney','Flitney'),(11165,'noice','Noice'),(11172,'odubade','Odubade'))


def main(pid=None):
    if pid is not None:
        deadline=time.monotonic()+1800
        while not (FOLDER/'complete-SOURCE-replay.json').exists():
            try:command=(Path('/proc')/str(pid)/'cmdline').read_bytes()
            except FileNotFoundError:raise ValueError('SOURCE builder stopped before proof; inspect rather than restart')
            if b'scripts.publish_eastleigh_private_20261017' not in command:
                raise ValueError('SOURCE wait PID identity changed')
            if time.monotonic()>deadline:raise ValueError('SOURCE observation window expired; inspect live process')
            time.sleep(10)
    if not (FOLDER/'complete-SOURCE-replay.json').exists():raise ValueError('whole SOURCE proof required')
    release=registry.load_registered_release(SEASON,RELEASE)
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    command,evidence=capture.capture_command(season=SEASON,worker='default',run_tag=TAG,
        compact_evidence=True,release_id=RELEASE)
    bound_capture(command,evidence,FOLDER/'startup-transport.json',release,env)
    players={p['carrier_id']:p for p in pipeline.read_json_file(release.package_path)['players']}
    for carrier,label,token in PROFILES:
        target=FOLDER/'runtime'/label
        command=[str(registry.ROOT/'scripts/run_stars_player_offer_probe_direct.sh'),
            '--worker','default','--run-tag',TAG+'_'+label,'--local-game-dir',str(release.game_path),
            '--local-artifact-dir',str(target),'--player-search',players[carrier]['name'],'--player-label',label,
            '--profile-name-token',token,'--profile-only','--provenance-file',str(release.compiler_receipt_path)]
        bound_capture(command,target,FOLDER/(label+'-profile-transport.json'),release,env)
        print(dict(actual_profile_captured=players[carrier]['name'],carrier=carrier,visual_review_pending=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--wait-source-pid',type=int)
    args=parser.parse_args();main(args.wait_source_pid)
