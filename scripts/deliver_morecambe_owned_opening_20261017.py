"""Publish only the original-frame-reviewed actual Morecambe squad repair."""
import argparse
import copy
from datetime import UTC,datetime

from scripts import build_morecambe_owned_opening_20261017 as build
from scripts.capture_morecambe_owned_opening_20261017 import TAG,PROFILES
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


def check_profile_observation(label,reviewed):
    expected={'mark_smith':'GOALKEEPER','kenny_takano':'MIDFIELDER',
        'john_norman':'FORWARD','andy_banks':'GOALKEEPER'}
    if (label not in expected or reviewed.get('observed_club')!='Morecambe'
            or reviewed.get('observed_position')!=expected[label]):
        raise ValueError('literal original profile club/broad position differs from source decision')
    if label=='mark_smith' and reviewed.get('observed_nationality')!='ENGLAND':
        raise ValueError('new opening keeper lacks literal original England observation')


def main(previous_version):
    previous_path=build.ROOT.parent/f'release-delivery-checklist-v{previous_version}.json'
    output=build.ROOT.parent/f'release-delivery-checklist-v{previous_version+1}.json'
    if output.exists():raise ValueError('completed Morecambe publication must not repeat')
    previous=pipeline.read_json_file(previous_path);initial=bindings()
    if initial!=previous['current_release_bindings']:raise ValueError('previous checklist does not bind actual current defaults')
    base=registry.load_preferred_release(build.SEASON)
    if base.release_id!=build.source.admission.BASE:raise ValueError('Morecambe parent advanced; no intervening fixes discarded')
    actual=registry.load_registered_release(build.SEASON,build.RELEASE)
    plan=pipeline.read_json_file(build.ROOT/'opening-ownership-plan.json')
    build.source.verify(base,plan)
    retained(build.ROOT/'independent-prepublication-native-proof.json',build.native_proof(base,actual,plan))
    rebuilt=registry.load_registered_release(build.SEASON,build.REPLAY)
    proof=pipeline.read_json_file(build.ROOT/'complete-SOURCE-replay.json')
    if not proof['complete_game_inventory_identical'] or not proof['complete_recipe_identical']:
        raise ValueError('Morecambe complete SOURCE proof missing')
    for release in (actual,rebuilt):pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(actual.inventory_path))
    if actual.package_path.read_bytes()!=rebuilt.package_path.read_bytes():raise ValueError('Morecambe SOURCE recipe changed')
    evidence=registry.ROOT/'.local/runlogs/pm99_runner'/TAG
    transport=pipeline.read_json_file(build.ROOT/'startup-transport.json')
    summary=pipeline.read_json_file(evidence/'summary.json')
    visual=pipeline.read_json_file(build.ROOT/'startup-visual-review.json');check_visual(visual)
    if (transport['exit_code']!=0 or transport['release_manifest_sha256']!=actual.manifest_sha256
            or transport['evidence']!=registry.relative_workspace_path(evidence)
            or visual['observed_team']!='Stoke City' or visual['observed_date']!='2000-08-01'
            or visual['screenshot_sha256']!=registry.sha256_file(lineup_frame(evidence))
            or visual['release_manifest_sha256']!=actual.manifest_sha256
            or summary.get('success') is not True or summary.get('crash_detected') or summary.get('wine_debugger_detected')
            or summary.get('release_manifest_sha256')!=actual.manifest_sha256
            or summary.get('output_inventory_fingerprint')!=actual.locator['game_inventory_fingerprint']):
        raise ValueError('Morecambe final actual game lacks successful exact original startup')
    digits(build.ROOT,build.SEASON,build.RELEASE,PROFILES)
    verify_profiles(build.ROOT,build.SEASON,build.RELEASE,PROFILES)
    for _,label,_,_ in PROFILES:
        reviewed=pipeline.read_json_file(build.ROOT/(label+'-profile-visual-review.json'))
        check_profile_observation(label,reviewed)
    source_choice=build.source.admission.ROOT/'takano-country-and-birthday-source-choice-v1.json'
    choice=pipeline.read_json_file(source_choice)
    if (choice['nationality']['nationality']!='JPN' or choice['adopted_birth_date']!='1976-09-30'
            or choice['legacy_birthday']['published_birthday']!='1978-09-30'):
        raise ValueError('Takano inherited country and secondary DOB uncertainty not explicitly retained')
    choice_binding=bind(source_choice)
    backup=verify_original2015()
    if bindings()!=initial or bind(source_choice)!=choice_binding:
        raise ValueError('preferred release or explicit uncertainty source changed during prepublication')
    publisher.register_completed_delta(build.SEASON,build.RELEASE)
    retained(build.ROOT/'final-attestation.json',runtime.attest(season=build.SEASON,evidence_dir=evidence))
    playable=registry.validate_preferred_release(build.SEASON,level='playable')
    if not playable['valid']:raise ValueError('Morecambe final preferred playable gate failed')
    retained(build.ROOT/'preferred-playable-validation.json',playable)
    current=bindings()
    if [r for r in current if r['season']!=build.SEASON]!=[r for r in initial if r['season']!=build.SEASON]:
        raise ValueError('Morecambe publication changed another season')
    result=copy.deepcopy(previous)
    for finding in result['additional_confirmed_findings']:
        if finding['id']=='Morecambe2000-existing-roster-under-Barrow-native3312':
            finding.update(state='delivered-original-label-opening18-native-SOURCE-and-targeted-runner-verified',
                opening_squad_still_open=False,opening_squad_evidence=bind(build.ROOT/'native-byte-proof.json'),
                missing_source_starting_keeper=None,repaired_source_starting_keeper='Mark Smith',
                exact_match_fine_roles_or_opaque_tactics_approved=False)
        if finding['id']=='Morecambe2000-original-carrier-club-label-restored':
            finding.update(missing_starting_keeper_and_secondary_facts_still_open=False,
                opening_squad_followup_evidence=bind(build.ROOT/'native-byte-proof.json'))
    result['additional_confirmed_findings'].append(dict(id='Morecambe2000-missing-opening-keeper-three-birthdays-inherited-role-repair',
        season=build.SEASON,state='delivered-source-native-SOURCE-and-targeted-runner-verified',
        new_opening_keeper=11002,filled_missing_resident_birthdays=[10992,10995,10997],
        existing_people_and_skills_retained=17,cross_club_cases_closed=0,source_plan=bind(build.ROOT/'opening-ownership-plan.json')))
    result['additional_confirmed_findings'].append(dict(id='Takano2000-inherited-England-fallback-and-secondary-birthday-disagreement',
        season=build.SEASON,carrier_id=10992,state='country-correction-open-birthday-source-choice-explicitly-disputed',
        intended_nationality='JPN',current_nationality_in_runner='ENGLAND',
        birthday_choice='detailed numeric official profile1976 retained; official aggregate1978 alternative logged, no consensus claim',
        optional_birthday_uncertainty_is_not_a_new_frozen_native_recipe_mismatch=True,evidence=bind(source_choice)))
    names=['opening-ownership-plan.json','native-byte-proof.json','complete-SOURCE-replay.json',
        'startup-transport.json','startup-visual-review.json','independent-prepublication-native-proof.json',
        'final-attestation.json','preferred-playable-validation.json']
    names += [label+suffix for _,label,_,_ in PROFILES for suffix in (
        '-profile-transport.json','-profile-visual-review.json','-original-digit-proof.json','-original-age-proof.json','-native-runtime-proof.json')]
    result['delivered_evidence'] += [backup,bind(source_choice)]+[bind(build.ROOT/name) for name in names]
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=bind(previous_path),current_release_bindings=current,
        fresh_runtime_runs_this_checklist=[build.SEASON],all_required_work_complete=False,
        next_batch='Deliver sourced Takano2000 JPN country correction without altering the explicitly disputed adopted DOB. Continue frozen2789 cross-club cases, duplicate Tranmere3301 positive replacement, remaining positions/managers/known facts/assets/final regression. Morecambe3312 is not a new clone target.')
    pipeline.write_canonical_json(output,result)
    retained(build.ROOT/'final-delivery-summary.json',dict(checklist=bind(output),opening_squad_delivered=18,
        unchanged_other25_preferred_bindings=True,original2015_backup_verified=True,cross_club_cases_closed=0,global_historical_RC=False))
    print(dict(actual_Morecambe_opening_squad_delivered=True,global_historical_RC=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-version',type=int,required=True)
    main(parser.parse_args().previous_version)
