"""Publish nine literal-date corrections only after actual native/SOURCE/runtime proof."""
import copy
from datetime import UTC, datetime

from scripts import season_kit_render_bindings_v1
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_source_bound_birthday_disagreements_v1 as source
from scripts import build_registered_quality_release_v1 as builder
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.build_midson_odubade_birthdays_20261016 import ROOT, RELEASE, REPLAY, TARGETS, proof
from scripts.capture_midson_odubade_birthdays_20261016 import tag, PROFILE_SEASONS
from scripts.review_rating_frames_20261011 import lineup_frame


def run():
    prior = ROOT.parent / 'release-delivery-checklist-v52.json'
    output = ROOT.parent / 'release-delivery-checklist-v53.json'
    if output.exists():
        raise ValueError('completed nine-birthday publication must not repeat')
    result = copy.deepcopy(pipeline.read_json_file(prior))
    old = {r['season']: r for r in result['current_release_bindings']}
    candidates = pipeline.read_json_file(ROOT / 'nine-current-native-candidates.json')['records']
    baselines = {r['season']: r['release_id'] for r in candidates}
    selected = {r[0] for r in TARGETS}
    if len(selected) != 9 or len(candidates) != 9:
        raise ValueError('original nine-player/season scope drifted')
    files = []; promotions = []; total_bytes = 0; findings = []
    for season, carrier, _, _ in TARGETS:
        root = ROOT / season
        base = registry.load_registered_release(season, baselines[season])
        actual = registry.load_registered_release(season, RELEASE)
        plan = pipeline.read_json_file(root / 'birthday-plan.json')
        source.verify(base, plan)
        proof(base, actual, plan, root)
        native = pipeline.read_json_file(root / 'native-byte-proof.json')
        independent = pipeline.read_json_file(root / 'independent-literal-readback.json')
        replay = pipeline.read_json_file(root / 'complete-SOURCE-replay.json')
        if (native['carrier_id'] != carrier or native['manifest_sha256'] != actual.manifest_sha256
                or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']
                or replay['release_id'] != REPLAY):
            raise ValueError('actual native/full SOURCE correction proof incomplete')
        if (independent['manifest_sha256'] != actual.manifest_sha256
                or independent['carrier_id'] != carrier or not independent['writer_not_called']
                or independent['actual_literal_birth_date'] != plan['updates'][0]['birth_date']
                or independent['actual_changed_offsets'] != native['changed_native_byte_offsets']
                or independent['source_plan_sha256'] != registry.sha256_file(root / 'birthday-plan.json')
                or not all(independent[k] for k in ('all_other_native_bytes_identical',
                    'all_other_player_facts_skills_names_clubs_identical', 'all_non_JUG_game_files_identical'))):
            raise ValueError('independent literal readback/preservation proof incomplete')
        total_bytes += native['changed_native_bytes']
        pipeline.assert_tree_matches_inventory(actual.game_path, pipeline.read_json_file(actual.inventory_path))
        transport = pipeline.read_json_file(root / 'startup-transport.json')
        evidence = registry.ROOT / transport['evidence']
        summary = pipeline.read_json_file(evidence / 'summary.json')
        review = pipeline.read_json_file(root / 'startup-visual-review.json')
        check_visual(review)
        if (transport['exit_code'] != 0 or transport['release_manifest_sha256'] != actual.manifest_sha256
                or summary.get('success') is not True or summary.get('crash_detected')
                or summary.get('release_manifest_sha256') != actual.manifest_sha256
                or summary.get('output_inventory_fingerprint') != actual.locator['game_inventory_fingerprint']
                or not summary.get('route_summaries', {}).get('line_up', {}).get('team_identity', {}).get('matched')
                or review.get('observed_team') != 'Stoke City' or review.get('observed_date') != season[:4] + '-08-01'
                or review.get('release_manifest_sha256') != actual.manifest_sha256
                or review['screenshot'] != registry.relative_workspace_path(lineup_frame(evidence))):
            raise ValueError('fresh corrected-game startup/visual proof incomplete')
        if season in PROFILE_SEASONS:
            verify_profiles(root, season, RELEASE, ((carrier, 'player', '', ''),))
            profile = pipeline.read_json_file(root / 'player-native-runtime-proof.json')
            profile_review = pipeline.read_json_file(root / 'player-profile-visual-review.json')
            check_visual(profile_review)
            profile_transport = pipeline.read_json_file(root / 'player-profile-transport.json')
            if (profile['release_id'] != RELEASE or profile['carrier_id'] != carrier
                    or profile['compiler_receipt_sha256'] != registry.sha256_file(actual.compiler_receipt_path)
                    or profile['visual_review_sha256'] != registry.sha256_file(root / 'player-profile-visual-review.json')
                    or profile['screenshot_sha256'] != profile_review['screenshot_sha256']
                    or profile_transport['exit_code'] != 0
                    or profile_transport['release_manifest_sha256'] != actual.manifest_sha256
                    or not profile['kit_pixels']['passed']
                    or not profile['native_inputs_hash_verified'] or not profile['ten_visible_skills_verified']):
                raise ValueError('actual representative corrected-age profile unproved')
            files.extend(root / n for n in ('player-profile-transport.json', 'player-profile-visual-review.json',
                                           'player-native-runtime-proof.json'))
        files.extend(root / n for n in ('birthday-plan.json', 'native-byte-proof.json', 'independent-literal-readback.json', 'complete-SOURCE-replay.json',
                                       'startup-transport.json', 'startup-visual-review.json'))
        promotions.append(dict(season=season, release_id=RELEASE, release_manifest_sha256=actual.manifest_sha256))
        findings.append(dict(id='additional-original-birthday-' + season + '-' + str(carrier), season=season,
            carrier_id=carrier, name=plan['updates'][0]['before_player']['source_name'],
            before_birth_date=plan['updates'][0]['before_birth_date'], birth_date=plan['updates'][0]['birth_date'],
            state='delivered-source-native-SOURCE-and-fresh-startup-verified',
            native_proof=binding(root / 'native-byte-proof.json'),
            scope='Additional source disagreement, not an original247 recipe/native mismatch or duplicate-case closure. Other same-name club records not approved.'))
    if total_bytes != 14:
        raise ValueError('nine-birthday batch must change exactly fourteen actual native bytes')
    def checked_bindings():
        current = bindings()
        for row in current:
            season = row['season']
            if season not in selected and row != old[season]:
                raise ValueError('unselected preferred release changed')
            if season in selected:
                if row['release_id'] not in (baselines[season], RELEASE):
                    raise ValueError('birthday immutable baseline was superseded')
                if row['release_id'] == baselines[season] and row != old[season]:
                    raise ValueError('selected birthday parent binding changed')
                expected = next(p['release_manifest_sha256'] for p in promotions if p['season'] == season)
                if row['release_id'] == RELEASE and row['manifest_sha256'] != expected:
                    raise ValueError('preferred birthday manifest differs from the actually checked game')
        return current
    checked_bindings()
    builder.register(promotions)
    for season in sorted(selected):
        root = ROOT / season
        if not (root / 'final-attestation.json').exists():
            retained(root / 'final-attestation.json', runtime.attest(season=season,
                evidence_dir=registry.ROOT / '.local/runlogs/pm99_runner' / (tag(season) + '_stoke')))
        validation = registry.validate_preferred_release(season, level='playable')
        if not validation['valid']:
            raise ValueError('actual corrected birthday release failed playable validation')
        retained(root / 'preferred-playable-validation.json', validation)
        files.extend(root / n for n in ('final-attestation.json', 'preferred-playable-validation.json'))
    if result['remaining_cross_club_cases'] != 2797:
        raise ValueError('birthday-only batch cannot reset frozen duplicate counts')
    birthdays = next(r for r in result['work_items'] if r['id'] == 'birthdays')
    if birthdays['verified_repair_count'] != 246 or birthdays['current_remaining_native_recipe_disagreements'] != 1:
        raise ValueError('original247 birthday denominator drifted')
    result['additional_confirmed_findings'].extend(findings)
    result['delivered_evidence'].extend(binding(p) for p in files)
    result.update(utc=datetime.now(UTC).isoformat(), previous_checklist=binding(prior),
        current_release_bindings=checked_bindings(), fresh_runtime_runs_this_checklist=sorted(selected),
        all_required_work_complete=False,
        next_batch='Nine additional Midson/Odubade birthday facts delivered without roster/skills changes. Continue2797 frozen cross-club groups, source-proven opening squads/positions, deferred/legacy managers, global kit/photo/fact QA. Original2015 fun backup retained.')
    retained(output, result)
    retained(ROOT / 'final-delivery-summary.json', dict(checklist=binding(output), corrected_player_seasons=9,
        changed_native_bytes=14, unselected17_preferred_unchanged=True,
        unchanged_frozen_cross_club_cases=2797, original247_birthday_cases_not_recounted=True,
        native_and_recipe_birthdays_delivered=True, global_historical_RC=False))
    print(dict(checklist=binding(output), birthday_corrections_delivered=9, actual_native_bytes=14), flush=True)


if __name__ == '__main__':
    run()
