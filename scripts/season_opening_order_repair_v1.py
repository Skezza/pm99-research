#!/usr/bin/env python3
"""Extend frozen tactics candidates with bounded, ownership-checked XI repairs.

No regeneration of facts, ratings, managers, rosters or assets. Existing grids
are retained byte-exact; only formerly queued clubs receive new contextual
tactics. Compact mode-0 startup writes require an explicit caller opt-in.
"""
from __future__ import annotations

import argparse
import copy
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'upstream/pm99-skezmod-db-editor')]
from app.eq_initial_tactics import GRID_BYTES, read_initial_tactics
from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import OrderReplacement, patch_initial_orders, read_initial_order
from scripts import season_contextual_tactics_v1 as tactics
from scripts import season_contextual_tactics_rollout_v1 as rollout
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry

SCHEMA = 'pm99-opening-order-repair-v1'
PREFIX = 'opening-order-'


def deployment_review(package):
    """Flag hard fact/deployment contradictions without declaring either true."""
    players = {p['id']: p for p in package['players']}
    rows, checked = [], 0
    for club in package['clubs']:
        context = club.get('opening', {}).get('tactics_context')
        if context is None:
            continue
        checked += 1
        for slot in context['slots']:
            player = players[slot['player_id']]
            facts, role = player['facts'], slot['role']
            broad, fine = facts['primary_position'], facts['fine_roles']
            if ((broad == 'F' and role in ('RB', 'LB', 'RCB', 'LCB', 'CB') and not set(fine) & {1, 2, 3, 4, 5}) or
                    (broad == 'D' and role in ('ST', 'SS') and not set(fine) & {8, 12, 15, 16})):
                rows.append({'club_id': club['id'], 'club': club['name'], 'player_id': player['id'],
                    'native_player_id': player['carrier_id'], 'name': player['name'],
                    'primary_position': broad, 'fine_roles': fine, 'deployment': role,
                    'reason': 'player-fact/deployment disagreement; needs source review, not an automatic position rewrite'})
    return {'contextual_clubs_checked': checked, 'warning_count': len(rows), 'warnings': rows,
            'scope': 'internal disagreement only; neither stored facts nor inferred deployment independently establishes history'}


def inferred_deployment(opening, players):
    """Fit the existing sourced fine roles to the declared shape, deterministically.

    Used only when the old XI order put an outfielder before the goalkeeper:
    those legacy slot coordinates cannot be trusted as named deployments.
    This is editorial deployment inference, not a player-fact rewrite.
    """
    slots = rollout.formation_template(opening['formation'])
    ids = opening['starting_xi_player_ids'][1:]
    positions = opening['tactics_positions'][1:]
    desired = {'RB': (1,), 'RWB': (1, 6), 'LB': (2,), 'LWB': (2, 10),
               'RCB': (5, 4, 3), 'LCB': (4, 5, 3), 'CB': (4, 5, 3),
               'DM': (14, 9), 'RCM': (9, 14), 'LCM': (9, 14), 'CM': (9,),
               'RM': (6, 11), 'LM': (10, 13), 'RW': (11, 6, 15),
               'LW': (13, 10, 16), 'AM': (9, 8), 'SS': (8, 12, 9), 'ST': (12, 8)}
    costs = []
    for pid, old in zip(ids, positions):
        facts = players[pid]['facts']
        roles = facts['fine_roles']
        row = []
        for role, lane, depth, _, _ in slots[1:]:
            broad = 'D' if role in ('RB', 'LB', 'RWB', 'LWB', 'RCB', 'LCB', 'CB') else 'F' if role in ('ST', 'SS') else 'M'
            broad_cost = 0 if facts['primary_position'] == broad else 1
            if role in ('RWB', 'LWB', 'RW', 'LW', 'SS') and any(r in desired[role] for r in roles):
                broad_cost = 0
            fine_cost = min((desired[role].index(r) for r in roles if r in desired[role]), default=10)
            # Fine-role evidence dominates old spatial proximity. Never pick a
            # side from G/D/M/F alone; ties retain the closest old deployment.
            row.append(broad_cost * 100000 + fine_cost * 1000 + abs(old[0] - lane) + abs(old[1] - depth))
        costs.append(row)

    @lru_cache(None)
    def best(i, used):
        if i == 10:
            return 0, ()
        options = []
        for slot in range(10):
            if not used & (1 << slot):
                cost, tail = best(i + 1, used | (1 << slot))
                options.append((costs[i][slot] + cost, (slot,) + tail))
        return min(options)

    total_cost, assigned = best(0, 0)
    opening['tactics_positions'] = [list(slots[0][1:])] + [list(slots[i + 1][1:]) for i in assigned]
    return {'method': 'deterministic editorial fit of existing sourced fine roles to declared formation',
            'not_independent_historical_deployment_proof': True, 'cost': total_cost,
            'players': [{'player_id': pid, 'role': slots[i + 1][0],
                        'existing_fine_roles': players[pid]['facts']['fine_roles']}
                       for pid, i in zip(ids, assigned)]}


def native_owners(eq):
    owners = {}
    for carrier, payload in tactics.payloads(eq).items():
        roster = parse_eq_external_team_roster_payload(payload, {})
        if (roster is None and len(payload) >= 0x2a and payload[0x29] in (0, 1)
                and int.from_bytes(payload[0x26:0x28], 'little') >= 600):
            raise ValueError('cannot prove ownership through an unreadable external club roster')
        if roster is not None:
            for row in roster.rows:
                owners.setdefault(row.player_record_id, set()).add(carrier)
    return owners


def apply_layer(eq, jug, layer, *, allow_compact=False):
    if layer.get('schema_version') != SCHEMA:
        raise ValueError('unsupported opening-order layer')
    records, owners = tactics.payloads(eq), native_owners(eq)
    replacements, seen = [], set()
    for club in layer['clubs']:
        cid = club['carrier_id']
        if cid in seen or cid not in records or records[cid][0x29] != 0:
            raise ValueError('opening-order target must be a unique mode-0 club')
        seen.add(cid)
        for row in club['players']:
            pid = row['native_player_id']
            if owners.get(pid) != {cid}:
                raise ValueError('opening-order player has absent or cross-club ownership')
            replacements.append(OrderReplacement(pid, row['native_name'], row['before'], row['after']))
    output = patch_initial_orders(jug, replacements, allow_compact=allow_compact)
    index = {e.record_id: e for e in IndexedFDIFile.from_bytes(output).entries}
    for club in layer['clubs']:
        expected = [(r['native_player_id'], r['native_name']) for r in club['players'][:11]]
        if tactics.native_xi(records[club['carrier_id']], output, index) != expected:
            raise ValueError('repaired native XI does not match named recipe')
    return output


def package_layers(package, path):
    result = []
    seen = set()
    season = f"{package['season']['start_year']}-{str(package['season']['end_year'])[-2:]}"
    for artifact in sorted(package.get('artifacts', []), key=lambda a: a['id']):
        if not artifact['id'].startswith(PREFIX):
            continue
        rel = Path(artifact.get('relative_path', ''))
        if not rel.parts or rel.is_absolute() or '..' in rel.parts:
            raise ValueError('unsafe opening-order artifact path')
        raw = (path.parent / rel).read_bytes()
        if hashlib.sha256(raw).hexdigest() != artifact['sha256']:
            raise ValueError('opening-order artifact hash changed')
        layer = json.loads(raw)
        if layer.get('season') != season:
            raise ValueError('opening-order artifact season changed')
        for club in layer['clubs']:
            if club['carrier_id'] in seen:
                raise ValueError('overlapping opening-order layers')
            seen.add(club['carrier_id'])
        result.append(layer)
    return result


def repair_club(club, players, jug_index, jug):
    opening = club['opening']
    xi, positions = opening['starting_xi_player_ids'], opening['tactics_positions']
    goalkeepers = [pid for pid in xi if players[pid]['facts']['primary_position'] == 'G']
    if len(goalkeepers) != 1 or len(xi) != 11 or len(positions) != 11:
        raise ValueError('repair needs eleven named players and one sourced goalkeeper')
    # Move player + their source deployment together. Never turn slot one's
    # outfield player into a GK or move the goalkeeper's coordinate to him.
    misordered_keeper = xi[0] != goalkeepers[0]
    indices = [xi.index(goalkeepers[0])] + [i for i, pid in enumerate(xi) if pid != goalkeepers[0]]
    opening['starting_xi_player_ids'] = [xi[i] for i in indices]
    opening['tactics_positions'] = [positions[i] for i in indices]
    deployment_correction = None
    # One legacy migration calls a clearly encoded diamond a flat 4-4-2.
    # Infer the label from that existing named deployment, not from a guessed
    # historical website formation or by inventing lateral order at a tie.
    if opening['formation'] == '4-4-2':
        ordered = sorted(opening['tactics_positions'][1:], key=lambda p: (p[1], p[0]))
        middle = ordered[4:8]
        depths = sorted({p[1] for p in middle})
        if (len(depths) == 3 and [sum(p[1] == d for p in middle) for d in depths] == [1, 2, 1]
                and middle[0][0] == middle[-1][0]
                and middle[1][0] < middle[0][0] < middle[2][0]
                and ordered[3][1] < depths[0] < depths[-1] < ordered[8][1]):
            opening['formation'] = '4-1-2-1-2'
            deployment_correction = {'before': '4-4-2', 'after': '4-1-2-1-2',
                'basis': 'inferred from existing named source-coordinate diamond; not a newly sourced historical claim'}
    inferred = inferred_deployment(opening, players) if misordered_keeper else None
    selected = opening['starting_xi_player_ids'] + opening['substitute_player_ids']
    roster = club['roster_player_ids']
    if len(selected) != len(set(selected)) or not set(selected) <= set(roster) or len(roster) != len(set(roster)):
        raise ValueError('repair selection or roster has duplicate/absent players')
    ordered = selected + [p for p in roster if p not in set(selected)]
    rows = []
    for order, pid in enumerate(ordered, 1):
        native_id = players[pid]['carrier_id']
        field = read_initial_order(jug_index[native_id].decode_payload(jug))
        rows.append({'player_id': pid, 'native_player_id': native_id, 'native_name': field.name,
                     'family': field.family, 'before': field.order, 'after': order})
    return {'carrier_id': club['carrier_id'], 'name': club['name'], 'players': rows,
            'reason': 'source opening XI before substitutes and reserves; unique native startup slots',
            'deployment_correction': deployment_correction, 'inferred_deployment': inferred}


def prepare(season, source, output, *, allow_compact=False):
    prior_audit = rollout.audit_candidate(source)
    prior = json.loads((source / 'candidate-receipt.json').read_text())
    english = json.loads((source / 'english-season-package.json').read_text())
    package = json.loads((source / 'season-package.json').read_text())
    layer = json.loads((source / 'contextual-tactics.json').read_text())
    eq, jug = (source / 'DBDAT/EQ98030.FDI').read_bytes(), (source / 'DBDAT/JUG98030.FDI').read_bytes()
    records = tactics.payloads(eq)
    index = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    players = {p['id']: p for p in english['players']}
    by_club = {c['carrier_id']: c for c in english['clubs']}
    plan = {'schema_version': SCHEMA, 'season': season, 'scope': 'English mode0 only',
            'source_jug_sha256': hashlib.sha256(jug).hexdigest(), 'clubs': []}
    for row in prior['editorial_queue']:
        plan['clubs'].append(repair_club(by_club[row['carrier_id']], players, index, jug))
    repaired_jug = apply_layer(eq, jug, plan, allow_compact=allow_compact)
    if apply_layer(eq, repaired_jug, plan, allow_compact=allow_compact) != repaired_jug:
        raise AssertionError('opening-order repair is not byte-idempotent')
    repaired_index = {e.record_id: e for e in IndexedFDIFile.from_bytes(repaired_jug).entries}
    offsets = rollout.movement_offsets((ROOT / '.local/visual-qa-20261003/native-source/EQ98030.FDI').read_bytes())
    for repaired in plan['clubs']:
        club = by_club[repaired['carrier_id']]
        context = rollout.build_context(club, players,
            tactics.native_xi(records[club['carrier_id']], repaired_jug, repaired_index), offsets)
        club['opening']['tactics_context'] = context
        club['opening']['tactics_positions'] = tactics.summary_positions(context)
        layer['clubs'].append({'carrier_id': club['carrier_id'], 'name': club['name'],
            'formation': club['opening']['formation'], 'context': context,
            'provenance': {'opening_order_repair': PREFIX + season,
                'fixture_date': club['opening']['fixture_date'], 'formation_source': club['opening']['proof'],
                'deployment_source': 'source recipe player-bound coordinates',
                'movement_policy': 'editorially-inferred-phase-anchors-centred-factory-envelope'}})
    layer['clubs'].sort(key=lambda c: c['carrier_id'])
    after = tactics.apply_layer(eq, repaired_jug, layer)
    if tactics.apply_layer(after, repaired_jug, layer) != after:
        raise AssertionError('repaired tactics are not byte-idempotent')
    repaired_carriers = {c['carrier_id'] for c in plan['clubs']}
    for carrier, payload in tactics.payloads(after).items():
        if carrier not in repaired_carriers and payload != records[carrier]:
            raise AssertionError('repair changed an existing contextual or foreign club')
    for club in package['clubs']:
        if club['carrier_id'] in by_club:
            club['opening'] = copy.deepcopy(by_club[club['carrier_id']]['opening'])
    package['artifacts'] = [a for a in package['artifacts'] if not a['id'].startswith(
        (tactics.ARTIFACT_PREFIX, PREFIX, 'english-contextual-package-'))]
    packages.validate_package(package)
    packages.validate_package(english)
    output.mkdir(parents=True, exist_ok=False)
    pipeline.write_canonical_json(output / 'opening-order.json', plan)
    pipeline.write_canonical_json(output / 'contextual-tactics.json', layer)
    (output / 'english-season-package.json').write_bytes(packages.canonical_json_bytes(english))
    inputs = [(PREFIX + season, 'opening-order.json'), ('english-contextual-package-' + season, 'english-season-package.json')]
    if not any(c['carrier_id'] in {r['carrier_id'] for r in layer['clubs']} for c in package['clubs']):
        inputs.append((tactics.ARTIFACT_PREFIX + season, 'contextual-tactics.json'))
    for identity, filename in inputs:
        package['artifacts'].append({'id': identity, 'kind': 'season-input',
            'media_type': 'application/json', 'relative_path': filename, 'sha256': registry.sha256_file(output / filename)})
    package['artifacts'].sort(key=lambda a: a['id'])
    (output / 'season-package.json').write_bytes(packages.canonical_json_bytes(package))
    shutil.copytree(source / 'DBDAT', output / 'DBDAT', copy_function=os.link)
    for filename, data in [('EQ98030.FDI', after), ('JUG98030.FDI', repaired_jug)]:
        temporary = output / (filename + '.partial')
        temporary.write_bytes(data)
        temporary.replace(output / 'DBDAT' / filename)
    receipt = {**prior, 'schema_version': 'pm99-contextual-tactics-candidate-v3',
        'prior_candidate_path': str(source.resolve()), 'prior_candidate_receipt_sha256': registry.sha256_file(source / 'candidate-receipt.json'),
        'prior_output_eq_sha256': prior['output_eq_sha256'], 'prior_audit': prior_audit,
        'output_eq_sha256': hashlib.sha256(after).hexdigest(), 'output_jug_sha256': hashlib.sha256(repaired_jug).hexdigest(),
        'contextual_clubs': len(layer['clubs']), 'editorial_queue': [],
        'repaired_clubs': sorted(repaired_carriers),
        'startup_bytes_changed': sum(a != b for a, b in zip(jug, repaired_jug)),
        'existing_contextual_clubs_preserved': prior['contextual_clubs'],
        'formations': sorted({c['formation'] for c in layer['clubs']}),
        'registered': False, 'runtime_proven': False}
    pipeline.write_canonical_json(output / 'candidate-receipt.json', receipt)
    return audit_candidate(output)


def audit_candidate(output):
    receipt = json.loads((output / 'candidate-receipt.json').read_text())
    source = Path(receipt['prior_candidate_path'])
    if registry.sha256_file(source / 'candidate-receipt.json') != receipt['prior_candidate_receipt_sha256']:
        raise ValueError('prior candidate receipt changed')
    rollout.audit_candidate(source)
    eq, jug = (source / 'DBDAT/EQ98030.FDI').read_bytes(), (source / 'DBDAT/JUG98030.FDI').read_bytes()
    actual_eq, actual_jug = (output / 'DBDAT/EQ98030.FDI').read_bytes(), (output / 'DBDAT/JUG98030.FDI').read_bytes()
    plan = json.loads((output / 'opening-order.json').read_text())
    layer = json.loads((output / 'contextual-tactics.json').read_text())
    if plan['season'] != receipt['season'] or layer['season'] != receipt['season']:
        raise ValueError('repair layer season mismatch')
    if (apply_layer(eq, jug, plan, allow_compact=True) != actual_jug or
            apply_layer(eq, actual_jug, plan, allow_compact=True) != actual_jug or
            tactics.apply_layer(eq, actual_jug, layer) != actual_eq or
            tactics.apply_layer(actual_eq, actual_jug, layer) != actual_eq):
        raise ValueError('repair layer failed exact/idempotent replay')
    if (hashlib.sha256(actual_jug).hexdigest() != receipt['output_jug_sha256'] or
            hashlib.sha256(actual_eq).hexdigest() != receipt['output_eq_sha256']):
        raise ValueError('repair output hash mismatch')
    repaired = {c['carrier_id'] for c in plan['clubs']}
    permitted_eq, before = set(), tactics.payloads(eq)
    for entry in IndexedFDIFile.from_bytes(eq).entries:
        if entry.record_id in repaired:
            start = entry.payload_offset + read_initial_tactics(before[entry.record_id]).grid_offset
            permitted_eq.update(range(start, start + GRID_BYTES))
    if len(eq) != len(actual_eq) or any(a != b and i not in permitted_eq for i, (a, b) in enumerate(zip(eq, actual_eq))):
        raise ValueError('repair escaped formerly queued tactics grids')
    # Independently locate each permitted startup byte and verify all other
    # JUG bytes (including facts, skills, portraits and unknowns) are exact.
    index = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    permitted_jug = {index[r['native_player_id']].payload_offset + read_initial_order(
        index[r['native_player_id']].decode_payload(jug)).offset for c in plan['clubs'] for r in c['players']}
    if len(jug) != len(actual_jug) or any(a != b and i not in permitted_jug for i, (a, b) in enumerate(zip(jug, actual_jug))):
        raise ValueError('repair changed player bytes outside startup order')
    english = json.loads((output / 'english-season-package.json').read_text())
    prior_english = json.loads((source / 'english-season-package.json').read_text())
    if english['players'] != prior_english['players'] or english['managers'] != prior_english['managers']:
        raise ValueError('repair changed player or manager recipe data')
    prior_by_club = {c['carrier_id']: c for c in prior_english['clubs']}
    by_club = {c['carrier_id']: c for c in english['clubs']}
    after_records = tactics.payloads(actual_eq)
    for cid, club in by_club.items():
        if {k: v for k, v in club.items() if k != 'opening'} != {k: v for k, v in prior_by_club[cid].items() if k != 'opening'}:
            raise ValueError('repair changed club fields outside opening tactics')
    package = json.loads((output / 'season-package.json').read_text())
    packages.validate_package(english)
    packages.validate_package(package)
    if len(layer['clubs']) != 92 or receipt['editorial_queue']:
        raise ValueError('repair did not close all 92 English clubs')
    for artifact in package['artifacts']:
        if artifact['id'].startswith((PREFIX, tactics.ARTIFACT_PREFIX, 'english-contextual-package-')):
            if registry.sha256_file(output / artifact['relative_path']) != artifact['sha256']:
                raise ValueError('repaired recipe input hash changed')
    package_layers(package, output / 'season-package.json')
    tactics.package_layers(package, output / 'season-package.json')
    for row in layer['clubs']:
        context = row['context']
        rollout.audit_context(context)
        opening = by_club[row['carrier_id']]['opening']
        if opening['tactics_context'] != context or opening['starting_xi_player_ids'] != [s['player_id'] for s in context['slots']]:
            raise ValueError('repaired named recipe differs from context')
        actual = read_initial_tactics(after_records[row['carrier_id']])
        if actual.states != tuple(tuple(tuple(s) for s in slot['states']) for slot in context['slots']):
            raise ValueError('repaired native coordinate readback differs')
    return {'season': receipt['season'], 'success': True, 'contextual_clubs': len(layer['clubs']),
            'repaired_clubs': len(repaired), 'startup_bytes_changed': receipt['startup_bytes_changed'],
            'coordinate_values_read_back': len(layer['clubs']) * 880,
            'existing_contexts_preserved': True, 'all_other_player_bytes_preserved': True,
            'all_other_club_bytes_preserved': True, 'byte_idempotent': True,
            'blocked_clubs': 0, 'registered': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season')
    parser.add_argument('--root', type=Path, default=ROOT / '.local/contextual-tactics-v1')
    parser.add_argument('--allow-compact-mode0', action='store_true')
    parser.add_argument('--audit', action='store_true')
    parser.add_argument('--deployment-audit', action='store_true')
    args = parser.parse_args()
    rows = []
    for season in registry.supported_seasons() if args.season == 'all' else [args.season]:
        parent = args.root / season
        output = parent / 'english-rollout-candidate-v3'
        if args.deployment_audit:
            package = json.loads((output / 'english-season-package.json').read_text())
            row = {'season': season, 'package_sha256': registry.sha256_file(output / 'english-season-package.json'),
                   **deployment_review(package)}
            rows.append(row)
            print(json.dumps({'season': season, 'deployment_warning_count': row['warning_count']}), flush=True)
            continue
        if args.audit or output.exists():
            row = audit_candidate(output)
        else:
            row = prepare(season, parent / 'english-rollout-candidate-v1', output,
                          allow_compact=args.allow_compact_mode0)
        rows.append(row)
        print(json.dumps(row), flush=True)
    if args.season == 'all':
        if args.deployment_audit:
            pipeline.write_canonical_json(args.root / 'rollout-deployment-review-queue-v1.json',
                {'schema_version': 'pm99-tactics-deployment-review-v1', 'seasons': rows,
                 'warning_count': sum(r['warning_count'] for r in rows),
                 'scope': 'internal positional disagreements, not verified historical errors', 'registered': False})
            return
        target = args.root / 'rollout-repaired-offline-audit-v3.json'
        report = {'schema_version': 'pm99-contextual-tactics-repaired-audit-v3', 'seasons': rows,
                  'contextual_clubs': sum(r['contextual_clubs'] for r in rows),
                  'repaired_clubs': sum(r['repaired_clubs'] for r in rows),
                  'registered': False, 'runtime_scope': 'offline only; runtime formation gate pending'}
        if target.exists() and json.loads(target.read_text()) != report:
            raise ValueError('existing aggregate repair audit differs')
        pipeline.write_canonical_json(target, report)


if __name__ == '__main__':
    main()
