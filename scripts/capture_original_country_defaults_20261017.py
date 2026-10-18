"""Serial actual country-batch startup/profile evidence, never visual approval."""
import argparse
from pathlib import Path
import time

from scripts import build_original_country_defaults_20261017 as build
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts.capture_shinnie_country_20261017 import main as capture,wait_owned
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def tag(season):
    return 'original_country_defaults_'+season.replace('-','_')+'_r127a_20261017'


def main(builder_pid,previous_runner_pid):
    wait_owned(previous_runner_pid,'scripts.capture_shinnie_position_20261017')
    rows=pipeline.read_json_file(build.ROOT/'batch-input.json')['rows']
    for row in rows:
        season=row['season'];folder=build.ROOT/season
        while not (folder/'complete-SOURCE-replay.json').exists():
            if any((folder/name).exists() for name in ('source-gap.json','build-failure.json')):
                print(dict(season=season,not_captured='retained refusal/partial state needs inspection'),flush=True)
                break
            process=Path('/proc')/str(builder_pid)/'cmdline'
            try:
                command=process.read_bytes()
            except FileNotFoundError as exc:
                raise ValueError('country builder stopped without required proof; inspect, do not restart') from exc
            if b'scripts.build_original_country_defaults_20261017' not in command:
                raise ValueError('country builder PID identity changed')
            time.sleep(10)
        else:
            release=registry.load_registered_release(season,build.RELEASE)
            plan=pipeline.read_json_file(folder/'country-plan.json')
            actors={p['carrier_id']:p for p in pipeline.read_json_file(release.package_path)['players']}
            priority=18083 if season=='2025-26' else min(r['carrier_id'] for r in plan['updates'])
            if priority not in {r['carrier_id'] for r in plan['updates']}:
                priority=min(r['carrier_id'] for r in plan['updates'])
            name=actors[priority]['name']
            search=build.source.original.names.undecorated(name)
            profile=dict(carrier_id=priority,label='country_'+str(priority),search=search,
                token=search.split()[-1],expected_native_name=name,
                expected_country=actors[priority]['facts']['nationality'])
            retained(folder/'runtime-profile-spec.json',dict(season=season,release_id=build.RELEASE,
                manifest_sha256=release.manifest_sha256,profiles=[profile],visual_approval=False,
                all_changed_countries_native_readback_required=True))
            capture(0,0,folder=folder,release_id=build.RELEASE,run_tag=tag(season),season=season,profile=profile)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--builder-pid',type=int,required=True)
    parser.add_argument('--previous-runner-pid',type=int,required=True)
    args=parser.parse_args();main(args.builder_pid,args.previous_runner_pid)
