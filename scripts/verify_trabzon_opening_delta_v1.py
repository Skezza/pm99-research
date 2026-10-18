"""Independent byte/readback verification of a delivered Trabzon2000 delta."""
import hashlib
import json

from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import read_initial_order
from app.indexed_jug_roles import read_indexed_native_roles
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline


def verify(baseline, candidate, plan):
    if (baseline.season, baseline.release_id, registry.sha256_file(baseline.package_path)) != (
            plan['season'], plan['release_id'], plan['package_sha256']):
        raise ValueError('independent Trabzon verification baseline changed')
    old_jug = (baseline.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    new_jug = (candidate.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    old_index, new_index = IndexedFDIFile.from_bytes(old_jug), IndexedFDIFile.from_bytes(new_jug)
    if len(old_jug) != len(new_jug) or old_jug[:old_index.index_end_offset] != new_jug[:new_index.index_end_offset]:
        raise ValueError('Trabzon changed player container/directory bytes')
    orders = {r['carrier_id']: r for r in plan['orders']}
    allowed = set()
    entries = {e.record_id: e for e in old_index.entries}
    if set(entries) != {e.record_id for e in new_index.entries}:
        raise ValueError('Trabzon changed player carrier directory')
    for id, row in orders.items():
        e = entries[id]
        original = read_initial_order(e.decode_payload(old_jug))
        if original.name != row['name'] or original.order != row['startup_order']:
            raise ValueError('Trabzon startup identity/preimage differs')
        offset = e.payload_offset + original.offset
        allowed.add(offset)
        if new_jug[offset] != row['after']:
            raise ValueError('Trabzon new startup order readback differs')
    changed = {i for i, (a, b) in enumerate(zip(old_jug, new_jug)) if a != b}
    primary_changes = plan.get('primary_role_changes', [])
    if primary_changes:
        from scripts import season_trabzon_opening_layer_v1 as layer
        if plan.get('schema') != layer.ROLE_SCHEMA or plan.get('primary_role_policy') != layer.ROLE_POLICY:
            raise ValueError('independent primary role policy/schema unsupported')
        for row in primary_changes:
            id = row['carrier_id']; e = entries[id]
            end, old_roles = read_indexed_native_roles(e.decode_payload(old_jug), id)
            _, new_roles = read_indexed_native_roles(e.decode_payload(new_jug), id)
            if (old_roles != row['native_roles_before'] or new_roles != row['native_roles_after']
                    or new_roles[1:] != old_roles[1:] or new_roles[0] != row['after']):
                raise ValueError('independent primary/secondary-role byte readback differs')
            allowed.add(e.payload_offset+end+2)
    if changed - allowed:
        raise ValueError('Trabzon changed player facts/skills/roles or unrelated bytes')
    old_eq = (baseline.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    new_eq = (candidate.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    old_entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(old_eq).entries}
    new_entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(new_eq).entries}
    if set(old_entries) != set(new_entries):
        raise ValueError('Trabzon changed club carrier directory')
    for id, e in old_entries.items():
        before = old_eq[e.payload_offset:e.payload_offset+e.payload_length]
        after_entry = new_entries[id]
        after = new_eq[after_entry.payload_offset:after_entry.payload_offset+after_entry.payload_length]
        if id != 1002:
            if before != after:
                raise ValueError('Trabzon changed another club payload')
            continue
        roster = parse_eq_external_team_roster_payload(before, {})
        if roster is None or [(r.player_record_id, r.flag) for r in roster.rows] != [tuple(r) for r in plan['before_rows']]:
            raise ValueError('Trabzon source roster preimage differs')
        first = roster.rows[0].raw_row_offset
        kept = [r for r in roster.rows if r.player_record_id != 32505]
        expected = before[:first-1] + bytes([len(kept)]) + b''.join(before[r.raw_row_offset:r.raw_row_offset+5] for r in kept)
        if after != expected:
            raise ValueError('Trabzon changed opaque club/tactics bytes or another roster row')
    inventory = pipeline.read_json_file(baseline.inventory_path)
    final_inventory = pipeline.read_json_file(candidate.inventory_path)
    pipeline.assert_tree_matches_inventory(baseline.game_path, inventory)
    pipeline.assert_tree_matches_inventory(candidate.game_path, final_inventory)
    difference = pipeline.inventory_difference(inventory, final_inventory)
    if (difference['only_left'] or difference['only_right'] or
            sorted(r['path'] for r in difference['changed']) != ['DBDAT/EQ98030.FDI', 'DBDAT/JUG98030.FDI']):
        raise ValueError('Trabzon delta changed other game files')
    return {'schema': 'pm99-independent-Trabzon-opening-byte-proof-v1', 'status': 'PASS',
        'baseline_release_id': baseline.release_id, 'candidate_release_id': candidate.release_id,
        'changed_player_bytes': len(changed), 'removed_roster_links': [32505],
        'only_files_changed': ['DBDAT/EQ98030.FDI', 'DBDAT/JUG98030.FDI'],
        'primary_role_changes': primary_changes,
        'all_other_facts_skills_secondary_roles_tactics_records_preserved': True,
        'jug_sha256': hashlib.sha256(new_jug).hexdigest(), 'eq_sha256': hashlib.sha256(new_eq).hexdigest(),
        'runtime_verified': False}
