"""Publish one already reviewed season through the reusable final-proof gate."""
import argparse
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts.checkpoint_frozen_fixture_reserve_v1 import run
from scripts.build_discovered_fixture_batches_20261017 import ROOT,RELEASE,REPLAY
from scripts.capture_discovered_fixture_batches_20261017 import tag


def main(season,previous_version):
    folder=ROOT/season
    release=registry.load_registered_release(season,RELEASE)
    spec=pipeline.read_json_file(folder/'runtime-profile-spec.json')
    if (spec['season'],spec['release_id'],spec['manifest_sha256'])!=(season,RELEASE,release.manifest_sha256):
        raise ValueError('runtime profile inputs bind another actual game')
    profiles=[(r['carrier_id'],r['label'],r['search'],r['token']) for r in spec['profiles']]
    run(folder,season,RELEASE,REPLAY,ROOT.parent/f'release-delivery-checklist-v{previous_version}.json',
        ROOT.parent/f'release-delivery-checklist-v{previous_version+1}.json',tag(season),profiles)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season',choices=['2011-12','2017-18','2021-22','2024-25','2025-26'],required=True)
    parser.add_argument('--previous-checklist-version',type=int,required=True)
    args=parser.parse_args();main(args.season,args.previous_checklist_version)
