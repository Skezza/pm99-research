"""Recipe-bound correction of copied seed exclusions, never foreign flags.

The original meaning of flag one is unknown. This policy applies only to
explicitly authored English mode-0 squads, not to native historical absences.
"""
import copy
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from scripts import season_package_compiler_v2
from scripts import season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_pipeline_v2 as pipeline
from scripts import season_package_v2 as packages
from app.fdi_indexed import IndexedFDIFile
from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.eq_roster_visibility import clear_authored_mode0_roster_exclusions

SCHEMA = 'pm99-authored-mode0-roster-visibility-layer-v1'
PREFIX = 'authored-roster-visibility-'
POLICY = 'clear-copied-seed-exclusions-in-explicitly-authored-English-squads-v1'
PILOT_IMAGE_SHA = '7fc45b01bfcc272095d67206222feaed6f41adf6031caa9848a29d366d68c939'


def native_rows(data, carrier):
    entries = [e for e in IndexedFDIFile.from_bytes(data).entries if e.record_id == carrier]
    if len(entries) != 1:
        raise ValueError('visibility layer requires one exact club')
    e = entries[0]
    roster = parse_eq_external_team_roster_payload(data[e.payload_offset:e.payload_offset+e.payload_length], {})
    if roster is None or roster.mode_byte != 0:
        raise ValueError('visibility layer is restricted to mode-0 clubs')
    return [(r.player_record_id, r.flag) for r in roster.rows]


def prepare(release, *, factory_path, pilot_path):
    eq = (release.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    factory = factory_path.read_bytes()
    if hashlib.sha256(factory).hexdigest() != 'e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c':
        raise ValueError('visibility correction requires the exact clean English factory')
    if not pilot_path.is_file() or registry.sha256_file(pilot_path) != PILOT_IMAGE_SHA:
        raise ValueError('exact visually reviewed actual-game exclusion evidence is missing or changed')
    clubs = []
    bindings = []
    for label, package, path in planner.package_layers(release):
        bindings.append({'layer': label, 'path': registry.relative_workspace_path(path),
                         'sha256': registry.sha256_file(path)})
        people = {p['id']: p for p in package['players']}
        for club in package['clubs']:
            if not club['id'].startswith('english-club-'):
                continue
            rows = native_rows(eq, club['carrier_id'])
            seed = native_rows(factory, club['carrier_id'])
            authored = {people[id]['carrier_id']: people[id] for id in club['roster_player_ids']}
            if set(authored) != {id for id, _ in rows}:
                raise ValueError('authored roster differs from native membership')
            changes = []
            for i, (id, flag) in enumerate(rows):
                if flag == 0:
                    continue
                if flag != 1 or i >= len(seed) or seed[i][1] != 1:
                    raise ValueError('exclusion is not an exact copied factory row flag')
                p = authored[id]
                changes.append({'player_id': p['id'], 'carrier_id': id,
                    'source_name': p.get('source_name') or p['name'],
                    'birth_date': p['facts'].get('birth_date'),
                    'declared_starter': p['id'] in club['opening']['starting_xi_player_ids'],
                    'copied_factory_row_index': i})
            if changes:
                clubs.append({'club_id': club['id'], 'carrier_id': club['carrier_id'],
                    'club_name': club['name'], 'expected_rows': [list(r) for r in rows], 'players': changes})
    return {'schema_version': SCHEMA, 'policy': POLICY, 'season': release.season,
        'source_release_id': release.release_id, 'package_sha256': registry.sha256_file(release.package_path),
        'eq_sha256': registry.sha256_file(release.game_path/'DBDAT/EQ98030.FDI'),
        'jug_sha256': registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI'),
        'recipe_layers': bindings, 'factory': {'path': registry.relative_workspace_path(factory_path),
            'sha256': hashlib.sha256(factory).hexdigest()},
        'runtime_control': {'path': registry.relative_workspace_path(pilot_path),
            'sha256': registry.sha256_file(pilot_path), 'scope': 'causal two-byte exclusion control, not full gameplay approval'},
        'clubs': clubs, 'historical_verification_complete': False}


def validate(layer):
    if layer.get('schema_version') != SCHEMA or layer.get('policy') != POLICY:
        raise ValueError('unsupported visibility layer policy')
    carriers = []
    for club in layer['clubs']:
        ids = [p['carrier_id'] for p in club['players']]
        rows = club['expected_rows']
        if (not club['club_id'].startswith('english-club-') or not ids or len(set(ids)) != len(ids)
                or len({id for id, _ in rows}) != len(rows)
                or any(flag not in (0, 1) for _, flag in rows)
                or set(ids) != {id for id, flag in rows if flag == 1}):
            raise ValueError('visibility layer contains an unbound exclusion')
        carriers.append(club['carrier_id'])
    if len(set(carriers)) != len(carriers):
        raise ValueError('duplicate visibility club carrier')


def apply(data, layer, *, exact_before=False):
    validate(layer)
    result, changes = data, []
    for club in layer['clubs']:
        rows = native_rows(result, club['carrier_id'])
        expected = [tuple(r) for r in club['expected_rows']]
        ids = {p['carrier_id'] for p in club['players']}
        if rows != expected and (exact_before or rows != [(id, 0 if id in ids else flag) for id, flag in expected]):
            raise ValueError('visibility layer native roster preimage changed')
        pending = [id for id, flag in rows if id in ids and flag == 1]
        if pending:
            result, written = clear_authored_mode0_roster_exclusions(result,
                club_record_id=club['carrier_id'], expected_rows=rows, player_record_ids=pending)
            changes.extend(asdict(x) for x in written)
    return result, changes


def verify_bound(release, layer):
    factory = registry.ROOT/layer['factory']['path']
    pilot = registry.ROOT/layer['runtime_control']['path']
    if registry.sha256_file(pilot) != layer['runtime_control']['sha256']:
        raise ValueError('visibility runtime control changed')
    if prepare(release, factory_path=factory, pilot_path=pilot) != layer:
        raise ValueError('visibility correction does not reproduce from exact current authored inputs')


def bind(package, layer):
    result = copy.deepcopy(package)
    identity = PREFIX+layer['season']
    descriptor = {'id': identity, 'kind': 'season-input', 'relative_path': 'roster-visibility.json',
        'sha256': hashlib.sha256(pipeline.canonical_json_bytes(layer)+b'\n').hexdigest(), 'media_type': 'application/json'}
    result['artifacts'] = sorted([a for a in result['artifacts'] if a['id'] != identity]+[descriptor], key=lambda a:a['id'])
    result['proofs'] = sorted([p for p in result['proofs'] if p['id'] != 'proof-'+identity]+[{
        'id': 'proof-'+identity, 'artifact_id': identity, 'grade': 'runtime-wine',
        'covers': ['bounded-authored-roster-visibility-policy-not-historical-certification']}], key=lambda p:p['id'])
    packages.validate_package(result)
    return result


def replay(eq_data, package, package_path):
    changes = []
    for artifact in package['artifacts']:
        if not artifact['id'].startswith(PREFIX):
            continue
        rel = Path(artifact['relative_path'])
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('unsafe visibility artifact path')
        path = package_path.parent/rel
        if registry.sha256_file(path) != artifact['sha256']:
            raise ValueError('visibility artifact hash changed')
        layer = json.loads(path.read_text())
        if layer['season'] != f"{package['season']['start_year']}-{str(package['season']['end_year'])[-2:]}":
            raise ValueError('visibility layer belongs to another season')
        eq_data, written = apply(eq_data, layer)
        changes.extend(written)
    return eq_data, changes
