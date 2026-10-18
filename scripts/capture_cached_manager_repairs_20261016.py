"""Capture exact completed manager candidates without promoting them."""
import argparse
import os
from scripts import season_release_registry_v1 as registry
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.capture_city_opening_exchange_20261011 import captured
from scripts.build_cached_manager_repairs_20261016 import ROOT, RELEASE


def tag(season):return 'cached_managers_'+season.replace('-','_')+'_r109a_20261016'


def main(seasons):
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    for season in seasons:
        root=ROOT/season
        if not all((root/name).exists() for name in ('native-byte-proof.json','complete-SOURCE-replay.json')):
            raise ValueError('actual manager candidate not complete')
        release=registry.load_registered_release(season,RELEASE)
        command,evidence=capture.capture_command(season=season,worker='default',run_tag=tag(season),
            compact_evidence=True,release_id=RELEASE)
        captured(command,evidence,root/'startup-transport.json',release,env)
        print(dict(season=season,actual_manager_game_startup_complete=True,original_visual_review_pending=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('seasons',nargs='*',default=['2000-01'])
    main(parser.parse_args().seasons)
