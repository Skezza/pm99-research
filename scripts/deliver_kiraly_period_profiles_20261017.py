"""Promote each exact source/native/SOURCE/original-frame-verified Kiraly game."""
import argparse
import copy
from datetime import UTC,datetime
from scripts import build_kiraly_period_profiles_20261017 as build
from scripts.capture_kiraly_period_profiles_20261017 import tag,profile
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import publish_historical_role_delta_v1 as publisher,attest_registered_season_runtime_v1 as runtime
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_remaining_manager_tenures_20261016 import verify_original2015
from scripts.review_rating_frames_20261011 import lineup_frame
from scripts.verify_profile_skill_digits_v1 import verify_profiles as digits
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def bind(path):return dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path))


def main(season,previous_version):
    root=build.ROOT/season;old_path=build.ROOT.parent/f'release-delivery-checklist-v{previous_version}.json'
    output=build.ROOT.parent/f'release-delivery-checklist-v{previous_version+1}.json'
    if output.exists():raise ValueError('completed country/keeper publication must not repeat')
    previous=pipeline.read_json_file(old_path);initial=bindings()
    if initial!=previous['current_release_bindings']:raise ValueError('country previous checkpoint differs from current defaults')
    delivered={r['season'] for r in previous['additional_confirmed_findings'] if r['id'].startswith('Kiraly-period-country-keeper-')}
    if season in delivered or not delivered<=set(build.source.TARGETS):raise ValueError('country/keeper count repeats or escapes fixed eight-season scope')
    plan=pipeline.read_json_file(root/'profile-plan.json');base=registry.load_preferred_release(season)
    if base.release_id!=plan['release_id']:raise ValueError('country exact source parent not yet default or has advanced; preserve intervening fixes')
    actual=registry.load_registered_release(season,build.RELEASE)
    retained(root/'independent-prepublication-native-proof.json',build.verify_native(base,actual,plan))
    rebuilt=registry.load_registered_release(season,build.REPLAY);proof=pipeline.read_json_file(root/'complete-SOURCE-replay.json')
    if not proof['complete_game_inventory_identical'] or not proof['complete_recipe_identical']:raise ValueError('Kiraly SOURCE proof incomplete')
    for release in (actual,rebuilt):pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(actual.inventory_path))
    if actual.package_path.read_bytes()!=rebuilt.package_path.read_bytes():raise ValueError('Kiraly full SOURCE recipe differs')
    evidence=registry.ROOT/'.local/runlogs/pm99_runner'/tag(season)
    transport=pipeline.read_json_file(root/'startup-transport.json');summary=pipeline.read_json_file(evidence/'summary.json')
    visual=pipeline.read_json_file(root/'startup-visual-review.json');check_visual(visual)
    if (transport['exit_code']!=0 or transport['release_manifest_sha256']!=actual.manifest_sha256
            or transport['evidence']!=registry.relative_workspace_path(evidence)
            or visual['observed_team']!='Stoke City' or visual['observed_date']!=season[:4]+'-08-01'
            or visual['screenshot_sha256']!=registry.sha256_file(lineup_frame(evidence))
            or visual['release_manifest_sha256']!=actual.manifest_sha256 or summary.get('success') is not True
            or summary.get('crash_detected') or summary.get('wine_debugger_detected')
            or summary.get('release_manifest_sha256')!=actual.manifest_sha256
            or summary.get('output_inventory_fingerprint')!=actual.locator['game_inventory_fingerprint']):
        raise ValueError('actual country/keeper startup lacks original-frame verification')
    spec=profile(season);digits(root,season,build.RELEASE,[spec]);verify_profiles(root,season,build.RELEASE,[spec])
    review=pipeline.read_json_file(root/(spec[1]+'-profile-visual-review.json'))
    if (review.get('observed_nationality')!='HUNGARY' or review.get('observed_position')!='GOALKEEPER'
            or review.get('observed_fine_position')!='KEEPER' or review['observed_age']!=int(season[:4])-1976):
        raise ValueError('original Kiraly Hungary/goalkeeper/keeper/age literal observation differs')
    backup=verify_original2015()
    if bindings()!=initial:raise ValueError('preferred games advanced during Kiraly prepublication')
    publisher.register_completed_delta(season,build.RELEASE)
    retained(root/'final-attestation.json',runtime.attest(season=season,evidence_dir=evidence))
    valid=registry.validate_preferred_release(season,level='playable')
    if not valid['valid']:raise ValueError('promoted Kiraly game failed playable check')
    retained(root/'preferred-playable-validation.json',valid);current=bindings()
    if [r for r in current if r['season']!=season]!=[r for r in initial if r['season']!=season]:
        raise ValueError('country/keeper publication changed another season')
    result=copy.deepcopy(previous)
    delivered.add(season)
    for item in result['new_required_followups']:
        if item['id']=='Hertha2000-retained-Kiraly-known-country-and-fine-role':
            item.update(status='delivered-eight-season-source-native-SOURCE-and-runner-verified' if len(delivered)==8 else 'cascade-in-progress-other-season-corrections-pending',
                delivered_seasons=sorted(delivered),remaining_confirmed_country_seasons=sorted(set(build.source.TARGETS)-delivered),
                ownership_and_other_Haladas_duplicates_not_approved=True)
    result['additional_confirmed_findings'].append(dict(id='Kiraly-period-country-keeper-'+season,
        season=season,state='delivered-native-SOURCE-and-runner-verified',carrier_id=plan['carrier_id'],
        country='HUNGARY',fine_roles=[0],native_bytes_changed=plan['expected_native_byte_changes'],
        role_values_corrected=int(plan['expected_native_byte_changes']==3),ratings_and_all_other_data_preserved=True,
        cross_club_cases_closed=0,historical_opening_ownership_approved=False,source_plan=bind(root/'profile-plan.json')))
    names=['profile-plan.json','native-byte-proof.json','complete-SOURCE-replay.json','startup-transport.json','startup-visual-review.json',
        'independent-prepublication-native-proof.json','final-attestation.json','preferred-playable-validation.json']
    names+=[spec[1]+s for s in ('-profile-transport.json','-profile-visual-review.json','-original-digit-proof.json','-original-age-proof.json','-native-runtime-proof.json')]
    result['delivered_evidence'] += [backup]+[bind(root/name) for name in names]
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=bind(old_path),current_release_bindings=current,
        fresh_runtime_runs_this_checklist=[season],all_required_work_complete=False,
        next_batch='Complete eight actual Kiraly country/keeper repairs, then frozen cross-club/opening squads and known kit/manager/facts/assets/final checklist. No country correction closes an ownership case or certifies the club/roster.')
    pipeline.write_canonical_json(output,result)
    retained(root/'final-delivery-summary.json',dict(checklist=bind(output),native_bytes_changed=plan['expected_native_byte_changes'],
        delivered_country_seasons=len(delivered),unchanged_other25_bindings=True,original2015_backup_verified=True,
        cross_club_cases_closed=0,global_historical_RC=False))
    print(dict(season=season,Kiraly_Hungary_keeper_delivered=True,delivered_country_seasons=len(delivered)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--season',choices=build.source.TARGETS,required=True)
    parser.add_argument('--previous-version',type=int,required=True);args=parser.parse_args()
    main(args.season,args.previous_version)
