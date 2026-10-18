"""Publish a reviewed final country game, proving any private country parents."""
import argparse

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_original_country_policy_v2 as source
from scripts import build_country_policy_v2_cohort_20261017 as build
from scripts import build_original_country_defaults_20261017 as initial
from scripts import build_original_country_policy_v2_20261017 as early
from scripts.capture_country_policy_v2_cohort_20261017 import tag
from scripts.checkpoint_original_country_batch_v1 import run
from scripts.verify_country_only_ancestry_v1 import Edge


def main(season, previous_version):
    folder=build.ROOT/season
    actual=registry.load_registered_release(season,build.RELEASE)
    spec=pipeline.read_json_file(folder/'runtime-profile-spec.json')
    if (spec['season'],spec['release_id'],spec['manifest_sha256'])!=(season,build.RELEASE,actual.manifest_sha256):
        raise ValueError('country cohort runtime spec binds another actual game')
    profiles=[(r['carrier_id'],r['label'],r['search'],r['token']) for r in spec['profiles']]
    run_tag=spec.get('startup_run_tag_override',tag(season))
    if run_tag not in (tag(season),tag(season)+'_disk_recovery_v1'):
        raise ValueError('unrecognised country runtime recovery tag')
    run(folder,season,build.RELEASE,build.REPLAY,
        build.ROOT.parent/f'release-delivery-checklist-v{previous_version}.json',
        build.ROOT.parent/f'release-delivery-checklist-v{previous_version+1}.json',
        run_tag,profiles,source=source,ancestors=[
            Edge(initial.RELEASE,initial.REPLAY,initial.ROOT/season),
            Edge(early.RELEASE,early.REPLAY,early.ROOT/season)])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season',required=True)
    parser.add_argument('--previous-checklist-version',type=int,required=True)
    args=parser.parse_args();main(args.season,args.previous_checklist_version)
