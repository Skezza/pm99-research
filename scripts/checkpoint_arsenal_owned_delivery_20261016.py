"""Publish the original Arsenal squad after exact source/native/runtime proof.

Only eleven positively resolved frozen duplicate pairs reduce the counter.
Known shirt defects remain explicit follow-up work, not historical approval.
"""
import copy
from datetime import UTC,datetime

from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_arsenal_2021_owned_opening_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.build_arsenal_owned_opening_20261016 import ROOT,SEASON,BASE,RELEASE
from scripts.capture_arsenal_owned_opening_20261016 import TAG,PROFILES
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.verify_arsenal_cross_club_cases_20261016 import verify as verify_cases
from scripts.verify_arsenal_tactics_runtime_20261016 import main as verify_tactics


def checked_bindings(previous,release):
    expected={r['season']:r for r in previous['current_release_bindings']}
    current=bindings()
    for row in current:
        if row['season']!=SEASON and row!=expected[row['season']]:raise ValueError('unselected season changed')
        if row['season']==SEASON and row['release_id'] not in (BASE,RELEASE):raise ValueError('Arsenal baseline changed')
        if row['season']==SEASON and row['release_id']==BASE and row!=expected[SEASON]:
            raise ValueError('Arsenal parent preferred binding changed')
        if row['season']==SEASON and row['release_id']==RELEASE and row['manifest_sha256']!=release.manifest_sha256:
            raise ValueError('Arsenal preferred manifest differs')
    return current


def validate_case_count(previous,cases,manifest_sha):
    closed={r['case_id'] for r in previous.get('cross_club_dispositions',[])}
    new_ids={r['case_id'] for r in cases['dispositions']}
    if (len(new_ids)!=11 or len(cases['dispositions'])!=11 or closed&new_ids
        or previous['remaining_cross_club_cases']!=2808 or cases['manifest_sha256']!=manifest_sha
        or cases['confirmed_frozen_cases_repaired']!=11):
        raise ValueError('frozen cross-club counter cannot be reset/double-counted')


def run():
    prior=ROOT.parent/'release-delivery-checklist-v49.json';output=ROOT.parent/'release-delivery-checklist-v50.json'
    if output.exists():raise ValueError('completed Arsenal publication must not repeat')
    previous=pipeline.read_json_file(prior);result=copy.deepcopy(previous)
    release=registry.load_registered_release(SEASON,RELEASE);base=registry.load_registered_release(SEASON,BASE)
    plan=pipeline.read_json_file(ROOT/'opening-ownership-plan.json')
    source.verify(base,plan)
    package=pipeline.read_json_file(release.package_path)
    if source.bind(pipeline.read_json_file(base.package_path),plan)!=package:raise ValueError('current Arsenal recipe differs')
    native=pipeline.read_json_file(ROOT/'native-byte-proof.json')
    replay=pipeline.read_json_file(ROOT/'complete-SOURCE-replay.json')
    if (native['manifest_sha256']!=release.manifest_sha256
        or native['plan_sha256']!=registry.sha256_file(ROOT/'opening-ownership-plan.json')
        or native['actual_Arsenal_capacity']!=25 or native['actual_formation']!='4-2-3-1'
        or len(native['all_ten_native_skills_preserved_for'])!=16
        or len(native['identity_changed_carriers'])!=17
        or not all(native[k] for k in ('exact_native_reproduction_from_sources','idempotent',
            'complete_recipe_exact','contextual_phase_tactics_written','managers_kits_and_EXE_unchanged',
            'exact_portrait_clear','unrelated_player_and_club_records_identical','all_other_game_files_identical'))
        or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']):
        raise ValueError('Arsenal actual native/full SOURCE proof incomplete or stale')
    startup=pipeline.read_json_file(ROOT/'startup-visual-review.json');check_visual(startup)
    transport=pipeline.read_json_file(ROOT/'startup-transport.json')
    if (startup['observed_team']!='Stoke City' or startup['observed_date']!='2021-08-01'
        or startup['release_manifest_sha256']!=release.manifest_sha256 or transport['exit_code']!=0
        or transport['release_manifest_sha256']!=release.manifest_sha256
        or transport['evidence']!=registry.relative_workspace_path(registry.ROOT/'.local/runlogs/pm99_runner'/(TAG+'_stoke'))):
        raise ValueError('unchanged ordinary startup contract not proved')
    visual=pipeline.read_json_file(ROOT/'Arsenal-lineup-tactics-visual-review.json')
    if (visual['observed_team']!='Arsenal' or visual['observed_date']!='2021-08-01'
        or visual['release_manifest_sha256']!=release.manifest_sha256
        or not visual['correct_original_first_XI_visually_checked']
        or not visual['distinct_phase_positions_visually_checked'] or len(visual['original_frames'])!=3):
        raise ValueError('original Arsenal XI and both phase screens unreviewed')
    for frame in visual['original_frames']:check_visual(frame)
    verify_tactics()
    tactics=pipeline.read_json_file(ROOT/'actual-Arsenal-tactics-runtime-proof.json')
    if (not tactics['success'] or tactics['carrier_id']!=309 or tactics['club']!='Arsenal'
        or tactics['formation']!='4-2-3-1' or tactics['named_player_phases_checked']!=22
        or tactics['release_manifest_sha256']!=release.manifest_sha256):raise ValueError('all880 live phase values not proved')
    # A source-backed number correction is next; don't turn this squad proof
    # into approval of the inherited numbers or every historical kit design.
    shirt_source=ROOT.parent/'arsenal-shirts-2021-v1/source-number-admission.json'
    shirts=pipeline.read_json_file(shirt_source)
    if len(shirts['updates'])!=25 or sum(r['before_number']!=r['number'] for r in shirts['updates'])!=13:
        raise ValueError('known sourced shirt defects must remain explicitly accounted')
    profiles=[(carrier,label,'',token) for carrier,label,token in PROFILES]
    verify_profiles(ROOT,SEASON,RELEASE,profiles)
    for carrier,label,_,_ in profiles:
        review=pipeline.read_json_file(ROOT/(label+'-profile-visual-review.json'));check_visual(review)
        proof=pipeline.read_json_file(ROOT/(label+'-native-runtime-proof.json'))
        if (proof['visual_review_sha256']!=registry.sha256_file(ROOT/(label+'-profile-visual-review.json'))
            or proof['compiler_receipt_sha256']!=registry.sha256_file(release.compiler_receipt_path)
            or proof['screenshot_sha256']!=review['screenshot_sha256']
            or proof['carrier_id']!=carrier or not proof['native_inputs_hash_verified']
            or not proof['ten_visible_skills_verified'] or not proof['kit_pixels']['passed']):
            raise ValueError('targeted actual profile proof stale/incomplete')
    cases=verify_cases()
    validate_case_count(previous,cases,release.manifest_sha256)
    checked_bindings(previous,release)
    pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(release.inventory_path))
    publisher.register_completed_delta(SEASON,RELEASE)
    attestation=ROOT/'final-attestation.json'
    if not attestation.exists():retained(attestation,runtime.attest(season=SEASON,
        evidence_dir=registry.ROOT/'.local/runlogs/pm99_runner'/(TAG+'_stoke')))
    validation=registry.validate_preferred_release(SEASON,level='playable')
    if not validation['valid']:raise ValueError('promoted Arsenal game failed final playable validation')
    retained(ROOT/'preferred-playable-validation.json',validation)
    for row in cases['dispositions']:
        result['cross_club_dispositions'].append(dict(row,delivery=binding(ROOT/'independent-eleven-cross-club-case-proof.json')))
    result['remaining_cross_club_cases']=2797
    result['additional_confirmed_findings'].append(dict(id='Arsenal2021-source25-four-paired-reserves',season=SEASON,
        state='delivered-native-SOURCE-and-runner-verified',source_plan=binding(ROOT/'opening-ownership-plan.json'),
        correct_original_XI_and_bench=True,positive_August_reserves=5,capacity=25,
        paired_reserve_replacements=4,represented_native_rating_profiles_preserved=16,
        exact_live_tactics_values=880,confirmed_frozen_cross_club_cases_closed=11,
        retained_DOB_corrections=2,new_Philogene_wrong_annual_DOB_not_used=True,
        frozen247_birthday_queue_unchanged=True,all_managers_and_kits_preserved=True))
    result['additional_confirmed_findings'].append(dict(id='Arsenal2021-source-backed-shirt-number-conflicts',season=SEASON,
        state='confirmed-native-defect-repair-pending',native_shirt_numbers_to_correct=13,
        evidence=binding(shirt_source),original_screenshot_review=binding(ROOT/'Arsenal-lineup-tactics-visual-review.json')))
    result['new_required_followups'].append(dict(id='Genoa2021-orange-profile-kit-design-review',
        classification='historical-design-review-candidate-not-encoding-failure',season=SEASON,
        status='open-source-comparison',evidence=binding(ROOT/'rovella-profile-visual-review.json'),
        scope='Displayed native pixels match the bitmap; historical design has not been certified.'))
    names=['opening-ownership-plan.json','native-byte-proof.json','complete-SOURCE-replay.json',
        'startup-transport.json','startup-visual-review.json','Arsenal-startup-tactics-transport.json',
        'Arsenal-lineup-tactics-visual-review.json','actual-Arsenal-tactics-runtime-proof.json',
        'independent-eleven-cross-club-case-proof.json','final-attestation.json','preferred-playable-validation.json']
    names.extend(label+suffix for _,label,_,_ in profiles for suffix in
        ('-profile-transport.json','-profile-visual-review.json','-native-runtime-proof.json'))
    result['delivered_evidence'].extend(binding(ROOT/name) for name in names)
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(prior),
        current_release_bindings=checked_bindings(previous,release),fresh_runtime_runs_this_checklist=[SEASON],
        all_required_work_complete=False,
        next_batch='Correct13 source-backed Arsenal shirt numbers without changing the validated squad/skills/tactics. Then continue fixed ownership/positions/managers/visual checklist;2797 cross-club candidates remain, not global historical approval.')
    pipeline.write_canonical_json(output,result)
    retained(ROOT/'final-delivery-summary.json',dict(checklist=binding(output),release_id=RELEASE,
        confirmed_frozen_cases_closed=11,remaining_frozen_cross_club_cases=2797,
        other25_preferred_unchanged=True,known_shirt_corrections_remaining=13,global_historical_RC=False))
    print(dict(checklist=binding(output),Arsenal_source25_delivered=True,
        frozen_cases_closed=11,remaining_cross_club_cases=2797,shirt_fix_next=True),flush=True)


if __name__=='__main__':run()
