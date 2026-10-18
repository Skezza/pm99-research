"""Promote actual paired club/coach repairs after original runtime review."""
import argparse
import copy
from datetime import UTC,datetime
from scripts import build_hertha_dated_cohort_coach_20261017 as build
from scripts.capture_hertha_dated_cohort_coach_20261017 import tag,profile
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import publish_historical_role_delta_v1 as publisher,attest_registered_season_runtime_v1 as runtime
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_remaining_manager_tenures_20261016 import verify_original2015
from scripts.review_rating_frames_20261011 import lineup_frame
from scripts.verify_profile_skill_digits_v1 import verify_profiles as digits
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.season_kiraly_period_profile_v1 import TARGETS as COUNTRY_TARGETS


def bind(path):return dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path))


def coach_owner_proof(actual):
    holders,names=build.source.prior.old._manager_graph(eq_path=actual.game_path/'DBDAT/EQ98030.FDI',
        ent_path=actual.game_path/'DBDAT/ENT98030.FDI')
    matches=[dict(manager_id=i,native_name=name,owners=[c['carrier_id'] for c in holders[i]])
        for i,name in names.items() if holders.get(i) and
        build.source.prior.old.roster.normalise(name).endswith('stevens')]
    if matches!=[dict(manager_id=1313,native_name='Stevens',owners=[421])]:
        raise ValueError('another active native Stevens alias/owner needs dated reconciliation')
    return dict(manifest_sha256=actual.manifest_sha256,active_named_coaches=matches,
        inactive_factory_manager_records_not_treated_as_active_duplicates=True)


def main(season,previous_version):
    root=build.ROOT/season;old=build.ROOT.parent/f'release-delivery-checklist-v{previous_version}.json'
    output=build.ROOT.parent/f'release-delivery-checklist-v{previous_version+1}.json'
    if output.exists():raise ValueError('completed coupled publication must not repeat')
    previous=pipeline.read_json_file(old);initial=bindings()
    if initial!=previous['current_release_bindings']:raise ValueError('previous checkpoint differs from current defaults')
    countries={r['season'] for r in previous['additional_confirmed_findings'] if r['id'].startswith('Kiraly-period-country-keeper-')}
    if countries!=set(COUNTRY_TARGETS):raise ValueError('finish the eight actual country deliveries before coupled publication')
    finding='Hertha-period-cohort-and-dated-coach-'+season
    if any(r['id']==finding for r in previous['additional_confirmed_findings']):raise ValueError('coupled case already delivered')
    plan=pipeline.read_json_file(root/'club-plan.json');base=registry.load_preferred_release(season)
    if base.release_id!=plan['release_id']:raise ValueError('source parent advanced; preserve intervening fixes')
    actual=registry.load_registered_release(season,build.RELEASE)
    retained(root/'independent-prepublication-native-proof.json',build.verify_native(base,actual,plan))
    retained(root/'active-coach-owner-proof.json',coach_owner_proof(actual))
    replay=pipeline.read_json_file(root/'complete-SOURCE-replay.json');rebuilt=registry.load_registered_release(season,build.REPLAY)
    if not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
        raise ValueError('coupled complete SOURCE proof missing')
    for release in (actual,rebuilt):pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(actual.inventory_path))
    if actual.package_path.read_bytes()!=rebuilt.package_path.read_bytes():raise ValueError('coupled SOURCE recipe differs')
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
        raise ValueError('coupled actual startup lacks original-frame proof')
    spec=profile(season);digits(root,season,build.RELEASE,[spec]);verify_profiles(root,season,build.RELEASE,[spec])
    visual=pipeline.read_json_file(root/(spec[1]+'-profile-visual-review.json'))
    if (visual['observed_club']!='Hertha Berlin' or visual['observed_nationality']!='HUNGARY'
            or visual['observed_position']!='GOALKEEPER' or visual['observed_fine_position']!='KEEPER'
            or visual['observed_age']!=int(season[:4])-1976):
        raise ValueError('actual restored club label or retained country/keeper/age differs')
    backup=verify_original2015()
    if bindings()!=initial:raise ValueError('defaults advanced during coupled verification')
    publisher.register_completed_delta(season,build.RELEASE)
    retained(root/'final-attestation.json',runtime.attest(season=season,evidence_dir=evidence))
    valid=registry.validate_preferred_release(season,level='playable')
    if not valid['valid']:raise ValueError('coupled preferred game failed playable validation')
    retained(root/'preferred-playable-validation.json',valid);current=bindings()
    if [r for r in initial if r['season']!=season]!=[r for r in current if r['season']!=season]:
        raise ValueError('coupled promotion changed another season')
    result=copy.deepcopy(previous)
    result['additional_confirmed_findings'].append(dict(id=finding,season=season,
        state='delivered-source-native-SOURCE-and-club-label-runner-verified',club_carrier_id=421,
        native_club='Hertha Berlin',manager_carrier_id=1313,sourced_full_manager='Huub Stevens',
        native_manager='Stevens',runner_loaded_correct_ENT_hash=True,manager_name_visually_opened=False,
        all_players_assets_and_prior_Kiraly_country_role_fix_preserved=True,cross_club_cases_closed=0,
        complete_opening_XI_or_historical_kit_design_approved=False,source_plan=bind(root/'club-plan.json')))
    names=['club-plan.json','manager-plan.json','native-byte-proof.json','complete-SOURCE-replay.json',
        'independent-prepublication-native-proof.json','active-coach-owner-proof.json','startup-transport.json','startup-visual-review.json',
        'final-attestation.json','preferred-playable-validation.json']
    names+=[spec[1]+suffix for suffix in ('-profile-transport.json','-profile-visual-review.json',
        '-original-digit-proof.json','-original-age-proof.json','-native-runtime-proof.json')]
    result['delivered_evidence'] += [backup]+[bind(root/name) for name in names]
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=bind(old),current_release_bindings=current,
        fresh_runtime_runs_this_checklist=[season],all_required_work_complete=False,
        next_batch='Continue frozen cross-club/opening squads and dated manager/club identities, known facts/kits/present portraits/final regression. Coupled cohort/coach correction is not complete historical squad or kit approval.')
    pipeline.write_canonical_json(output,result)
    retained(root/'final-delivery-summary.json',dict(checklist=bind(output),coupled_club_and_coach_delivered=True,
        unchanged_other25_bindings=True,original2015_backup_verified=True,cross_club_cases_closed=0,global_historical_RC=False))
    print(dict(season=season,coupled_Hertha_and_Stevens_delivered=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--season',choices=['2002-03','2003-04'],required=True)
    parser.add_argument('--previous-version',type=int,required=True);args=parser.parse_args()
    main(args.season,args.previous_version)
