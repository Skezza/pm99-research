"""Actual final-game checks of the replacement and retained native owner."""
import argparse
import os
from pathlib import Path
import time
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.capture_arsenal_owned_opening_20261016 import bound_capture
from scripts.build_aldred_frozen_fixture_20261017 import ROOT,SEASON,RELEASE

TAG='original_fixture_reserve_2014_15_r122a_20261017'
PROFILES=((9520,'waddington','Mark Waddington','Waddington'),(9580,'aldred','Aldred','Aldred'))


def main(pid=None):
    if pid is not None:
        deadline=time.monotonic()+1800
        while not (ROOT/'complete-SOURCE-replay.json').exists():
            try:command=(Path('/proc')/str(pid)/'cmdline').read_bytes()
            except FileNotFoundError:raise ValueError('original fixture builder stopped before proof; inspect, never restart')
            if b'scripts.build_aldred_frozen_fixture_20261017' not in command:
                raise ValueError('builder wait PID identity changed')
            if time.monotonic()>deadline:raise ValueError('observation window expired; inspect existing live builder')
            time.sleep(10)
    if not (ROOT/'complete-SOURCE-replay.json').exists():raise ValueError('whole SOURCE proof required')
    release=registry.load_registered_release(SEASON,RELEASE)
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    command,evidence=capture.capture_command(season=SEASON,worker='default',run_tag=TAG,
        compact_evidence=True,release_id=RELEASE)
    bound_capture(command,evidence,ROOT/'startup-transport.json',release,env)
    plan=pipeline.read_json_file(ROOT/'ownership-plan.json')
    if plan['updates'][0]['duplicate_source_person']['family_name']!='Aldred':
        raise ValueError('retained search surname is not the original exact published component')
    # Native #5 is a retained published shirt-heading decoration, not part of
    # the publisher's surname. Search the proved surname; final original frame
    # must still show the complete exact native actor and actual club/skills.
    for carrier,label,search,token in PROFILES:
        target=ROOT/'runtime'/label
        command=[str(registry.ROOT/'scripts/run_stars_player_offer_probe_direct.sh'),
            '--worker','default','--run-tag',TAG+'_'+label,'--local-game-dir',str(release.game_path),
            '--local-artifact-dir',str(target),'--player-search',search,'--player-label',label,
            '--profile-name-token',token,'--profile-only','--provenance-file',str(release.compiler_receipt_path)]
        bound_capture(command,target,ROOT/(label+'-profile-transport.json'),release,env)
        print(dict(actual_final_profile_captured=carrier,label=label,visual_review_pending=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--wait-builder-pid',type=int)
    args=parser.parse_args();main(args.wait_builder_pid)
