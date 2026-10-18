"""Deliver the 26 actual ability-only games only after native and runner checks."""
import copy
import gzip
import hashlib
from datetime import UTC,datetime
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import publish_historical_role_delta_v1 as publisher,attest_registered_season_runtime_v1 as runtime
from scripts import season_quality_only_delta_v1 as layer
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.build_all_rating_calibrations_20261011 import ROOT,release_id
from scripts.capture_all_rating_calibrations_20261011 import tag
from scripts.capture_rating_profiles_20261011 import PROFILES
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.review_rating_frames_20261011 import lineup_frame
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

def run():
    prior=ROOT.parent/'release-delivery-checklist-v42.json';output=ROOT.parent/'release-delivery-checklist-v43.json'
    if output.exists():raise ValueError('completed26 rating checkpoint must not repeat')
    result=copy.deepcopy(pipeline.read_json_file(prior));baselines=pipeline.read_json_file(ROOT/'pinned-baselines.json')
    if {r['season'] for r in baselines}!=set(registry.supported_seasons()) or len(baselines)!=26:
        raise ValueError('rating baseline scope not exactly26')
    old={r['season']:r for r in result['current_release_bindings']};candidates=[];evidence=[];total=0
    for b in baselines:
        season=b['season'];root=ROOT/season;release=registry.load_registered_release(season,release_id(season))
        if registry.load_preferred_release(season).release_id not in (b['release_id'],release.release_id):
            raise ValueError('preferred season changed outside owned transaction')
        plan=pipeline.read_json_file(root/'quality-plan.json');base=registry.load_registered_release(season,b['release_id'])
        if plan['release_id']!=base.release_id or plan['kind']!='season-rating-calibration-v3':raise ValueError('rating baseline/kind differs')
        layer.verify(base,plan)
        proof=pipeline.read_json_file(root/'native-byte-proof.json');replay=pipeline.read_json_file(root/'complete-SOURCE-replay.json')
        native=pipeline.read_json_file(root/'all-updated-players-native-readback.json')
        if (proof['actual_manifest_sha256']!=release.manifest_sha256 or proof['package_sha256']!=registry.sha256_file(release.package_path)
                or proof['plan_sha256']!=registry.sha256_file(root/'quality-plan.json')
                or not proof['skills_changed'] or proof['nationalities_changed']
                or not proof['exact_native_reproduction'] or not proof['fixed_rosters_roles_tactics_managers_assets_EXE']
                or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']
                or native['manifest_sha256']!=release.manifest_sha256
                or native['actual_JUG_sha256']!=registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI')
                or native['updated_player_count']!=len(plan['updates'])
                or not all(native[k] for k in ('all_selected_ten_skills_match_recipe','all_unselected_native_records_identical',
                    'non_rating_recipe_fields_identical','outfield_handling_guard_passed'))):raise ValueError('actual26 native/full replay proof incomplete')
        detail=registry.ROOT/native['players_path']
        if (registry.sha256_file(detail)!=native['players_gzip_sha256']
                or hashlib.sha256(gzip.decompress(detail.read_bytes())).hexdigest()!=native['players_sha256']):
            raise ValueError('compressed full native readback detail hash differs')
        visual=pipeline.read_json_file(root/'startup-visual-review.json');check_visual(visual)
        transport=pipeline.read_json_file(root/'startup-transport.json')
        summary_path=registry.ROOT/transport['evidence']/'summary.json';summary=pipeline.read_json_file(summary_path)
        frame=lineup_frame(summary_path.parent)
        identity=summary.get('route_summaries',{}).get('line_up',{}).get('team_identity',{})
        if (visual['observed_team']!='Stoke City' or visual['observed_date']!=season[:4]+'-08-01'
                or visual['screenshot']!=registry.relative_workspace_path(frame)
                or visual['screenshot_sha256']!=registry.sha256_file(frame)
                or transport['evidence']!=registry.relative_workspace_path(registry.ROOT/'.local/runlogs/pm99_runner'/tag(season))
                or visual['release_manifest_sha256']!=release.manifest_sha256
                or transport['exit_code']!=0 or transport['release_manifest_sha256']!=release.manifest_sha256
                or summary.get('success') is not True or summary.get('crash_detected') or summary.get('wine_debugger_detected')
                or summary.get('process_exit_code') not in (None,0) or not identity.get('matched')
                or summary['release_manifest_sha256']!=release.manifest_sha256
                or summary['output_inventory_fingerprint']!=release.locator['game_inventory_fingerprint']):raise ValueError('actual26 startup not exact release/club/date/no-crash')
        pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(release.inventory_path))
        candidates.append(release);total+=len(plan['updates'])
        evidence.extend(binding(root/name) for name in ('quality-plan.json','native-byte-proof.json','complete-SOURCE-replay.json',
            'owned-identical-content-sharing.json','all-updated-players-native-readback.json','startup-visual-review.json','startup-transport.json','calibration-summary.json'))
        evidence.append(binding(detail))
    for season,carrier,label,token in PROFILES:
        verify_profiles(ROOT/season,season,release_id(season),[(carrier,label,'',token)])
        evidence.extend(binding(ROOT/season/(label+suffix)) for suffix in ('-profile-transport.json','-profile-visual-review.json','-native-runtime-proof.json'))
    positions=pipeline.read_json_file(ROOT/'baseline-primary-position-consistency.json')
    if positions['checked_players']!=total or positions['mismatches']:
        raise ValueError('rating basis conflicts with actual native keeper/outfield position')
    evidence.extend(binding(ROOT/name) for name in ('baseline-primary-position-consistency.json',
        'pre-build-adversarial-benchmarks.json','all26-planned-method-summary.json','dated-policy-sources.json'))
    # All candidate conditions have passed before any preferred binding moves.
    for release in candidates:
        publisher.register_completed_delta(release.season,release.release_id)
        retained(ROOT/release.season/'final-attestation.json',runtime.attest(season=release.season,
            evidence_dir=registry.ROOT/'.local/runlogs/pm99_runner'/tag(release.season)))
        validation=registry.validate_preferred_release(release.season,level='release')
        if not validation['valid']:raise ValueError('promoted actual game release validation failed: '+release.season)
        retained(ROOT/release.season/'preferred-release-validation.json',validation)
        evidence.extend(binding(ROOT/release.season/name) for name in ('final-attestation.json','preferred-release-validation.json'))
    current=bindings()
    for row in current:
        row['layers']=[l for l in row['layers'] if l['label'] in {l['label'] for l in old[row['season']]['layers']}]
    result['additional_confirmed_findings'].append(dict(id='all26-source-bound-native-rating-calibration-v3',
        state='repaired-and-runtime-verified',seasons=26,actual_player_rating_updates=total,actual_startup_screenshots=26,
        actual_ten_skill_profiles_verified=len(PROFILES),non_rating_native_and_recipe_fields_preserved=True,
        source_matches_and_proxies_separately_labelled=True,not_perfect_historical_abilities_or_global_RC=True))
    result['delivered_evidence'].extend(evidence)
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(prior),current_release_bindings=current,
        fresh_runtime_runs_this_checklist=registry.supported_seasons(),all_required_work_complete=False,
        next_batch='Woking16 nationalities and26 rating-only games delivered and runner verified. Incomplete source identities/optional images and broader historical queues remain explicit; no global RC or perfect-ability claim. Original duplicate/birthday denominators and 2015 fun backup unchanged.')
    pipeline.write_canonical_json(output,result)
    retained(ROOT/'final-delivery-summary.json',dict(checklist=binding(output),seasons_delivered=26,updated_players=total,
        genuine_startup_screenshots=26,ten_skill_profiles_verified=len(PROFILES),all_preferred_release_validation_passed=True,
        season_evidence=[dict(season=release.season,release_id=release.release_id,
            release_manifest_sha256=release.manifest_sha256,
            startup_screenshot=pipeline.read_json_file(ROOT/release.season/'startup-visual-review.json')['screenshot'],
            actual_rating_updates=pipeline.read_json_file(ROOT/release.season/'all-updated-players-native-readback.json')['updated_player_count'],
            profiles=[pipeline.read_json_file(ROOT/s/(label+'-native-runtime-proof.json'))['screenshot']
                for s,_,label,_ in PROFILES if s==release.season]) for release in candidates],
        perfect_historical_accuracy_claimed=False))
    print(dict(checklist=binding(output),seasons_delivered=26,actual_rating_updates=total),flush=True)

if __name__=='__main__':run()
