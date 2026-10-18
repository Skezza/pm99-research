"""Publish the reviewed atomic roster and its isolated historical kit child."""
import copy
from datetime import UTC, datetime

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_kit_render_bindings_v1 as kits
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts import season_verified_owned_roster_transaction_v1 as transaction
from scripts.prepare_reviewed_kit_delta_v1 import verify_sources
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_remaining_manager_tenures_20261016 import verify_original2015
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.checkpoint_frozen_fixture_reserve_v1 import next_count
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.verify_profile_skill_digits_v1 import verify_profiles as verify_digits
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/consolidated-audit-20261009'
FOLDER = ROOT / 'Barrow2017-owned-roster-delivery-v1'
FINAL = FOLDER / 'kit-final'
SEASON = '2017-18'
ROSTER = 'sourced-owned-opening-20261017-r146a'
RELEASE = 'sourced-owned-opening-period-kit-20261017-r147a'


def run():
    prior = ROOT / 'release-delivery-checklist-v114.json'
    output = ROOT / 'release-delivery-checklist-v115.json'
    if output.exists():
        raise ValueError('completed checkpoint must not repeat')
    previous = pipeline.read_json_file(prior)
    if bindings() != previous['current_release_bindings']:
        raise ValueError('preferred releases advanced; inspect before publication')
    roster = registry.load_registered_release(SEASON, ROSTER)
    final = registry.load_registered_release(SEASON, RELEASE)
    plan_path = registry.ROOT / roster.locator['sourced_profile_assignment_plan_path']
    plan = pipeline.read_json_file(plan_path)
    transaction.verify(registry.load_registered_release(SEASON, plan['release_id']), plan)
    native = pipeline.read_json_file(FOLDER / 'actual-native-readback.json')
    if native['manifest_sha256'] != roster.manifest_sha256 or native['source_people'] != 19:
        raise ValueError('actual native roster proof differs')
    for folder, actual, replay_id in (
            (FOLDER, roster, 'replayed-owned-opening-20261017-r146b'),
            (FINAL, final, 'replayed-owned-opening-period-kit-20261017-r147b')):
        replay = pipeline.read_json_file(folder / 'complete-SOURCE-replay.json')
        if not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
            raise ValueError('whole SOURCE proof incomplete')
        rebuilt = registry.load_registered_release(SEASON, replay_id)
        pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(actual.inventory_path))
        if rebuilt.package_path.read_bytes() != actual.package_path.read_bytes():
            raise ValueError('SOURCE recipe does not match exact actual release')
    pipeline.assert_tree_matches_inventory(final.game_path, pipeline.read_json_file(final.inventory_path))
    if final.package_path.read_bytes() != roster.package_path.read_bytes():
        raise ValueError('kit child changed corrected recipe')
    left = {r['path']: r['sha256'] for r in pipeline.read_json_file(roster.inventory_path)['files']}
    right = {r['path']: r['sha256'] for r in pipeline.read_json_file(final.inventory_path)['files']}
    changed = {k for k in set(left) | set(right) if left.get(k) != right.get(k)}
    if changed != {'DBDAT/' + a for a in kits.ARCHIVES}:
        raise ValueError('kit child changed roster or other native files')
    for archive in kits.ARCHIVES:
        a = kits._record_index(roster.game_path / 'DBDAT' / archive)
        b = kits._record_index(final.game_path / 'DBDAT' / archive)
        if set(a) != set(b) or {c for c in a if a[c].raw_bitmap != b[c].raw_bitmap} != {3312}:
            raise ValueError('kit child changed an unrelated icon')
    verify_sources(pipeline.read_json_file(FOLDER / 'kit-catalogue.json'))
    candidate = pipeline.read_json_file(FOLDER / 'kit-candidate-visual-review.json')
    if not candidate['original_frame_visually_inspected'] or not candidate['all_three_native_sizes_inspected']:
        raise ValueError('three-size/source review missing')
    if registry.sha256_file(registry.ROOT / candidate['source_original']) != candidate['source_sha256']:
        raise ValueError('reviewed original source changed')
    if registry.sha256_file(registry.ROOT / candidate['candidate_sheet']) != candidate['candidate_sheet_sha256']:
        raise ValueError('reviewed candidate sheet changed')
    profiles = ((10987, 'moore', '', 'Moore'), (10989, 'dunne', '', 'Dunne'),
                (9592, 'hornby', '', 'Hornby'))
    verify_profiles(FOLDER, SEASON, ROSTER, profiles)
    verify_digits(FOLDER, SEASON, ROSTER, profiles)
    verify_profiles(FINAL, SEASON, RELEASE, ((10987, 'moore', '', 'Moore'),))
    verify_digits(FINAL, SEASON, RELEASE, ((10987, 'moore', '', 'Moore'),))
    startup = pipeline.read_json_file(FINAL / 'startup-visual-review.json')
    check_visual(startup)
    transport = pipeline.read_json_file(FINAL / 'startup-transport.json')
    evidence = registry.ROOT / transport['evidence']
    summary = pipeline.read_json_file(evidence / 'summary.json')
    if (startup['observed_team'] != 'Stoke City' or startup['observed_date'] != '2017-08-01'
            or startup['release_manifest_sha256'] != final.manifest_sha256
            or transport['exit_code'] != 0 or transport['release_manifest_sha256'] != final.manifest_sha256
            or not summary.get('success') or summary.get('crash_detected')
            or summary.get('wine_debugger_detected')
            or summary['release_manifest_sha256'] != final.manifest_sha256
            or summary['output_inventory_fingerprint'] != final.locator['game_inventory_fingerprint']):
        raise ValueError('fresh final-game startup unproved')
    proof = pipeline.read_json_file(FOLDER / 'independent-frozen-case-proof.json')
    if proof['manifest_sha256'] != roster.manifest_sha256:
        raise ValueError('frozen-case proof bound to another roster')
    inventory_binding = proof['source_inventory']
    if registry.sha256_file(registry.ROOT / inventory_binding['path']) != inventory_binding['sha256']:
        raise ValueError('frozen source inventory changed')
    frozen = pipeline.read_json_file(registry.ROOT / previous['cross_club_case_file'])
    frozen_matches = [case for group in frozen['seasons'] if group['season'] == SEASON
        for case in group['candidates']
        if pipeline.canonical_json_sha256(dict(season=SEASON, case=case)) == proof['case_id']]
    if len(frozen_matches) != 1 or {p['carrier_id'] for p in frozen_matches[0]['players']} != {9592, 11214}:
        raise ValueError('case is not the exact original frozen Jimmy pair')
    remaining = next_count(previous, [proof])
    backup = verify_original2015()
    publisher.register_completed_delta(SEASON, RELEASE)
    retained(FINAL / 'final-attestation.json', runtime.attest(season=SEASON, evidence_dir=evidence))
    valid = registry.validate_preferred_release(SEASON, level='playable')
    if not valid['valid']:
        raise ValueError('promoted game failed playable validation')
    retained(FINAL / 'preferred-playable-validation.json', valid)
    old = {r['season']: r for r in previous['current_release_bindings']}
    after = bindings()
    if any(r != old[r['season']] for r in after if r['season'] != SEASON):
        raise ValueError('another season changed')
    result = copy.deepcopy(previous)
    disposition = dict(proof, runtime_pending=False, final_release_id=RELEASE,
                       final_manifest_sha256=final.manifest_sha256,
                       final_JUG_and_recipe_equal_to_verified_roster=True,
                       delivery=binding(FOLDER / 'independent-frozen-case-proof.json'))
    result['cross_club_dispositions'].append(disposition)
    result['remaining_cross_club_cases'] = remaining
    result['additional_confirmed_findings'].append(dict(
        id='Barrow2017-positive-opening19-and-period-kit', season=SEASON,
        state='delivered-native-SOURCE-and-runner-verified', corrected_players=19,
        frozen_duplicate_cases_closed=1, source_XI=11, published_bench=5,
        positive_dated_reserves=2, corrected_kit_carriers=[3312], kit_exact_artwork_certified=False))
    graph = ROOT / 'luna-closeout-20261017/stoke-six-player-opening-ownership-graph.json'
    result['new_required_followups'].append(dict(
        id='Stoke2013-positive-opening-late-arrival-ownership', season='2013-14',
        status='open-source-confirmed-opening-ownership', confirmed_cases=3,
        players=['Peter Odemwingie', 'Marko Arnautovic', 'John Guidetti'],
        evidence=binding(graph),
        scope='Outside frozen2809 denominator. Coupled owners and August replacements required; do not send Odemwingie to Cardiff for August2013.'))
    result['delivered_evidence'].extend([backup, binding(plan_path),
        binding(FOLDER / 'actual-native-readback.json'), binding(FOLDER / 'complete-SOURCE-replay.json'),
        binding(FOLDER / 'independent-frozen-case-proof.json'), binding(FOLDER / 'kit-catalogue.json'),
        binding(FOLDER / 'kit-candidate-visual-review.json')])
    for folder, selected in ((FOLDER, profiles), (FINAL, ((10987, 'moore', '', 'Moore'),))):
        for _, label, _, _ in selected:
            result['delivered_evidence'].extend(binding(folder / (label + suffix)) for suffix in
                ('-profile-transport.json', '-profile-visual-review.json', '-native-runtime-proof.json',
                 '-original-digit-proof.json', '-original-age-proof.json'))
    result['delivered_evidence'].extend(binding(FINAL / name) for name in
        ('complete-SOURCE-replay.json', 'startup-transport.json', 'startup-visual-review.json',
         'final-attestation.json', 'preferred-playable-validation.json'))
    result.update(utc=datetime.now(UTC).isoformat(), previous_checklist=binding(prior),
        current_release_bindings=after, fresh_runtime_runs_this_checklist=[SEASON],
        all_required_work_complete=False,
        next_batch='Aldershot2018 duplicate club/Orient positive roster and retained starter permutations; preserve all prior fixes. Then remaining bounded critical checklist.')
    retained(output, result)
    retained(FINAL / 'final-delivery-summary.json', dict(checklist=binding(output),
        source_people_corrected=19, frozen_cases_closed=1, remaining_candidates=remaining,
        period_kit_corrected=True, other25_unchanged=True, original2015_preserved=True,
        global_historical_RC=False))
    print(dict(delivered=True, actual_players_corrected=19, frozen_cases_closed=1,
               remaining_candidates=remaining, global_complete=False), flush=True)


if __name__ == '__main__':
    run()
