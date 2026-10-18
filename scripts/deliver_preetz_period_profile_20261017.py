"""Promote exact native/SOURCE/original-frame-verified Preetz repairs only."""
import argparse
import copy
from datetime import UTC,datetime
from scripts import build_preetz_period_profile_20261017 as build
from scripts.capture_preetz_period_profile_20261017 import PROFILE,tag
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.review_rating_frames_20261011 import lineup_frame
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_remaining_manager_tenures_20261016 import verify_original2015
from scripts.verify_profile_skill_digits_v1 import verify_profiles as digits
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def bind(path):return dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path))


def main(season,previous_version):
    folder=build.ROOT/season;old_path=build.ROOT.parent/f'release-delivery-checklist-v{previous_version}.json'
    output=build.ROOT.parent/f'release-delivery-checklist-v{previous_version+1}.json'
    if output.exists():raise ValueError('completed Preetz publication must not repeat')
    previous=pipeline.read_json_file(old_path);initial=bindings()
    if initial!=previous['current_release_bindings']:raise ValueError('Preetz previous checkpoint differs from actual defaults')
    plan=pipeline.read_json_file(folder/'profile-plan.json');base=registry.load_preferred_release(season)
    if base.release_id!=plan['release_id']:raise ValueError('Preetz parent advanced; preserve intervening fixes')
    actual=registry.load_registered_release(season,build.RELEASE)
    retained(folder/'independent-prepublication-native-proof.json',build.verify_native(base,actual,plan))
    rebuilt=registry.load_registered_release(season,build.REPLAY)
    proof=pipeline.read_json_file(folder/'complete-SOURCE-replay.json')
    if not proof['complete_game_inventory_identical'] or not proof['complete_recipe_identical']:
        raise ValueError('Preetz complete SOURCE proof incomplete')
    for release in (actual,rebuilt):pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(actual.inventory_path))
    if actual.package_path.read_bytes()!=rebuilt.package_path.read_bytes():raise ValueError('Preetz SOURCE recipe differs')
    evidence=registry.ROOT/'.local/runlogs/pm99_runner'/tag(season)
    transport=pipeline.read_json_file(folder/'startup-transport.json');summary=pipeline.read_json_file(evidence/'summary.json')
    visual=pipeline.read_json_file(folder/'startup-visual-review.json');check_visual(visual)
    if (transport['exit_code']!=0 or transport['release_manifest_sha256']!=actual.manifest_sha256
            or transport['evidence']!=registry.relative_workspace_path(evidence)
            or visual['observed_team']!='Stoke City' or visual['observed_date']!=season[:4]+'-08-01'
            or visual['screenshot_sha256']!=registry.sha256_file(lineup_frame(evidence))
            or visual['release_manifest_sha256']!=actual.manifest_sha256
            or summary.get('success') is not True or summary.get('crash_detected') or summary.get('wine_debugger_detected')
            or summary.get('release_manifest_sha256')!=actual.manifest_sha256
            or summary.get('output_inventory_fingerprint')!=actual.locator['game_inventory_fingerprint']):
        raise ValueError('Preetz actual final-game startup lacks independent literal verification')
    digits(folder,season,build.RELEASE,[PROFILE]);verify_profiles(folder,season,build.RELEASE,[PROFILE])
    review=pipeline.read_json_file(folder/(PROFILE[1]+'-profile-visual-review.json'))
    if (review.get('observed_nationality')!='GERMANY' or review.get('observed_position')!='FORWARD'
            or review.get('observed_fine_position')!='CENTRAL STRIKER' or review['observed_age']!=int(season[:4])-1967):
        raise ValueError('literal Preetz Germany/forward/central-striker/age frame not approved')
    backup=verify_original2015()
    if bindings()!=initial:raise ValueError('preferred games advanced during Preetz prepublication')
    publisher.register_completed_delta(season,build.RELEASE)
    retained(folder/'final-attestation.json',runtime.attest(season=season,evidence_dir=evidence))
    playable=registry.validate_preferred_release(season,level='playable')
    if not playable['valid']:raise ValueError('Preetz final default failed playable gate')
    retained(folder/'preferred-playable-validation.json',playable);current=bindings()
    if [r for r in current if r['season']!=season]!=[r for r in initial if r['season']!=season]:
        raise ValueError('Preetz publication changed another season')
    result=copy.deepcopy(previous)
    for item in result['new_required_followups']:
        if item['id']=='Michael-Preetz-inherited-country-and-fine-position':
            item['affected_season_carriers']=[['2000-01',12468],['2001-02',12468]]
            item['scoped_2002_03_already_correct_no_native_or_recipe_changes']=True
            item['delivered_seasons']=sorted(set(item.get('delivered_seasons',[])+[season]))
            item['status']=('delivered-native-SOURCE-and-runner-verified' if len(item['delivered_seasons'])==2 else 'one-season-delivered-second-confirmed-repair-pending')
    result['additional_confirmed_findings'].append(dict(id='Preetz-country-and-first-profile-role-'+season,
        season=season,state='delivered-native-SOURCE-and-runner-verified',country='GERMANY',fine_role='Central Striker',
        fine_role_mapping='explicit-standard-editorial-from-official-dated-striker-role-not-FIFA',
        native_byte_changes=2,cross_club_cases_closed=0,source_plan=bind(folder/'profile-plan.json')))
    if season=='2001-02' and review['observed_club']=='1. FC Koln':
        result['new_required_followups'].append(dict(id='Hertha2001-native421-Koln-club-label-source-conflict',
            season=season,status='open-observed-source-club-label-conflict-cohort-adjudication-required',
            evidence=bind(folder/(PROFILE[1]+'-profile-visual-review.json')),
            source_decision=bind(folder/'profile-plan.json'),
            scope='Preetz profile still displays inherited Koln club label, inconsistent with official Hertha2000-2003 captaincy. Country/position delivery is not club-label approval. Independently verify full authored cohort/native coach/ground/original carrier before label-only or coupled repair.'))
    names=['profile-plan.json','native-byte-proof.json','complete-SOURCE-replay.json','startup-transport.json','startup-visual-review.json',
        'independent-prepublication-native-proof.json','final-attestation.json','preferred-playable-validation.json']
    names+=[PROFILE[1]+s for s in ('-profile-transport.json','-profile-visual-review.json','-original-digit-proof.json','-original-age-proof.json','-native-runtime-proof.json')]
    result['delivered_evidence'] += [backup]+[bind(folder/name) for name in names]
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=bind(old_path),current_release_bindings=current,
        fresh_runtime_runs_this_checklist=[season],all_required_work_complete=False,
        next_batch='Finish both source-confirmed Preetz fixes, then frozen2789 cross-club cases including Kiraly/Haladas original opening keeper and broader opening-squad/position/manager/known-fact/asset/final checklist. No global historical approval.')
    pipeline.write_canonical_json(output,result)
    retained(folder/'final-delivery-summary.json',dict(checklist=bind(output),native_byte_changes=2,
        unaffected_other25_bindings_preserved=True,original2015_backup_verified=True,global_historical_RC=False))
    print(dict(season=season,Preetz_Germany_striker_delivered=True,global_historical_RC=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--season',choices=build.source.TARGETS,required=True)
    parser.add_argument('--previous-version',type=int,required=True);args=parser.parse_args()
    main(args.season,args.previous_version)
