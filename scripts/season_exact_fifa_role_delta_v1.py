"""Exact target-edition FIFA role corrections; never infer historical ownership.

Only authored main-layer players with full published names and literal DOBs
are eligible. Existing English2015 custom roles, all skills and EQ tactics stay
untouched. Role updates are six bounded native bytes, not profile recompiles.
"""
import copy
import csv
from datetime import date
from functools import lru_cache
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles, rewrite_indexed_native_roles
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_package_v2 as packages, season_historical_roster_audit_v1 as roster
from scripts import season_rating_calibration_v3 as identity
from scripts.season_historical_role_plan_v1 import ROLE_MAP

SCHEMA = 'pm99-exact-target-FIFA-six-role-only-delta-v1'
PREFIX = 'source-bound-exact-fifa-roles-'
MODE = 'known-good-baseline-exact-target-FIFA-role-only-v1'


def digest(value):
    return identity.old.sha(value)


def filename(plan):
    return 'exact-FIFA-roles-' + plan['transaction_id'] + '.json'


def names(player):
    result = set()
    for name in (player.get('source_name', ''), player.get('name', '')):
        if not isinstance(name, str):
            continue
        if len(identity.tokens(name)) >= 2 and all(len(t) > 1 for t in identity.tokens(name)):
            result.add(name)
        if name.count(',') == 1:
            family, given = (part.strip() for part in name.split(','))
            if family and given and all(len(t) > 1 for t in identity.tokens(given + ' ' + family)):
                result.add(given + ' ' + family)
    return result


@lru_cache(maxsize=2)
def index(file_sha):
    result = {}
    with identity.old.FIFA.open(newline='') as stream:
        for row in csv.DictReader(stream):
            key = (int(row['fifa_version']), row['dob'])
            result.setdefault(key, []).append({k: row[k] for k in
                ('player_id', 'dob', 'long_name', 'short_name', 'player_positions', 'fifa_update_date')})
    return result


def match(player, season, source):
    edition = int(season[:4]) - 1999
    birth = player['facts'].get('birth_date')
    if not 15 <= edition <= 23 or not isinstance(birth, str):
        return None
    alternatives = names(player)
    hits = {}
    for row in source.get((edition, birth), []):
        if any(roster.normalise(n) in (roster.normalise(row['long_name']), roster.normalise(row['short_name']))
               or identity.subsequence(identity.tokens(n), identity.tokens(row['long_name'])) for n in alternatives):
            hits.setdefault(row['player_id'], []).append(row)
    if len(hits) != 1:
        return None
    rows = next(iter(hits.values()))
    # Multiple updates must not silently overwrite contradictory role records.
    if len({r['player_positions'] for r in rows}) != 1:
        return None
    return min(rows, key=lambda r: r['fifa_update_date'])


def compatible(position, role):
    if not isinstance(position, str):
        return False
    return role in {'G': {0}, 'D': {1, 2, 3, 4, 5},
        'M': {6, 7, 9, 10, 11, 13, 14}, 'F': {8, 11, 12, 13, 15, 16}}.get(position, set())


def prepare(base):
    edition = int(base.season[:4]) - 1999
    if not 15 <= edition <= 23:
        raise ValueError('no exact cached target FIFA edition; no future/past role substitution')
    package = pipeline.read_json_file(base.package_path)
    file_sha = registry.sha256_file(identity.old.FIFA)
    source = index(file_sha)
    raw = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(raw).entries}
    updates, skipped = [], {}
    for player in package['players']:
        if player.get('policy') == 'preserve-existing-mode1':
            continue
        row = match(player, base.season, source)
        if row is None:
            continue
        labels = [s.strip() for s in row['player_positions'].split(',')]
        if not labels or any(s not in ROLE_MAP for s in labels):
            raise ValueError('unrecognised exact-source role taxonomy')
        roles = list(dict.fromkeys(ROLE_MAP[s] for s in labels))[:6]
        if not compatible(player['facts'].get('primary_position'), roles[0]):
            skipped['primary-class-needs-separate-source-review'] = skipped.get('primary-class-needs-separate-source-review', 0) + 1
            continue
        carrier = player['carrier_id']
        payload = entries[carrier].decode_payload(raw)
        native = roster.native_player(payload, carrier)
        _, old = read_indexed_native_roles(payload, carrier)
        end = native['name_end']
        try:
            born = date(int.from_bytes(bytes(b ^ 0x61 for b in payload[end+14:end+16]), 'little'),
                        payload[end+13] ^ 0x61, payload[end+12] ^ 0x61).isoformat()
        except ValueError:
            skipped['invalid-native-birthday-not-guessed'] = skipped.get('invalid-native-birthday-not-guessed', 0) + 1
            continue
        if (native['position'] != player['facts']['primary_position'] or born != player['facts']['birth_date']
                or roster.normalise(native['name']) != roster.normalise(player['name'])):
            skipped['native-identity-or-primary-preimage-needs-review'] = skipped.get('native-identity-or-primary-preimage-needs-review', 0) + 1
            continue
        declared = player['facts'].get('fine_roles')
        active = [r for r in old if r != 98]
        if active == roles and declared == roles:
            continue
        updates.append(dict(carrier_id=carrier, player_id=player['id'], name=player['name'],
            before_player_sha256=digest(player), before_native_roles=old, fine_roles=roles,
            source=dict(row, edition=edition)))
    doc = dict(schema=SCHEMA, season=base.season, release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),
        jug_sha256=registry.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI'),
        source_bindings=[dict(path=registry.relative_workspace_path(p), sha256=registry.sha256_file(p))
            for p in (identity.old.FIFA, registry.ROOT / 'scripts/season_exact_fifa_role_delta_v1.py',
                      registry.ROOT / 'scripts/season_rating_calibration_v3.py',
                      registry.ROOT / 'scripts/season_historical_role_plan_v1.py')],
        updates=updates, skipped=skipped,
        scope='Only declared main-player six fine-role bytes and matching recipe fine_roles; all ten skills, broad position, names, dates, countries, ownership, opening orders, tactics, managers, assets and EXE preserved. Not August ownership or all-position approval.')
    doc['transaction_id'] = digest(doc)[:24]
    return doc


def verify(base, plan):
    if plan.get('schema') != SCHEMA or packages.canonical_json_bytes(prepare(base)) != packages.canonical_json_bytes(plan):
        raise ValueError('exact FIFA source/preimage/role plan changed')


def bind(package, plan):
    result = copy.deepcopy(package)
    people = {p['carrier_id']: p for p in result['players']}
    for row in plan['updates']:
        player = people[row['carrier_id']]
        if digest(player) != row['before_player_sha256']:
            raise ValueError('role-only player preimage changed')
        player['facts']['fine_roles'] = list(row['fine_roles'])
    aid = PREFIX + plan['transaction_id']
    result['artifacts'].append(dict(id=aid, kind='season-input', relative_path=filename(plan),
        sha256=digest(plan), media_type='application/json'))
    result['proofs'].append(dict(id='proof-' + aid, grade='source-receipt', artifact_id=aid,
        covers=['exact-target-FIFA-identity-DOB-fine-role-mapping-not-opening-membership']))
    for key in ('artifacts', 'proofs'):
        result[key].sort(key=lambda r: r['id'])
    packages.validate_package(result)
    return result


def apply(jug, eq, plan):
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    original = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    if registry.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI') != plan['jug_sha256'] or eq != (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes():
        raise ValueError('role-only native/EQ baseline changed')
    selected = {r['carrier_id']: r['fine_roles'] for r in plan['updates']}
    if len(selected) != len(plan['updates']):
        raise ValueError('ambiguous role-only carrier')
    actual, _ = rewrite_indexed_native_roles(original, selected)
    if jug not in (original, actual):
        raise ValueError('role-only input is neither exact whole preimage nor postimage')
    return actual, eq


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts', [])):
        raise ValueError('exact role-only layer requires source-bound reconstruction, not factory recompilation')


def reconstruction(previous, release_id):
    relative = previous.locator.get('sourced_profile_assignment_plan_path')
    if not relative:
        return None
    path = registry.ROOT / relative
    plan = pipeline.read_json_file(path)
    if plan.get('schema') != SCHEMA:
        return None
    from scripts import publish_historical_role_delta_v1 as publisher
    base = registry.load_registered_release(previous.season, plan['release_id'])
    verify(base, plan)
    package = pipeline.read_json_file(previous.package_path)
    if bind(pipeline.read_json_file(base.package_path), plan) != package:
        raise ValueError('role SOURCE would discard recipe edits')
    artifact = next(a for a in package['artifacts'] if a['id'] == PREFIX + plan['transaction_id'])
    if path.resolve() != (previous.package_path.parent / filename(plan)).resolve() or registry.sha256_file(path) != artifact['sha256']:
        raise ValueError('role SOURCE artifact path/hash differs')
    for release in (base, previous):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    descriptor = previous.package_path.parent / 'role-delta-input.json'
    if pipeline.read_json_file(descriptor) != dict(season=base.season, release_id=base.release_id,
            package_sha256=plan['package_sha256'], jug_sha256=plan['jug_sha256'], updates=[], unresolved=[]):
        raise ValueError('role SOURCE inert descriptor differs')
    publisher.publish(previous.season, descriptor, release_id=release_id,
        source_release_id=base.release_id, profile_assignment_plan_path=path)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path) != package:
        raise ValueError('role SOURCE complete recipe differs')
    return dict(season=previous.season, release_id=release_id,
        complete_game_inventory_identical=True, complete_recipe_identical=True)
