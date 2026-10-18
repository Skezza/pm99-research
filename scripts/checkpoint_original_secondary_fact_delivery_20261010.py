"""Deliver seven original birthdays and one nationality after exact runtime proof."""
import copy
from datetime import UTC, datetime

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_original_secondary_facts_v1 as layer
from scripts import build_registered_quality_release_v1 as builder
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.checkpoint_original_person_year_delivery_20261010 import validate_frozen_birthdays
from scripts.audit_compiled_player_birth_dates_v1 import audit
from scripts.build_original_secondary_facts_20261010 import ROOT, CASES


def check_visual(review, *, name=None, club=None, age=None, nationality=None):
    if (review.get('method') != 'assistant-original-image-visual-review'
            or not review.get('original_frame_visually_inspected')
            or registry.sha256_file(registry.ROOT / review['screenshot']) != review['screenshot_sha256']):
        raise ValueError('original factual runtime frame not visually inspected and hash bound')
    if name is not None and (review.get('observed_native_name') != name
            or review.get('observed_club') != club or review.get('observed_age') != age
            or review.get('expected_age') != age or not review.get('visible_skills_match_native_baseline')):
        raise ValueError('actual exact person, club, age or unchanged skills unproved')
    if nationality is not None and review.get('observed_nationality') != nationality:
        raise ValueError('actual corrected nationality unproved')


def run(*, root=ROOT, cases=CASES, profiles=None, prior_version=24, next_version=25,
        expected_delivered=235, expected_remaining=12, expected_new_dates=7,
        native_readback_version=7, proof_suffix='-independent-proof-v2.json',
        close_ferran_finding=True, count_frozen_native_year_repairs=False):
    prior = root.parent / ('release-delivery-checklist-v' + str(prior_version) + '.json')
    output = root.parent / ('release-delivery-checklist-v' + str(next_version) + '.json')
    if output.exists():
        raise ValueError('completed secondary-fact checkpoint must not repeat')
    result = copy.deepcopy(pipeline.read_json_file(prior))
    old = {row['season']: row for row in result['current_release_bindings']}
    updates, evidence, promotions = [], [], []
    profiles = profiles or {
        '2021-22': ('ferran', 9166, '#9 Ferran Torres', 'Manchester City', 21, 'SPAIN'),
        '2025-26': ('otegbayo', 10249, 'Gabriel Otegbayo', 'Sheffield Wednesday', 20, None),
    }
    for season, case in cases.items():
        plan_path = root / (season + '-plan.json')
        plan = pipeline.read_json_file(plan_path)
        release = registry.load_registered_release(season, case['release'])
        layer.verify(registry.load_registered_release(season, case['base']), plan)
        proof = pipeline.read_json_file(root / (season + proof_suffix))
        replay = pipeline.read_json_file(root / (season + '-complete-replay-proof.json'))
        visual = pipeline.read_json_file(root / (season + '-startup-visual-review.json'))
        transport = pipeline.read_json_file(root / (season + '-startup-transport.json'))
        check_visual(visual)
        saved = registry.ROOT / release.locator['sourced_profile_assignment_plan_path']
        if (len(plan['updates']) != case['count'] or plan['unresolved']
                or proof['source_plan_sha256'] != registry.sha256_file(saved)
                or proof['package_sha256'] != registry.sha256_file(release.package_path)
                or not proof['all_other_native_bytes_identical']
                or not proof['all_other_game_files_identical']
                or not proof['all_other_recipe_facts_identical']
                or not replay['complete_game_inventory_identical']
                or not replay['complete_recipe_identical']
                or visual['observed_team'] != 'Stoke City'
                or visual['observed_date'] != season[:4] + '-08-01'
                or visual['release_manifest_sha256'] != release.manifest_sha256
                or transport['exit_code'] != 0
                or transport['release_manifest_sha256'] != release.manifest_sha256):
            raise ValueError('secondary-fact source/native/full replay/startup incomplete')
        if registry.load_preferred_release(season).release_id not in (case['base'], case['release']):
            raise ValueError('secondary-fact preferred baseline changed')
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
        label, carrier, name, club, age, nationality = profiles[season]
        profile_visual = pipeline.read_json_file(root / (label + '-profile-visual-review.json'))
        profile = pipeline.read_json_file(root / (label + '-profile-native-and-kit-proof.json'))
        profile_transport = pipeline.read_json_file(root / (label + '-profile-transport.json'))
        check_visual(profile_visual, name=name, club=club, age=age, nationality=nationality)
        if (profile['player_carrier_id'] != carrier or not profile['native_inputs_hash_verified']
                or not profile['kit_pixels']['passed']
                or profile['screenshot_sha256'] != profile_visual['screenshot_sha256']
                or profile_transport['exit_code'] != 0):
            raise ValueError('exact factual profile/kit/native-input proof incomplete')
        updates.extend(dict(season=season, carrier_id=row['carrier_id'], name=row['before_player']['name'],
            birth_date=row['birth_date'], source_plan=binding(plan_path))
            for row in plan['updates'] if 'birth_date' in row['fields']
            or (count_frozen_native_year_repairs and row['fields']==['native_birth_year']))
        evidence.extend(binding(root / (season + suffix)) for suffix in ('-plan.json',
            proof_suffix, '-complete-replay-proof.json',
            '-startup-visual-review.json', '-startup-transport.json'))
        evidence.extend(binding(root / (label + suffix)) for suffix in
            ('-profile-visual-review.json', '-profile-native-and-kit-proof.json', '-profile-transport.json'))
        promotions.append(dict(season=season, release_id=case['release'],
            release_manifest_sha256=release.manifest_sha256))
    if len(updates) != expected_new_dates:
        raise ValueError('declared full-birthday correction count differs')
    def checked_bindings():
        current = bindings()
        for row in current:
            row['layers'] = [l for l in row['layers'] if l['label'] in
                {l['label'] for l in old[row['season']]['layers']}]
            if row['season'] not in cases and row != old[row['season']]:
                raise ValueError('unselected preferred binding changed')
        return current
    checked_bindings()
    original = pipeline.read_json_file(root.parent / 'current-literal-birthdays-20261010-v1.json')
    candidate = [audit(s, cases[s]['release'] if s in cases else None)
        for s in registry.supported_seasons()]
    validate_frozen_birthdays(result, candidate, updates, original,
        expected_delivered=expected_delivered, expected_remaining=expected_remaining)
    builder.register(promotions)
    for season, case in cases.items():
        tag = 'original_secondary_' + season.replace('-', '_') + '_' + case['release'].split('-')[-1] + '_20261010'
        path = root / (season + '-final-attestation.json')
        attestation = runtime.attest(season=season,
            evidence_dir=registry.ROOT / '.local/runlogs/pm99_runner' / tag)
        if path.exists():
            if pipeline.read_json_file(path) != attestation:
                raise ValueError('retained secondary-fact attestation differs')
        else:
            pipeline.write_canonical_json(path, attestation)
        evidence.append(binding(path))
    current = checked_bindings()
    fresh = [audit(s) for s in registry.supported_seasons()]
    validate_frozen_birthdays(result, fresh, updates, original,
        expected_delivered=expected_delivered, expected_remaining=expected_remaining)
    native_readback = root.parent / ('current-literal-birthdays-20261010-v' + str(native_readback_version) + '.json')
    pipeline.write_canonical_json(native_readback, dict(schema_version=original['schema_version'],
        seasons=fresh, failure_count=expected_remaining, scope=original['scope']))
    item = next(row for row in result['work_items'] if row['id'] == 'birthdays')
    item['verified_repairs'].extend(updates)
    item.update(verified_repair_count=expected_delivered,
        current_remaining_native_recipe_disagreements=expected_remaining, state='open')
    if close_ferran_finding:
        finding = next(row for row in result['additional_confirmed_findings']
            if row['id'] == 'ferran-2021-runner-nationality-eng-instead-of-esp')
        finding.update(state='repaired-and-runtime-verified', corrected_observed='SPAIN',
            correction_evidence=binding(root / 'ferran-profile-visual-review.json'),
            source_plan=binding(root / '2021-22-plan.json'))
    duplicate_open=result['within_club_progress']['open_real_club_cases']
    counted_open=sum(c['status']=='open-source-and-ownership-review' for c in result['within_club_cases'])
    if len(result['within_club_cases']) != 82 or duplicate_open!=counted_open:
        raise ValueError('frozen duplicate case accounting drifted')
    result.update(utc=datetime.now(UTC).isoformat(), previous_checklist=binding(prior),
        current_release_bindings=current, fresh_runtime_runs_this_checklist=list(cases),
        all_required_work_complete=False,
        next_batch=f'{duplicate_open} real-club duplicate cases and {expected_remaining} literal birthday issues remain OPEN. Other checklist queues remain OPEN; missing secondary facts do not mean invented historical approval.')
    result['delivered_evidence'].extend(evidence + [binding(native_readback)])
    pipeline.write_canonical_json(output, result)
    print(dict(checklist=binding(output), birthdays_delivered=expected_delivered, remaining=expected_remaining,
        new_birthdays_delivered=expected_new_dates, additional_ferran_country_change=close_ferran_finding,
        duplicates_still_open=duplicate_open, all_required_work_complete=False), flush=True)


if __name__ == '__main__':
    run()
