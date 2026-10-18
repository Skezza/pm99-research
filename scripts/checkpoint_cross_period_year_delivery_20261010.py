"""Install R70 only after source/native/replay and original runtime proofs.

Keep the original 247 birthday and 82 duplicate issue identities. Never
convert a source-acquisition gap or a wrong recipe date into a closed issue.
"""
import copy
from datetime import UTC, datetime

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import build_registered_quality_release_v1 as builder
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.audit_compiled_player_birth_dates_v1 import audit
from scripts.build_cross_period_birth_years_20261010 import ROOT, RELEASE


def run():
    output = ROOT.parent / 'release-delivery-checklist-v16.json'
    if output.exists():
        raise ValueError('completed release checkpoint must not be repeated')
    prior = ROOT.parent / 'release-delivery-checklist-v15.json'
    result = copy.deepcopy(pipeline.read_json_file(prior))
    old = {row['season']: row for row in result['current_release_bindings']}
    promotions, evidence, year_rows = [], [], []
    changed = set()
    for year in range(2020, 2026):
        season = f'{year}-{str(year+1)[-2:]}'
        release = registry.load_registered_release(season, RELEASE)
        plan = pipeline.read_json_file(ROOT / (season + '-plan.json'))
        proof = pipeline.read_json_file(ROOT / (season + '-independent-proof.json'))
        semantic = pipeline.read_json_file(ROOT / (season + '-skill-and-all-file-proof.json'))
        replay = pipeline.read_json_file(ROOT / (season + '-complete-replay-proof.json'))
        visual = pipeline.read_json_file(ROOT / (season + '-startup-visual-review.json'))
        if (not proof['all_other_native_bytes_identical'] or not semantic['all_other_game_files_identical']
                or not semantic['all_visible_skills_and_role_ratings_identical']
                or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']
                or not visual['original_frame_visually_inspected'] or visual['observed_team'] != 'Stoke City'
                or visual['observed_date'] != f'{year}-08-01'
                or visual['release_manifest_sha256'] != release.manifest_sha256
                or registry.sha256_file(registry.ROOT / visual['screenshot']) != visual['screenshot_sha256']):
            raise ValueError('R70 native, replay or original-frame runtime proof incomplete')
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
        current = registry.load_preferred_release(season)
        if current.release_id not in (plan['release_id'], RELEASE):
            raise ValueError('another worker changed preferred baseline; no edit overwritten')
        year_rows.extend(dict(season=season, carrier_id=row['carrier_id'], name=row['name'],
            birth_date=row['birth_date'], source_plan=binding(ROOT / (season + '-plan.json')))
            for row in plan['updates'])
        evidence.extend(binding(ROOT / (season + suffix)) for suffix in
            ('-plan.json', '-independent-proof.json', '-skill-and-all-file-proof.json',
             '-complete-replay-proof.json', '-startup-visual-review.json'))
        promotions.append(dict(season=season, release_id=RELEASE, release_manifest_sha256=release.manifest_sha256))
        changed.add(season)
    visual = pipeline.read_json_file(ROOT / 'assal-correct-slot-visual-review.json')
    profile = pipeline.read_json_file(ROOT / 'assal-age-native-and-kit-proof.json')
    if (visual['observed_age'] != 20 or visual['expected_age'] != 20
            or visual['observed_native_name'] != '#7 Ayoub Assal' or visual['observed_club'] != 'AFC Wimbledon'
            or not visual['visible_skills_match_native_baseline'] or profile['player_carrier_id'] != 9590
            or not profile['native_inputs_hash_verified'] or not profile['kit_pixels']['passed']):
        raise ValueError('actual source-bound Assal9590 age/club/unchanged skills/kit unproved')
    evidence.extend(binding(ROOT / name) for name in
        ('assal-correct-slot-visual-review.json', 'assal-age-native-and-kit-proof.json'))
    if len(year_rows) != 18 or len({(row['season'], row['carrier_id']) for row in year_rows}) != 18:
        raise ValueError('actual accepted R70 year accounting differs')
    builder.register(promotions)
    for row in promotions:
        season = row['season']
        evidence_dir = registry.ROOT / (f'.local/runlogs/pm99_runner/cross_period_year_r70a_{season.replace("-", "_")}_20261010')
        attestation = runtime.attest(season=season, evidence_dir=evidence_dir)
        path = ROOT / (season + '-final-attestation.json')
        if path.exists():
            if pipeline.read_json_file(path) != attestation:
                raise ValueError('retained R70 attestation differs')
        else:
            pipeline.write_canonical_json(path, attestation)
        evidence.append(binding(path))
    current = bindings()
    for row in current:
        row['layers'] = [layer for layer in row['layers'] if layer['label'] in
            {layer['label'] for layer in old[row['season']]['layers']}]
        if row['season'] not in changed and row != old[row['season']]:
            raise ValueError('unselected preferred season changed')
    readbacks = [audit(season) for season in registry.supported_seasons()]
    remaining = sum(row['failure_count'] for row in readbacks)
    item = next(row for row in result['work_items'] if row['id'] == 'birthdays')
    selected = {(row['season'], row['carrier_id']) for row in item['verified_repairs'] + year_rows}
    original = pipeline.read_json_file(ROOT.parent / 'current-literal-birthdays-20261010-v1.json')
    before_ids = {(r['season'], f['carrier_id']) for r in original['seasons'] for f in r['failures']}
    after_ids = {(r['season'], f['carrier_id']) for r in readbacks for f in r['failures']}
    if (before_ids - after_ids != selected or after_ids - before_ids or remaining != 42
            or item['frozen_baseline']['count'] != 247 or len(selected) != 205):
        raise ValueError('frozen birthday issue identities drifted or new failure introduced')
    fresh = ROOT.parent / 'current-literal-birthdays-20261010-v4.json'
    pipeline.write_canonical_json(fresh, dict(schema_version=original['schema_version'], seasons=readbacks,
        failure_count=remaining, scope=original['scope']))
    item['verified_repairs'].extend(year_rows)
    item.update(verified_repair_count=205, current_remaining_native_recipe_disagreements=42, state='open')
    result.update(utc=datetime.now(UTC).isoformat(), previous_checklist=binding(prior), current_release_bindings=current,
        fresh_runtime_runs_this_checklist=sorted(changed), all_required_work_complete=False,
        next_batch='13 real stock cases OPEN. Wrong recipe dates, aliases/shared-family year gaps explicit. Original roles/managers/ratings/assets checklist still OPEN.')
    result['delivered_evidence'].extend(evidence + [binding(fresh)])
    if len(result['within_club_cases']) != 82 or result['within_club_progress']['open_real_club_cases'] != 13:
        raise ValueError('frozen duplicate denominator drifted')
    pipeline.write_canonical_json(output, result)
    print(dict(checklist=binding(output), birthdays_frozen=247, delivered=205, remaining=42,
        new_years_delivered=18, duplicates_still_open=13, all_required_work_complete=False), flush=True)


if __name__ == '__main__':
    run()
