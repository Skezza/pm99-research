"""Publish a fully ROOT-reviewed position correction without unrelated changes."""
import argparse

from scripts import build_exact_position_batch_20261017 as build
from scripts.capture_exact_position_batch_20261017 import tag
from scripts.checkpoint_exact_primary_position_v1 import run


def main(season,previous_version):
    folder=build.ROOT/season
    spec=build.pipeline.read_json_file(folder/'runtime-profile-spec.json')
    actual=build.registry.load_registered_release(season,build.RELEASE)
    if (spec['season'],spec['release_id'],spec['manifest_sha256'])!=(season,build.RELEASE,actual.manifest_sha256):
        raise ValueError('position runtime spec binds another actual game')
    profiles=[(r['carrier_id'],r['label'],r['search'],r['token']) for r in spec['profiles']]
    run(folder,season,build.RELEASE,build.REPLAY,
        build.ROOT.parent/f'release-delivery-checklist-v{previous_version}.json',
        build.ROOT.parent/f'release-delivery-checklist-v{previous_version+1}.json',tag(season),profiles)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season',required=True);parser.add_argument('--previous-checklist-version',type=int,required=True)
    args=parser.parse_args();main(args.season,args.previous_checklist_version)
