#!/usr/bin/env python3
"""Capture the public transfer history used by the publisher's own webpage.

Stable player IDs only; no profile/current-club inference or authentication.
One request per second, immutable raw responses and original URL/SHA receipts.
Supplement a pinned chronology only when no existing dated edge contradicts it.
"""
import argparse
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.season_art_transaction_v1 import atomic_bytes

BASE = 'https://tmapi.transfermarkt.technology/transfer/history/player/'
SCHEMA = 'pm99-public-original-player-transfer-history-v1'
POLICY = 'original-history-superset-of-pinned-dated-edges-v1'


def parse(document, player_id):
    data = document.get('data', {})
    if document.get('success') is not True or str(data.get('playerId')) != str(player_id):
        raise ValueError('original history does not identify the requested player')
    history = data.get('history')
    if not isinstance(history, dict) or not isinstance(history.get('terminated'), list):
        raise ValueError('original history lacks a terminated transfer list')
    ids, events = set(), []
    for row in history['terminated']:
        details = row['details']
        if str(details['playerId']) != str(player_id) or details.get('isPending') is not False:
            raise ValueError('transfer row player or completion status disagrees')
        id = str(row['id'])
        if not id.isdigit() or id in ids or not re.search(
                rf'/spieler/{int(player_id)}/transfer_id/{int(id)}(?:/|$)', row['relativeUrl']):
            raise ValueError('transfer row identity is ambiguous or inconsistent')
        ids.add(id)
        when = dt.datetime.fromisoformat(details['date'])
        if when.tzinfo is None:
            raise ValueError('original transfer timestamp lacks its published timezone')
        before, after = str(row['transferSource']['clubId']), str(row['transferDestination']['clubId'])
        if not before.isdigit() or not after.isdigit():
            raise ValueError('original transfer has an unpublished club ID')
        events.append({'date': when.date().isoformat(), 'from_club_id': int(before),
            'to_club_id': int(after), 'from_club': 'published-club-id:' + before,
            'to_club': 'published-club-id:' + after})
    for pending in history.get('pending', []):
        details = pending['details']
        if str(details['playerId']) != str(player_id):
            raise ValueError('pending row identifies another person')
        # Pending records in a historical game period make the snapshot
        # incomplete. Do not silently treat them as completed transfers.
        if dt.datetime.fromisoformat(details['date']).date() <= dt.date(2025, 12, 31):
            raise ValueError('unconfirmed historical pending transfer prevents chronology proof')
    return sorted(events, key=lambda e: e['date'])


def merge(events, supplement):
    if supplement.get('schema_version') != SCHEMA or supplement.get('policy') != POLICY:
        raise ValueError('unsupported original transfer-history supplement')
    result = {id: list(rows) for id, rows in events.items()}
    accepted, refused = [], []
    for record in supplement['players']:
        if record['status'] != 'raw-history-parsed':
            refused.append({'player_id': record['player_id'], 'reason': record['status']})
            continue
        id = record['player_id']
        path = ROOT / record['raw_path']
        if registry.sha256_file(path) != record['raw_sha256']:
            raise ValueError('original public transfer response changed')
        expected_url = BASE + str(id)
        if record['source_url'] != expected_url:
            raise ValueError('transfer response is not bound to the original publisher/player')
        metadata = json.loads((ROOT / record['source_receipt_path']).read_text())
        if metadata != {'url': expected_url, 'sha256': record['raw_sha256']}:
            raise ValueError('original transfer response URL/SHA receipt changed')
        rows = parse(json.loads(path.read_text()), id)
        if rows != record['events']:
            raise ValueError('saved transfer chronology differs from original response')
        def edge(e):
            return (e['date'], e['from_club_id'], e['to_club_id'])
        prior = collections.Counter(edge(e) for e in events.get(id, []))
        current = collections.Counter(edge(e) for e in rows)
        if prior - current:
            refused.append({'player_id': id, 'reason': 'original-history-conflicts-with-a-pinned-dated-edge'})
            continue
        result[id] = rows
        accepted.append(id)
    return result, {'accepted_player_ids': accepted, 'refused': refused}


def repaired_club_plan_ids(path):
    """Fetch only published matchday people in an independently repaired XI.

    A club-transaction proposal does not itself authorise roster edits. Its
    exact original earliest fixture is replayed before broadening the read-only
    query scope beyond the ordinary unresolved-duplicate plans.
    """
    from scripts import repair_prefix_selected_opening_sources_v1 as repair
    plan = json.loads(path.read_text())
    if plan.get('schema_version') != 'pm99-source-repaired-opening-club-roster-plan-v1':
        raise ValueError('unsupported source-repaired club plan')
    binding = plan['bindings']
    source_path = ROOT / binding['source_correction_path']
    if registry.sha256_file(source_path) != binding['source_correction_sha256']:
        raise ValueError('club original source correction changed')
    correction = json.loads(source_path.read_text())
    if (correction['club'], correction['carrier_id']) != (plan['club'], plan['carrier_id']):
        raise ValueError('club source correction identifies another club')
    original_path = ROOT / correction['original_capture_path']
    if registry.sha256_file(original_path) != correction['original_capture_sha256']:
        raise ValueError('club original capture changed')
    corrected, evidence, _ = repair.replay(correction['before'],
        json.loads(original_path.read_text()), original_path.parent / 'cache')
    if corrected != correction['after']:
        raise ValueError('club repaired original report does not reproduce')
    people = set(map(int, evidence['starting_xi'])) | set(map(int, evidence['substitutes']))
    if people != {r['source_player_id'] for r in plan['desired_matchday_people']}:
        raise ValueError('club plan people differ from original matchday IDs')
    return {r['source_player_id'] for r in plan['desired_matchday_people']
            if r['requires_new_club_slot'] and r['other_club_player_ids']}


def capture(plan_roots, cache, output, club_plans=()):
    if output.exists():
        raise ValueError('transfer history supplement is immutable')
    claims, plans = set(), []
    for root in plan_roots:
        for path in sorted(root.glob('*/ownership-plan.json')):
            plan = json.loads(path.read_text())
            plans.append({'path': registry.relative_workspace_path(path), 'sha256': registry.sha256_file(path)})
            for row in plan['unresolved']:
                person = row.get('identity', {}).get('source_person')
                if person is not None:
                    claims.add(person['source_player_id'])
    for path in club_plans:
        claims.update(repaired_club_plan_ids(path))
        plans.append({'path': registry.relative_workspace_path(path), 'sha256': registry.sha256_file(path),
                      'scope': 'independently replayed repaired-club matchday people with other-club copies'})
    return capture_ids(claims, cache, output, plans,
        'stable published IDs from unresolved duplicate-ownership plans and independently replayed repaired-club matchday people'
        if club_plans else 'stable published IDs from unresolved duplicate-ownership plans only')


def capture_ids(claims, cache, output, plans, scope):
    """Acquisition only: callers must derive exact IDs from original evidence.

    This function cannot authorise ownership or native writes. The existing
    merge independently replays receipts and rejects conflicts with the pin.
    """
    if output.exists():
        raise ValueError('transfer history supplement is immutable')
    if any(type(id) is not int or id < 1 for id in claims):
        raise ValueError('history acquisition requires explicit positive publisher IDs')
    results = []
    for id in sorted(claims):
        url = BASE + str(id)
        path = cache / 'history' / f'{id}.json'
        receipt = path.with_suffix('.source.json')
        try:
            if path.exists():
                raw = path.read_bytes()
                binding = json.loads(receipt.read_text())
                if binding != {'url': url, 'sha256': hashlib.sha256(raw).hexdigest()}:
                    raise ValueError('cached response URL/SHA changed')
            else:
                request = Request(url, headers={'Accept': 'application/json',
                    'Accept-Language': 'en-GB', 'User-Agent': 'Mozilla/5.0'})
                with urlopen(request, timeout=25) as response:
                    raw = response.read()
                if len(raw) > 2 * 1024 * 1024:
                    raise ValueError('public history response exceeds the bounded cache size')
                # Preserve even an unparseable original response as a logged
                # gap; never retry a successful raw fetch to get nicer data.
                json.loads(raw)
                atomic_bytes(path, raw)
                pipeline.write_canonical_json(receipt, {'url': url, 'sha256': hashlib.sha256(raw).hexdigest()})
                time.sleep(1)
            events = parse(json.loads(raw), id)
            row = {'player_id': id, 'status': 'raw-history-parsed',
                'source_url': url, 'raw_path': registry.relative_workspace_path(path),
                'raw_sha256': hashlib.sha256(raw).hexdigest(),
                'source_receipt_path': registry.relative_workspace_path(receipt), 'events': events}
        except Exception as exc:
            row = {'player_id': id, 'status': 'source-history-gap', 'source_url': url,
                   'reason': str(exc)}
            if not path.exists():
                time.sleep(1)
        results.append(row)
        print(json.dumps({'player_id': id, 'status': row['status'],
            'completed': len(results), 'total': len(claims)}), flush=True)
    pipeline.write_canonical_json(output, {'schema_version': SCHEMA, 'policy': POLICY,
        'source': 'Transfermarkt public history service used by its player-transfer-history component',
        'request_scope': scope,
        'input_plans': plans, 'players': results})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-root', action='append', type=Path, default=[])
    parser.add_argument('--club-plan', action='append', type=Path, default=[])
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.plan_root and not args.club_plan:
        parser.error('at least one --plan-root or --club-plan is required')
    capture(args.plan_root, args.cache, args.output, args.club_plan)
