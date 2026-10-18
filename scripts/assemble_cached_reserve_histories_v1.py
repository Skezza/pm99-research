#!/usr/bin/env python3
"""Freeze already fetched original reserve histories without refetching them.

Each person's public response is complete even when the overall request queue
is still running. A partial queue is explicit, never absence/ownership proof.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_published_transfer_history_v1 as history


def cached_record(id, cache):
    path = cache / 'history' / f'{id}.json'
    receipt = path.with_suffix('.source.json')
    if not path.is_file() or not receipt.is_file():
        return None
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    url = history.BASE + str(id)
    if json.loads(receipt.read_text()) != {'url': url, 'sha256': digest}:
        raise ValueError('cached reserve original URL/SHA differs')
    try:
        events = history.parse(json.loads(raw), id)
    except (ValueError, KeyError, TypeError) as exc:
        return {'player_id': id, 'status': 'source-history-gap', 'source_url': url,
                'reason': str(exc), 'raw_path': registry.relative_workspace_path(path), 'raw_sha256': digest}
    return {'player_id': id, 'status': 'raw-history-parsed', 'source_url': url,
        'raw_path': registry.relative_workspace_path(path), 'raw_sha256': digest,
        'source_receipt_path': registry.relative_workspace_path(receipt), 'events': events}


def assemble(query_path, prior_path, cache, output):
    if output.exists():
        raise ValueError('combined history supplement is immutable')
    inputs = {k: {'path': registry.relative_workspace_path(p), 'sha256': registry.sha256_file(p)}
              for k, p in [('reserve_queries', query_path), ('prior_histories', prior_path)]}
    query = json.loads(query_path.read_text())
    if query.get('schema_version') != 'pm99-unused-opening-reserve-history-requests-v1':
        raise ValueError('unsupported reserve query ledger')
    prior = json.loads(prior_path.read_text())
    history.merge({}, prior)
    records = {row['player_id']: row for row in prior['players']}
    unfetched, captured = [], []
    for key in sorted(query['claims'], key=int):
        id = int(key)
        if any(row['source_person']['source_player_id'] != id for row in query['claims'][key]):
            raise ValueError('reserve query identifies a different person')
        row = cached_record(id, cache)
        if row is None:
            unfetched.append(id)
            continue
        if id in records and records[id] != row:
            raise ValueError('overlapping original history records disagree')
        records[id] = row
        captured.append(id)
    result = {'schema_version': history.SCHEMA, 'policy': history.POLICY,
        'input_ledgers': inputs, 'players': [records[id] for id in sorted(records)],
        'reserve_request_queue': {'captured': len(captured), 'unfetched': len(unfetched),
                                  'unfetched_player_ids': unfetched,
                                  'partial_queue_is_not_absence_or_ownership_proof': True}}
    history.merge({}, result)
    for item in inputs.values():
        if registry.sha256_file(ROOT / item['path']) != item['sha256']:
            raise ValueError('combined history inputs changed')
    pipeline.write_canonical_json(output, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--query-input', type=Path, required=True)
    parser.add_argument('--prior-input', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = assemble(args.query_input, args.prior_input, args.cache, args.output)
    print(json.dumps({'histories': len(result['players']), **{
        k: v for k, v in result['reserve_request_queue'].items() if k != 'unfetched_player_ids'}}))
