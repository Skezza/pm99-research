"""Capture proved actual batches serially on the existing single runner lane.

No generated approval: ROOT still inspects every returned original frame.
"""
import argparse
import os
from pathlib import Path
import time
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_frozen_fixture_reserve_v1 as source
from scripts import capture_registered_season_runtime_v1 as capture
from scripts.capture_arsenal_owned_opening_20261016 import bound_capture
from scripts.build_discovered_fixture_batches_20261017 import ROOT,RELEASE
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def tag(season):return 'frozen_original_fixture_'+season.replace('-','_')+'_r123a_20261017'


def wait_build(season,pid):
    folder=ROOT/season;deadline=time.monotonic()+3600
    while not (folder/'complete-SOURCE-replay.json').exists():
        if any((folder/name).exists() for name in ('source-gap.json','build-failure.json')):return False
        try:command=(Path('/proc')/str(pid)/'cmdline').read_bytes()
        except FileNotFoundError:raise ValueError('batch builder stopped without source proof/failure; inspect partial state')
        if b'scripts.build_discovered_fixture_batches_20261017' not in command:raise ValueError('batch wait PID identity changed')
        if time.monotonic()>deadline:raise ValueError('batch observation expired; inspect exact existing process')
        time.sleep(10)
    return True


def run(season):
    folder=ROOT/season;release=registry.load_registered_release(season,RELEASE)
    package=pipeline.read_json_file(release.package_path);players={p['carrier_id']:p for p in package['players']}
    plan=pipeline.read_json_file(folder/'ownership-plan.json');profiles={}
    for update in plan['updates']:
        for carrier,kind in ((update['carrier_id'],'replacement'),(update['retained_carrier_id'],'retained')):
            # The last-word token only locates the OCR screen; it never changes
            # a database name or authorises identity. Exact original full native
            # name, club, source DOB, ten skills and inputs still require review.
            name=players[carrier]['name'];label=kind+'_'+str(carrier)
            profiles[carrier]=dict(carrier_id=carrier,label=label,search=source.heading_name(name),
                token=source.heading_name(name).split()[-1],expected_exact_native_name=name,
                expected_source_name=players[carrier]['source_name'])
    retained(folder/'runtime-profile-spec.json',dict(season=season,release_id=RELEASE,
        manifest_sha256=release.manifest_sha256,profiles=list(profiles.values()),visual_approval=False))
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    command,evidence=capture.capture_command(season=season,worker='default',run_tag=tag(season),
        compact_evidence=True,release_id=RELEASE)
    bound_capture(command,evidence,folder/'startup-transport.json',release,env)
    for row in profiles.values():
        label=row['label'];target=folder/'runtime'/label
        command=[str(registry.ROOT/'scripts/run_stars_player_offer_probe_direct.sh'),
            '--worker','default','--run-tag',tag(season)+'_'+label,'--local-game-dir',str(release.game_path),
            '--local-artifact-dir',str(target),'--player-search',row['search'],'--player-label',label,
            '--profile-name-token',row['token'],'--profile-only','--provenance-file',str(release.compiler_receipt_path)]
        bound_capture(command,target,folder/(label+'-profile-transport.json'),release,env)
        print(dict(season=season,actual_profile_captured=row['expected_exact_native_name'],visual_review_pending=True),flush=True)
    retained(folder/'runtime-capture-summary.json',dict(season=season,release_id=RELEASE,
        actual_startup_and_profiles_captured=True,profiles=len(profiles),original_visual_review_pending=True,preferred_changed=False))


def main(pid):
    rows=pipeline.read_json_file(ROOT/'batch-input.json')['seasons']
    for row in rows:
        season=row['season']
        if not wait_build(season,pid):
            print(dict(season=season,not_captured='source/build refusal retained; no assumed success'),flush=True);continue
        run(season)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--batch-builder-pid',type=int,required=True)
    args=parser.parse_args();main(args.batch_builder_pid)
