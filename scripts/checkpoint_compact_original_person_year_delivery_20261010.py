"""Deliver two compact year repairs without moving frozen case denominators."""
import copy
from datetime import UTC, datetime
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_original_secondary_facts_v1 as layer
from scripts import build_registered_quality_release_v1 as builder
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.checkpoint_original_person_year_delivery_20261010 import validate_frozen_birthdays
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.audit_compiled_player_birth_dates_v1 import audit
from scripts.build_compact_original_person_years_20261010 import ROOT, CASES

PROFILES = {
    '2024-25': ('tezgel', 'Emre Tezgel', 'Stoke City', 19, 10744),
    '2025-26': ('mubama', 'Divin Mubama', 'Stoke City', 21, 10341),
}


def validate_representative(target_raw, representative_raw, person, season, age, declared):
    from datetime import date
    native = layer.original.audit.native_player(representative_raw, person['carrier_id'])
    end = native['name_end']
    birthday = date(int.from_bytes(bytes(v ^ 0x61 for v in representative_raw[end+14:end+16]), 'little'),
        representative_raw[end+13] ^ 0x61, representative_raw[end+12] ^ 0x61)
    if (target_raw[2:5] not in (b'\xdd\x63\x60', b'\xdd\x63\x61')
            or target_raw[2:5] != representative_raw[2:5] or birthday.year < 2000
            or birthday.isoformat() != person['facts']['birth_date']
            or int(season[:4]) - birthday.year != age or not declared):
        raise ValueError('representative age check lacks the actual same native family and modern date')


def run():
    prior = ROOT.parent / 'release-delivery-checklist-v25.json'
    output = ROOT.parent / 'release-delivery-checklist-v26.json'
    if output.exists():
        raise ValueError('completed compact-year checkpoint must not repeat')
    result = copy.deepcopy(pipeline.read_json_file(prior))
    old = {r['season']: r for r in result['current_release_bindings']}
    updates, evidence, promotions = [], [], []
    for season, case in CASES.items():
        plan_path = ROOT / (season + '-plan.json')
        plan = pipeline.read_json_file(plan_path)
        layer.verify(registry.load_registered_release(season, case['base']), plan)
        release = registry.load_registered_release(season, case['release'])
        proof = pipeline.read_json_file(ROOT / (season + '-independent-proof.json'))
        replay = pipeline.read_json_file(ROOT / (season + '-complete-replay-proof.json'))
        visual = pipeline.read_json_file(ROOT / (season + '-startup-visual-review.json'))
        transport = pipeline.read_json_file(ROOT / (season + '-startup-transport.json'))
        check_visual(visual)
        if (len(plan['updates']) != 1 or plan['unresolved']
                or plan['updates'][0]['fields'] != ['native_birth_year']
                or plan['updates'][0]['carrier_id'] != 10958
                or proof['native_bytes_changed'] not in (1, 2)
                or proof['package_sha256'] != registry.sha256_file(release.package_path)
                or not proof['all_other_native_bytes_identical'] or not proof['all_other_game_files_identical']
                or not proof['all_other_recipe_facts_identical']
                or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']
                or visual['observed_team'] != 'Stoke City' or visual['observed_date'] != season[:4] + '-08-01'
                or visual['release_manifest_sha256'] != release.manifest_sha256
                or transport['exit_code'] != 0 or transport['release_manifest_sha256'] != release.manifest_sha256):
            raise ValueError('compact native/source/replay/startup proof incomplete')
        if registry.load_preferred_release(season).release_id not in (case['base'], case['release']):
            raise ValueError('compact preferred baseline changed')
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
        label, name, club, age, representative_carrier = PROFILES[season]
        profile_visual = pipeline.read_json_file(ROOT / (label + '-profile-visual-review.json'))
        profile = pipeline.read_json_file(ROOT / (label + '-profile-native-and-kit-proof.json'))
        profile_transport = pipeline.read_json_file(ROOT / (label + '-profile-transport.json'))
        check_visual(profile_visual, name=name, club=club, age=age)
        if (profile['player_carrier_id'] != representative_carrier or not profile['native_inputs_hash_verified']
                or not profile['kit_pixels']['passed']
                or profile['screenshot_sha256'] != profile_visual['screenshot_sha256']
                or profile_transport['exit_code'] != 0):
            raise ValueError('actual compact person/age/unchanged skills/kit proof incomplete')
        # Explicit representative loader coverage, never pretend the inaccessible
        # NPC was itself opened. Require its actual native family and modern DOB
        # to equal the tested profile family/date, independent of a display guess.
        from app.fdi_indexed import IndexedFDIFile
        raw_jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
        entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(raw_jug).entries}
        target_raw = entries[10958].decode_payload(raw_jug)
        representative_raw = entries[representative_carrier].decode_payload(raw_jug)
        person = next(p for p in pipeline.read_json_file(release.package_path)['players']
            if p['carrier_id'] == representative_carrier)
        validate_representative(target_raw, representative_raw, person, season, age,
            profile_visual.get('representative_age_check_not_direct_target_profile'))
        row = plan['updates'][0]
        updates.append(dict(season=season, carrier_id=10958, name=row['before_player']['name'],
            birth_date=row['birth_date'], source_plan=binding(plan_path)))
        evidence.extend(binding(ROOT / (season + suffix)) for suffix in ('-plan.json',
            '-independent-proof.json', '-complete-replay-proof.json', '-startup-visual-review.json', '-startup-transport.json'))
        evidence.extend(binding(ROOT / (label + suffix)) for suffix in
            ('-profile-visual-review.json', '-profile-native-and-kit-proof.json', '-profile-transport.json'))
        promotions.append(dict(season=season, release_id=case['release'], release_manifest_sha256=release.manifest_sha256))
    def checked_bindings():
        current = bindings()
        for row in current:
            row['layers'] = [l for l in row['layers'] if l['label'] in {l['label'] for l in old[row['season']]['layers']}]
            if row['season'] not in CASES and row != old[row['season']]:
                raise ValueError('unselected compact-year binding changed')
        return current
    checked_bindings()
    original = pipeline.read_json_file(ROOT.parent / 'current-literal-birthdays-20261010-v1.json')
    candidate = [audit(s, CASES[s]['release'] if s in CASES else None) for s in registry.supported_seasons()]
    validate_frozen_birthdays(result, candidate, updates, original, expected_delivered=237, expected_remaining=10)
    builder.register(promotions)
    for season, case in CASES.items():
        tag = 'original_secondary_' + season.replace('-', '_') + '_' + case['release'].split('-')[-1] + '_20261010'
        path = ROOT / (season + '-final-attestation.json')
        attestation = runtime.attest(season=season, evidence_dir=registry.ROOT / '.local/runlogs/pm99_runner' / tag)
        if path.exists():
            if pipeline.read_json_file(path) != attestation:
                raise ValueError('retained compact final attestation differs')
        else:
            pipeline.write_canonical_json(path, attestation)
        evidence.append(binding(path))
    current = checked_bindings()
    fresh = [audit(s) for s in registry.supported_seasons()]
    validate_frozen_birthdays(result, fresh, updates, original, expected_delivered=237, expected_remaining=10)
    readback = ROOT.parent / 'current-literal-birthdays-20261010-v8.json'
    pipeline.write_canonical_json(readback, dict(schema_version=original['schema_version'], seasons=fresh,
        failure_count=10, scope=original['scope']))
    item = next(r for r in result['work_items'] if r['id'] == 'birthdays')
    item['verified_repairs'].extend(updates)
    item.update(verified_repair_count=237, current_remaining_native_recipe_disagreements=10, state='open')
    if len(result['within_club_cases']) != 82 or result['within_club_progress']['open_real_club_cases'] != 7:
        raise ValueError('frozen duplicate accounting drifted')
    result.update(utc=datetime.now(UTC).isoformat(), previous_checklist=binding(prior),
        current_release_bindings=current, fresh_runtime_runs_this_checklist=list(CASES),
        all_required_work_complete=False,
        next_batch='7 real-club duplicates and10 literal DOB disagreements remain OPEN; roles/ratings/source/asset checklist queues unchanged and not approved by year repair.')
    result['delivered_evidence'].extend(evidence + [binding(readback)])
    failed_search = ROOT / 'shade-profile-transport.json'
    if failed_search.exists():
        result['delivered_evidence'].append(binding(failed_search))
        failed_tag = 'original_secondary_2024_25_r81a_20261010_shade'
        failure_frame = ROOT / 'runtime' / failed_tag / failed_tag / 'screens/44_profile_only_shade_done.png'
        result['delivered_evidence'].append(binding(failure_frame))
    result['mode1_year_runtime_coverage'] = dict(
        corrected_dates='Independent literal original-source/native readback of both10958 targets.',
        profiles='Actual same-release/same-native-family modern-age representatives Tezgel10744 andMubama10341.',
        direct_target_profile_approved=False,
        failed_shade_search_retained=failed_search.exists(),
        limitation='Shade was not returned by transfer search. No direct NPC-profile or NPC-searchability approval is claimed.')
    pipeline.write_canonical_json(output, result)
    print(dict(checklist=binding(output), new_birthdays_delivered=2, birthdays_delivered=237,
        remaining=10, duplicates_still_open=7, all_required_work_complete=False), flush=True)


if __name__ == '__main__':
    run()
