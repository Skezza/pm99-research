"""Install the proved2004 OFK transaction; close exactly one frozen case."""
import copy
from datetime import UTC, datetime

from scripts import prepare_ofk_2004_source_allocation_v1 as source
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.publish_historical_role_delta_v1 import register_completed_delta
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.audit_compiled_player_birth_dates_v1 import audit

RELEASE = 'sourced-ofk-opening-20261010-r71a'
CASE = '97f1aee9baeb153de722f30bb1bbfb747a2932576c22a9e86025b556c124dd12'


def run():
    root = source.AUDIT.parent
    prior = root / 'release-delivery-checklist-v16.json'
    output = root / 'release-delivery-checklist-v17.json'
    if output.exists(): raise ValueError('completed checkpoint must not be repeated')
    result = copy.deepcopy(pipeline.read_json_file(prior))
    release = registry.load_registered_release('2004-05', RELEASE)
    candidate = release.package_path.parent
    native = pipeline.read_json_file(candidate / 'independent-native.json')
    identity = pipeline.read_json_file(candidate / 'independent-identity.json')
    replay = pipeline.read_json_file(source.AUDIT / 'ofk-2004-complete-replay-proof-v1.json')
    profile = pipeline.read_json_file(source.AUDIT / 'ofk-2004-profile-runtime-proof-v2.json')
    visual_path = source.AUDIT / 'ofk-2004-startup-visual-review-v1.json'
    visual = pipeline.read_json_file(visual_path)
    evidence_dir = registry.ROOT / '.local/runlogs/pm99_runner/ofk_r71a_2004_05_stoke_20261010'
    summary = pipeline.read_json_file(evidence_dir / 'summary.json')
    if (not native['source_bound_complete_game'] or not native['source_people_unique']
            or not native['unrelated_native_records_byte_identical']
            or native['package_sha256'] != registry.sha256_file(release.package_path)
            or identity['introduced_candidate_groups'] or identity['replacement_cross_club_candidates']
            or not identity['stale_portraits_cleared']
            or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']
            or not replay['private_runner_game_inventory_identical']
            or not profile['uploaded_DBDAT_hashes_verified'] or not profile['kit_pixels']['passed']
            or registry.sha256_file(registry.ROOT / profile['screenshot']) != profile['screenshot_sha256']
            or visual['observed_team'] != 'Stoke City' or visual['observed_date'] != '2004-08-01'
            or not visual['original_frame_visually_inspected']
            or registry.sha256_file(registry.ROOT / visual['screenshot']) != visual['screenshot_sha256']
            or visual['release_manifest_sha256'] != release.manifest_sha256
            or not summary['success'] or summary['release_manifest_sha256'] != release.manifest_sha256
            or summary['output_inventory_fingerprint'] != release.locator['game_inventory_fingerprint']):
        raise ValueError('OFK original/source/native/replay/actual runtime proof incomplete')
    if registry.load_preferred_release('2004-05').release_id not in (RELEASE, 'sourced-reserve-assignment-pruning-20261010-r59a'):
        raise ValueError('another worker changed preferred2004 baseline')
    register_completed_delta('2004-05', RELEASE)
    attestation = runtime.attest(season='2004-05', evidence_dir=evidence_dir)
    attest_path = source.AUDIT / 'ofk-2004-final-attestation-v1.json'
    if attest_path.exists():
        if pipeline.read_json_file(attest_path) != attestation: raise ValueError('retained OFK attestation changed')
    else: pipeline.write_canonical_json(attest_path, attestation)
    case = next(c for c in result['within_club_cases'] if c['id'] == CASE)
    if case['status'] != 'open-source-and-ownership-review': raise ValueError('OFK case already counted')
    files = [candidate / 'independent-native.json', candidate / 'independent-identity.json',
        candidate / 'candidate-receipt.json', candidate / 'foreign-fixed-roster.json',
        source.AUDIT / 'ofk-2004-complete-replay-proof-v1.json',
        source.AUDIT / 'ofk-2004-profile-runtime-proof-v2.json', visual_path, attest_path]
    case.update(status='confirmed-fault-repaired-current-game', delivery=dict(
        release_id=RELEASE, evidence=[binding(p) for p in files], actual_team_XI_screen_captured=False,
        scope='Replace fixed18 Becej706 with source-bound OFK53: actual earliest league XI11 plus7 strict dated reserves; original biographies, dated Babic and ground, all3 period-reviewed factory kits. No invented bench, source-aware display allocation, deterministic skills and complete game/recipe replay. Source nationals18/heights16; two heights/all weights logged native fallbacks. All18 old portraits cleared. Actual Damjanac/profile/153 kit pixels plus fresh normal Stoke startup proved. Native opaque mode1 tactics and fine roles not historically approved; Damjanac sourceDOB disagreement with Wikipedia retained.'))
    old = {r['season']:r for r in result['current_release_bindings']}
    current = bindings()
    for row in current:
        labels = {layer['label'] for layer in old[row['season']]['layers']}
        row['layers'] = [layer for layer in row['layers'] if layer['label'] in labels]
        if row['season'] != '2004-05' and row != old[row['season']]:
            raise ValueError('an unselected preferred season changed')
    progress = result['within_club_progress']
    progress.update(confirmed_faults_repaired=22, disposed=70, open_real_club_cases=12)
    if len(result['within_club_cases']) != 82 or sum(c['status']=='open-source-and-ownership-review' for c in result['within_club_cases']) != 12:
        raise ValueError('frozen duplicate issue identities drifted')
    birthday = audit('2004-05')
    prior_dates = pipeline.read_json_file(root / 'current-literal-birthdays-20261010-v4.json')
    previous_dates = next(r for r in prior_dates['seasons'] if r['season']=='2004-05')
    if birthday['failures'] != previous_dates['failures']:
        raise ValueError('OFK transaction changed frozen birthday issue accounting')
    result['delivered_evidence'].extend(binding(p) for p in files)
    result.update(utc=datetime.now(UTC).isoformat(), previous_checklist=binding(prior),
        current_release_bindings=current, fresh_runtime_runs_this_checklist=['2004-05'],
        all_required_work_complete=False,
        next_batch='12 stock duplicate cases remain (Becej6/Minerven6); original cross-club, DOB42, roles, managers, ratings and global visual checklist still open. OFK2015 originalXI/bench14 plus8 strict extra candidates recovered; not yet native approved.')
    pipeline.write_canonical_json(output, result)
    print(dict(checklist=binding(output), within_club_progress=progress,
        other25_preferred_bindings_unchanged=True, all_required_work_complete=False),flush=True)


if __name__=='__main__': run()
