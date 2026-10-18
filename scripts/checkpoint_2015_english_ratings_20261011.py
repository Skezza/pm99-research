"""Complete the rating milestone with the previously omitted English layer."""
import copy
import gzip
import hashlib
from datetime import UTC,datetime
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_quality_only_delta_v1 as quality
from scripts import season_2015_english_rating_calibration_v3 as english
from scripts import publish_historical_role_delta_v1 as publisher,attest_registered_season_runtime_v1 as runtime
from scripts.build_2015_english_ratings_20261011 import ROOT,SEASON,RELEASE,TAG,PROFILES
from scripts.build_all_rating_calibrations_20261011 import ROOT as BATCH,release_id
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.review_rating_frames_20261011 import lineup_frame
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

def verify_woking_after_ratings():
    from app.fdi_indexed import IndexedFDIFile
    from scripts import season_historical_roster_audit_v1 as roster
    source_path=BATCH.parent/'woking-nationalities-v1/sixteen-native-nationalities.json'
    expected=pipeline.read_json_file(source_path)['players']
    release=registry.load_registered_release('2003-04',release_id('2003-04'))
    raw=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(raw).entries}
    package=pipeline.read_json_file(release.package_path);players={p['carrier_id']:p for p in package['players']}
    if len(expected)!=16 or len({p['carrier_id'] for p in expected})!=16:raise ValueError('Woking source scope changed')
    for row in expected:
        carrier=row['carrier_id'];payload=entries[carrier].decode_payload(raw)
        actual=payload[roster.native_player(payload,carrier)['name_end']+8]^0x61
        if actual!=row['native_code'] or players[carrier]['facts']['nationality']!=row['country']:
            raise ValueError('Woking nationality regressed after rating calibration')
    path=BATCH/'woking16-after-rating-native-nationalities.json'
    retained(path,dict(season='2003-04',release_id=release.release_id,manifest_sha256=release.manifest_sha256,
        actual_JUG_sha256=registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI'),source=binding(source_path),
        verified_players=16,XXX_remaining=0,all_literal_country_codes_preserved=True,players=expected))
    return path

def run():
    prior=BATCH.parent/'release-delivery-checklist-v43.json';output=BATCH.parent/'release-delivery-checklist-v44.json'
    if output.exists():raise ValueError('completed English rating checkpoint must not repeat')
    previous=pipeline.read_json_file(prior);result=copy.deepcopy(previous)
    baseline=registry.load_registered_release(SEASON,release_id(SEASON));release=registry.load_registered_release(SEASON,RELEASE)
    if registry.load_preferred_release(SEASON).release_id not in (baseline.release_id,release.release_id):
        raise ValueError('English rating preferred baseline moved outside this transaction')
    old={r['season']:r for r in previous['current_release_bindings']}
    for row in bindings():
        if row['season']!=SEASON and row!=old[row['season']]:raise ValueError('another preferred season changed during English closeout')
    plan=pipeline.read_json_file(ROOT/'quality-plan.json');quality.verify(baseline,plan)
    if plan['kind']!=english.KIND or plan['release_id']!=baseline.release_id:raise ValueError('English calibration source kind/preimage differs')
    proof=pipeline.read_json_file(ROOT/'native-byte-proof.json');replay=pipeline.read_json_file(ROOT/'complete-SOURCE-replay.json')
    native=pipeline.read_json_file(ROOT/'all-updated-players-native-readback.json')
    if (proof['actual_manifest_sha256']!=release.manifest_sha256 or proof['package_sha256']!=registry.sha256_file(release.package_path)
            or proof['plan_sha256']!=registry.sha256_file(ROOT/'quality-plan.json')
            or not proof['skills_changed'] or proof['nationalities_changed'] or not proof['exact_native_reproduction']
            or not proof['fixed_rosters_roles_tactics_managers_assets_EXE']
            or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']
            or native['manifest_sha256']!=release.manifest_sha256
            or native['actual_JUG_sha256']!=registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI')
            or native['updated_player_count']!=2300 or len(plan['updates'])!=2300
            or not all(native[k] for k in ('all_selected_ten_skills_match_recipe','all_unselected_native_records_identical',
                'non_rating_recipe_fields_identical','outfield_handling_guard_passed'))):raise ValueError('actual English native/SOURCE proof incomplete')
    detail=registry.ROOT/native['players_path']
    if (registry.sha256_file(detail)!=native['players_gzip_sha256']
            or hashlib.sha256(gzip.decompress(detail.read_bytes())).hexdigest()!=native['players_sha256']):
        raise ValueError('English native readback detail hash differs')
    main=pipeline.read_json_file(release.package_path)
    if main!=quality.bind(pipeline.read_json_file(baseline.package_path),plan):raise ValueError('English edit changed unrelated main recipe data')
    if english.overlay(release)[0]!=english.updated_english(plan):raise ValueError('edited English recipe artifact differs')
    gate=pipeline.read_json_file(ROOT/'pre-build-English-position-and-handling-gates.json')
    if gate['source_players_checked']!=2300 or gate['primary_position_mismatches']:raise ValueError('English actual keeper/outfield class not verified')
    # Both actual recipe layers are checked, not just main.players.
    from scripts.season_duplicate_ownership_plan_v1 import package_layers
    for _,package,_ in package_layers(release):
        for player in package['players']:
            if player['facts'].get('primary_position') in ('D','M','F') and player['ratings']['values']['handling']>20:
                raise ValueError('remaining 2015 source-authored outfield handling above20')
    transport=pipeline.read_json_file(ROOT/'startup-transport.json');visual=pipeline.read_json_file(ROOT/'startup-visual-review.json')
    check_visual(visual);evidence=registry.ROOT/transport['evidence'];summary=pipeline.read_json_file(evidence/'summary.json')
    frame=lineup_frame(evidence);identity=summary.get('route_summaries',{}).get('line_up',{}).get('team_identity',{})
    if (transport['exit_code']!=0 or transport['release_manifest_sha256']!=release.manifest_sha256
            or transport['evidence']!=registry.relative_workspace_path(registry.ROOT/'.local/runlogs/pm99_runner'/TAG)
            or visual['observed_team']!='Stoke City' or visual['observed_date']!='2015-08-01'
            or visual['screenshot']!=registry.relative_workspace_path(frame) or visual['screenshot_sha256']!=registry.sha256_file(frame)
            or visual['release_manifest_sha256']!=release.manifest_sha256
            or summary.get('success') is not True or summary.get('crash_detected') or summary.get('wine_debugger_detected')
            or summary.get('process_exit_code') not in (None,0) or not identity.get('matched')
            or summary['release_manifest_sha256']!=release.manifest_sha256
            or summary['output_inventory_fingerprint']!=release.locator['game_inventory_fingerprint']):raise ValueError('English-final actual startup differs')
    verify_profiles(ROOT,SEASON,RELEASE,[(c,l,'',t) for c,l,t in PROFILES])
    woking_proof=verify_woking_after_ratings()
    pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(release.inventory_path))
    publisher.register_completed_delta(SEASON,RELEASE)
    retained(ROOT/'final-attestation.json',runtime.attest(season=SEASON,evidence_dir=evidence))
    validation=registry.validate_preferred_release(SEASON,level='release')
    if not validation['valid']:raise ValueError('English-final preferred release validation failed')
    retained(ROOT/'preferred-release-validation.json',validation)
    result['additional_confirmed_findings'].append(dict(id='separate-2015-English-ten-skills-native-and-recipe-repair-v3',
        state='repaired-and-runtime-verified',actual_player_rating_updates=2300,Afellay_handling=7,Arnautovic_handling=15,
        foreign_main_players_and_all_non_rating_game_data_preserved=True,original_2015_fun_backup_untouched=True))
    evidence_bindings=[binding(ROOT/n) for n in ('quality-plan.json','native-byte-proof.json','complete-SOURCE-replay.json',
        'owned-identical-content-sharing.json','all-updated-players-native-readback.json','calibration-summary.json',
        'pre-build-English-position-and-handling-gates.json','startup-transport.json','startup-visual-review.json',
        'final-attestation.json','preferred-release-validation.json')]
    evidence_bindings.append(binding(detail))
    evidence_bindings.append(binding(woking_proof))
    evidence_bindings.extend(binding(ROOT/(label+suffix)) for _,label,_ in PROFILES
        for suffix in ('-profile-transport.json','-profile-visual-review.json','-native-runtime-proof.json'))
    result['delivered_evidence'].extend(evidence_bindings)
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(prior),current_release_bindings=bindings(),
        fresh_runtime_runs_this_checklist=[SEASON],all_required_work_complete=False,
        next_batch='Woking countries and all26 rating-calibrated actual games closed, including the separate2300-player 2015 English layer. Existing broader historical/editorial and optional-image queues remain; no global RC/perfect-ability claim.')
    pipeline.write_canonical_json(output,result)
    main_delivery=pipeline.read_json_file(BATCH/'final-delivery-summary.json')
    rows=copy.deepcopy(main_delivery['season_evidence'])
    for row in rows:
        if row['season']==SEASON:
            row.update(release_id=RELEASE,release_manifest_sha256=release.manifest_sha256,
                startup_screenshot=visual['screenshot'],actual_rating_updates=row['actual_rating_updates']+2300,
                profiles=[pipeline.read_json_file(ROOT/(label+'-native-runtime-proof.json'))['screenshot'] for _,label,_ in PROFILES])
    retained(BATCH/'final-complete-delivery-summary.json',dict(checklist=binding(output),seasons_delivered=26,
        updated_players=main_delivery['updated_players']+2300,genuine_startup_screenshots=27,
        current_preferred_season_startup_screenshots=26,ten_skill_profiles_verified=10,
        all_preferred_release_validation_passed=True,season_evidence=rows,original_2015_fun_backup_untouched=True,
        perfect_historical_accuracy_claimed=False))
    print(dict(checklist=binding(output),seasons_delivered=26,actual_rating_updates=main_delivery['updated_players']+2300),flush=True)

if __name__=='__main__':run()
