"""Repair a demonstrably incompatible legacy role set without backcasting a career.

Requires an exact biography identity and a fine role compatible with the
retained broad fact. Already compatible roles are NOT overwritten. Only the
six-byte role set changes; no adjacent fact or control byte may change.
The fine-role source is a published biography, not an exact-season FIFA claim.
"""
import copy
import re

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles
from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.season_historical_roster_audit_v1 import role_conflict
from scripts.season_within_club_reserve_repair_v1 import native_facts
from scripts.season_historical_role_plan_v1 import HTML_ROLES
from scripts.season_exact_fifa_role_delta_v1 import compatible

KIND = 'compatible-biography-conflicting-role-set-repair'
SCOPE = 'Only the selected contradictory legacy six-byte fine-role set and corresponding recipe fine-role fact/fallback. Broad position, name, DOB, country, skills, orders, owners, tactics, managers, photos and kit assets unchanged. Compatible published biography role, not exact-period fine-role proof; inherited contradictory secondary roles cleared, not retained as historical claims.'


def historical_provider_id(base, package, actor):
    """Bind the provider ID independently of the newly selected biography.

    A source-row actor may have acquired an adjudicated identity in its parent.
    Revalidate that hash-bound historical chain rather than trusting the new
    request's ID, name and birthday as evidence of their own correctness.
    """
    direct = re.fullmatch(r'person-transfermarkt-([1-9][0-9]*)', actor.get('person_id', ''))
    if direct:
        return int(direct.group(1))
    from scripts import season_adjudicated_player_facts_v1 as adjudicated
    ids = set()
    for artifact in package.get('artifacts', []):
        if not artifact['id'].startswith('source-backed-player-changes-'):
            continue
        path = base.package_path.parent / artifact['relative_path']
        if (not path.resolve().is_relative_to(base.package_path.parent.resolve())
                or registry.sha256_file(path) != artifact['sha256']):
            raise ValueError('biography/native identity parent evidence hash differs')
        plan = pipeline.read_json_file(path)
        if plan.get('kind') != adjudicated.KIND:
            continue
        for update in plan.get('updates', []):
            witness = update.get('witness', {})
            if (update.get('carrier_id') == actor['carrier_id']
                    and witness.get('person_id') == actor.get('person_id')
                    and witness.get('full_name') == actor.get('source_name')):
                values = adjudicated.adjudicate(witness)
                if any(actor['facts'].get(k) != v for k, v in values.items()):
                    raise ValueError('biography/native identity parent facts differ')
                ids.add(int(witness['historical_identity']['provider_player_id']))
    if len(ids) != 1:
        raise ValueError('biography/native identity requires one independent historical provider ID')
    return ids.pop()


def prepare(base, path, request):
    from scripts import season_source_verified_player_changes_v1 as changes
    if (request.get('schema') != changes.INPUT_SCHEMA or request.get('kind') != KIND
            or request.get('season') != base.season or request.get('release_id') != base.release_id
            or not request.get('changes')):
        raise ValueError('compatible primary-role repair needs exact parent and explicit actors')
    package = pipeline.read_json_file(base.package_path)
    players = {p['carrier_id']: p for p in package['players']}
    clubs = {c['id']: c for c in package['clubs']}
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    owners = ownership.native_owners(eq)
    updates, seen = [], set()
    for selection in request['changes']:
        carrier = selection['carrier_id']
        if type(carrier) is not int or carrier in seen or selection.get('field_mask') != ['fine_roles']:
            raise ValueError('unique literal primary-fine-role-only actors required')
        seen.add(carrier)
        actor = players[carrier]
        if selection['profile']['provider_player_id'] != historical_provider_id(base, package, actor):
            raise ValueError('biography/native identity historical provider ID differs')
        published = exchange.read_transfermarkt_profile(selection['profile'], selection['profile']['provider_player_id'])
        observed = native_facts(jug, carrier)
        broad = actor['facts']['primary_position']
        entry = entries[carrier]
        end, roles = read_indexed_native_roles(entry.decode_payload(jug), carrier)
        if (selection['before'] != actor or published['published_birth_date'] != actor['facts']['birth_date']
                or exchange.published_name_key(published['published_full_name']) != exchange.published_name_key(actor.get('source_name') or actor['name'])
                or observed['birth_date'] != actor['facts']['birth_date']
                or observed['name'].casefold() != actor['name'].casefold() or observed['position'] != broad
                or broad not in ('D', 'M', 'F') or not role_conflict(broad, roles[0])
                or owners.get(carrier) != {clubs[actor['club_id']]['carrier_id']}):
            raise ValueError('exact biography/native identity and a demonstrated conflicting first role required')
        key = ''.join(c for c in (published['published_profile_position'] or '').casefold() if c.isalpha())
        fine = HTML_ROLES.get(key)
        if fine is None or not compatible(broad, fine):
            raise ValueError('source fine role must be compatible with retained broad role')
        after_roles = [fine, 98, 98, 98, 98, 98]
        masks = []
        for i in range(6):
            offset = entry.payload_offset + end + 2 + i
            old = roles[i] + 1 if roles[i] != 98 else 0
            if jug[offset] != old:
                raise ValueError('native role-set physical field boundary differs')
            masks.append(dict(file='DBDAT/JUG98030.FDI', record_offset=end+2+i,
                              file_offset=offset, before=old, after=fine+1 if i == 0 else 0))
        candidate = bytearray(jug)
        for mask in masks:
            candidate[mask['file_offset']] = mask['after']
        _, reread = read_indexed_native_roles(entry.decode_payload(bytes(candidate)), carrier)
        if reread != after_roles or native_facts(bytes(candidate), carrier) != observed:
            raise ValueError('first-role post-readback changed other biography fields')
        updates.append(dict(carrier_id=carrier, before=copy.deepcopy(actor), values=dict(fine_roles=[fine]),
            field_mask=['fine_roles'], native_masks=masks,
            evidence=dict(profile=selection['profile'], parsed_profile=published, before_native_roles=roles,
                after_native_roles=after_roles), expected_owner=clubs[actor['club_id']]['carrier_id']))
    result = dict(schema=changes.SCHEMA, kind=KIND, season=base.season, release_id=base.release_id,
        source_input=changes.binding(path), package_sha256=registry.sha256_file(base.package_path),
        jug_sha256=changes.digest(jug), eq_sha256=changes.digest(eq), updates=updates, scope=SCOPE,
        source_policy='exact-identity-conflicting-legacy-role-set-to-compatible-published-biography-v1')
    result['transaction_id'] = changes.digest(packages.canonical_json_bytes(result))[:24]
    validate_mask(result)
    return result


def validate_mask(plan):
    from scripts import season_source_verified_player_changes_v1 as changes
    rows = plan.get('updates', [])
    if plan.get('schema') != changes.SCHEMA or plan.get('kind') != KIND or not rows:
        raise ValueError('explicit compatible primary-role repair required')
    seen, offsets = set(), set()
    for row in rows:
        roles = row.get('values', {}).get('fine_roles', [])
        if (set(row) != {'carrier_id', 'before', 'values', 'field_mask', 'native_masks', 'evidence', 'expected_owner'}
                or type(row['carrier_id']) is not int or row['carrier_id'] in seen
                or row['field_mask'] != ['fine_roles'] or set(row['values']) != {'fine_roles'}
                or len(roles) != 1
                or any(type(r) is not int or not 0 <= r <= 17 for r in roles)
                or len(row['native_masks']) != 6):
            raise ValueError('unique selected fine-role-set-only rows required')
        seen.add(row['carrier_id'])
        masks = row['native_masks']
        if ([m['record_offset']-masks[0]['record_offset'] for m in masks] != list(range(6))
                or [m['after'] for m in masks] != [roles[0]+1, 0, 0, 0, 0, 0]):
            raise ValueError('only exact complete fine-role field boundaries permitted')
        for mask in masks:
            if (set(mask) != {'file', 'record_offset', 'file_offset', 'before', 'after'}
                or mask['file'] != 'DBDAT/JUG98030.FDI'
                or any(type(mask[k]) is not int for k in ('record_offset', 'file_offset', 'before', 'after'))
                or mask['record_offset'] < 2 or mask['file_offset'] < mask['record_offset']
                or not 0 <= mask['before'] <= 18 or mask['file_offset'] in offsets
                or mask['file_offset'] - mask['record_offset'] != masks[0]['file_offset'] - masks[0]['record_offset']):
                raise ValueError('exact distinct fine-role pre/post byte required')
            offsets.add(mask['file_offset'])
