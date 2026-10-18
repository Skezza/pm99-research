"""Close the frozen2014 Minerven case only after complete independent proof."""
import copy
from datetime import UTC, datetime

from scripts import prepare_ofk_2004_source_allocation_v1 as source
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.publish_historical_role_delta_v1 import register_completed_delta
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.audit_compiled_player_birth_dates_v1 import audit

RELEASE = 'sourced-tachira-opening-20261010-r73a'
CASE = 'b18c64ef26bd2d34b706fe45fdd4b5224f1e36da35c408c4aa9e022806054917'
RUN = 'tachira_r73a_2014_15_stoke_20261010'


def run():
    root = source.AUDIT.parent
    prior = root / 'release-delivery-checklist-v18.json'
    output = root / 'release-delivery-checklist-v19.json'
    if output.exists():
        raise ValueError('completed checkpoint must not be repeated')
    result = copy.deepcopy(pipeline.read_json_file(prior))
    release = registry.load_registered_release('2014-15', RELEASE)
    candidate = release.package_path.parent
    native_path, identity_path = candidate/'independent-native.json', candidate/'independent-identity.json'
    native, identity = pipeline.read_json_file(native_path), pipeline.read_json_file(identity_path)
    receipt_path = candidate/'candidate-receipt.json'
    receipt = pipeline.read_json_file(receipt_path)
    replay_path = source.AUDIT/'tachira-2014-complete-replay-proof-v1.json'
    replay = pipeline.read_json_file(replay_path)
    if (not native['source_bound_complete_game'] or not native['source_allocation_replayed']
            or not native['all_selected_native_ownership_exclusive'] or not native['source_people_unique']
            or len(native['players']) != 16 or not native['unrelated_native_records_byte_identical']
            or native['package_sha256'] != registry.sha256_file(release.package_path)
            or native['source_candidate_receipt_sha256'] != registry.sha256_file(receipt_path)
            or identity['candidate_receipt_sha256'] != registry.sha256_file(receipt_path)
            or identity['package_sha256'] != native['package_sha256']
            or identity['introduced_candidate_groups'] or identity['replacement_cross_club_candidates']
            or not identity['stale_portraits_cleared']
            or not identity['unselected_recipe_people_clubs_managers_identical']
            or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']
            or receipt['game_inventory_fingerprint'] != release.locator['game_inventory_fingerprint']):
        raise ValueError('complete source/native/identity/reconstruction proof incomplete')
    private = source.AUDIT/'tachira-2014-complete-source-replay-v3'
    private_receipt = private/'candidate-receipt.json'
    if pipeline.read_json_file(private_receipt)['game_inventory_fingerprint'] != receipt['game_inventory_fingerprint']:
        raise ValueError('actual profile candidate differs from published complete game')
    profile_path = source.AUDIT/'tachira-2014-contreras-native-kit-runtime-v1.json'
    review_path = source.AUDIT/'tachira-2014-contreras-original-profile-review-v1.json'
    profile, review = pipeline.read_json_file(profile_path), pipeline.read_json_file(review_path)
    if (profile['player_carrier_id'] != 17858 or profile['club'] != 'Deportivo Tachira'
            or not profile['native_inputs_hash_verified'] or not profile['kit_pixels']['passed']
            or profile['candidate_receipt_sha256'] != registry.sha256_file(private_receipt)
            or profile['screenshot_sha256'] != review['screenshot_sha256']
            or registry.sha256_file(registry.ROOT/profile['screenshot']) != profile['screenshot_sha256']):
        raise ValueError('original corrected-player native kit/profile proof missing')
    visual_path = source.AUDIT/'tachira-2014-startup-visual-review-v1.json'
    visual = pipeline.read_json_file(visual_path)
    evidence_dir = registry.ROOT/'.local/runlogs/pm99_runner'/RUN
    summary = pipeline.read_json_file(evidence_dir/'summary.json')
    if (visual['observed_team'] != 'Stoke City' or visual['observed_date'] != '2014-08-01'
            or not visual['original_frame_visually_inspected']
            or registry.sha256_file(registry.ROOT/visual['screenshot']) != visual['screenshot_sha256']
            or visual['release_manifest_sha256'] != release.manifest_sha256
            or not summary['success'] or summary['release_manifest_sha256'] != release.manifest_sha256
            or summary['output_inventory_fingerprint'] != release.locator['game_inventory_fingerprint']):
        raise ValueError('fresh final-bound original normal startup proof incomplete')
    birthday = audit('2014-15', RELEASE)
    previous = next(r for r in pipeline.read_json_file(root/'current-literal-birthdays-20261010-v4.json')['seasons']
                    if r['season'] == '2014-15')
    if birthday['failures'] != previous['failures']:
        raise ValueError('transaction changed frozen birthday issue accounting')
    old = {r['season']:r for r in result['current_release_bindings']}
    if registry.load_preferred_release('2014-15').release_id not in (RELEASE, receipt['baseline_release_id']):
        raise ValueError('another worker changed preferred2014 baseline')
    # Check every unselected binding BEFORE promotion as well as afterwards.
    def checked_bindings():
        current = bindings()
        for row in current:
            labels = {layer['label'] for layer in old[row['season']]['layers']}
            row['layers'] = [layer for layer in row['layers'] if layer['label'] in labels]
            if row['season'] != '2014-15' and row != old[row['season']]:
                raise ValueError('an unselected preferred season changed')
        return current
    checked_bindings()
    case = next(c for c in result['within_club_cases'] if c['id'] == CASE)
    if case['status'] != 'open-source-and-ownership-review':
        raise ValueError('case already counted')
    register_completed_delta('2014-15', RELEASE)
    attestation = runtime.attest(season='2014-15', evidence_dir=evidence_dir)
    attest_path = source.AUDIT/'tachira-2014-final-attestation-v1.json'
    if attest_path.exists():
        if pipeline.read_json_file(attest_path) != attestation:
            raise ValueError('retained attestation changed')
    else:
        pipeline.write_canonical_json(attest_path, attestation)
    files = [native_path, identity_path, receipt_path, candidate/'foreign-fixed-roster.json', replay_path,
             profile_path, review_path, visual_path, attest_path]
    case.update(status='confirmed-fault-repaired-current-game', delivery=dict(
        release_id=RELEASE, evidence=[binding(p) for p in files], actual_team_XI_screen_captured=False,
        scope='Original first league2014-08-10 Táchira XI11 plus five positive published substitutes replace fixed16 obsolete Minerven.16 unique native biographies/skills/order/exclusive physical ownership; dated Farías/Pueblo Nuevo and3 photo-reviewed factory kit sizes.0 introduced identities,16 stale portraits cleared. Complete source-rebuilt game AND recipe identical, actual Contreras profile/kit and final-bound normal startup inspected. Cermeño role disagreement excluded from bench selection; Gerzon DOB conflict explicitly retained. Calendar catalogue secondary facts not opening membership; missing weights/portraits allowed, opaque foreign tactics not certified, kit sponsor/panel detail simplified.'))
    progress = result['within_club_progress']
    progress.update(confirmed_faults_repaired=24, disposed=72, open_real_club_cases=10)
    if len(result['within_club_cases']) != 82 or sum(c['status']=='open-source-and-ownership-review' for c in result['within_club_cases']) != 10:
        raise ValueError('frozen duplicate identities drifted')
    result['delivered_evidence'].extend(binding(p) for p in files)
    result.update(utc=datetime.now(UTC).isoformat(), previous_checklist=binding(prior),
        current_release_bindings=checked_bindings(), fresh_runtime_runs_this_checklist=['2014-15'],
        all_required_work_complete=False,
        next_batch='10 stock duplicate cases remain (Becej5/Minerven5); original cross-club, DOB42, roles, managers, ratings and global visual checklist still open.')
    pipeline.write_canonical_json(output, result)
    print(dict(checklist=binding(output), within_club_progress=progress,
               other25_preferred_bindings_unchanged=True, all_required_work_complete=False), flush=True)


if __name__ == '__main__':
    run()
