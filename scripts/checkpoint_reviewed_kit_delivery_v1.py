"""Reusable final gate for a source-reviewed, kit-only registered game child."""
import copy
from datetime import UTC, datetime
from PIL import Image

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_kit_render_bindings_v1 as kits
from scripts import build_registered_quality_release_v1 as builder
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.prepare_reviewed_kit_delta_v1 import verify_sources
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.verify_profile_skill_digits_v1 import verify_profiles as verify_digits
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_remaining_manager_tenures_20261016 import verify_original2015
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.probe_sourced_factory_kit_v1 import kit_image


def run(*, root, season, parent_id, release_id, replay_id, prior, output,
        followup_id, profiles, historical_scope):
    if output.exists():
        raise ValueError('completed kit checkpoint must not repeat')
    previous = pipeline.read_json_file(prior)
    if bindings() != previous['current_release_bindings']:
        raise ValueError('preferred release bindings changed')
    parent = registry.load_preferred_release(season)
    if parent.release_id != parent_id:
        raise ValueError('kit parent is no longer preferred')
    actual = registry.load_registered_release(season, release_id)
    replay = registry.load_registered_release(season, replay_id)
    catalogue = pipeline.read_json_file(root / 'kit-catalogue.json')
    verify_sources(catalogue)
    carriers = {r['carrier_id'] for r in catalogue['rows']}
    if not carriers or len(carriers) != len(catalogue['rows']):
        raise ValueError('kit scope empty or duplicated')
    plan = pipeline.read_json_file(registry.ROOT / actual.locator['visual_patch_plan_path'])
    if (plan['inputs']['release_id'] != parent_id
            or plan['inputs']['package_sha256'] != registry.sha256_file(parent.package_path)
            or plan['inputs']['catalogue_sha256'] != registry.sha256_file(root / 'kit-catalogue.json')):
        raise ValueError('kit child has a different baseline')
    for release in (actual, replay):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(actual.inventory_path))
        if release.package_path.read_bytes() != parent.package_path.read_bytes():
            raise ValueError('kit-only child or SOURCE changed recipe')
    left = {r['path']: r['sha256'] for r in pipeline.read_json_file(parent.inventory_path)['files']}
    right = {r['path']: r['sha256'] for r in pipeline.read_json_file(actual.inventory_path)['files']}
    changed = {name for name in set(left) | set(right) if left.get(name) != right.get(name)}
    if changed != {'DBDAT/' + name for name in kits.ARCHIVES}:
        raise ValueError('kit child changed other game data')
    for archive in kits.ARCHIVES:
        before = kits._record_index(parent.game_path / 'DBDAT' / archive)
        after = kits._record_index(actual.game_path / 'DBDAT' / archive)
        if set(before) != set(after) or {c for c in before if before[c].raw_bitmap != after[c].raw_bitmap} != carriers:
            raise ValueError('changed native icons differ from declared source scope')
    visual = pipeline.read_json_file(root / 'candidate-visual-review.json')
    if not visual.get('original_frame_visually_inspected') or not visual.get('all_three_native_sizes_inspected'):
        raise ValueError('source and three-size original review missing')
    for name, digest in (('source_original', 'source_sha256'), ('candidate_sheet', 'candidate_sheet_sha256')):
        if registry.sha256_file(registry.ROOT / visual[name]) != visual[digest]:
            raise ValueError('visually reviewed source or candidate changed')
    package = pipeline.read_json_file(actual.package_path)
    actors = {p['carrier_id']: p for p in package['players']}
    clubs = {c['id']: c for c in package['clubs']}
    if {clubs[actors[c]['club_id']]['carrier_id'] for c, _, _, _ in profiles} != carriers:
        raise ValueError('each changed club requires its genuine final-game profile')
    verify_profiles(root, season, release_id, profiles)
    verify_digits(root, season, release_id, profiles)
    startup = pipeline.read_json_file(root / 'startup-visual-review.json')
    check_visual(startup)
    transport = pipeline.read_json_file(root / 'startup-transport.json')
    evidence = registry.ROOT / transport['evidence']
    summary = pipeline.read_json_file(evidence / 'summary.json')
    if (transport['exit_code'] != 0 or transport['release_manifest_sha256'] != actual.manifest_sha256
            or startup['release_manifest_sha256'] != actual.manifest_sha256
            or startup['observed_team'] != 'Stoke City' or startup['observed_date'] != season[:4] + '-08-01'
            or not summary.get('success') or summary.get('crash_detected') or summary.get('wine_debugger_detected')
            or summary['release_manifest_sha256'] != actual.manifest_sha256
            or summary['output_inventory_fingerprint'] != actual.locator['game_inventory_fingerprint']):
        raise ValueError('actual final-game startup unproved')
    followups = [r for r in previous['new_required_followups'] if r['id'] == followup_id and r['season'] == season]
    if len(followups) != 1 or set(carriers) != {followups[0]['club_carrier_id']}:
        raise ValueError('kit correction does not match exactly one required followup')
    palette, _ = kits._palette(actual.game_path / 'DBDAT')
    actual_sheet = Image.new('RGB', (600, 250), (37, 49, 58))
    carrier = next(iter(carriers))
    for index, archive in enumerate(kits.ARCHIVES):
        record = kits._record_index(actual.game_path / 'DBDAT' / archive)[carrier]
        actual_sheet.paste(kit_image(record, palette), (index * 200, 0))
    with Image.open(registry.ROOT / visual['candidate_sheet']) as reviewed_sheet:
        if reviewed_sheet.size != actual_sheet.size or reviewed_sheet.convert('RGB').tobytes() != actual_sheet.tobytes():
            raise ValueError('approved three-size sheet does not show actual installed pixels')
    native = root / 'native-byte-proof.json'
    retained(native, dict(manifest_sha256=actual.manifest_sha256, parent_id=parent_id,
        changed_files=sorted(changed), changed_kit_carriers=sorted(carriers),
        all_other_game_files_and_all_recipe_bytes_identical=True,
        SOURCE_game_and_recipe_exact=True, replay_id=replay_id, historical_scope=historical_scope))
    backup = verify_original2015()
    if bindings() != previous['current_release_bindings']:
        raise ValueError('release bindings changed during final checks')
    builder.register([dict(season=season, release_id=release_id, release_manifest_sha256=actual.manifest_sha256)])
    retained(root / 'final-attestation.json', runtime.attest(season=season, evidence_dir=evidence))
    valid = registry.validate_preferred_release(season, level='playable')
    if not valid['valid']:
        raise ValueError('promoted kit game not playable')
    retained(root / 'preferred-playable-validation.json', valid)
    old = {r['season']: r for r in previous['current_release_bindings']}
    after = bindings()
    if any(row != old[row['season']] for row in after if row['season'] != season):
        raise ValueError('unaffected preferred game changed')
    result = copy.deepcopy(previous)
    followup = next(r for r in result['new_required_followups'] if r['id'] == followup_id)
    followup.update(status='delivered-period-combination-three-sizes-SOURCE-and-runner-verified',
        delivery=binding(native), historical_scope=historical_scope,
        exact_home_every_fixture_design_certified=False)
    result['delivered_evidence'].extend([backup, binding(native)])
    result['delivered_evidence'].extend(binding(root / name) for name in (
        'kit-catalogue.json', 'candidate-visual-review.json', 'complete-SOURCE-replay.json',
        'startup-transport.json', 'startup-visual-review.json', 'final-attestation.json',
        'preferred-playable-validation.json'))
    for _, label, _, _ in profiles:
        result['delivered_evidence'].extend(binding(root / (label + suffix)) for suffix in (
            '-profile-transport.json', '-profile-visual-review.json', '-native-runtime-proof.json',
            '-original-digit-proof.json', '-original-age-proof.json'))
    result.update(utc=datetime.now(UTC).isoformat(), previous_checklist=binding(prior),
        current_release_bindings=after, fresh_runtime_runs_this_checklist=[season],
        all_required_work_complete=False,
        next_batch='Continue positive opening-ownership corrections and remaining fixed candidate checklist; preserve all completed releases.')
    retained(output, result)
    retained(root / 'final-delivery-summary.json', dict(checklist=binding(output),
        release_id=release_id, period_kit_delivered=True, other25_unchanged=True,
        duplicate_counts_unchanged=True, global_historical_RC=False))
    print(dict(kit_delivered=True, season=season, checklist=str(output), global_complete=False), flush=True)
