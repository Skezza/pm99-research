#!/usr/bin/env python3
"""Capture dated histories for real unused squad players at duplicate-hit clubs.

An annual squad row is a query candidate, never opening ownership approval.
Reuse original raw caches; require independent historical squad parsing and
an exact published name/DOB person join before making any request.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_public_identity_and_history_inputs_v1 as public
from scripts import season_published_person_identity_v1 as people_source
from scripts import season_published_transfer_history_v1 as history
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts.season_art_transaction_v1 import atomic_bytes


def candidate_person(raw, people, used_ids, known_histories):
    if not isinstance(raw.get('birth_date'), str) or raw.get('position') not in {'G', 'D', 'M', 'F'}:
        return None
    person = transfer.unique_person({'name': raw['name'], 'facts': raw}, people)
    if person is None or person['source_player_id'] in used_ids | known_histories:
        return None
    return person


def discover(plan_root, source_root, person_path, history_path, output):
    if output.exists():
        raise ValueError('reserve history query ledger is immutable')
    people, events, _, pin = transfer.load_snapshot(
        ROOT / '.local/external-sources/transfermarkt-datasets/transfermarkt-datasets.duckdb',
        ROOT / '.local/season-pipeline-v2/world-2015-transfermarkt-opening-fixtures-20260831.json')
    bindings = {'published_person_supplement': public.binding(person_path, people_source.POLICY),
                'published_transfer_supplement': public.binding(history_path, history.POLICY)}
    people, events, _ = public.merge_bound(people, events, bindings)
    known = {r['player_id'] for r in json.loads(history_path.read_text())['players']}
    claims, inputs = {}, []
    for season in registry.supported_seasons():
        plan_path = plan_root / season / 'ownership-plan.json'
        plan = json.loads(plan_path.read_text())
        release = registry.load_registered_release(season, plan['release_id'])
        if registry.sha256_file(release.package_path) != plan['package_sha256']:
            raise ValueError('bound discovery recipe changed')
        inputs.append({'path': registry.relative_workspace_path(plan_path), 'sha256': registry.sha256_file(plan_path)})
        players, clubs = {}, {}
        for _, package, _ in planner.package_layers(release):
            players.update({p['id']: p for p in package['players']})
            clubs.update({c['id']: c for c in package['clubs']})
        used = {p['source_player_id'] for raw in players.values() if (p := transfer.unique_person(raw, people))}
        used.update(row['replacement']['source_person']['source_player_id'] for row in plan['updates'])
        needed = {players[row['player_id']]['club_id'] for row in plan['unresolved']
                  if row['reason'] == 'owner-proven-but-no-unused-role-compatible-opening-substitute'}
        captures, capture_bindings = roster.load_sources(season)
        opening_path = source_root / 'opening' / season / 'opening-review.json'
        opening = json.loads(opening_path.read_text())
        transfer.verify_opening_sources(opening)
        inputs.append({'path': registry.relative_workspace_path(opening_path), 'sha256': registry.sha256_file(opening_path)})
        report_path = source_root / 'reviews' / season / 'report.json'
        if not report_path.exists():
            report_path = source_root / 'reviews' / season / 'roster-audit.json'
        verifier = roster.SourceVerifier(season, json.loads(report_path.read_text()), capture_bindings)
        sources = {r['carrier_id']: r['evidence'] for r in opening['clubs']
                   if r['status'] == 'original-first-fixture-reparsed'}
        for club_id in sorted(needed):
            club = clubs[club_id]
            source = sources.get(club['carrier_id'])
            if source is None:
                continue
            aliases = roster.club_names(roster.club_group(club), club['name'], club.get('full_name', ''))
            for capture in captures:
                if (roster.source_group(capture['country_catalog']) != roster.club_group(club)
                        or roster.normalise(capture['club_name']) not in aliases):
                    continue
                proof = verifier.verify(capture)
                if proof['status'] != 'raw-source-reparsed':
                    continue
                for raw in capture['players']:
                    person = candidate_person(raw, people, used, known)
                    if person is None or str(person['source_player_id']) in source['starting_xi']:
                        continue
                    claims.setdefault(person['source_player_id'], []).append({'season': season,
                        'club_id': club_id, 'club': club['name'], 'opening_date': source['date'],
                        'source_club_id': source['source_club_id'], 'source_player': raw,
                        'source_person': person, 'raw_evidence': proof,
                        'opening_membership_approved': False})
        print(json.dumps({'season': season, 'query_people_so_far': len(claims)}), flush=True)
    for item in inputs:
        if registry.sha256_file(ROOT / item['path']) != item['sha256']:
            raise ValueError('reserve history discovery inputs changed')
    pipeline.write_canonical_json(output, {'schema_version': 'pm99-unused-opening-reserve-history-requests-v1',
        'scope': 'independently parsed annual squad query candidates; not opening membership approval',
        'snapshot': pin, 'public_bindings': bindings, 'input_documents': inputs, 'claims': claims})


def capture(query_path, cache, output):
    if output.exists():
        raise ValueError('reserve history evidence is immutable')
    digest = registry.sha256_file(query_path)
    query = json.loads(query_path.read_text())
    if query.get('schema_version') != 'pm99-unused-opening-reserve-history-requests-v1':
        raise ValueError('unsupported reserve history query schema')
    records = []
    for key in sorted(query['claims'], key=int):
        id = int(key)
        if any(row['source_person']['source_player_id'] != id for row in query['claims'][key]):
            raise ValueError('reserve query person ID disagrees')
        url = history.BASE + str(id)
        path = cache / 'history' / f'{id}.json'
        receipt = path.with_suffix('.source.json')
        try:
            if path.exists():
                raw = path.read_bytes()
                if json.loads(receipt.read_text()) != {'url': url, 'sha256': hashlib.sha256(raw).hexdigest()}:
                    raise ValueError('cached reserve history URL/SHA changed')
            else:
                with urlopen(Request(url, headers={'Accept': 'application/json', 'Accept-Language': 'en-GB',
                        'User-Agent': 'Mozilla/5.0'}), timeout=25) as response:
                    raw = response.read()
                if len(raw) > 2 * 1024 * 1024:
                    raise ValueError('reserve history response exceeds bounded size')
                json.loads(raw)
                atomic_bytes(path, raw)
                pipeline.write_canonical_json(receipt, {'url': url, 'sha256': hashlib.sha256(raw).hexdigest()})
                time.sleep(1)
            records.append({'player_id': id, 'status': 'raw-history-parsed', 'source_url': url,
                'raw_path': registry.relative_workspace_path(path), 'raw_sha256': hashlib.sha256(raw).hexdigest(),
                'source_receipt_path': registry.relative_workspace_path(receipt), 'events': history.parse(json.loads(raw), id)})
        except Exception as exc:
            records.append({'player_id': id, 'status': 'source-history-gap', 'source_url': url, 'reason': str(exc)})
            if not path.exists():
                time.sleep(1)
        print(json.dumps({'completed': len(records), 'total': len(query['claims']), 'status': records[-1]['status']}), flush=True)
    if registry.sha256_file(query_path) != digest:
        raise ValueError('reserve history query changed during capture')
    pipeline.write_canonical_json(output, {'schema_version': history.SCHEMA, 'policy': history.POLICY,
        'query_input': {'path': registry.relative_workspace_path(query_path), 'sha256': digest}, 'players': records})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['discover', 'capture'])
    parser.add_argument('--plan-root', type=Path)
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--person-input', type=Path)
    parser.add_argument('--history-input', type=Path)
    parser.add_argument('--query-input', type=Path)
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'discover':
        discover(args.plan_root, args.source_root, args.person_input, args.history_input, args.output)
    else:
        capture(args.query_input, args.cache, args.output)
