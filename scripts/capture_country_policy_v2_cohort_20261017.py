"""Capture completed policy-cohort games on the existing FIFO runner lane."""
import argparse
from pathlib import Path
import time

from scripts import build_country_policy_v2_cohort_20261017 as build
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts.capture_shinnie_country_20261017 import main as capture
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def tag(season):
    return 'country_policy_v2_cohort_'+season.replace('-','_')+'_r129a_20261017'


def main(builder_pid):
    rows=pipeline.read_json_file(build.ROOT/'batch-input.json')['rows']
    for row in rows:
        season=row['season'];folder=build.ROOT/season
        while not (folder/'complete-SOURCE-replay.json').exists():
            result_path=folder/'cohort-result.json'
            if result_path.exists() and pipeline.read_json_file(result_path)['status']=='no-new-game-already-correct-or-unresolved':
                print(dict(season=season,no_capture='no new game; source-complete parent retained'),flush=True)
                break
            if (folder/'build-failure.json').exists():
                print(dict(season=season,no_capture='retained build failure needs inspection'),flush=True)
                break
            try:
                command=Path(f'/proc/{builder_pid}/cmdline').read_bytes()
            except FileNotFoundError as exc:
                raise ValueError('policy cohort builder stopped without proof/result; inspect existing state') from exc
            if b'scripts.build_country_policy_v2_cohort_20261017' not in command:
                raise ValueError('policy cohort builder PID changed')
            time.sleep(10)
        else:
            actual=registry.load_registered_release(season,build.RELEASE)
            plan=pipeline.read_json_file(folder/'country-plan.json')
            changed=sorted(plan['updates'],key=lambda r:(r['native_label']!='CONGO',r['native_label']!='XXX',r['carrier_id']))
            selected=changed[0];carrier=selected['carrier_id']
            actor=next(p for p in pipeline.read_json_file(actual.package_path)['players'] if p['carrier_id']==carrier)
            search=build.source.original.names.undecorated(actor['name'])
            profile=dict(carrier_id=carrier,label='country_'+str(carrier),search=search,token=search.split()[-1],
                expected_native_name=actor['name'],expected_country=actor['facts']['nationality'],
                expected_native_country_label=selected['native_label'])
            retained(folder/'runtime-profile-spec.json',dict(season=season,release_id=build.RELEASE,
                manifest_sha256=actual.manifest_sha256,profiles=[profile],visual_approval=False,
                parent_chain_may_need_composed_country_delivery=True))
            capture(0,0,folder=folder,release_id=build.RELEASE,run_tag=tag(season),season=season,profile=profile)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--builder-pid',type=int,required=True)
    main(parser.parse_args().builder_pid)
