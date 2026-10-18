"""Explicit original-annual plus exact-edition FIFA broad/fine role repairs.

Not an ownership policy. Target names/DOBs must match exclusive native actors;
all dated annual witnesses must agree with the exact edition's first role.
V2 also bridges exact published names omitting middle names, but only through
an unambiguous exact-edition FIFA full-name/DOB identity. V1 remains immutable.
No fallback roles, goalkeeper conversions, source-side guesses or skill edits.
"""
import copy
from datetime import date
import hashlib

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import rewrite_indexed_native_roles
from app.xor import xor_encode
from scripts import season_exact_fifa_role_delta_v1 as fifa
from scripts import season_exact_fifa_role_delta_v2 as conservative
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_package_v2 as packages, season_package_compiler_v2 as compiler
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_opening_order_repair_v1 as owners

SCHEMA = 'pm99-explicit-original-annual-exact-FIFA-broad-and-fine-position-v2'
PREFIX = 'source-bound-exact-primary-position-v2-'
MODE = 'known-good-baseline-original-annual-exact-FIFA-primary-position-v2'
digest = fifa.digest


def filename(plan):
    return 'exact-primary-position-' + plan['transaction_id'] + '.json'


def primary(position):
    if position in ('RB', 'RWB', 'LB', 'LWB', 'SW', 'CB'):
        return 'D'
    if position in ('RM', 'CM', 'CAM', 'LM', 'CDM'):
        return 'M'
    if position in ('CF', 'RW', 'ST', 'LW', 'RF', 'LF'):
        return 'F'
    raise ValueError('unsupported or goalkeeper broad-position conversion')


def annual_person_names(player, row):
    """No fuzzy annual lookup: exact names linked by one exact-edition person."""
    from scripts.season_number_label_names_v2 import undecorated
    full = fifa.identity.tokens(row['long_name'])
    result = {roster.normalise(row['long_name'])}
    for published in fifa.names(player):
        name = undecorated(published)
        tokens = fifa.identity.tokens(name)
        if (len(tokens) >= 2 and all(len(t) > 1 for t in tokens)
                and fifa.identity.subsequence(tokens, full)):
            result.add(roster.normalise(name))
    return result


def prepare(base, targets):
    if (not targets or len(targets) != len(set(targets))
            or any(isinstance(n, bool) or not isinstance(n, int) or n < 1 for n in targets)):
        raise ValueError('explicit unique integer target carriers required')
    package = pipeline.read_json_file(base.package_path)
    players = {p['carrier_id']: p for p in package['players']}
    clubs = {c['id']: c for c in package['clubs']}
    data = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(data).entries}
    ownership = owners.native_owners(eq)
    fifa_path = fifa.identity.old.FIFA
    fifa_hash = registry.sha256_file(fifa_path)
    index = fifa.index(fifa_hash)
    captures, source_bindings = roster.load_sources(base.season)
    verifier = roster.SourceVerifier(base.season)
    updates = []
    for carrier in sorted(targets):
        player = players[carrier]
        if player.get('policy') == 'preserve-existing-mode1':
            raise ValueError('whole-record fallback is not an authored position target')
        row = fifa.match(player, base.season, index)
        if row is None:
            raise ValueError('target has no unambiguous exact-edition name/DOB/role witness')
        labels = row['player_positions'].split(', ')
        if not labels or any(label not in fifa.ROLE_MAP for label in labels):
            raise ValueError('unsupported exact-edition role labels')
        broad = primary(labels[0])
        roles = list(dict.fromkeys(fifa.ROLE_MAP[label] for label in labels))[:6]
        payload = entries[carrier].decode_payload(data)
        native = roster.native_player(payload, carrier)
        end = native['name_end']
        birthday = date(int.from_bytes(bytes(v ^ 0x61 for v in payload[end+14:end+16]), 'little'),
                        payload[end+13] ^ 0x61, payload[end+12] ^ 0x61).isoformat()
        if (payload[2:5] != bytes.fromhex('dd6361')
                or ownership.get(carrier) != {clubs[player['club_id']]['carrier_id']}
                or roster.normalise(native['name']) != roster.normalise(player['name'])
                or birthday != player['facts']['birth_date'] or birthday != row['dob']
                or native['position'] != player['facts']['primary_position']
                or native['position'] in ('G', broad)):
            raise ValueError('target broad position/native name/DOB/exclusive ownership preimage differs')
        witnesses = []
        values = set()
        accepted_annual_names = annual_person_names(player, row)
        for capture in captures:
            matching = [p for p in capture['players']
                if roster.normalise(p['name']) in accepted_annual_names
                and p.get('birth_date') == birthday]
            if not matching:
                continue
            proof = verifier.verify(capture)
            if proof['status'] != 'raw-source-reparsed':
                raise ValueError('matching annual position source not independently reparsed')
            if len(matching) != 1:
                raise ValueError('matching annual full-name/DOB identity is ambiguous')
            values.add(matching[0].get('position'))
            witnesses.append(dict(source_club=capture['club_name'], player=matching[0], original=proof,
                                  approves_opening_club_membership=False,
                                  name_bridge=dict(policy='exact-published-name-DOB-unambiguous-target-FIFA-person-v2',
                                      fifa_player_id=row['player_id'], fifa_full_name=row['long_name'],
                                      annual_literal_name=matching[0]['name'], birth_date=birthday)))
        if values != {broad} or not witnesses:
            raise ValueError('exact-edition broad position lacks unanimous original dated annual corroboration')
        roles = conservative.preserve_cb_side(dict(fine_roles=roles,
            before_native_roles=native['roles'], source=row))
        updates.append(dict(carrier_id=carrier, before_player=player, before_native=native,
            primary_position=broad, fine_roles=roles, source=row, dated_annuals=witnesses))
    plan = dict(schema=SCHEMA, season=base.season, release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path), jug_sha256=registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),
        eq_sha256=registry.sha256_file(base.game_path/'DBDAT/EQ98030.FDI'), targets=sorted(targets), updates=updates,
        source_bindings=source_bindings, implementation_inputs=[dict(path=registry.relative_workspace_path(p),
            sha256=registry.sha256_file(p)) for p in (fifa_path, registry.ROOT/'scripts/season_exact_primary_position_delta_v2.py',
                registry.ROOT/'scripts/season_exact_fifa_role_delta_v1.py', registry.ROOT/'scripts/season_exact_fifa_role_delta_v2.py',
                registry.ROOT/'upstream/pm99-skezmod-db-editor/app/models.py')],
        scope='Only explicit dd6361 profile broad-position byte at name_end+11 and six fine-role bytes plus matching recipe fields. The adjacent +10 is preserve-only, not assumed a second position byte. Preserve names/DOB/country/skills/owners/orders/EQ tactics/coaches/assets. Annual/FIFA evidence does not approve August ownership or tactical coordinates.')
    plan['transaction_id'] = digest(plan)[:24]
    return plan


def verify(base, plan):
    if plan.get('schema') != SCHEMA or prepare(base, plan['targets']) != plan:
        raise ValueError('exact primary-position original inputs/preimage did not reproduce')


def bind(package, plan):
    if plan.get('schema') != SCHEMA:
        raise ValueError('primary-position recipe schema differs')
    result = copy.deepcopy(package)
    for row in plan['updates']:
        player = next(p for p in result['players'] if p['carrier_id'] == row['carrier_id'])
        if player != row['before_player']:
            raise ValueError('primary-position exact player recipe preimage differs')
        player['facts'].update(primary_position=row['primary_position'], fine_roles=row['fine_roles'])
        if 'fact_fallbacks' in player:
            player['fact_fallbacks'] = [f for f in player['fact_fallbacks']
                                      if f['field'] not in ('primary_position', 'fine_roles')]
    result['artifacts'].append(dict(id=PREFIX+plan['transaction_id'], kind='season-input',
        relative_path=filename(plan), sha256=digest(plan), media_type='application/json'))
    result['artifacts'].sort(key=lambda a: a['id'])
    packages.validate_package(result)
    return result


def apply(jug, eq, plan):
    if plan.get('schema') != SCHEMA or not plan.get('updates'):
        raise ValueError('nonempty exact primary-position schema required')
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    before = (base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    if registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI') != plan['jug_sha256'] or hashlib.sha256(eq).hexdigest() != plan['eq_sha256']:
        raise ValueError('primary-position whole native preimage changed')
    patched, _ = rewrite_indexed_native_roles(before, {r['carrier_id']: r['fine_roles'] for r in plan['updates']})
    result = bytearray(patched)
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(before).entries}
    for row in plan['updates']:
        entry = entries[row['carrier_id']]
        end = row['before_native']['name_end']
        code = compiler.POSITION[row['primary_position']]
        result[entry.payload_offset+end+11] = xor_encode(bytes([code ^ 0x61]))[0]
    result = bytes(result)
    allowed = {entries[row['carrier_id']].payload_offset + row['before_native']['name_end'] + offset
               for row in plan['updates'] for offset in (*range(2, 8), 11)}
    if len(result) != len(before) or any(a != b and i not in allowed for i, (a, b) in enumerate(zip(before, result))):
        raise ValueError('primary-position patch changes another native field')
    if jug not in (before, result):
        raise ValueError('primary-position input is neither exact whole preimage nor postimage')
    return result, eq


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts', [])):
        raise ValueError('primary-position recipe needs exact SOURCE replay, not factory recompilation')


def reconstruction(previous, release_id):
    relative = previous.locator.get('sourced_profile_assignment_plan_path')
    if not relative:
        return None
    path = registry.ROOT/relative
    plan = pipeline.read_json_file(path)
    if plan.get('schema') != SCHEMA:
        return None
    base = registry.load_registered_release(previous.season, plan['release_id'])
    verify(base, plan)
    if bind(pipeline.read_json_file(base.package_path), plan) != pipeline.read_json_file(previous.package_path):
        raise ValueError('primary-position SOURCE would discard recipe edits')
    package = pipeline.read_json_file(previous.package_path)
    artifact = next(a for a in package['artifacts'] if a['id'] == PREFIX+plan['transaction_id'])
    if artifact['sha256'] != registry.sha256_file(path) or path.resolve() != (previous.package_path.parent/filename(plan)).resolve():
        raise ValueError('primary-position SOURCE original local plan artifact differs')
    descriptor = previous.package_path.parent/'role-delta-input.json'
    if pipeline.read_json_file(descriptor) != dict(season=base.season, release_id=base.release_id,
            package_sha256=plan['package_sha256'], jug_sha256=plan['jug_sha256'], updates=[], unresolved=[]):
        raise ValueError('primary-position SOURCE baseline descriptor differs')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season, descriptor,
        release_id=release_id, source_release_id=base.release_id, profile_assignment_plan_path=path)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes() != previous.package_path.read_bytes():
        raise ValueError('primary-position SOURCE whole recipe differs')
    return dict(season=previous.season, complete_game_inventory_identical=True, complete_recipe_identical=True)
