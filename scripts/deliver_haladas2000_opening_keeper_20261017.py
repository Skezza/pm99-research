"""Close exactly the source/native/SOURCE/runner-proved Kiraly owner case."""
import argparse
import copy
from datetime import UTC,datetime
from scripts import build_haladas2000_opening_keeper_20261017 as build
from scripts.capture_haladas2000_opening_keeper_20261017 import TAG,PROFILES
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_frozen_fixture_reserve_v1 import next_count
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_remaining_manager_tenures_20261016 import verify_original2015
from scripts.review_rating_frames_20261011 import lineup_frame
from scripts.verify_profile_skill_digits_v1 import verify_profiles as digits
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def bind(path):return dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path))


def main(previous_version):
    root=build.ROOT;season='2000-01';old_path=root.parent/f'release-delivery-checklist-v{previous_version}.json'
    output=root.parent/f'release-delivery-checklist-v{previous_version+1}.json'
    if output.exists():raise ValueError('completed Haladas publication must not repeat')
    previous=pipeline.read_json_file(old_path);initial=bindings()
    if initial!=previous['current_release_bindings']:raise ValueError('Haladas previous checkpoint differs from actual defaults')
    plan=pipeline.read_json_file(root/'keeper-plan.json');base=registry.load_preferred_release(season)
    if base.release_id!=plan['release_id']:raise ValueError('Haladas parent advanced; preserve intervening fixes')
    actual=registry.load_registered_release(season,build.RELEASE)
    retained(root/'independent-prepublication-native-proof.json',build.verify_native(base,actual,plan))
    case_id=plan['source_decision']['frozen_case_id'];remaining=next_count(previous,[dict(case_id=case_id)])
    package=pipeline.read_json_file(actual.package_path)
    actors=[p for _,layer,_ in build.source.delta.planner.package_layers(actual) for p in layer['players']]
    if {p['carrier_id'] for p in actors if build.source.roster.normalise(p.get('source_name') or p['name'])=='gaborkiraly'
            and p['facts'].get('birth_date')=='1976-04-01'}!={2211}:
        raise ValueError('frozen Kiraly identity still has another represented copy')
    selected=next(p for p in package['players'] if p['carrier_id']==8507)
    if (selected['source_name'],selected['facts']['birth_date'],selected['facts']['nationality'])!=('Kornél Kurucsai','1972-01-18','HUN'):
        raise ValueError('selected current replacement is not exact original opening person')
    rebuilt=registry.load_registered_release(season,build.REPLAY);proof=pipeline.read_json_file(root/'complete-SOURCE-replay.json')
    if not proof['complete_game_inventory_identical'] or not proof['complete_recipe_identical']:raise ValueError('Haladas SOURCE incomplete')
    for release in (actual,rebuilt):pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(actual.inventory_path))
    if actual.package_path.read_bytes()!=rebuilt.package_path.read_bytes():raise ValueError('Haladas SOURCE recipe differs')
    evidence=registry.ROOT/'.local/runlogs/pm99_runner'/TAG
    transport=pipeline.read_json_file(root/'startup-transport.json');summary=pipeline.read_json_file(evidence/'summary.json')
    visual=pipeline.read_json_file(root/'startup-visual-review.json');check_visual(visual)
    if (transport['exit_code']!=0 or transport['release_manifest_sha256']!=actual.manifest_sha256
            or transport['evidence']!=registry.relative_workspace_path(evidence)
            or visual['observed_team']!='Stoke City' or visual['observed_date']!='2000-08-01'
            or visual['screenshot_sha256']!=registry.sha256_file(lineup_frame(evidence))
            or visual['release_manifest_sha256']!=actual.manifest_sha256 or summary.get('success') is not True
            or summary.get('crash_detected') or summary.get('wine_debugger_detected')
            or summary.get('release_manifest_sha256')!=actual.manifest_sha256
            or summary.get('output_inventory_fingerprint')!=actual.locator['game_inventory_fingerprint']):
        raise ValueError('Haladas final actual startup lacks exact original-frame approval')
    digits(root,season,build.RELEASE,PROFILES);verify_profiles(root,season,build.RELEASE,PROFILES)
    keeper=pipeline.read_json_file(root/'haladas_kurucsai-profile-visual-review.json')
    if keeper.get('observed_nationality')!='HUNGARY' or keeper.get('observed_position')!='GOALKEEPER' or keeper['observed_age']!=28:
        raise ValueError('original selected keeper nationality/role/age observation differs')
    backup=verify_original2015()
    if bindings()!=initial:raise ValueError('preferred releases advanced during Haladas prepublication')
    publisher.register_completed_delta(season,build.RELEASE)
    retained(root/'final-attestation.json',runtime.attest(season=season,evidence_dir=evidence))
    valid=registry.validate_preferred_release(season,level='playable')
    if not valid['valid']:raise ValueError('Haladas final default failed playable gate')
    retained(root/'preferred-playable-validation.json',valid);current=bindings()
    if [r for r in current if r['season']!=season]!=[r for r in initial if r['season']!=season]:
        raise ValueError('Haladas publication changed another season')
    result=copy.deepcopy(previous)
    result['cross_club_dispositions'].append(dict(case_id=case_id,season=season,
        state='confirmed-fault-repaired-current-game',retained_native_carrier=2211,replaced_native_carrier=8507,
        replacement='Kornél Kurucsai, original first-round Haladas goalkeeper',
        delivery=bind(root/'independent-prepublication-native-proof.json')))
    result['remaining_cross_club_cases']=remaining
    result['additional_confirmed_findings'].append(dict(id='Haladas2000-positive-original-opening-keeper',
        season=season,state='delivered-native-SOURCE-and-runner-verified',frozen_cases_closed=1,
        selected_keeper=8507,retained_Kiraly=2211,full_Haladas_or_Hertha_squad_approved=False,
        source_plan=bind(root/'keeper-plan.json')))
    result['new_required_followups'].append(dict(id='Hertha2000-retained-Kiraly-known-country-and-fine-role',
        season=season,status='open-known-wrong-facts-not-approved-by-ownership-preservation',carrier_id=2211,
        evidence=bind(root/'hertha_kiraly_retained-profile-visual-review.json'),
        scope='Retained native keeper has inherited Germany and forward fine roles12/8. Source-bound period-country and keeper-role repair required, including all26 identity scope. Hertha startup7 and full Haladas future-cohort squad remain unapproved.'))
    result['new_required_followups'].append(dict(id='Haladas2000-cyan-magenta-profile-kit-period-colour-conflict',
        season=season,status='open-observed-kit-colour-conflict-exact2000-design-proof-required',club_carrier_id=1706,
        evidence=bind(root/'haladas_kurucsai-profile-visual-review.json'),
        original_neighbouring_season_source=build.source.admission.external('haladas2000-index2001-secondary-player-facts'),
        scope='Original October2001 Index club source explicitly gives green-white; actual2000 profile shows cyan/magenta. This is a neighbouring-season colour conflict, NOT an exact2000 design certificate. Native pixel correspondence is not historical kit approval. Confirm target design and repair kit assets; all kit bytes deliberately preserved by this keeper-identity transaction.'))
    names=['keeper-plan.json','native-byte-proof.json','complete-SOURCE-replay.json','startup-transport.json','startup-visual-review.json',
        'independent-prepublication-native-proof.json','final-attestation.json','preferred-playable-validation.json']
    names+=[label+s for _,label,_,_ in PROFILES for s in ('-profile-transport.json','-profile-visual-review.json','-original-digit-proof.json','-original-age-proof.json','-native-runtime-proof.json')]
    result['delivered_evidence'] += [backup]+[bind(root/name) for name in names]
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=bind(old_path),current_release_bindings=current,
        fresh_runtime_runs_this_checklist=[season],all_required_work_complete=False,
        next_batch=f'Continue frozen{remaining} cross-club/opening squads and known Kiraly country/keeper-role source cascade, Hertha2001 club-label adjudication, manager/facts/assets/final checklist. No global historical approval.')
    pipeline.write_canonical_json(output,result)
    retained(root/'final-delivery-summary.json',dict(checklist=bind(output),frozen_cases_closed=1,remaining_cross_club_cases=remaining,
        other25_preferred_bindings_preserved=True,original2015_backup_verified=True,global_historical_RC=False))
    print(dict(actual_Haladas_keeper_delivered=True,frozen_cases_closed=1,remaining_cross_club_cases=remaining),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--previous-version',type=int,required=True)
    main(parser.parse_args().previous_version)
