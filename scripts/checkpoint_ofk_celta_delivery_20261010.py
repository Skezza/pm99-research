"""Close one frozen duplicate case only after source, native and runtime proof."""
import copy
from datetime import UTC, datetime

from scripts import prepare_ofk_2004_source_allocation_v1 as source
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.publish_historical_role_delta_v1 import register_completed_delta
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.audit_compiled_player_birth_dates_v1 import audit

RELEASE = 'sourced-ofk-celta-opening-20261010-r72a'
CASE = 'fd85157fecc806d01b5398378846291327528d3bc5058c5b83a0047033138360'


def run():
    root = source.AUDIT.parent
    prior = root / 'release-delivery-checklist-v17.json'
    output = root / 'release-delivery-checklist-v18.json'
    if output.exists():
        raise ValueError('completed checkpoint must not be repeated')
    result = copy.deepcopy(pipeline.read_json_file(prior))
    release = registry.load_registered_release('2015-16', RELEASE)
    candidate = release.package_path.parent
    native_path = candidate / 'independent-native-and-identity.json'
    native = pipeline.read_json_file(native_path)
    replay_path = source.AUDIT / 'ofk-2015-celta-complete-replay-proof-v1.json'
    replay = pipeline.read_json_file(replay_path)
    private = source.AUDIT / 'ofk-2015-celta-private-game-v1'
    receipt = pipeline.read_json_file(private / 'candidate-receipt.json')
    if (not native['source_bound_complete_game'] or not native['original_sources_replayed']
            or not native['all19_native_identities_and_skills_read_back']
            or not native['all_unselected_native_records_identical']
            or not native['all_unselected_recipe_players_identical']
            or not native['Celta_fixed25_availability_preserved']
            or not native['OFK_XI_and_complete18_source_order_verified']
            or not native['stale_portraits_cleared']
            or native['package_sha256'] != registry.sha256_file(release.package_path)
            or native['introduced_candidate_groups'] or native['replacement_cross_club_candidates']
            or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']
            or receipt['inventory_fingerprint'] != release.locator['game_inventory_fingerprint']):
        raise ValueError('source/native/complete-game reconstruction proof incomplete')
    files = [native_path, candidate / 'candidate-receipt.json', candidate / 'foreign-fixed-roster.json', replay_path]
    for prefix, carrier, club in [('ofk-2015-cupic', 14605, 'OFK Beograd'),
                                  ('ofk-2015-celta-madinda', 20586, 'Celta Vigo')]:
        profile_path = source.AUDIT / (prefix + '-native-kit-runtime-v1.json')
        review_path = source.AUDIT / (prefix + '-original-profile-review-v1.json')
        profile = pipeline.read_json_file(profile_path)
        review = pipeline.read_json_file(review_path)
        if (profile['player_carrier_id'] != carrier or profile['club'] != club
                or not profile['native_inputs_hash_verified'] or not profile['kit_pixels']['passed']
                or profile['candidate_receipt_sha256'] != registry.sha256_file(private / 'candidate-receipt.json')
                or profile['screenshot_sha256'] != review['screenshot_sha256']
                or registry.sha256_file(registry.ROOT / profile['screenshot']) != profile['screenshot_sha256']):
            raise ValueError('original actual named-player/kit proof missing')
        files += [profile_path, review_path]
    visual_path = source.AUDIT / 'ofk-2015-celta-startup-visual-review-v1.json'
    visual = pipeline.read_json_file(visual_path)
    evidence_dir = registry.ROOT / '.local/runlogs/pm99_runner/ofk_celta_r72a_2015_16_stoke_20261010'
    summary = pipeline.read_json_file(evidence_dir / 'summary.json')
    if (visual['observed_team'] != 'Stoke City' or visual['observed_date'] != '2015-08-01'
            or not visual['original_frame_visually_inspected']
            or registry.sha256_file(registry.ROOT / visual['screenshot']) != visual['screenshot_sha256']
            or visual['release_manifest_sha256'] != release.manifest_sha256
            or not summary['success'] or summary['release_manifest_sha256'] != release.manifest_sha256
            or summary['output_inventory_fingerprint'] != release.locator['game_inventory_fingerprint']):
        raise ValueError('fresh normal original startup proof incomplete')
    birthday = audit('2015-16', RELEASE)
    previous = next(r for r in pipeline.read_json_file(root / 'current-literal-birthdays-20261010-v4.json')['seasons']
                    if r['season'] == '2015-16')
    if birthday['failures'] != previous['failures']:
        raise ValueError('coupled transaction changed frozen birthday issue accounting')
    if registry.load_preferred_release('2015-16').release_id not in (RELEASE, 'sourced-maccabi-name-only-20261010-r58a'):
        raise ValueError('another worker changed preferred2015 baseline')
    register_completed_delta('2015-16', RELEASE)
    attestation = runtime.attest(season='2015-16', evidence_dir=evidence_dir)
    attest_path = source.AUDIT / 'ofk-2015-celta-final-attestation-v1.json'
    if attest_path.exists():
        if pipeline.read_json_file(attest_path) != attestation:
            raise ValueError('retained attestation changed')
    else:
        pipeline.write_canonical_json(attest_path, attestation)
    files += [visual_path, attest_path]
    case = next(c for c in result['within_club_cases'] if c['id'] == CASE)
    if case['status'] != 'open-source-and-ownership-review':
        raise ValueError('case already counted')
    case.update(status='confirmed-fault-repaired-current-game', delivery=dict(
        release_id=RELEASE, evidence=[binding(p) for p in files], actual_team_XI_screen_captured=False,
        scope='Original OFK first league XI11/used bench3 plus4 strictly dated reserves replace fixed18 Becej. Drazic carrier moves from Celta to OFK; original opening member Madinda occupies exchanged carrier at Celta, preserving fixed25/flags.19 native facts/all10 skills read back, manager Petrovic/dated ground,3 period source-reviewed kits, zero new cross-club candidates, all19 stale portraits cleared. Complete source rebuilt game AND recipe exact; actual Cupic and Madinda profiles/153 kit pixels exact, fresh dated normal startup. Celta historical XI and opaque foreign tactics not certified; Cancarevic nationality chronology inference disclosed; weights fallback, simplified kit artwork.'))
    old = {r['season']: r for r in result['current_release_bindings']}
    current = bindings()
    for row in current:
        labels = {layer['label'] for layer in old[row['season']]['layers']}
        row['layers'] = [layer for layer in row['layers'] if layer['label'] in labels]
        if row['season'] != '2015-16' and row != old[row['season']]:
            raise ValueError('an unselected preferred season changed')
    progress = result['within_club_progress']
    progress.update(confirmed_faults_repaired=23, disposed=71, open_real_club_cases=11)
    if len(result['within_club_cases']) != 82 or sum(c['status'] == 'open-source-and-ownership-review' for c in result['within_club_cases']) != 11:
        raise ValueError('frozen duplicate identities drifted')
    result['delivered_evidence'].extend(binding(p) for p in files)
    result.update(utc=datetime.now(UTC).isoformat(), previous_checklist=binding(prior),
        current_release_bindings=current, fresh_runtime_runs_this_checklist=['2015-16'],
        all_required_work_complete=False,
        next_batch='11 stock duplicate cases remain (Becej5/Minerven6); original cross-club, DOB42, roles, managers, ratings and global visual checklist still open.')
    pipeline.write_canonical_json(output, result)
    print(dict(checklist=binding(output), within_club_progress=progress,
               other25_preferred_bindings_unchanged=True, all_required_work_complete=False), flush=True)


if __name__ == '__main__':
    run()
