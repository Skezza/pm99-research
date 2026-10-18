"""Capture one SOURCE-complete versioned country-policy game on the shared lane."""
import argparse
from scripts import build_original_country_policy_v2_20261017 as build
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts.capture_shinnie_country_20261017 import main as capture
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def tag(season):
    return 'original_country_policy_v2_'+season.replace('-','_')+'_r128a_20261017'


def main(season):
    folder=build.ROOT/season
    if not (folder/'complete-SOURCE-replay.json').exists():
        raise ValueError('versioned country policy whole SOURCE proof required before capture')
    actual=registry.load_registered_release(season,build.RELEASE)
    plan=pipeline.read_json_file(folder/'country-plan.json')
    carrier=min(r['carrier_id'] for r in plan['updates'])
    actor=next(p for p in pipeline.read_json_file(actual.package_path)['players'] if p['carrier_id']==carrier)
    search=build.source.original.names.undecorated(actor['name'])
    profile=dict(carrier_id=carrier,label='country_'+str(carrier),search=search,token=search.split()[-1],
        expected_native_name=actor['name'],expected_source_country=actor['facts']['nationality'])
    retained(folder/'runtime-profile-spec.json',dict(season=season,release_id=build.RELEASE,
        manifest_sha256=actual.manifest_sha256,profiles=[profile],visual_approval=False))
    capture(0,0,folder=folder,release_id=build.RELEASE,run_tag=tag(season),season=season,profile=profile)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--season',required=True)
    main(parser.parse_args().season)
