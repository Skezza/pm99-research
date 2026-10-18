#!/usr/bin/env python3
"""Rebind unchanged raw opening evidence after an authorised club/coach delta.

Only source-row-certified renamed clubs replace their old club's evidence.
Other records require their original club label. No old result is relabelled
to approve a different historical team, and no raw source is downloaded.
"""
import argparse
import collections
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_historical_opening_review_v1 as opening
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_club_label_plan_v1 as labels
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph


def refreshed_rows(clubs, players, old_rows, updates, native_managers, check_source):
    old = {r['club_id']: r for r in old_rows}; renamed = {r['club_id']: r for r in updates}
    rows, evidence_by_club, counts = [], {}, collections.Counter()
    for club in clubs:
        previous = old[club['id']]; row = copy.deepcopy(previous)
        proof = None
        if club['id'] in renamed:
            update = renamed[club['id']]
            if (club['carrier_id'], club['name']) != (update['carrier_id'], update['after']):
                raise ValueError('renamed club differs from its authorised source-row plan')
            proof = update['evidence']; row.pop('error', None)
        elif (club['carrier_id'], club['name']) != (previous['carrier_id'], previous['club']):
            raise ValueError('cannot relabel old opening evidence as another club')
        elif previous['status'] == 'original-first-fixture-reparsed':
            proof = previous['evidence']
        native_id, native_name, owners = native_managers[club['carrier_id']]
        row.update(club=club['name'], native_manager=native_name,
            native_manager_carrier_id=native_id, native_manager_owner_count=owners,
            manager_status='not-independently-verified', full_opening_roster_verified=False)
        if proof:
            for source in proof['raw_sources']: check_source(source)
            evidence_by_club[club['id']] = proof
            row.update(status='original-first-fixture-reparsed', evidence=proof,
                manager_status=('match' if opening._normalise(proof['manager']) == opening._normalise(native_name)
                    else 'mismatch') if proof.get('manager') else 'source-manager-unpublished')
            names = {opening._normalise(p.get('source_name') or p['name']) for p in players if p['club_id'] == club['id']}
            row['published_matchday_players'] = len(proof['starting_xi']) + len(proof['substitutes'])
            row['full_name_matchday_members_in_recipe'] = sum(opening._normalise(n) in names
                for field in ('starting_xi', 'substitutes') for n in proof[field].values())
            if club['id'] in renamed: row['authored_starter_source_ids_rechecked_by_club_plan'] = 11
        counts[row['status']] += 1; counts['manager:' + row['manager_status']] += 1
        rows.append(row)
    duplicates = opening.duplicate_queue(players, {c['id']: c for c in clubs}, evidence_by_club)
    for row in duplicates: counts['duplicate:' + row['status']] += 1
    return rows, duplicates, counts


def refresh(season, prior_path, destination):
    release = registry.load_preferred_release(season); package = json.loads(release.package_path.read_text())
    clubs, players, legacy = roster.add_legacy_english(package, season)
    previous = json.loads(prior_path.read_text()); plan_path = release.package_path.parent / 'club-plan.json'
    descriptor = next(a for a in package['artifacts'] if a['id'] == 'historical-club-label-plan-' + season)
    plan = json.loads(plan_path.read_text())
    if hashlib.sha256(pipeline.canonical_json_bytes(plan)).hexdigest() != descriptor['sha256']:
        raise ValueError('current recipe does not bind its original club label plan')
    if plan['schema_version'] != labels.SCHEMA or previous['schema_version'] != opening.SCHEMA or previous['season'] != season:
        raise ValueError('wrong club plan or prior first-fixture report')
    capture = previous['bindings']['opening_capture_path']
    if (capture, previous['bindings']['opening_capture_sha256']) != (
            plan['source_bindings']['original_capture_path'], plan['source_bindings']['original_capture_sha256']):
        raise ValueError('opening capture changed between completed source audits')
    if registry.sha256_file(ROOT / capture) != previous['bindings']['opening_capture_sha256']:
        raise ValueError('original opening capture bytes changed')
    holders, names = _manager_graph(eq_path=release.game_path / 'DBDAT/EQ98030.FDI', ent_path=release.game_path / 'DBDAT/ENT98030.FDI')
    native = {c['carrier_id']: (id, names.get(id), len(owned)) for id, owned in holders.items() for c in owned}
    checked = {}
    def check_source(source):
        path = ROOT / source['path']
        if path not in checked: checked[path] = registry.sha256_file(path)
        if checked[path] != source['sha256']: raise ValueError('original first-fixture bytes changed')
    rows, duplicates, counts = refreshed_rows(clubs, players, previous['clubs'], plan['updates'], native, check_source)
    result = {**previous, 'clubs': rows, 'duplicate_players': duplicates,
        'summary': {'season': season, 'clubs': len(rows), 'duplicate_person_candidates': len(duplicates), **dict(counts)},
        'bindings': {**previous['bindings'], 'release_id': release.release_id,
            'package_sha256': registry.sha256_file(release.package_path),
            'eq_sha256': registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'),
            'ent_sha256': registry.sha256_file(release.game_path / 'DBDAT/ENT98030.FDI'), 'legacy': legacy},
        'completed_source_evidence_reuse': {'prior_path': registry.relative_workspace_path(prior_path),
            'prior_sha256': registry.sha256_file(prior_path), 'club_plan_path': registry.relative_workspace_path(plan_path),
            'club_plan_sha256': registry.sha256_file(plan_path),
            'scope': 'Original bytes rehashed; native coaches and current duplicate queues recomputed; no roster certification'}}
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists(): raise ValueError('completed opening refresh already exists')
    pipeline.write_canonical_json(destination, result)
    return result['summary']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season'); parser.add_argument('--prior-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    for season in registry.supported_seasons() if args.season == 'all' else [args.season]:
        release = registry.load_preferred_release(season)
        if not (release.package_path.parent / 'club-plan.json').exists(): continue
        print(json.dumps(refresh(season, args.prior_root / season / 'opening-review.json',
            args.output / season / 'opening-review.json')), flush=True)


if __name__ == '__main__': main()
