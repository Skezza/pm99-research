"""Select ten incremental birthday fixes only after actual final-game evidence."""
import copy
from datetime import UTC, datetime
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import build_registered_quality_release_v1 as builder
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts import season_original_person_birth_years_v1 as source
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.audit_compiled_player_birth_dates_v1 import audit
from scripts.checkpoint_original_person_year_delivery_20261010 import validate_frozen_birthdays
from scripts.build_additional_original_person_years_20261010 import ROOT, RELEASE, COUNTS


def run():
    prior = ROOT.parent / 'release-delivery-checklist-v23.json'
    output = ROOT.parent / 'release-delivery-checklist-v24.json'
    if output.exists():
        raise ValueError('completed incremental checkpoint must not repeat')
    result = copy.deepcopy(pipeline.read_json_file(prior))
    old = {r['season']: r for r in result['current_release_bindings']}
    promotions, evidence, updates = [], [], []
    for season, count in COUNTS.items():
        release = registry.load_registered_release(season, RELEASE)
        plan = pipeline.read_json_file(ROOT / (season + '-plan.json'))
        source.verify(registry.load_registered_release(season, plan['release_id']), plan)
        proof = pipeline.read_json_file(ROOT / (season + '-independent-proof.json'))
        replay = pipeline.read_json_file(ROOT / (season + '-complete-replay-proof.json'))
        visual = pipeline.read_json_file(ROOT / (season + '-startup-visual-review.json'))
        transport = pipeline.read_json_file(ROOT / (season + '-startup-transport.json'))
        if (len(plan['updates']) != count or proof['corrected_birth_years'] != count
                or not proof['all_other_native_bytes_identical'] or not proof['all_other_recipe_facts_ratings_identical']
                or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']
                or visual['method'] != 'assistant-original-image-visual-review'
                or not visual['original_frame_visually_inspected'] or visual['observed_team'] != 'Stoke City'
                or visual['observed_date'] != season[:4] + '-08-01'
                or visual['release_manifest_sha256'] != release.manifest_sha256
                or registry.sha256_file(registry.ROOT / visual['screenshot']) != visual['screenshot_sha256']
                or transport['exit_code'] != 0 or transport['release_manifest_sha256'] != release.manifest_sha256):
            raise ValueError('incremental source/native/full replay/original runtime incomplete')
        if registry.load_preferred_release(season).release_id not in (plan['release_id'], RELEASE):
            raise ValueError('incremental preferred baseline changed')
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
        updates.extend(dict(season=season, carrier_id=r['carrier_id'], name=r['name'],
            birth_date=r['birth_date'], source_plan=binding(ROOT / (season + '-plan.json'))) for r in plan['updates'])
        evidence.extend(binding(ROOT / (season + suffix)) for suffix in ('-plan.json', '-independent-proof.json',
            '-complete-replay-proof.json', '-startup-visual-review.json', '-startup-transport.json'))
        promotions.append(dict(season=season, release_id=RELEASE, release_manifest_sha256=release.manifest_sha256))
    visual = pipeline.read_json_file(ROOT / 'apter-profile-visual-review.json')
    profile = pipeline.read_json_file(ROOT / 'apter-profile-native-and-kit-proof.json')
    transport = pipeline.read_json_file(ROOT / 'apter-profile-transport.json')
    if (visual['method'] != 'assistant-original-image-visual-review' or not visual['original_frame_visually_inspected']
            or visual['observed_native_name'] != '#30 Rob Apter' or visual['observed_age'] != 22
            or visual['expected_age'] != 22 or not visual['visible_skills_match_native_baseline']
            or profile['player_carrier_id'] != 9518 or not profile['native_inputs_hash_verified']
            or not profile['kit_pixels']['passed'] or visual['screenshot_sha256'] != profile['screenshot_sha256']
            or registry.sha256_file(registry.ROOT / profile['screenshot']) != profile['screenshot_sha256']
            or transport['exit_code'] != 0):
        raise ValueError('actual exact Rob Apter age/unchanged skills/kit proof missing')
    evidence.extend(binding(ROOT / n) for n in ('apter-profile-visual-review.json',
        'apter-profile-native-and-kit-proof.json', 'apter-profile-transport.json'))
    if len(updates) != 10:
        raise ValueError('incremental declared update count differs')
    for row in bindings():
        row['layers'] = [l for l in row['layers'] if l['label'] in {l['label'] for l in old[row['season']]['layers']}]
        if row['season'] not in COUNTS and row != old[row['season']]:
            raise ValueError('unselected preferred binding changed')
    original = pipeline.read_json_file(ROOT.parent / 'current-literal-birthdays-20261010-v1.json')
    candidate_rows = [audit(s, RELEASE if s in COUNTS else None) for s in registry.supported_seasons()]
    validate_frozen_birthdays(result, candidate_rows, updates, original, expected_delivered=228, expected_remaining=19)
    builder.register(promotions)
    for row in promotions:
        s = row['season']
        evidence_dir = registry.ROOT / ('.local/runlogs/pm99_runner/additional_person_year_r78a_'
            + s.replace('-', '_') + '_20261010')
        path = ROOT / (s + '-final-attestation.json')
        attestation = runtime.attest(season=s, evidence_dir=evidence_dir)
        if path.exists():
            if pipeline.read_json_file(path) != attestation:
                raise ValueError('retained incremental attestation differs')
        else:
            pipeline.write_canonical_json(path, attestation)
        evidence.append(binding(path))
    current = bindings()
    for row in current:
        row['layers'] = [l for l in row['layers'] if l['label'] in {l['label'] for l in old[row['season']]['layers']}]
        if row['season'] not in COUNTS and row != old[row['season']]:
            raise ValueError('unselected binding changed during promotion')
    fresh_rows = [audit(s) for s in registry.supported_seasons()]
    validate_frozen_birthdays(result, fresh_rows, updates, original, expected_delivered=228, expected_remaining=19)
    fresh = ROOT.parent / 'current-literal-birthdays-20261010-v6.json'
    pipeline.write_canonical_json(fresh, dict(schema_version=original['schema_version'], seasons=fresh_rows,
        failure_count=19, scope=original['scope']))
    item = next(r for r in result['work_items'] if r['id'] == 'birthdays')
    item['verified_repairs'].extend(updates)
    item.update(verified_repair_count=228, current_remaining_native_recipe_disagreements=19, state='open')
    if len(result['within_club_cases']) != 82 or result['within_club_progress']['open_real_club_cases'] != 7:
        raise ValueError('frozen duplicate case accounting drifted')
    result.update(utc=datetime.now(UTC).isoformat(), previous_checklist=binding(prior), current_release_bindings=current,
        fresh_runtime_runs_this_checklist=list(COUNTS), all_required_work_complete=False,
        next_batch='7 real-club duplicate cases OPEN;19 literal birthday issues remain. Ferran nationality and seven explicit placeholder DOB corrections BUILT/private pending runtime. Other checklist queues OPEN.')
    result['delivered_evidence'].extend(evidence + [binding(fresh)])
    pipeline.write_canonical_json(output, result)
    print(dict(checklist=binding(output), birthdays_delivered=228, remaining=19,
        new_birthdays_delivered=10, duplicates_still_open=7, all_required_work_complete=False), flush=True)


if __name__ == '__main__':
    run()
