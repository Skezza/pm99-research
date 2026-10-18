"""Capture each newly changed game once, waiting only on the live own builder."""
import argparse
import os
from pathlib import Path
import time
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.build_donor_role_safety_20261016 import ROOT, RELEASE
from scripts.capture_city_opening_exchange_20261011 import captured


def tag(season):
    return 'donor_role_safety_'+season.replace('-','_')+'_r108a_20261016'


def main(build_pid):
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    for season in registry.supported_seasons():
        root=ROOT/season;deadline=time.monotonic()+14400
        while not (root/'complete-SOURCE-replay.json').exists():
            proc=Path('/proc')/str(build_pid)/'cmdline'
            if not proc.exists() or b'scripts.build_donor_role_safety_20261016' not in proc.read_bytes():
                raise ValueError('own builder is no longer live; inspect its terminal outcome before resuming')
            if time.monotonic()>deadline:raise ValueError('bounded own build wait expired')
            time.sleep(10)
        release=registry.load_registered_release(season,RELEASE)
        receipt=root/'startup-transport.json'
        if receipt.exists():
            prior=pipeline.read_json_file(receipt)
            if prior['exit_code']!=0 or prior['release_manifest_sha256']!=release.manifest_sha256:
                raise ValueError('existing startup transport failed or belongs to a different game')
            print(dict(season=season,reused_existing_exact_startup=True),flush=True)
            continue
        command,evidence=capture.capture_command(season=season,worker='default',run_tag=tag(season),
            compact_evidence=True,release_id=RELEASE)
        captured(command,evidence,receipt,release,env)
        print(dict(season=season,actual_new_game_startup_complete=True,original_visual_review_pending=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-pid',type=int,required=True)
    main(parser.parse_args().build_pid)
