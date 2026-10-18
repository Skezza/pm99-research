"""Promote R77 only with immutable source, byte, replay and live evidence."""
import copy
from datetime import UTC, datetime

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import build_registered_quality_release_v1 as builder
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts import season_original_person_birth_years_v1 as source
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.audit_compiled_player_birth_dates_v1 import audit
from scripts.build_original_person_years_20261010 import ROOT, RELEASE, SEASONS


def validate_frozen_birthdays(result, readbacks, updates, original, *, expected_delivered=218, expected_remaining=29):
    item = next(row for row in result['work_items'] if row['id'] == 'birthdays')
    rows = item['verified_repairs'] + updates
    selected = {(r['season'], r['carrier_id']) for r in rows}
    before_ids = {(r['season'], f['carrier_id']) for r in original['seasons'] for f in r['failures']}
    after_ids = {(r['season'], f['carrier_id']) for r in readbacks for f in r['failures']}
    remaining = sum(row['failure_count'] for row in readbacks)
    if (len(selected) != len(rows) or before_ids - after_ids != selected or after_ids - before_ids
            or remaining != expected_remaining or item['frozen_baseline']['count'] != 247
            or len(selected) != expected_delivered or expected_delivered + expected_remaining != 247):
        raise ValueError('frozen birthday identities drifted or new failure introduced')
    return remaining


def run():
    prior = ROOT.parent / 'release-delivery-checklist-v22.json'
    output = ROOT.parent / 'release-delivery-checklist-v23.json'
    if output.exists():
        raise ValueError('completed release checkpoint must not be repeated')
    result = copy.deepcopy(pipeline.read_json_file(prior))
    old = {row['season']: row for row in result['current_release_bindings']}
    promotions, evidence, updates = [], [], []
    for season in SEASONS:
        release = registry.load_registered_release(season, RELEASE)
        plan = pipeline.read_json_file(ROOT / (season + '-plan.json'))
        source.verify(registry.load_registered_release(season, plan['release_id']), plan)
        proof = pipeline.read_json_file(ROOT / (season + '-independent-proof.json'))
        replay = pipeline.read_json_file(ROOT / (season + '-complete-replay-proof.json'))
        visual = pipeline.read_json_file(ROOT / (season + '-startup-visual-review.json'))
        transport = pipeline.read_json_file(ROOT / (season + '-startup-transport.json'))
        if (proof['corrected_birth_years'] != len(plan['updates'])
                or not proof['all_other_native_bytes_identical']
                or not proof['all_other_recipe_facts_ratings_identical']
                or not replay['complete_game_inventory_identical']
                or not replay['complete_recipe_identical']
                or visual['method'] != 'assistant-original-image-visual-review'
                or not visual['original_frame_visually_inspected']
                or visual['observed_team'] != 'Stoke City'
                or visual['observed_date'] != season[:4] + '-08-01'
                or visual['release_manifest_sha256'] != release.manifest_sha256
                or registry.sha256_file(registry.ROOT / visual['screenshot']) != visual['screenshot_sha256']
                or transport['exit_code'] != 0
                or transport['release_manifest_sha256'] != release.manifest_sha256):
            raise ValueError('source/native/replay/original-frame runtime proof incomplete')
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
        current = registry.load_preferred_release(season)
        if current.release_id not in (plan['release_id'], RELEASE):
            raise ValueError('preferred baseline changed; no worker edits overwritten')
        updates.extend(dict(season=season, carrier_id=row['carrier_id'], name=row['name'],
            birth_date=row['birth_date'], source_plan=binding(ROOT / (season + '-plan.json')))
            for row in plan['updates'])
        evidence.extend(binding(ROOT / (season + suffix)) for suffix in
            ('-plan.json', '-independent-proof.json', '-complete-replay-proof.json',
             '-startup-visual-review.json', '-startup-transport.json'))
        promotions.append(dict(season=season, release_id=RELEASE,
            release_manifest_sha256=release.manifest_sha256))
    visual = pipeline.read_json_file(ROOT / 'ferran-profile-visual-review.json')
    profile = pipeline.read_json_file(ROOT / 'ferran-profile-native-and-kit-proof.json')
    transport = pipeline.read_json_file(ROOT / 'ferran-profile-transport.json')
    if (visual['method'] != 'assistant-original-image-visual-review'
            or not visual['original_frame_visually_inspected']
            or visual['observed_native_name'] != '#9 Ferran Torres'
            or visual['observed_club'] != 'Manchester City'
            or visual['observed_age'] != 21 or visual['expected_age'] != 21
            or not visual['visible_skills_match_native_baseline']
            or profile['player_carrier_id'] != 9166
            or not profile['native_inputs_hash_verified'] or not profile['kit_pixels']['passed']
            or visual['screenshot_sha256'] != profile['screenshot_sha256']
            or registry.sha256_file(registry.ROOT / profile['screenshot']) != profile['screenshot_sha256']
            or transport['exit_code'] != 0):
        raise ValueError('actual leap-day Ferran age, exact slot, unchanged skills and kit unproved')
    evidence.extend(binding(ROOT / name) for name in ('ferran-profile-visual-review.json',
        'ferran-profile-native-and-kit-proof.json', 'ferran-profile-transport.json'))
    if len(updates) != 13 or len({(r['season'], r['carrier_id']) for r in updates}) != 13:
        raise ValueError('accepted original-person update count differs')
    # Validate unchanged bindings BEFORE changing preferred registrations.
    for row in bindings():
        row['layers'] = [layer for layer in row['layers'] if layer['label'] in
            {layer['label'] for layer in old[row['season']]['layers']}]
        if row['season'] not in SEASONS and row != old[row['season']]:
            raise ValueError('unselected preferred release changed')
    original = pipeline.read_json_file(ROOT.parent / 'current-literal-birthdays-20261010-v1.json')
    candidate_readbacks = [audit(season, RELEASE if season in SEASONS else None)
        for season in registry.supported_seasons()]
    validate_frozen_birthdays(result, candidate_readbacks, updates, original)
    builder.register(promotions)
    for row in promotions:
        season = row['season']
        evidence_dir = registry.ROOT / ('.local/runlogs/pm99_runner/original_person_year_r77a_'
            + season.replace('-', '_') + '_20261010')
        attestation = runtime.attest(season=season, evidence_dir=evidence_dir)
        path = ROOT / (season + '-final-attestation.json')
        if path.exists():
            if pipeline.read_json_file(path) != attestation:
                raise ValueError('retained final attestation differs')
        else:
            pipeline.write_canonical_json(path, attestation)
        evidence.append(binding(path))
    current = bindings()
    for row in current:
        row['layers'] = [layer for layer in row['layers'] if layer['label'] in
            {layer['label'] for layer in old[row['season']]['layers']}]
        if row['season'] not in SEASONS and row != old[row['season']]:
            raise ValueError('unselected release changed during promotion')
    readbacks = [audit(season) for season in registry.supported_seasons()]
    remaining = validate_frozen_birthdays(result, readbacks, updates, original)
    item = next(row for row in result['work_items'] if row['id'] == 'birthdays')
    fresh = ROOT.parent / 'current-literal-birthdays-20261010-v5.json'
    pipeline.write_canonical_json(fresh, dict(schema_version=original['schema_version'], seasons=readbacks,
        failure_count=remaining, scope=original['scope']))
    item['verified_repairs'].extend(updates)
    item.update(verified_repair_count=218, current_remaining_native_recipe_disagreements=29, state='open')
    result.setdefault('additional_confirmed_findings', []).append(dict(
        id='ferran-2021-runner-nationality-eng-instead-of-esp', season='2021-22', carrier_id=9166,
        classification='confirmed-visible-nationality-defect-not-introduced-by-year-delta',
        state='open', observed='ENGLAND', expected='SPAIN',
        evidence=binding(ROOT / 'ferran-profile-visual-review.json'),
        scope='Separately source-bound nationality cascade required; no change to the frozen82 duplicate identities.'))
    result.update(utc=datetime.now(UTC).isoformat(), previous_checklist=binding(prior),
        current_release_bindings=current, fresh_runtime_runs_this_checklist=list(SEASONS),
        all_required_work_complete=False,
        next_batch='7 real stock duplicate cases OPEN;29 literal birthday cases remain. Source-only alternatives and all original remaining checklist queues explicitly OPEN.')
    result['delivered_evidence'].extend(evidence + [binding(fresh)])
    if len(result['within_club_cases']) != 82 or result['within_club_progress']['open_real_club_cases'] != 7:
        raise ValueError('frozen duplicate denominator drifted')
    pipeline.write_canonical_json(output, result)
    print(dict(checklist=binding(output), birthdays_frozen=247, delivered=218, remaining=29,
        new_years_delivered=13, duplicates_still_open=7, all_required_work_complete=False), flush=True)


if __name__ == '__main__':
    run()
