#!/usr/bin/env python3
"""Identity-bound, contextual mode-0 tactics; never a foreign-team guess.

Coordinates are pitch pixels, not the old misaligned on-disk words. A layer
contains every one of the twenty states for both phases of each named XI slot.
It can be reapplied byte-identically after unrelated recipe changes. Historical
formation/player sources and inferred tactical movement are kept distinct.
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
from app.eq_initial_tactics import FORMAT, GRID_BYTES, patch_indexed_tactics, read_initial_tactics, validate_states
from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.fdi_indexed import IndexedFDIFile
from app.editor_actions import _indexed_variable_name_runtime_segments
from scripts import season_package_v2 as package_v2
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry

SCHEMA = 'pm99-contextual-tactics-layer-v1'
ARTIFACT_PREFIX = 'contextual-tactics-'
PILOT_ROLES = ('GK', 'RCB', 'LCB', 'LB', 'RB', 'DM', 'RCM', 'LCM', 'LW', 'RW', 'ST')
ROLES = PILOT_ROLES + ('CB', 'RWB', 'LWB', 'CM', 'RM', 'LM', 'AM', 'SS')


def payloads(data):
    index = IndexedFDIFile.from_bytes(data)
    return {e.record_id: data[e.payload_offset:e.payload_offset + e.payload_length] for e in index.entries}


def native_xi(eq_payload, jug_data, by_id=None):
    if by_id is None:
        index = IndexedFDIFile.from_bytes(jug_data)
        by_id = {e.record_id: e for e in index.entries}
    roster = parse_eq_external_team_roster_payload(eq_payload, {})
    if roster is None:
        raise ValueError('unreadable native tactics roster')
    starters = {}
    for row in roster.rows:
        pid = row.player_record_id
        if pid not in by_id:
            raise ValueError('tactics roster references absent native player')
        decoded = by_id[pid].decode_payload(jug_data)
        parts = _indexed_variable_name_runtime_segments(decoded)
        end = parts['full_name_end']
        order = decoded[end] ^ 0x61
        if 1 <= order <= 11:
            if order in starters:
                raise ValueError('ambiguous native opening XI order')
            starters[order] = (pid, decoded[parts['full_name_start']:end].decode('cp1252'))
    if set(starters) != set(range(1, 12)):
        raise ValueError('native opening XI lacks eleven ordered players')
    return [starters[i] for i in range(1, 12)]


def validate_context(context, expected_player_ids=None):
    if context.get('format') != FORMAT:
        raise ValueError('unsupported contextual tactics format')
    slots = context.get('slots', [])
    if any(not isinstance(s, dict) or not isinstance(s.get('player_id'), str) or
           type(s.get('native_player_id')) is not int or s['native_player_id'] < 1 or
           not isinstance(s.get('native_name'), str) or not s['native_name'] for s in slots):
        raise ValueError('tactics slots require explicit recipe and native player identities')
    if len(slots) != 11 or len({s['player_id'] for s in slots}) != 11:
        raise ValueError('contextual tactics need eleven unique named slots')
    if expected_player_ids is not None and [s['player_id'] for s in slots] != expected_player_ids:
        raise ValueError('contextual tactics slot IDs differ from opening XI order')
    if any(s.get('role') not in ROLES for s in slots):
        raise ValueError('unsupported explicit deployment role')
    if [s['role'] for s in slots].count('GK') != 1 or slots[0]['role'] != 'GK':
        raise ValueError('contextual tactics require goalkeeper in slot one')
    validate_states([s['states'] for s in slots])
    if slots[0]['states'][0][3] != 0:
        raise ValueError('native first goalkeeper attack depth must remain zero')


def summary_positions(context):
    validate_context(context)
    return [[sum(state[c] for state in slot['states']) // 20 for c in range(4)]
            for slot in context['slots']]


def apply_layer(eq_data, jug_data, layer):
    if layer.get('schema_version') != SCHEMA or not layer.get('clubs'):
        raise ValueError('invalid contextual tactics layer')
    records = payloads(eq_data)
    jug_index = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug_data).entries}
    replacements, control_repairs = {}, {}
    for club in layer['clubs']:
        carrier = club['carrier_id']
        if type(carrier) is not int or carrier in replacements or carrier not in records:
            raise ValueError('duplicate or absent tactics club carrier')
        context = club['context']
        validate_context(context)
        xi = native_xi(records[carrier], jug_data, jug_index)
        if [(s['native_player_id'], s['native_name']) for s in context['slots']] != xi:
            raise ValueError('tactics identity does not match actual native opening XI')
        replacements[carrier] = [slot['states'] for slot in context['slots']]
        if 'restore_control_prefix' in club:
            controls = club['restore_control_prefix']
            if len(controls) != 2 or any(type(v) is not int or not 0 <= v <= 255 for v in controls):
                raise ValueError('invalid explicitly evidenced control repair')
            # The original Stoke pilot predates the explicit preimage field.
            # Its only permitted old value is the measured shifted-writer
            # corruption, not an arbitrary later user's control settings.
            before = club.get('control_prefix_before', [159, 1])
            if len(before) != 2 or any(type(v) is not int or not 0 <= v <= 255 for v in before):
                raise ValueError('invalid control repair preimage')
            current = read_initial_tactics(records[carrier]).controls[:2]
            if current not in (bytes(before), bytes(controls)):
                raise ValueError('control repair would overwrite unrelated control settings')
            control_repairs[carrier] = bytes(controls)
    output = bytearray(patch_indexed_tactics(eq_data, replacements))
    index = IndexedFDIFile.from_bytes(eq_data)
    for entry in index.entries:
        if entry.record_id in control_repairs:
            offset = entry.payload_offset + read_initial_tactics(records[entry.record_id]).grid_offset + GRID_BYTES
            output[offset:offset + 2] = control_repairs[entry.record_id]
    return bytes(output)


def package_layers(package, package_path):
    """Read only recipe-local, hash-verified contextual inputs, in stable order."""
    layers = []
    seen = set()
    for artifact in sorted(package.get('artifacts', []), key=lambda a: a['id']):
        if not artifact['id'].startswith(ARTIFACT_PREFIX):
            continue
        relative = Path(artifact.get('relative_path', ''))
        if not relative.parts or relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe contextual tactics artifact path')
        raw = (package_path.parent / relative).read_bytes()
        if hashlib.sha256(raw).hexdigest() != artifact['sha256']:
            raise ValueError('contextual tactics input hash differs')
        layer = json.loads(raw)
        expected = f"{package['season']['start_year']}-{str(package['season']['end_year'])[-2:]}"
        if layer.get('season') != expected:
            raise ValueError('contextual tactics input belongs to another season')
        for club in layer['clubs']:
            if club['carrier_id'] in seen:
                raise ValueError('multiple tactics layers target the same carrier')
            seen.add(club['carrier_id'])
        layers.append(layer)
    return layers


def build_stoke_layer(english, english_sha, eq_data, jug_data, factory_data):
    club = next(c for c in english['clubs'] if c['carrier_id'] == 307)
    players = {p['id']: p for p in english['players']}
    xi = native_xi(payloads(eq_data)[307], jug_data)
    ids = club['opening']['starting_xi_player_ids']
    if [players[p]['carrier_id'] for p in ids] != [p[0] for p in xi]:
        raise ValueError('English source recipe differs from actual native XI')
    # Native ball-state ordering is retained. Factory movement is an envelope,
    # not a donor formation: remove each row's mean before applying small,
    # role-specific contextual offsets to the sourced 4-1-4-1 anchors.
    if hashlib.sha256(factory_data).hexdigest() != 'e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c':
        raise ValueError('factory movement input is not the verified clean English base')
    factory = read_initial_tactics(payloads(factory_data)[307])
    anchors = [
        (114, 20, 114, 25), (89, 100, 89, 135), (138, 100, 138, 135),
        (179, 105, 179, 180), (48, 105, 48, 180), (114, 155, 114, 210),
        (94, 220, 94, 280), (134, 220, 134, 280),
        (164, 230, 164, 330), (64, 230, 64, 330), (114, 300, 114, 370),
    ]
    slots = []
    # Use all outfield factory rows to avoid importing a mismatched donor role.
    offsets = []
    for zone in range(20):
        offsets.append([sum(rows[zone][c] - sum(s[c] for s in rows) // 20
                            for rows in factory.states[1:]) // 10 for c in range(4)])
    for i, (pid, role, anchor) in enumerate(zip(ids, PILOT_ROLES, anchors)):
        states = []
        scale = 0.15 if role == 'GK' else 0.45 if role in ('RCB', 'LCB') else 0.65 if role == 'DM' else 0.8
        for offset in offsets:
            states.append([max(12 if c % 2 == 0 else 8, min(216 if c % 2 == 0 else 390,
                anchor[c] + max(-18, min(18, round(offset[c] * scale))))) for c in range(4)])
        if role == 'GK':
            # Real load readback resets this one depth to zero. Factory slot
            # one/state zero also uses zero; retain that native convention.
            # Do not invent a two-byte prefix to protect it: it is a field.
            states[0][3] = 0
        slots.append({'player_id': pid, 'native_player_id': xi[i][0], 'native_name': xi[i][1],
                      'role': role, 'states': states})
    context = {'format': FORMAT, 'template_id': 'stoke-2015-4-1-4-1-v1', 'slots': slots}
    validate_context(context, ids)
    return {'schema_version': SCHEMA, 'season': '2015-16',
        'provenance': {'english_package_sha256': english_sha,
            'fixture_date': club['opening']['fixture_date'], 'formation_source': club['opening']['proof'],
            'factory_eq_sha256': hashlib.sha256(factory_data).hexdigest(),
            'movement_policy': 'inferred-role-specific-phase-anchors-and-centred-factory-zone-envelope',
            'native_loader': {'reader': 'MANAGPRE:5c2380', 'writer': 'MANAGPRE:5c22b0',
                              'raw_order': ['attack_depth', 'attack_lane', 'defend_depth', 'defend_lane'],
                              'biases': [14, 12, 8, 9], 'prefix_bytes': 0, 'control_bytes': 7,
                              'gk_first_attack_depth': 'zero-as-in-factory-and-measured-runtime'}},
        'clubs': [{'carrier_id': 307, 'name': club['name'], 'formation': club['opening']['formation'],
                   'context': context,
                   'control_prefix_before': list(read_initial_tactics(payloads(eq_data)[307]).controls[:2]),
                   'restore_control_prefix': list(factory.controls[:2])}]}


def prepare(output):
    """A bounded candidate, never registered merely because it compiles."""
    release = registry.load_preferred_release('2015-16')
    english_path = ROOT / '.local/season-2015-16/2015-16-english92.v2.json'
    factory_path = ROOT / '.local/visual-qa-20261003/native-source/EQ98030.FDI'
    english_raw = english_path.read_bytes()
    english = json.loads(english_raw)
    eq_path = release.game_path / 'DBDAT/EQ98030.FDI'
    eq_data = eq_path.read_bytes()
    jug_data = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    layer = build_stoke_layer(english, hashlib.sha256(english_raw).hexdigest(), eq_data, jug_data, factory_path.read_bytes())
    patched = apply_layer(eq_data, jug_data, layer)
    if apply_layer(patched, jug_data, layer) != patched:
        raise ValueError('contextual tactics are not byte-idempotent')
    output.mkdir(parents=True, exist_ok=False)
    # These links are read-only upload inputs. The changed EQ is a new inode;
    # the runner creates its own independent writable runtime installation.
    shutil.copytree(release.game_path / 'DBDAT', output / 'DBDAT', copy_function=os.link)
    temporary = output / 'patched-eq.tmp'
    temporary.write_bytes(patched)
    temporary.replace(output / 'DBDAT/EQ98030.FDI')
    pipeline.write_canonical_json(output / 'contextual-tactics.json', layer)
    club = next(c for c in english['clubs'] if c['carrier_id'] == 307)
    club['opening']['tactics_context'] = layer['clubs'][0]['context']
    club['opening']['tactics_positions'] = summary_positions(club['opening']['tactics_context'])
    (output / 'english-season-package.json').write_bytes(package_v2.canonical_json_bytes(english))
    package = json.loads(release.package_path.read_text())
    package['artifacts'].append({'id': ARTIFACT_PREFIX + '2015-16', 'kind': 'season-input',
        'sha256': registry.sha256_file(output / 'contextual-tactics.json'),
        'media_type': 'application/json', 'relative_path': 'contextual-tactics.json'})
    package['artifacts'].sort(key=lambda a: a['id'])
    (output / 'season-package.json').write_bytes(package_v2.canonical_json_bytes(package))
    changed = [i for i, (a, b) in enumerate(zip(eq_data, patched)) if a != b]
    receipt = {'schema_version': 'pm99-contextual-tactics-candidate-v1', 'season': '2015-16',
        'source_release_id': release.release_id, 'source_game_path': str(release.game_path),
        'source_package_path': str(release.package_path), 'source_package_sha256': registry.canonical_document_sha256(release.package_path),
        'source_eq_sha256': hashlib.sha256(eq_data).hexdigest(), 'output_eq_sha256': hashlib.sha256(patched).hexdigest(),
        'source_jug_sha256': hashlib.sha256(jug_data).hexdigest(), 'changed_bytes': len(changed),
        'changed_carriers': [307], 'byte_idempotent': True, 'registered': False,
        'runtime_proven': False, 'exe_path': str(release.game_path / 'MANAGPRE.EXE')}
    pipeline.write_canonical_json(output / 'candidate-receipt.json', receipt)
    if eq_path.read_bytes() != eq_data:
        raise ValueError('source release changed during candidate preparation')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output.resolve()), indent=2))


if __name__ == '__main__':
    main()
