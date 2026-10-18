"""Publish only the exact final-game-reviewed original Hertha club label."""
import argparse
import copy
from datetime import UTC,datetime
from scripts import build_hertha_cohort_label_20261017 as build
from scripts.capture_hertha_cohort_label_20261017 import TAG,PROFILE
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


def main(previous_version):
    old_path=build.ROOT.parent/f'release-delivery-checklist-v{previous_version}.json'
    output=build.ROOT.parent/f'release-delivery-checklist-v{previous_version+1}.json'
    if output.exists():raise ValueError('completed Hertha publication must not repeat')
    previous=pipeline.read_json_file(old_path);initial=bindings()
    if initial!=previous['current_release_bindings']:raise ValueError('Hertha previous checkpoint differs from actual current defaults')
    base=registry.load_preferred_release(build.SEASON)
    if base.release_id!=build.BASE:raise ValueError('Hertha source parent advanced; preserve intervening fixes')
    actual=registry.load_registered_release(build.SEASON,build.RELEASE)
    plan=pipeline.read_json_file(build.ROOT/'club-plan.json')
    retained(build.ROOT/'independent-prepublication-native-proof.json',build.verify_native(base,actual,plan))
    rebuilt=registry.load_registered_release(build.SEASON,build.REPLAY)
    proof=pipeline.read_json_file(build.ROOT/'complete-SOURCE-replay.json')
    if not proof['complete_game_inventory_identical'] or not proof['complete_recipe_identical']:
        raise ValueError('Hertha complete SOURCE proof incomplete')
    for release in (actual,rebuilt):pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(actual.inventory_path))
    if actual.package_path.read_bytes()!=rebuilt.package_path.read_bytes():raise ValueError('Hertha complete SOURCE recipe differs')
    evidence=registry.ROOT/'.local/runlogs/pm99_runner'/TAG
    transport=pipeline.read_json_file(build.ROOT/'startup-transport.json')
    summary=pipeline.read_json_file(evidence/'summary.json')
    visual=pipeline.read_json_file(build.ROOT/'startup-visual-review.json');check_visual(visual)
    if (transport['exit_code']!=0 or transport['release_manifest_sha256']!=actual.manifest_sha256
            or transport['evidence']!=registry.relative_workspace_path(evidence)
            or visual['observed_team']!='Stoke City' or visual['observed_date']!=build.SEASON[:4]+'-08-01'
            or visual['screenshot_sha256']!=registry.sha256_file(lineup_frame(evidence))
            or visual['release_manifest_sha256']!=actual.manifest_sha256
            or summary.get('success') is not True or summary.get('crash_detected') or summary.get('wine_debugger_detected')
            or summary.get('release_manifest_sha256')!=actual.manifest_sha256
            or summary.get('output_inventory_fingerprint')!=actual.locator['game_inventory_fingerprint']):
        raise ValueError('Hertha actual final game lacks exact successful original startup')
    digits(build.ROOT,build.SEASON,build.RELEASE,[PROFILE]);verify_profiles(build.ROOT,build.SEASON,build.RELEASE,[PROFILE])
    review=pipeline.read_json_file(build.ROOT/'hertha_preetz-profile-visual-review.json')
    if review['observed_club']!='Hertha Berlin':raise ValueError('retained source player does not actually display restored Hertha label')
    backup=verify_original2015()
    if bindings()!=initial:raise ValueError('preferred games changed during Hertha prepublication')
    publisher.register_completed_delta(build.SEASON,build.RELEASE)
    retained(build.ROOT/'final-attestation.json',runtime.attest(season=build.SEASON,evidence_dir=evidence))
    playable=registry.validate_preferred_release(build.SEASON,level='playable')
    if not playable['valid']:raise ValueError('restored Hertha default failed playable gate')
    retained(build.ROOT/'preferred-playable-validation.json',playable)
    current=bindings()
    if [r for r in current if r['season']!=build.SEASON]!=[r for r in initial if r['season']!=build.SEASON]:
        raise ValueError('Hertha label publication changed another season')
    result=copy.deepcopy(previous)
    result['additional_confirmed_findings'].append(dict(id='Hertha'+build.SEASON[:4]+'-authored-cohort-under-Koln-native421',
        season=build.SEASON,state='label-delivered-original-source-native-SOURCE-and-runner-verified',
        carrier_id=421,before='1. FC Koln',after='Hertha Berlin',retained_native_people=25,
        player_coach_ground_roster_tactic_asset_or_EXE_changes=0,cross_club_cases_closed=0,
        full_opening_XI_or_historical_kit_design_approved=False,source_plan=bind(build.ROOT/'club-plan.json')))
    if review.get('observed_nationality')=='NORWAY' or review.get('observed_fine_position')=='CENTRAL MID.':
        result['new_required_followups'].append(dict(
            id='Michael-Preetz-inherited-country-and-fine-position',
            status='open-source-confirmed-actual-game-repair-required',
            evidence=bind(build.ROOT/'hertha_preetz-profile-visual-review.json'),
            all26_scope=bind(build.ROOT/'all26-Preetz-source-name-scope-v92.json'),
            observed_country=review.get('observed_nationality'),observed_fine_position=review.get('observed_fine_position'),
            expected_country='GERMANY',expected_broad_role='FORWARD',
            affected_season_carriers=[['2000-01',12468],['2001-02',12468],['2002-03',18894]],
            scope='Hertha label-only release retains the pre-existing player faults; no historical player-fact approval. Verify every affected native record before source-bound country/role repair.'))
    for item in result['new_required_followups']:
        if item['id']=='Hertha'+build.SEASON[:4]+'-native421-Koln-club-label-source-conflict':
            item.update(status='label-delivered-original-source-native-SOURCE-and-runner-verified',
                correction_evidence=bind(build.ROOT/'hertha_preetz-profile-visual-review.json'))
    names=['club-plan.json','native-byte-proof.json','complete-SOURCE-replay.json','startup-transport.json','startup-visual-review.json',
        'independent-prepublication-native-proof.json','final-attestation.json','preferred-playable-validation.json']
    names+=['hertha_preetz'+s for s in ('-profile-transport.json','-profile-visual-review.json','-original-digit-proof.json','-original-age-proof.json','-native-runtime-proof.json')]
    result['delivered_evidence'] += [backup]+[bind(build.ROOT/name) for name in names]
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=bind(old_path),current_release_bindings=current,
        fresh_runtime_runs_this_checklist=[build.SEASON],all_required_work_complete=False,
        next_batch='Continue frozen cross-club cases, source-bound known player facts/roles, opening squads/managers/assets/final regression. Preserve declared spelling aliases and completed Preetz repairs; Hertha label repair is not historical player-fact, squad or kit approval.')
    pipeline.write_canonical_json(output,result)
    retained(build.ROOT/'final-delivery-summary.json',dict(checklist=bind(output),club_labels_corrected=1,retained_players=25,
        unchanged_other25_preferred_bindings=True,original2015_backup_verified=True,cross_club_cases_closed=0,global_historical_RC=False))
    print(dict(Hertha_label_delivered=True,all_player_and_asset_bytes_preserved=True,global_historical_RC=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-version',type=int,required=True)
    main(parser.parse_args().previous_version)
