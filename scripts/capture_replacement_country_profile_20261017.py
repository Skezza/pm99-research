"""Capture ONLY a missing alternate country profile after a wrong-carrier search.

Retain the original failed carrier evidence/spec; never rerun startup or build.
"""
import argparse
import os

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import build_original_country_defaults_20261017 as build
from scripts.capture_original_country_defaults_20261017 import tag
from scripts.capture_arsenal_owned_opening_20261016 import bound_capture
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def main(season, carrier):
    folder=build.ROOT/season
    actual=registry.load_registered_release(season,build.RELEASE)
    plan=pipeline.read_json_file(folder/'country-plan.json')
    if carrier not in {r['carrier_id'] for r in plan['updates']}:
        raise ValueError('alternate must be an actually corrected country carrier')
    old=pipeline.read_json_file(folder/'runtime-profile-spec.json')
    old_label=old['profiles'][0]['label']
    if old['manifest_sha256']!=actual.manifest_sha256 or carrier==old['profiles'][0]['carrier_id']:
        raise ValueError('alternate must use the same game and a distinct missing carrier')
    saved=folder/'runtime-profile-spec-rejected-wrong-carrier-v1.json'
    if saved.exists():
        raise ValueError('alternate capture already prepared; inspect before rerun')
    label='country_'+str(carrier)
    if (folder/(label+'-profile-transport.json')).exists():
        raise ValueError('existing alternate transport needs inspection')
    old_review=folder/(old_label+'-profile-visual-review.json')
    if old_review.exists():
        old_review.rename(folder/(old_label+'-profile-visual-review-rejected-wrong-carrier-v1.json'))
    (folder/'runtime-profile-spec.json').rename(saved)
    actor=next(p for p in pipeline.read_json_file(actual.package_path)['players'] if p['carrier_id']==carrier)
    search=build.source.original.names.undecorated(actor['name'])
    profile=dict(carrier_id=carrier,label=label,search=search,token=search.split()[-1],
        expected_native_name=actor['name'],expected_country=actor['facts']['nationality'])
    retained(folder/'runtime-profile-spec.json',dict(season=season,release_id=build.RELEASE,
        manifest_sha256=actual.manifest_sha256,profiles=[profile],visual_approval=False,
        all_changed_countries_native_readback_required=True,
        previous_profile_rejected='Original country_9912 search opened carrier9201 Chelsea, not9912 Wigan; ten-skill gate refused publication.' if season=='2012-13' else 'Wrong carrier: retained rejected evidence requires independent review.'))
    env=dict(os.environ,PM99_RUNNER_ARCHIVE_COLD_RUNS='0',PM99_RUNNER_RUN_ROOT_BUDGET_ENFORCE='0')
    target=folder/'runtime'/label
    command=[str(registry.ROOT/'scripts/run_stars_player_offer_probe_direct.sh'),
        '--worker','default','--run-tag',tag(season)+'_'+label,
        '--local-game-dir',str(actual.game_path),'--local-artifact-dir',str(target),
        '--player-search',search,'--player-label',label,'--profile-name-token',profile['token'],
        '--profile-only','--provenance-file',str(actual.compiler_receipt_path)]
    bound_capture(command,target,folder/(label+'-profile-transport.json'),actual,env)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season',required=True);parser.add_argument('--carrier',type=int,required=True)
    args=parser.parse_args();main(args.season,args.carrier)
