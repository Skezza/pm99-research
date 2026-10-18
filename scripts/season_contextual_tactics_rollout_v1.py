#!/usr/bin/env python3
"""Deterministic, named-player tactics rollout; ambiguous native XIs are queued.

Uses the recipe's existing formation and player deployment ordering. It does
not invent a historical formation from primary player positions, rewrite JUG,
or change opaque foreign tactics. Candidates are not automatically registered.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'upstream/pm99-skezmod-db-editor')]
from app.eq_initial_tactics import GRID_BYTES, read_initial_tactics
from app.fdi_indexed import IndexedFDIFile
from scripts import season_contextual_tactics_v1 as tactics
from scripts import season_package_v2 as package_v2
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry

FORMATIONS = ('4-4-2', '4-3-3', '4-2-3-1', '4-1-4-1', '5-4-1', '5-3-2',
              '4-5-1', '5-2-3', '3-5-2', '3-4-3', '4-1-3-2', '4-4-1-1',
              '4-3-1-2', '3-4-1-2', '3-4-2-1', '3-1-4-2', '4-3-2-1', '4-1-2-1-2')
FACTORY_SHA = 'e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c'


def formation_template(formation):
    """Slots are right-to-left per formation line, not native player order."""
    if formation not in FORMATIONS:
        raise ValueError('formation has no reviewed contextual template: ' + formation)
    bands = [int(n) for n in formation.split('-')]
    defence = {
        3: [('RCB', 78, 100, 132), ('CB', 114, 95, 128), ('LCB', 150, 100, 132)],
        4: [('RB', 48, 105, 180), ('RCB', 89, 100, 135),
            ('LCB', 138, 100, 135), ('LB', 179, 105, 180)],
        5: [('RWB', 38, 120, 215), ('RCB', 78, 100, 135), ('CB', 114, 95, 128),
            ('LCB', 150, 100, 135), ('LWB', 190, 120, 215)],
    }[bands[0]]
    result = [(r, lane, dd, lane, ad) for r, lane, dd, ad in defence]
    middle = bands[1:-1]
    for index, count in enumerate(middle):
        if len(middle) == 1 or (index == 0 and count >= 3):
            dd, ad = 195, 275
            roles = {2: ['RCM', 'LCM'], 3: ['RCM', 'DM', 'LCM'], 4: ['RM', 'RCM', 'LCM', 'LM'],
                     5: ['RM', 'RCM', 'DM', 'LCM', 'LM']}[count]
        elif index == 0:
            dd, ad = 155, 210
            roles = ['DM'] * count
        elif formation == '4-1-2-1-2' and index == 1:
            dd, ad = 195, 275
            roles = ['RCM', 'LCM']
        else:
            dd, ad = (220, 280) if len(middle) == 3 and index == 1 else (240, 325)
            roles = {1: ['SS' if formation == '4-4-1-1' else 'AM'], 2: ['AM', 'AM'], 3: ['RW', 'AM', 'LW'],
                     4: ['RM', 'RCM', 'LCM', 'LM']}[count]
        lanes = {1: [114], 2: [94, 134], 3: [64, 114, 164],
                 4: [44, 94, 134, 184], 5: [38, 78, 114, 150, 190]}[count]
        # In a three-man central midfield, do not turn the two CMs into wingers.
        if count == 3 and roles == ['RCM', 'DM', 'LCM']:
            lanes = [84, 114, 144]
        for role, lane in zip(roles, lanes):
            wide = role in ('RM', 'LM', 'RW', 'LW')
            result.append((role, lane, 155 if role == 'DM' else dd, lane,
                           210 if role == 'DM' else ad + (20 if wide else 0)))
    count = bands[-1]
    front = {1: [('ST', 114)], 2: [('ST', 94), ('ST', 134)],
             3: [('RW', 64), ('ST', 114), ('LW', 164)]}[count]
    result.extend((role, lane, 280 if role != 'ST' else 300, lane,
                   345 if role != 'ST' else 370) for role, lane in front)
    if len(result) != 10:
        raise AssertionError('contextual template does not contain ten outfield slots')
    return [('GK', 114, 20, 114, 25)] + result


def movement_offsets(factory_data):
    if hashlib.sha256(factory_data).hexdigest() != FACTORY_SHA:
        raise ValueError('movement envelope needs the verified factory database')
    factory = read_initial_tactics(tactics.payloads(factory_data)[307])
    return [[sum(rows[z][c] - sum(s[c] for s in rows) // 20
                 for rows in factory.states[1:]) // 10 for c in range(4)] for z in range(20)]


def build_context(club, players, native_xi, offsets):
    opening = club['opening']
    ids = opening['starting_xi_player_ids']
    native_ids = [players[p]['carrier_id'] for p in ids]
    if len(set(native_ids)) != 11 or set(native_ids) != {n[0] for n in native_xi}:
        raise ValueError('recipe and native opening XI contain different players')
    if players[ids[0]]['facts']['primary_position'] != 'G' or native_xi[0][0] != native_ids[0]:
        raise ValueError('recipe/native goalkeeper identity is inconsistent')
    positions = opening['tactics_positions']
    template = formation_template(opening['formation'])
    # Existing coordinates identify membership of each formation line. Keep
    # players attached to those source deployments, including fullbacks whose
    # natural position is M. Ties crossing lines are not silently guessed.
    ordered = sorted(range(1, 11), key=lambda i: (positions[i][1], positions[i][0]))
    mapping = {native_ids[0]: template[0]}
    cursor = 0
    for count in map(int, opening['formation'].split('-')):
        selected = ordered[cursor:cursor + count]
        if cursor + count < 10 and positions[selected[-1]][1] == positions[ordered[cursor + count]][1]:
            raise ValueError('source deployment has an ambiguous formation-line boundary')
        selected.sort(key=lambda i: positions[i][0])
        if len({positions[i][0] for i in selected}) != len(selected):
            raise ValueError('source deployment has duplicate lateral positions in one line')
        for i, anchor in zip(selected, template[1 + cursor:1 + cursor + count]):
            mapping[native_ids[i]] = anchor
        cursor += count
    recipe_by_native = dict(zip(native_ids, ids))
    slots = []
    for native_id, name in native_xi:
        role, *anchor = mapping[native_id]
        scale = .15 if role == 'GK' else .45 if role in ('RCB', 'CB', 'LCB') else .65 if role == 'DM' else .8
        states = [[max(12 if c % 2 == 0 else 8, min(216 if c % 2 == 0 else 390,
                    anchor[c] + max(-18, min(18, round(offset[c] * scale)))))
                   for c in range(4)] for offset in offsets]
        if role == 'GK':
            states[0][3] = 0
        slots.append({'player_id': recipe_by_native[native_id], 'native_player_id': native_id,
                      'native_name': name, 'role': role, 'states': states})
    context = {'format': tactics.FORMAT, 'template_id': 'formation-' + opening['formation'] + '-contextual-v1',
               'slots': slots}
    audit_context(context)
    return context


def audit_context(context):
    tactics.validate_context(context)
    for slot in context['slots']:
        if slot['role'] != 'GK' and any(s[3] - s[1] < 20 for s in slot['states']):
            raise ValueError('outfield attack phase does not advance from defence')
        if len({tuple(s) for s in slot['states']}) == 1:
            raise ValueError('contextual slot has no ball-state movement')
    for state in range(20):
        for phase in (0, 2):
            points = [s['states'][state][phase:phase + 2] for s in context['slots']]
            for i, a in enumerate(points):
                for b in points[i + 1:]:
                    if sum((a[c] - b[c]) ** 2 for c in range(2)) < 16 ** 2:
                        raise ValueError('contextual formation has overlapping player markers')


def load_english(release, package):
    artifacts = [a for a in package.get('artifacts', []) if a['id'].startswith('english-contextual-package-')]
    if artifacts:
        if len(artifacts) != 1:
            raise ValueError('multiple English recipe inputs')
        artifact = artifacts[0]
        path = release.package_path.parent / artifact['relative_path']
        if registry.sha256_file(path) != artifact['sha256']:
            raise ValueError('English recipe input hash changed')
        return json.loads(path.read_text())
    return copy.deepcopy(package)


def prepare(season, output):
    release = registry.load_preferred_release(season)
    source_package = json.loads(release.package_path.read_text())
    english = load_english(release, source_package)
    players = {p['id']: p for p in english['players']}
    eq_path = release.game_path / 'DBDAT/EQ98030.FDI'
    eq, jug = eq_path.read_bytes(), (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    records = tactics.payloads(eq)
    jug_index = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    offsets = movement_offsets((ROOT / '.local/visual-qa-20261003/native-source/EQ98030.FDI').read_bytes())
    existing = {c['carrier_id']: c for l in tactics.package_layers(source_package, release.package_path) for c in l['clubs']}
    clubs, queue, reordered, preserved = [], [], [], []
    for club in sorted(english['clubs'], key=lambda c: c['carrier_id']):
        carrier = club['carrier_id']
        if records[carrier][0x29] != 0:
            continue
        try:
            xi = tactics.native_xi(records[carrier], jug, jug_index)
            if carrier in existing:
                row = copy.deepcopy(existing[carrier])
                if [(s['native_player_id'], s['native_name']) for s in row['context']['slots']] != xi:
                    raise ValueError('existing contextual layer native identity changed')
                preserved.append(carrier)
            else:
                context = build_context(club, players, xi, offsets)
                row = {'carrier_id': carrier, 'name': club['name'],
                       'formation': club['opening']['formation'], 'context': context,
                       'provenance': {'fixture_date': club['opening']['fixture_date'],
                                      'formation_source': club['opening']['proof'],
                                      'deployment_source': 'existing-recipe-opening-tactics-positions',
                                      'movement_policy': 'editorially-inferred-phase-anchors-centred-factory-envelope'}}
            ids = [s['player_id'] for s in row['context']['slots']]
            if ids != club['opening']['starting_xi_player_ids']:
                reordered.append({'carrier_id': carrier, 'old': club['opening']['starting_xi_player_ids'], 'native': ids})
                club['opening']['starting_xi_player_ids'] = ids
            club['opening']['tactics_context'] = row['context']
            club['opening']['tactics_positions'] = tactics.summary_positions(row['context'])
            clubs.append(row)
        except (ValueError, KeyError) as error:
            queue.append({'carrier_id': carrier, 'club': club['name'], 'reason': str(error)})
    if not clubs:
        raise ValueError('no unambiguous contextual tactics can be applied')
    layer = {'schema_version': tactics.SCHEMA, 'season': season,
             'provenance': {'source_package_sha256': registry.canonical_document_sha256(release.package_path),
                            'factory_eq_sha256': FACTORY_SHA,
                            'scope': 'English mode0 only; foreign mode1 preserved'}, 'clubs': clubs}
    after = tactics.apply_layer(eq, jug, layer)
    if tactics.apply_layer(after, jug, layer) != after:
        raise AssertionError('batch tactics layer is not byte-idempotent')
    changes, permitted = [], set()
    after_records = tactics.payloads(after)
    for entry in IndexedFDIFile.from_bytes(eq).entries:
        old, new = records[entry.record_id], after_records[entry.record_id]
        if old == new:
            continue
        if entry.record_id not in {c['carrier_id'] for c in clubs}:
            raise AssertionError('an unselected club changed')
        read = read_initial_tactics(old)
        allowed = range(entry.payload_offset + read.grid_offset, entry.payload_offset + read.grid_offset + GRID_BYTES)
        permitted.update(allowed)
        if read.controls != read_initial_tactics(new).controls:
            raise AssertionError('batch rollout changed tactics controls')
        changes.append(entry.record_id)
    differing = {i for i, (a, b) in enumerate(zip(eq, after)) if a != b}
    if len(eq) != len(after) or not differing <= permitted:
        raise AssertionError('batch tactics bytes escaped selected grids')
    # Merge existing contextual inputs instead of overlapping the Stoke pilot.
    package = copy.deepcopy(source_package)
    package['artifacts'] = [a for a in package['artifacts'] if not a['id'].startswith(
        (tactics.ARTIFACT_PREFIX, 'english-contextual-package-'))]
    output.mkdir(parents=True, exist_ok=False)
    pipeline.write_canonical_json(output / 'contextual-tactics.json', layer)
    english_path = output / 'english-season-package.json'
    english_path.write_bytes(package_v2.canonical_json_bytes(english))
    # English clubs in the main recipe use the one inline context, never both
    # inline and layered writes. The layer remains the durable world-2015 input.
    if any(c['carrier_id'] in {r['carrier_id'] for r in clubs} for c in package['clubs']):
        by_carrier = {c['carrier_id']: c for c in english['clubs']}
        for club in package['clubs']:
            if club['carrier_id'] in {c['carrier_id'] for c in clubs}:
                club['opening'] = copy.deepcopy(by_carrier[club['carrier_id']]['opening'])
    else:
        package['artifacts'].append({'id': tactics.ARTIFACT_PREFIX + season, 'kind': 'season-input',
            'sha256': registry.sha256_file(output / 'contextual-tactics.json'),
            'media_type': 'application/json', 'relative_path': 'contextual-tactics.json'})
    package['artifacts'].append({'id': 'english-contextual-package-' + season, 'kind': 'season-input',
        'sha256': registry.sha256_file(english_path), 'media_type': 'application/json',
        'relative_path': 'english-season-package.json'})
    package['artifacts'].sort(key=lambda a: a['id'])
    package_v2.validate_package(package)
    (output / 'season-package.json').write_bytes(package_v2.canonical_json_bytes(package))
    # Immutable upload inputs only; runner writes an independent installation.
    shutil.copytree(release.game_path / 'DBDAT', output / 'DBDAT', copy_function=os.link)
    temporary = output / 'EQ.partial'
    temporary.write_bytes(after)
    temporary.replace(output / 'DBDAT/EQ98030.FDI')
    receipt = {'schema_version': 'pm99-contextual-tactics-candidate-v1', 'season': season,
        'source_release_id': release.release_id, 'source_game_path': str(release.game_path),
        'source_package_path': str(release.package_path),
        'source_package_sha256': registry.canonical_document_sha256(release.package_path),
        'source_eq_sha256': hashlib.sha256(eq).hexdigest(), 'output_eq_sha256': hashlib.sha256(after).hexdigest(),
        'source_jug_sha256': hashlib.sha256(jug).hexdigest(), 'exe_path': str(release.game_path / 'MANAGPRE.EXE'),
        'changed_bytes': len(differing), 'changed_carriers': changes,
        'contextual_clubs': len(clubs), 'preserved_contextual_carriers': preserved,
        'native_order_recipe_alignment': reordered, 'editorial_queue': queue,
        'formations': sorted({c['formation'] for c in clubs}),
        'byte_idempotent': True, 'all_controls_preserved': True,
        'foreign_records_preserved': True, 'registered': False, 'runtime_proven': False}
    pipeline.write_canonical_json(output / 'candidate-receipt.json', receipt)
    if eq_path.read_bytes() != eq:
        raise AssertionError('source release changed during candidate authoring')
    return receipt


def audit_candidate(output):
    """Independent readback of a frozen candidate; never rebuild on failure."""
    receipt = json.loads((output / 'candidate-receipt.json').read_text())
    release = registry.load_registered_release(receipt['season'], receipt['source_release_id'])
    source = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    actual = (output / 'DBDAT/EQ98030.FDI').read_bytes()
    if (release.release_id != receipt['source_release_id'] or
            registry.canonical_document_sha256(release.package_path) != receipt['source_package_sha256'] or
            hashlib.sha256(source).hexdigest() != receipt['source_eq_sha256'] or
            hashlib.sha256(jug).hexdigest() != receipt['source_jug_sha256'] or
            hashlib.sha256(actual).hexdigest() != receipt['output_eq_sha256'] or
            (output / 'DBDAT/JUG98030.FDI').read_bytes() != jug):
        raise ValueError('frozen tactics candidate/source database binding changed')
    layer = json.loads((output / 'contextual-tactics.json').read_text())
    if layer['season'] != receipt['season']:
        raise ValueError('candidate layer season changed')
    if tactics.apply_layer(source, jug, layer) != actual or tactics.apply_layer(actual, jug, layer) != actual:
        raise ValueError('candidate layer does not reproduce exact, idempotent database bytes')
    before, after = tactics.payloads(source), tactics.payloads(actual)
    permitted = set()
    for entry in IndexedFDIFile.from_bytes(source).entries:
        if entry.record_id not in {c['carrier_id'] for c in layer['clubs']}:
            if before[entry.record_id] != after[entry.record_id]:
                raise ValueError('unselected or foreign club record changed')
            continue
        old = read_initial_tactics(before[entry.record_id])
        new = read_initial_tactics(after[entry.record_id])
        if old.controls != new.controls:
            raise ValueError('rollout changed protected controls')
        permitted.update(range(entry.payload_offset + old.grid_offset,
                               entry.payload_offset + old.grid_offset + GRID_BYTES))
    differences = {i for i, (a, b) in enumerate(zip(source, actual)) if a != b}
    if len(source) != len(actual) or not differences <= permitted:
        raise ValueError('rollout changed bytes outside selected tactics grids')
    english = json.loads((output / 'english-season-package.json').read_text())
    package = json.loads((output / 'season-package.json').read_text())
    package_v2.validate_package(english)
    package_v2.validate_package(package)
    artifact = next(a for a in package['artifacts'] if a['id'] == 'english-contextual-package-' + receipt['season'])
    if registry.sha256_file(output / 'english-season-package.json') != artifact['sha256']:
        raise ValueError('English candidate recipe artifact hash changed')
    tactics.package_layers(package, output / 'season-package.json')
    by_carrier = {c['carrier_id']: c for c in english['clubs']}
    for row in layer['clubs']:
        context = row['context']
        audit_context(context)
        opening = by_carrier[row['carrier_id']]['opening']
        if (opening.get('tactics_context') != context or opening['tactics_positions'] != tactics.summary_positions(context)
                or opening['starting_xi_player_ids'] != [s['player_id'] for s in context['slots']]):
            raise ValueError('named candidate recipe differs from frozen tactics layer')
        if read_initial_tactics(after[row['carrier_id']]).states != tuple(
                tuple(tuple(s) for s in slot['states']) for slot in context['slots']):
            raise ValueError('native full-grid readback differs from named recipe')
    return {'season': receipt['season'], 'success': True, 'contextual_clubs': len(layer['clubs']),
            'blocked_clubs': len(receipt['editorial_queue']), 'changed_bytes': len(differences),
            'coordinate_values_read_back': len(layer['clubs']) * 880,
            'outside_grid_bytes_preserved': True, 'players_and_controls_preserved': True,
            'byte_idempotent': True, 'registered': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season')
    parser.add_argument('output', type=Path)
    parser.add_argument('--audit', action='store_true')
    args = parser.parse_args()
    rows = []
    seasons = registry.supported_seasons() if args.season == 'all' else [args.season]
    for season in seasons:
        destination = (args.output / season / 'english-rollout-candidate-v1'
                       if args.season == 'all' else args.output).resolve()
        if args.audit:
            row = audit_candidate(destination)
            rows.append(row)
            print(json.dumps(row), flush=True)
            continue
        if destination.exists():
            report = json.loads((destination / 'candidate-receipt.json').read_text())
            release = registry.load_preferred_release(season)
            expected = (report['source_release_id'], report['source_package_sha256'],
                        report['source_eq_sha256'], report['source_jug_sha256'], report['output_eq_sha256'])
            actual = (release.release_id, registry.canonical_document_sha256(release.package_path),
                      registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'),
                      registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
                      registry.sha256_file(destination / 'DBDAT/EQ98030.FDI'))
            if expected != actual:
                raise ValueError('existing candidate/source hash drift; never silently regenerate')
            resumed = True
        else:
            report = prepare(season, destination)
            resumed = False
        row = {k: report[k] for k in ('season', 'contextual_clubs', 'changed_bytes', 'formations', 'registered')}
        row.update({'candidate': registry.relative_workspace_path(destination),
                    'blocked_clubs': len(report['editorial_queue']), 'resumed': resumed})
        rows.append(row)
        print(json.dumps(row), flush=True)
        if args.season == 'all':
            matrix_path = args.output / ('rollout-matrix-through-' + season + '-v1.json')
            # Progress snapshots are immutable. Resume keeps old evidence and
            # verifies each existing candidate instead of rebuilding it.
            if matrix_path.exists():
                continue
            pipeline.write_canonical_json(matrix_path, {
                'schema_version': 'pm99-contextual-tactics-rollout-matrix-v1',
                'scope': 'offline candidates, not registered or runtime-proven releases', 'seasons': rows})
    if args.audit and args.season == 'all':
        pipeline.write_canonical_json(args.output / 'rollout-offline-audit-v1.json', {
            'schema_version': 'pm99-contextual-tactics-rollout-audit-v1', 'success': all(r['success'] for r in rows),
            'scope': 'independent offline readback only; not runtime or publication proof', 'seasons': rows})


if __name__ == '__main__':
    main()
