"""Reusable final gate for source-verified frozen-pair reserve batches."""
import copy
from datetime import UTC,datetime
from app.fdi_indexed import IndexedFDIFile
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_frozen_fixture_reserve_v1 as source
from scripts import season_duplicate_layered_packages_v1 as layered
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_opening_order_repair_v1 as owners
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_remaining_manager_tenures_20261016 import verify_original2015
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.verify_profile_skill_digits_v1 import verify_profiles as verify_digit_profiles
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def next_count(previous,proofs):
    baseline=next(r['frozen_baseline']['cross_club_groups'] for r in previous['work_items'] if r['id']=='roster-duplicates')
    closed={r['case_id'] for r in previous['cross_club_dispositions']}
    new={r['case_id'] for r in proofs}
    if (len(closed)!=len(previous['cross_club_dispositions']) or len(new)!=len(proofs) or not new
            or closed&new or baseline-len(closed)!=previous['remaining_cross_club_cases']):
        raise ValueError('fixed frozen counter reset, duplicate closure or inconsistent baseline')
    return baseline-len(closed)-len(new)


def run(root,season,release_id,replay_id,previous_path,output,tag,profiles):
    if output.exists():raise ValueError('completed fixture batch publication must not repeat')
    previous=pipeline.read_json_file(previous_path);release=registry.load_registered_release(season,release_id)
    plan_path=registry.ROOT/release.locator['ownership_plan_path'];plan=pipeline.read_json_file(plan_path)
    base=registry.load_registered_release(season,plan['release_id']);delta.verify_plan(base,plan)
    proofs=plan['bindings']['positive_pairs'];remaining=next_count(previous,proofs)
    old=pipeline.read_json_file(base.package_path);actual=pipeline.read_json_file(release.package_path)
    original=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();jug=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    expected,english,view,_=layered.prepare(base,plan,original)
    if english is not None or expected!=actual:raise ValueError('whole current recipe differs from original source replay')
    selected={r['carrier_id'] for r in plan['updates']};selected_ids={r['player_id'] for r in plan['updates']}
    countries=delta.compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    if delta.compile_planned_players(original,view,selected_ids,countries,plan)!=jug:
        raise ValueError('complete native player bytes do not reproduce exactly')
    preserve_other_records(original,jug,selected)
    # These are reserve-only corrections: all club, manager, startup-XI,
    # tactical and kit files must remain byte-identical to their exact parent.
    for name in ('EQ98030.FDI','ENT98030.FDI','RIDIESC.PKF','MINIESC.PKF','NANOESC.PKF'):
        if registry.sha256_file(base.game_path/'DBDAT'/name)!=registry.sha256_file(release.game_path/'DBDAT'/name):
            raise ValueError('fixture reserve batch changed club/manager/kit context')
    new_actors={p['carrier_id']:p for p in actual['players']};old_actors={p['carrier_id']:p for p in old['players']}
    ownership=owners.native_owners((release.game_path/'DBDAT/EQ98030.FDI').read_bytes())
    for proof in proofs:
        keep=proof['retained_carrier'];retired=proof['displaced_carrier']
        if new_actors[keep]!=old_actors[keep]:raise ValueError('retained original owner actor changed')
        key=source.identity(new_actors[keep])
        if [p['carrier_id'] for p in actual['players'] if source.identity(p)==key]!=[keep]:
            raise ValueError('frozen identity still has another current copy')
        club=next(c for c in actual['clubs'] if c['id']==new_actors[keep]['club_id'])
        if ownership.get(keep)!={club['carrier_id']} or retired not in selected:
            raise ValueError('retained native owner or selected duplicate differs')
    replay=pipeline.read_json_file(root/'complete-SOURCE-replay.json')
    if not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
        raise ValueError('complete SOURCE proof missing')
    rebuilt=registry.load_registered_release(season,replay_id)
    for game in (release,rebuilt):pipeline.assert_tree_matches_inventory(game.game_path,pipeline.read_json_file(release.inventory_path))
    if rebuilt.package_path.read_bytes()!=release.package_path.read_bytes():raise ValueError('whole SOURCE recipe bytes differ')
    evidence=registry.ROOT/'.local/runlogs/pm99_runner'/tag
    visual=pipeline.read_json_file(root/'startup-visual-review.json');check_visual(visual)
    transport=pipeline.read_json_file(root/'startup-transport.json');summary=pipeline.read_json_file(evidence/'summary.json')
    if (transport['exit_code']!=0 or transport['release_manifest_sha256']!=release.manifest_sha256
            or transport['evidence']!=registry.relative_workspace_path(evidence)
            or visual['observed_team']!='Stoke City' or visual['observed_date']!=season[:4]+'-08-01'
            or visual['release_manifest_sha256']!=release.manifest_sha256 or not summary.get('success')
            or summary.get('crash_detected') or summary.get('wine_debugger_detected')
            or summary['release_manifest_sha256']!=release.manifest_sha256
            or summary['output_inventory_fingerprint']!=release.locator['game_inventory_fingerprint']):
        raise ValueError('fresh actual startup not bound/successful')
    if {c for c,_,_,_ in profiles}!=(selected|{p['retained_carrier'] for p in proofs}):
        raise ValueError('every changed and retained source actor needs its actual profile')
    verify_digit_profiles(root,season,release_id,profiles)
    verify_profiles(root,season,release_id,profiles)
    for carrier,label,_,_ in profiles:
        reviewed=pipeline.read_json_file(root/(label+'-profile-visual-review.json'));check_visual(reviewed)
        proof=pipeline.read_json_file(root/(label+'-native-runtime-proof.json'))
        if (proof['carrier_id']!=carrier or proof['release_id']!=release_id
                or proof['compiler_receipt_sha256']!=registry.sha256_file(release.compiler_receipt_path)
                or proof['visual_review_sha256']!=registry.sha256_file(root/(label+'-profile-visual-review.json'))
                or proof['screenshot_sha256']!=reviewed['screenshot_sha256']
                or not proof['native_inputs_hash_verified'] or not proof['ten_visible_skills_verified'] or not proof['kit_pixels']['passed']):
            raise ValueError('target profile/native/kit proof changed or incomplete')
    current=bindings();expected_bindings=previous['current_release_bindings']
    if current!=expected_bindings:raise ValueError('preferred games advanced; preserve intervening repairs')
    if next(r['release_id'] for r in current if r['season']==season)!=base.release_id:
        raise ValueError('the exact source parent is not current')
    backup=verify_original2015()
    retained(root/'prepublication-proof.json',dict(season=season,release_id=release_id,manifest_sha256=release.manifest_sha256,
        source_plan=binding(plan_path),frozen_cases=[p['case_id'] for p in proofs],native_writes_reproduced=True,
        complete_SOURCE=True,actual_profiles_verified=len(profiles),remaining_cross_club_cases_after=remaining))
    publisher.register_completed_delta(season,release_id)
    retained(root/'final-attestation.json',runtime.attest(season=season,evidence_dir=evidence))
    valid=registry.validate_preferred_release(season,level='playable')
    if not valid['valid']:raise ValueError('promoted fixture reserve game failed playable check')
    retained(root/'preferred-playable-validation.json',valid)
    result=copy.deepcopy(previous)
    for proof in proofs:
        result['cross_club_dispositions'].append(dict(case_id=proof['case_id'],season=season,
            state='confirmed-fault-repaired-current-game',source_person_id=proof['source_person_id'],
            retained_native_carrier=proof['retained_carrier'],replaced_native_carrier=proof['displaced_carrier'],
            delivery=binding(root/'prepublication-proof.json')))
    result['remaining_cross_club_cases']=remaining
    result['additional_confirmed_findings'].append(dict(id='original-fixture-reserve-'+release_id,season=season,
        state='delivered-native-SOURCE-and-runner-verified',players_corrected=len(selected),frozen_cases_closed=len(proofs),
        all_unrelated_players_clubs_managers_tactics_kits_preserved=True,source_plan=binding(plan_path)))
    names=['native-byte-proof.json','complete-SOURCE-replay.json','startup-transport.json','startup-visual-review.json',
        'prepublication-proof.json','final-attestation.json','preferred-playable-validation.json']
    names += [label+suffix for _,label,_,_ in profiles for suffix in ('-profile-transport.json','-profile-visual-review.json','-native-runtime-proof.json','-original-digit-proof.json','-original-age-proof.json')]
    result['delivered_evidence'] += [backup]+[binding(root/name) for name in names]
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(previous_path),
        current_release_bindings=bindings(),fresh_runtime_runs_this_checklist=[season],all_required_work_complete=False,
        next_batch=f'Continue frozen{remaining} cross-club/opening-squad cases and outstanding manager/role/known-fact/assets queues. No global historical RC.')
    # Verify non-selected defaults once more after the sole catalogue change.
    if [r for r in result['current_release_bindings'] if r['season']!=season]!=[r for r in expected_bindings if r['season']!=season]:
        raise ValueError('another season changed during publication')
    pipeline.write_canonical_json(output,result)
    retained(root/'final-delivery-summary.json',dict(checklist=binding(output),players_corrected=len(selected),
        frozen_cases_closed=len(proofs),remaining_cross_club_cases=remaining,all_other25_preferred_bindings_unchanged=True,
        original2015_backup_verified=True,global_historical_RC=False))
    print(dict(delivered=True,players_corrected=len(selected),frozen_cases_closed=len(proofs),remaining_cross_club_cases=remaining),flush=True)
