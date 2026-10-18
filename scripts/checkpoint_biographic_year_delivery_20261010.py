"""Record actual accepted birthday counts, retaining the frozen issue ledger."""
import copy
from datetime import UTC, datetime

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.audit_compiled_player_birth_dates_v1 import audit


def run():
    root = registry.ROOT / '.local/consolidated-audit-20261009'
    batch = root / 'biographic-birth-years-v1'
    prior = root / 'release-delivery-checklist-v13.json'
    result = copy.deepcopy(pipeline.read_json_file(prior))
    old_bindings = {row['season']: row for row in result['current_release_bindings']}
    updates, evidence, selected = [], [], set()
    for year in range(2019, 2026):
        season = f'{year}-{str(year+1)[-2:]}'
        release = registry.load_preferred_release(season)
        if (release.release_id != 'sourced-biographic-birth-years-20261010-r67a'
                or not registry.validate_preferred_release(season, level='playable')['valid']
                or registry._validate_runtime_attestation(release)):
            raise ValueError('biography candidate lacks current exact runtime qualification')
        plan = pipeline.read_json_file(batch / (season + '-plan.json'))
        proof = pipeline.read_json_file(batch / (season + '-independent-proof.json'))
        replay = pipeline.read_json_file(batch / (season + '-complete-replay-proof.json'))
        if (proof['corrected_birth_years'] != len(plan['updates'])
                or not proof['all_other_native_bytes_identical']
                or not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']):
            raise ValueError('biography source/native/replay evidence is incomplete')
        for row in plan['updates']:
            key = (season, row['carrier_id'])
            if key in selected:
                raise ValueError('birthday accepted twice')
            selected.add(key)
            updates.append(dict(season=season, carrier_id=row['carrier_id'], name=row['name'],
                birth_date=row['birth_date'], source_plan=binding(batch / (season + '-plan.json'))))
        for suffix in ('-plan.json', '-independent-proof.json', '-complete-replay-proof.json',
                '-startup-visual-review.json', '-final-attestation.json'):
            evidence.append(binding(batch / (season + suffix)))
    age = pipeline.read_json_file(batch / 'bursik-correct-slot-visual-review.json')
    live = pipeline.read_json_file(batch / 'bursik-age-native-and-kit-proof.json')
    if (age['observed_age'] != age['expected_age'] or age['observed_age'] != 20
            or live['player_carrier_id'] != 10661 or not live['native_inputs_hash_verified']
            or not live['kit_pixels']['passed']):
        raise ValueError('actual corrected10661 age/slot/kit was not proved')
    evidence.extend(binding(batch / name) for name in ('bursik-correct-slot-visual-review.json',
        'bursik-age-native-and-kit-proof.json', 'bursik-first-profile-rejection-v1.json'))
    current = bindings()
    for row in current:
        row['layers'] = [layer for layer in row['layers'] if layer['label'] in
            {layer['label'] for layer in old_bindings[row['season']]['layers']}]
        if row['season'] not in {season for season, _ in selected} and row != old_bindings[row['season']]:
            raise ValueError('unselected season binding changed')
    readbacks = [audit(season) for season in registry.supported_seasons()]
    remaining = sum(row['failure_count'] for row in readbacks)
    item = next(row for row in result['work_items'] if row['id'] == 'birthdays')
    frozen = item['frozen_baseline']['count']
    if frozen != 247 or remaining + len(selected) != frozen:
        raise ValueError('frozen birthday accounting drift or a new birthday failure')
    old_readback = pipeline.read_json_file(root / 'current-literal-birthdays-20261010-v1.json')
    before_ids = {(row['season'], failure['carrier_id']) for row in old_readback['seasons'] for failure in row['failures']}
    after_ids = {(row['season'], failure['carrier_id']) for row in readbacks for failure in row['failures']}
    if before_ids - after_ids != selected or after_ids - before_ids:
        raise ValueError('literal birthday changes do not equal exact declared23 identities')
    fresh = root / 'current-literal-birthdays-20261010-v2.json'
    pipeline.write_canonical_json(fresh, dict(schema_version=old_readback['schema_version'],
        seasons=readbacks, failure_count=remaining, scope=old_readback['scope']))
    item.update(verified_repairs=updates, verified_repair_count=len(selected),
        current_remaining_native_recipe_disagreements=remaining,
        prior_informational_projection=25, correction='Actual independent accepted total is23, not the preliminary25 projection; counters are computed from immutable source/native proofs.',
        state='open', original_roster_ownership_approved=False)
    result.update(utc=datetime.now(UTC).isoformat(), previous_checklist=binding(prior),
        current_release_bindings=current, fresh_runtime_runs_this_checklist=[f'{year}-{str(year+1)[-2:]}' for year in range(2019,2026)],
        all_required_work_complete=False,
        next_batch='13 real stock duplicate cases remain. R69 fixed-display-window names/164 years PRIVATE with full native skill semantics; runtime validation next. Original other checklist queues still open.')
    result['delivered_evidence'].extend(evidence + [binding(fresh)])
    if len(result['within_club_cases']) != 82 or result['within_club_progress']['open_real_club_cases'] != 13:
        raise ValueError('duplicate denominator drift')
    output = root / 'release-delivery-checklist-v14.json'
    pipeline.write_canonical_json(output, result)
    print(dict(checklist=binding(output), birthdays_frozen=frozen, delivered=len(selected), remaining=remaining,
        duplicates_still_open=13, all_required_work_complete=False), flush=True)


if __name__ == '__main__':
    run()
