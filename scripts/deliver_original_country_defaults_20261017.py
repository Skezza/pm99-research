"""Publish one actually reviewed r127 country season; never auto-review frames."""
import argparse
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts.build_original_country_defaults_20261017 import ROOT,RELEASE,REPLAY
from scripts.capture_original_country_defaults_20261017 import tag
from scripts.checkpoint_original_country_batch_v1 import run


def main(season,previous_version):
    folder=ROOT/season;actual=registry.load_registered_release(season,RELEASE)
    spec=pipeline.read_json_file(folder/'runtime-profile-spec.json')
    if (spec['season'],spec['release_id'],spec['manifest_sha256'])!=(season,RELEASE,actual.manifest_sha256):
        raise ValueError('country runtime spec binds another actual game')
    profiles=[(r['carrier_id'],r['label'],r['search'],r['token']) for r in spec['profiles']]
    run(folder,season,RELEASE,REPLAY,ROOT.parent/f'release-delivery-checklist-v{previous_version}.json',
        ROOT.parent/f'release-delivery-checklist-v{previous_version+1}.json',tag(season),profiles)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season',required=True)
    parser.add_argument('--previous-checklist-version',type=int,required=True)
    args=parser.parse_args();main(args.season,args.previous_checklist_version)
