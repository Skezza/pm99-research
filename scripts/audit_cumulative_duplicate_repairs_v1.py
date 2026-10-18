#!/usr/bin/env python3
"""Bind cumulative corrected slots to current recipes and portrait availability."""
from __future__ import annotations
import argparse
import collections
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline


def merge_slots(prior, plans):
    slots = {}
    for row in prior['players']:
        key = (row['season'], row['carrier_id'])
        if key in slots:
            raise ValueError('prior ledger contains a repeated carrier')
        slots[key] = {'season': row['season'], 'carrier_id': row['carrier_id'],
            'player_id': row['player_id'], 'name': row['name'], 'birth_date': row['birth_date']}
        if 'chained_disposition' in row:
            slots[key]['chained_disposition'] = row['chained_disposition']
    for path, plan in plans:
        for row in plan['updates']:
            key = (plan['season'], row['carrier_id'])
            if key in slots:
                raise ValueError('repeated correction requires a separate chained-disposition ledger')
            player = row['replacement']['source_player']
            slots[key] = {'season': plan['season'], 'carrier_id': row['carrier_id'],
                'player_id': row['player_id'], 'name': player['name'], 'birth_date': player['birth_date'],
                'plan_path': registry.relative_workspace_path(path),
                'plan_sha256': registry.sha256_file(path)}
    return slots


def run(prior_path, roots, output):
    if output.exists():
        raise ValueError('cumulative evidence is immutable')
    prior = json.loads(prior_path.read_text())
    plans = [(path, json.loads(path.read_text())) for root in roots
             for path in sorted(root.glob('*/ownership-plan.json'))]
    slots = merge_slots(prior, plans)
    return verify_slots(prior_path, slots, output)


def merge_chained_slots(prior, season, allocation, binding):
    """Replace a previously corrected slot only with its exact before identity.

    Count distinct season/carrier slots, not repeated writes. Keep the earlier
    disposition in each affected row so whole-club retirement cannot erase it.
    """
    slots = merge_slots(prior, [])
    seen = set()
    for row in allocation:
        key = (season, row['carrier_id'])
        if key in seen:
            raise ValueError('chained disposition repeats a carrier')
        seen.add(key)
        before = row['before_recipe']
        if (before['carrier_id'], before['id']) != (row['carrier_id'], row['player_id']):
            raise ValueError('chained before identity is another native slot')
        previous = slots.get(key)
        if previous and (previous['player_id'], previous['name'], previous['birth_date']) != (
                before['id'], before.get('source_name') or before['name'], before['facts']['birth_date']):
            raise ValueError('chained disposition does not extend the prior corrected identity')
        person = row['replacement']['source_player']
        slots[key] = {'season': season, 'carrier_id': row['carrier_id'],
            'player_id': row['player_id'], 'name': person['name'], 'birth_date': person['birth_date'],
            'chained_disposition': dict(binding, previous_corrected_identity=previous,
                retired_name=before.get('source_name') or before['name'],
                retired_birth_date=before['facts']['birth_date'])}
    return slots


def run_chained(prior_path, candidate, identity_path, output):
    if output.exists():
        raise ValueError('cumulative evidence is immutable')
    from scripts import prepare_duplicate_whole_club_native_v1 as native
    receipt_path = candidate / 'candidate-receipt.json'
    receipt = json.loads(receipt_path.read_text())
    proof = json.loads(identity_path.read_text())
    if (proof.get('candidate_receipt_sha256') != registry.sha256_file(receipt_path)
            or proof.get('introduced_candidate_groups') != 0
            or proof.get('replacement_cross_club_candidates') != 0
            or proof.get('stale_portraits_cleared') is not True):
        raise ValueError('chained disposition lacks the exact independent identity proof')
    pair = json.loads(native.original(receipt['source_pair']).read_text())
    allocations = [row for item in pair['proposals']
        for row in json.loads(native.original(item).read_text())['allocation']]
    if set(proof['corrected_slots']) != {r['carrier_id'] for r in allocations}:
        raise ValueError('chained identity proof covers different slots')
    current = registry.load_preferred_release(pair['season'])
    if registry.sha256_file(current.package_path) != registry.sha256_file(candidate / 'season-package.json'):
        raise ValueError('chained candidate is not the installed recipe')
    for name, digest in receipt['native_hashes'].items():
        if registry.sha256_file(current.game_path / 'DBDAT' / name) != digest:
            raise ValueError('chained candidate is not the installed native game')
    binding = {'source_pair': receipt['source_pair'],
        'candidate_receipt': {'path': registry.relative_workspace_path(receipt_path),
            'sha256': registry.sha256_file(receipt_path)},
        'identity_proof': {'path': registry.relative_workspace_path(identity_path),
            'sha256': registry.sha256_file(identity_path)}}
    prior = json.loads(prior_path.read_text())
    slots = merge_chained_slots(prior, pair['season'], allocations, binding)
    return verify_slots(prior_path, slots, output)


def verify_slots(prior_path, slots, output):
    """Read back every cumulative identity and photo association in current games."""
    grouped = collections.defaultdict(list)
    for (season, _), slot in sorted(slots.items()):
        grouped[season].append(slot)
    rows = []
    for season, corrections in sorted(grouped.items()):
        release = registry.load_preferred_release(season)
        players, clubs = {}, {}
        for _, package, _ in planner.package_layers(release):
            players.update({p['carrier_id']: p for p in package['players']})
            clubs.update({c['id']: c for c in package['clubs']})
        active = delta._active_offsets_for_players(
            bytearray((release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()),
            [s['carrier_id'] for s in corrections])
        package_sha = registry.sha256_file(release.package_path)
        for slot in corrections:
            player = players[slot['carrier_id']]
            if ((player.get('source_name') or player['name'], player['facts']['birth_date'])
                    != (slot['name'], slot['birth_date'])):
                raise ValueError('corrected source identity is not installed in current recipe')
            bmp = release.game_path / f'DBDAT/MINIFOTO/J96{slot["carrier_id"]:05d}.BMP'
            rows.append(dict(slot, release_id=release.release_id, package_sha256=package_sha,
                club=clubs[player['club_id']]['name'], loose_bitmap_present=bmp.is_file(),
                bitmap_sha256=registry.sha256_file(bmp) if bmp.is_file() else None,
                active_archive_entries=len(active.get(slot['carrier_id'], []))))
    present = sum(r['loose_bitmap_present'] or bool(r['active_archive_entries']) for r in rows)
    result = {'schema_version': 'pm99-cumulative-ownership-repair-and-portrait-ledger-v2',
        'scope': 'corrected season-carrier slots only; photo presence is not identity/date approval',
        'prior_path': registry.relative_workspace_path(prior_path),
        'prior_sha256': registry.sha256_file(prior_path),
        'corrected_slot_count': len(rows), 'portrait_present_count': present,
        'photo_missing_count': len(rows) - present, 'players': rows}
    pipeline.write_canonical_json(output, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prior-ledger', type=Path, required=True)
    parser.add_argument('--plan-root', type=Path, action='append')
    parser.add_argument('--chained-candidate', type=Path)
    parser.add_argument('--identity-proof', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.chained_candidate is not None:
        if args.plan_root or args.identity_proof is None:
            parser.error('chained candidate requires identity proof, without plan roots')
        result = run_chained(args.prior_ledger, args.chained_candidate, args.identity_proof, args.output)
    else:
        if not args.plan_root or args.identity_proof:
            parser.error('normal cumulative audit requires plan roots, without identity proof')
        result = run(args.prior_ledger, args.plan_root, args.output)
    print(json.dumps({k: v for k, v in result.items() if k != 'players'}))
