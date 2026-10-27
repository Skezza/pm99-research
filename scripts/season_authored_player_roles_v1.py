"""Reviewed same-person role edits, including starters, without rebuilding XIs.

Historical evidence belongs to the bound authoring receipt. This adapter closes
the recipe mask and writes only the six known role bytes and broad-position
byte. Existing reserve/country adapters and their SOURCE contracts stay intact.
"""
import copy
from datetime import date
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import rewrite_indexed_native_roles
from app.xor import xor_encode
from scripts import season_authored_country_delta_v2 as common
from scripts import season_exact_fifa_role_delta_v1 as roles
from scripts import season_historical_roster_audit_v1 as audit
from scripts import season_opening_order_repair_v1 as owners
from scripts import season_package_compiler_v2 as compiler
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as p, season_release_registry_v1 as r

SCHEMA = 'pm99-reviewed-same-identity-player-roles-v1'
MODE = 'known-good-reviewed-same-identity-player-roles-v1'
# Reuse the existing factory-recompilation rejection boundary.
PREFIX = common.PREFIX
digest = common.digest
_parent = common._parent
_bound = common._bound
SCOPE = ('Only selected same-person primary_position/fine_roles and their proof; '
         'native writes restricted to six role bytes and name_end+11. Identity, '
         'DOB, abilities, adjacent+10, all orders, rosters, tactics, managers, '
         'photos, kits and all other native bytes remain exact.')


def filename(plan):
    return PREFIX + plan['transaction_id'] + '.json'


def verify_recipe_mask(before, after, request):
    if request.get('selection_kind') != 'same-identity-player-roles':
        raise ValueError('explicit same-identity role selection required')
    closed = dict(request, selection_kind='players-only')
    _, selected, _ = common.verify_recipe_mask(before, after, closed)
    if before['assets'] != after['assets']:
        raise ValueError('same-person roles cannot change any assets')
    old = {a['id']: a for a in before['players']}
    new = {a['id']: a for a in after['players']}
    for identity in selected:
        left, right = old[identity], new[identity]
        ignored = {'facts', 'proof', 'fact_fallbacks'}
        if {k: v for k, v in left.items() if k not in ignored} != {
                k: v for k, v in right.items() if k not in ignored}:
            raise ValueError('role edit changes identity or another player field')
        lf, rf = left['facts'], right['facts']
        if set(lf) != set(rf) or any(lf[k] != rf[k] for k in lf
                                   if k not in {'primary_position', 'fine_roles'}):
            raise ValueError('role edit changes a non-role fact')
        fields = rf['fine_roles']
        if (not isinstance(rf['primary_position'], str)
                or rf['primary_position'] not in {'G', 'D', 'M', 'F'}
                or not isinstance(fields, list) or not 1 <= len(fields) <= 6
                or any(type(v) is not int or not 0 <= v <= 17 for v in fields)
                or len(set(fields)) != len(fields)
                or not roles.compatible(rf['primary_position'], fields[0])):
            raise ValueError('explicit compatible native role set required')
        if ((lf['primary_position'] == 'G') != (rf['primary_position'] == 'G')
                or (rf['primary_position'] != 'G' and 0 in fields)):
            raise ValueError('same-person role lane does not convert goalkeepers')
        strip = lambda actor: [x for x in actor.get('fact_fallbacks', [])
                               if x['field'] not in {'primary_position', 'fine_roles'}]
        if strip(left) != strip(right):
            raise ValueError('role edit changes unrelated fact provenance')
    return selected


def _reconstruct(base, request):
    if request.get('schema') != SCHEMA + '-input' or request['parent'] != _parent(base):
        raise ValueError('role request does not bind its immutable parent')
    child = _bound(request['child_recipe'])
    receipt = p.read_json_file(_bound(request['authoring_receipt']))
    if (receipt.get('country') != request['country']
            or receipt.get('child_recipe_sha256') != r.sha256_file(child)):
        raise ValueError('role authoring receipt belongs to another recipe')
    for binding in receipt['source_bindings']:
        _bound(binding)
    before, after = p.read_json_file(base.package_path), p.read_json_file(child)
    selected = verify_recipe_mask(before, after, request)
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    ent = (base.game_path / 'DBDAT/ENT98030.FDI').read_bytes()
    old = {a['id']: a for a in before['players']}
    new = {a['id']: a for a in after['players']}
    clubs = {c['id']: c for c in before['clubs']}
    ownership = owners.native_owners(eq)
    index = IndexedFDIFile.from_bytes(jug)
    updates, entries, natives = {}, {}, {}
    for identity in sorted(selected):
        actor = old[identity]
        carrier = actor['carrier_id']
        matches = [e for e in index.entries if e.record_id == carrier]
        if len(matches) != 1 or ownership.get(carrier) != {clubs[actor['club_id']]['carrier_id']}:
            raise ValueError('role target lacks unique native record and exclusive owner')
        entry = matches[0]
        payload = entry.decode_payload(jug)
        native = audit.native_player(payload, carrier)
        end = native['name_end']
        birthday = date(int.from_bytes(bytes(v ^ 0x61 for v in payload[end + 14:end + 16]),
                                       'little'), payload[end + 13] ^ 0x61,
                        payload[end + 12] ^ 0x61).isoformat()
        if (payload[2:5].hex() not in {'dd6360', 'dd6361'}
                or audit.normalise(native['name']) != audit.normalise(actor['name'])
                or birthday != actor['facts'].get('birth_date')
                or native['position'] != actor['facts']['primary_position']):
            raise ValueError('native role identity/preimage differs from the recipe')
        entries[carrier], natives[carrier] = entry, native
        updates[carrier] = new[identity]['facts']['fine_roles']
    patched, _ = rewrite_indexed_native_roles(jug, updates)
    result = bytearray(patched)
    allowed = set()
    for identity in selected:
        actor = new[identity]
        carrier = actor['carrier_id']
        entry, native = entries[carrier], natives[carrier]
        end = native['name_end']
        result[entry.payload_offset + end + 11] = xor_encode(bytes([
            compiler.POSITION[actor['facts']['primary_position']] ^ 0x61]))[0]
        allowed.update(entry.payload_offset + end + i for i in (*range(2, 8), 11))
    result = bytes(result)
    if len(result) != len(jug) or any(a != b and i not in allowed
                                     for i, (a, b) in enumerate(zip(jug, result))):
        raise ValueError('role patch changed an unrelated native byte')
    for identity in selected:
        actor = new[identity]
        carrier = actor['carrier_id']
        native = audit.native_player(entries[carrier].decode_payload(result), carrier)
        if (native['position'] != actor['facts']['primary_position']
                or native['roles'] != actor['facts']['fine_roles']
                + [98] * (6 - len(actor['facts']['fine_roles']))):
            raise ValueError('role postimage readback differs')
    return dict(package=after, jug=result, eq=eq, ent=ent,
                selected_players=sorted(updates), selected_clubs=[], selected_managers=[])


def prepare(base, input_path):
    path = Path(input_path).resolve()
    request = p.read_json_file(path)
    _reconstruct(base, request)
    plan = dict(schema=SCHEMA, season=base.season, release_id=base.release_id,
                parent=request['parent'], source_input=dict(
                    path=r.relative_workspace_path(path), sha256=r.sha256_file(path)),
                package_sha256=r.sha256_file(base.package_path),
                jug_sha256=r.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI'), scope=SCOPE)
    plan['transaction_id'] = digest(packages.canonical_json_bytes(plan))[:24]
    return plan


def _outputs(plan):
    if plan.get('schema') != SCHEMA:
        raise ValueError('unsupported same-person role schema')
    path = _bound(plan['source_input'])
    base = r.load_registered_release(plan['season'], plan['release_id'])
    if prepare(base, path) != plan:
        raise ValueError('role plan does not reproduce')
    return _reconstruct(base, p.read_json_file(path))


def verify(base, plan):
    if (base.season, base.release_id) != (plan['season'], plan['release_id']):
        raise ValueError('role plan has another parent')
    _outputs(plan)


def bind(package, plan):
    if digest(packages.canonical_json_bytes(package)) != plan['package_sha256']:
        raise ValueError('role recipe parent differs')
    result = copy.deepcopy(_outputs(plan)['package'])
    result['artifacts'].append(dict(id=PREFIX + plan['transaction_id'], kind='season-input',
        relative_path=filename(plan), sha256=digest(packages.canonical_json_bytes(plan)),
        media_type='application/json'))
    result['artifacts'].sort(key=lambda a: a['id'])
    packages.validate_package(result)
    return result


def apply(jug, eq, plan):
    base = r.load_registered_release(plan['season'], plan['release_id'])
    out = _outputs(plan)
    before = ((base.game_path / 'DBDAT/JUG98030.FDI').read_bytes(), out['eq'])
    after = (out['jug'], out['eq'])
    if (jug, eq) not in (before, after):
        raise ValueError('role input is neither complete parent nor postimage')
    return after


def apply_ent(ent, plan):
    if ent != _outputs(plan)['ent']:
        raise ValueError('role edit cannot change managers')
    return ent


def apply_minifoto(archive, plan):
    base = r.load_registered_release(plan['season'], plan['release_id'])
    if archive != (base.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes():
        raise ValueError('role edit cannot change portraits')
    return archive, {}


def copy_new_inputs(workspace, plan):
    request = p.read_json_file(_bound(plan['source_input']))
    artifacts = {a.get('relative_path'): a for a in _outputs(plan)['package']['artifacts']}
    for row in request.get('new_recipe_artifacts', []):
        relative = Path(row['relative_path'])
        if (relative.is_absolute() or '..' in relative.parts
                or artifacts.get(str(relative), {}).get('sha256') != row['sha256']):
            raise ValueError('role artifact is not a confined child recipe input')
        target = Path(workspace) / relative
        if target.exists():
            raise ValueError('role artifact would overwrite an existing input')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_bound(row).read_bytes())


def reconstruction(previous, release_id, *, minimum_free_bytes=8 * 1024**3):
    from scripts import publish_historical_role_delta_v1 as publisher
    path = r.ROOT / previous.locator['sourced_profile_assignment_plan_path']
    plan = p.read_json_file(path)
    base = r.load_registered_release(plan['season'], plan['release_id'])
    verify(base, plan)
    receipt = p.read_json_file(previous.compiler_receipt_path)
    if (path.resolve() != (previous.package_path.parent / filename(plan)).resolve()
            or r.sha256_file(path) != receipt.get('original_profile_assignment_plan_sha256')
            or p.read_json_file(previous.package_path) != bind(p.read_json_file(base.package_path), plan)):
        raise ValueError('role SOURCE plan or recipe differs from reviewed inputs')
    publisher.publish(base.season, previous.package_path.parent / 'role-delta-input.json',
        release_id=release_id, source_release_id=base.release_id,
        profile_assignment_plan_path=path, minimum_free_bytes=minimum_free_bytes)
    child = r.load_registered_release(base.season, release_id)
    p.assert_tree_matches_inventory(child.game_path, p.read_json_file(previous.inventory_path))
    if child.package_path.read_bytes() != previous.package_path.read_bytes():
        raise ValueError('role SOURCE recipe bytes differ')
    return dict(complete_recipe_identical=True, complete_game_inventory_identical=True)
