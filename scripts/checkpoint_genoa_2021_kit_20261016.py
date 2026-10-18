"""Promote Genoa207 artwork only after exact native/SOURCE/fresh runtime proof."""
import copy
from datetime import UTC, datetime
from pathlib import Path

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_kit_render_bindings_v1 as kits
from scripts import build_registered_quality_release_v1 as builder
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.prepare_reviewed_kit_delta_v1 import verify_sources
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.build_genoa_2021_kit_20261016 import ROOT, SEASON, BASE, RELEASE
from scripts.capture_genoa_2021_kit_runtime_20261016 import TAG


def run():
    prior = ROOT.parent / 'release-delivery-checklist-v51.json'
    output = ROOT.parent / 'release-delivery-checklist-v52.json'
    if output.exists():
        raise ValueError('completed kit delivery checkpoint must not repeat')
    result = copy.deepcopy(pipeline.read_json_file(prior))
    old = {r['season']: r for r in result['current_release_bindings']}
    release = registry.load_registered_release(SEASON, RELEASE)
    base = registry.load_registered_release(SEASON, BASE)
    native = pipeline.read_json_file(ROOT / 'native-byte-proof.json')
    replay = pipeline.read_json_file(ROOT / 'complete-SOURCE-replay.json')
    catalogue = pipeline.read_json_file(ROOT / 'kit-catalogue.json')
    verify_sources(catalogue)
    if (native['manifest_sha256'] != release.manifest_sha256
            or native['only_changed_kit_carrier'] != 207
            or native['unchanged_records_by_archive'] != {a: 543 for a in kits.ARCHIVES}
            or not native['every_database_EXE_portrait_and_unselected_game_file_identical']
            or not native['complete_recipe_identical']
            or not replay['complete_game_inventory_identical']
            or not replay['complete_recipe_identical']):
        raise ValueError('Genoa native/full SOURCE evidence incomplete')
    if release.package_path.read_bytes() != base.package_path.read_bytes():
        raise ValueError('kit correction changed recipe bytes')
    before = pipeline.read_json_file(base.inventory_path)
    after = pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    difference = pipeline.inventory_difference(before, after)
    if (difference['only_left'] or difference['only_right']
            or {r['path'] for r in difference['changed']} != {'DBDAT/' + a for a in kits.ARCHIVES}):
        raise ValueError('actual game changed outside three kit archives')
    for name in kits.ARCHIVES:
        left = kits._record_index(base.game_path / 'DBDAT' / name)
        right = kits._record_index(release.game_path / 'DBDAT' / name)
        if set(left) != set(right) or {c for c in left if left[c].raw_bitmap != right[c].raw_bitmap} != {207}:
            raise ValueError('actual icon change extends beyond Genoa207')
    review = pipeline.read_json_file(ROOT / 'actual-three-size-visual-review.json')
    check_visual(review)
    if not review.get('all_three_native_sizes_inspected') or not review.get('original_Kappa_source_compared'):
        raise ValueError('actual native icons have not been visually reviewed')
    startup = pipeline.read_json_file(ROOT / 'startup-visual-review.json')
    check_visual(startup)
    transport = pipeline.read_json_file(ROOT / 'startup-transport.json')
    evidence = registry.ROOT / transport['evidence']
    summary = pipeline.read_json_file(evidence / 'summary.json')
    if (startup.get('observed_team') != 'Stoke City' or startup.get('observed_date') != '2021-08-01'
            or startup.get('release_manifest_sha256') != release.manifest_sha256
            or transport['exit_code'] != 0 or transport['release_manifest_sha256'] != release.manifest_sha256
            or not summary.get('success') or summary.get('crash_detected')
            or summary.get('release_manifest_sha256') != release.manifest_sha256
            or summary.get('output_inventory_fingerprint') != release.locator['game_inventory_fingerprint']):
        raise ValueError('fresh current game startup unproved')
    verify_profiles(ROOT, SEASON, RELEASE, ((14650, 'rovella', 'Nicolò Rovella', 'Rovella'),))
    profile = pipeline.read_json_file(ROOT / 'rovella-native-runtime-proof.json')
    if (profile['release_id'] != RELEASE or profile['club'] != 'Genoa'
            or not profile['kit_pixels']['passed'] or not profile['native_inputs_hash_verified']):
        raise ValueError('actual corrected kit pixels unproved')
    def current_bindings():
        current = bindings()
        for row in current:
            if row['season'] != SEASON and row != old[row['season']]:
                raise ValueError('another preferred season changed')
            if row['season'] == SEASON:
                if row['release_id'] not in (BASE, RELEASE):
                    raise ValueError('Genoa parent was superseded')
                if row['package_sha256'] != old[SEASON]['package_sha256']:
                    raise ValueError('Genoa kit changed another recipe')
        return current
    current_bindings()
    builder.register([dict(season=SEASON, release_id=RELEASE, release_manifest_sha256=release.manifest_sha256)])
    if not (ROOT / 'final-attestation.json').exists():
        retained(ROOT / 'final-attestation.json', runtime.attest(season=SEASON, evidence_dir=evidence))
    validation = registry.validate_preferred_release(SEASON, level='playable')
    if not validation['valid']:
        raise ValueError('actual kit release failed playable validation')
    retained(ROOT / 'preferred-playable-validation.json', validation)
    followup = next(r for r in result['new_required_followups']
                    if r['id'] == 'Genoa2021-orange-profile-kit-design-review')
    followup.update(status='delivered-three-native-sizes-SOURCE-and-fresh-profile-pixels-verified',
        classification='confirmed-inherited-native-kit-design-defect-corrected',
        delivery=binding(ROOT / 'native-byte-proof.json'),
        historical_scope='Original July2021 Kappa home shirt, white permitted shorts combination; logos/cuffs/collar simplified. Not global kit certification.')
    if result['remaining_cross_club_cases'] != 2797:
        raise ValueError('kit patch must not reset duplicate counters')
    names = ('kit-catalogue.json', 'native-byte-proof.json', 'complete-SOURCE-replay.json',
        'actual-three-size-visual-review.json', 'startup-transport.json', 'startup-visual-review.json',
        'rovella-profile-transport.json', 'rovella-profile-visual-review.json', 'rovella-native-runtime-proof.json',
        'final-attestation.json', 'preferred-playable-validation.json')
    result['delivered_evidence'].extend(binding(ROOT / name) for name in names)
    result.update(utc=datetime.now(UTC).isoformat(), previous_checklist=binding(prior),
        current_release_bindings=current_bindings(), fresh_runtime_runs_this_checklist=[SEASON],
        all_required_work_complete=False,
        next_batch='Genoa2021 inherited kit repaired. Continue2797 frozen cross-club groups, broader opening/position reviews, deferred managers/legacy2015, global kit/photo/fact QA; keep completed games and original2015 backup.')
    retained(output, result)
    retained(ROOT / 'final-delivery-summary.json', dict(checklist=binding(output),
        only_changed_club=207, three_native_sizes_delivered=True, actual_profile_pixels_verified=True,
        other25_preferred_unchanged=True, all_recipes_unchanged=True,
        remaining_cross_club_cases_unchanged=2797, global_historical_RC=False))
    print(dict(checklist=binding(output), Genoa_kit_delivered=True, other25_unchanged=True), flush=True)


if __name__ == '__main__':
    run()
