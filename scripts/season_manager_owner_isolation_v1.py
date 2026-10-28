"""Split one shared coach reference using an existing, wholly unused ENT slot.

This is an optional part of the existing manager plan, not a new build lane.
The SDK owns the native link/name writers. No Native IDs or profiles are added.
"""
import copy
import hashlib

from app.eq_team_manager_links import (
    parse_indexed_eq_manager_links, patch_indexed_eq_active_manager_id,
)
from app.fdi_indexed import IndexedFDIFile
from app.xor import xor_decode
from scripts.build_2015_english92_release import _rebuild_indexed


def validated_rows(package, plan):
    rows = plan.get('owner_isolations', [])
    if not isinstance(rows, list) or len(rows) > 1:
        raise ValueError('manager isolation permits one explicit owner split per plan')
    if not rows:
        return []
    row = rows[0]
    keys = {'club_id', 'club_carrier_id', 'from_manager_id', 'from_carrier_id',
            'to_manager_id', 'to_carrier_id', 'to_raw_record_sha256'}
    if not isinstance(row, dict) or set(row) != keys:
        raise ValueError('manager isolation requires the complete explicit binding')
    for key in ('club_carrier_id', 'from_carrier_id', 'to_carrier_id'):
        if type(row[key]) is not int or row[key] <= 0:
            raise ValueError('manager isolation IDs must be positive integers')
    if (row['from_manager_id'] != f"manager-{row['from_carrier_id']}"
            or row['to_manager_id'] != f"manager-{row['to_carrier_id']}"
            or row['from_carrier_id'] == row['to_carrier_id']):
        raise ValueError('manager isolation recipe/native IDs disagree')
    managers = {m['id']: m for m in package['managers']}
    clubs = {c['id']: c for c in package['clubs']}
    old = managers.get(row['from_manager_id'])
    club = clubs.get(row['club_id'])
    if (old is None or club is None or old['carrier_id'] != row['from_carrier_id']
            or club['carrier_id'] != row['club_carrier_id']
            or club['manager_id'] != row['from_manager_id']):
        raise ValueError('manager isolation source owner changed')
    owners = [c for c in package['clubs'] if c['manager_id'] == old['id']]
    if len(owners) < 2:
        raise ValueError('an exclusive coach needs a normal name correction')
    if (row['to_manager_id'] in managers
            or any(m['carrier_id'] == row['to_carrier_id'] for m in managers.values())):
        raise ValueError('manager isolation destination already has a recipe actor')
    updates = [u for u in plan['updates'] if u['manager_id'] == row['to_manager_id']]
    if (len(updates) != 1 or updates[0]['club_id'] != row['club_id']
            or updates[0]['club_carrier_id'] != row['club_carrier_id']
            or updates[0]['carrier_id'] != row['to_carrier_id']
            or updates[0]['before'] != old['name']
            or updates[0]['before_policy'] != old.get('policy')):
        raise ValueError('manager isolation lacks its exact sourced name update')
    remaining = [c for c in owners if c['id'] != row['club_id']]
    remaining_updates = [u for u in plan['updates'] if u['manager_id'] == old['id']]
    if len(remaining_updates) != 1:
        raise ValueError('manager isolation requires one sourced decision for the remaining coach owner')
    for update in plan['updates']:
        if update['manager_id'] == old['id'] and (
                len(remaining) != 1 or update.get('club_id') != remaining[0]['id']
                or update.get('club_carrier_id') != remaining[0]['carrier_id']):
            raise ValueError('remaining shared coach correction must bind its sole remaining owner')
    return rows


def prepare_recipe(package, plan):
    """Return a detached recipe with only the target link and one new row."""
    rows = validated_rows(package, plan)
    result = copy.deepcopy(package)
    for row in rows:
        old = next(m for m in result['managers'] if m['id'] == row['from_manager_id'])
        new = dict(copy.deepcopy(old), id=row['to_manager_id'], carrier_id=row['to_carrier_id'])
        result['managers'].append(new)
        result['managers'].sort(key=lambda manager: manager['id'])
        club = next(c for c in result['clubs'] if c['id'] == row['club_id'])
        club['manager_id'] = new['id']
    return result


def apply_native(eq_data, ent_data, package, plan):
    """Patch the existing active link only after proving the spare is unused."""
    rows = validated_rows(package, plan)
    if not rows:
        return eq_data
    row = rows[0]
    eq_index = IndexedFDIFile.from_bytes(eq_data)
    ent_index = IndexedFDIFile.from_bytes(ent_data)
    ent_entries = {e.record_id: e for e in ent_index.entries}
    destination = ent_entries.get(row['to_carrier_id'])
    if destination is None or row['from_carrier_id'] not in ent_entries:
        raise ValueError('manager isolation requires two existing native ENT records')
    raw = ent_data[destination.payload_offset:destination.payload_offset + destination.payload_length]
    if hashlib.sha256(raw).hexdigest() != row['to_raw_record_sha256']:
        raise ValueError('manager isolation spare profile preimage changed')
    native_owners = set()
    target = None
    for entry in eq_index.entries:
        payload = eq_data[entry.payload_offset:entry.payload_offset + entry.payload_length]
        links = parse_indexed_eq_manager_links(payload)
        if row['to_carrier_id'] in links.manager_record_ids:
            raise ValueError('manager isolation spare has an active or inactive native reference')
        if links.active_manager_record_id == row['from_carrier_id']:
            native_owners.add(entry.record_id)
        if entry.record_id == row['club_carrier_id']:
            target = (entry, payload, links)
    expected = {c['carrier_id'] for c in package['clubs']
                if c['manager_id'] == row['from_manager_id']}
    if native_owners != expected or target is None:
        raise ValueError('manager isolation native and recipe owners disagree')
    entry, payload, links = target
    if links.active_manager_record_id != row['from_carrier_id']:
        raise ValueError('manager isolation active native owner changed')
    patched = patch_indexed_eq_active_manager_id(payload, row['to_carrier_id'])
    result = _rebuild_indexed(eq_data, eq_index, {entry.record_id: xor_decode(patched)})
    before = {e.record_id: e.decode_payload(eq_data) for e in eq_index.entries}
    for e in IndexedFDIFile.from_bytes(result).entries:
        expected_payload = xor_decode(patched) if e.record_id == entry.record_id else before[e.record_id]
        if e.decode_payload(result) != expected_payload:
            raise ValueError('manager isolation changed an unrelated native club payload')
    return result
