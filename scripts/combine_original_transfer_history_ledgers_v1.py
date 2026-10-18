#!/usr/bin/env python3
"""Combine independently replayed original histories without choosing conflicts.

No network or game writes. Every input remains hash-bound; identical overlaps
are reused, contradictory chronologies stop the merge rather than being hidden.
"""
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_published_transfer_history_v1 as history


def original_key(row):
    return {key: row.get(key) for key in (
        'player_id', 'status', 'source_url', 'raw_sha256', 'events', 'reason')}


def combine(paths, output):
    if output.exists():
        raise ValueError('combined original history ledger is immutable')
    if not paths or len({path.resolve() for path in paths}) != len(paths):
        raise ValueError('distinct original history input ledgers are required')
    inputs, records = [], {}
    for path in paths:
        digest = registry.sha256_file(path)
        document = json.loads(path.read_text())
        history.merge({}, document)
        inputs.append({'path': registry.relative_workspace_path(path), 'sha256': digest})
        seen = set()
        for row in document['players']:
            id = row['player_id']
            if id in seen:
                raise ValueError('duplicate player ID within original history ledger')
            seen.add(id)
            if id in records and original_key(records[id]) != original_key(row):
                raise ValueError('overlapping original histories disagree')
            records.setdefault(id, copy.deepcopy(row))
    result = {'schema_version': history.SCHEMA, 'policy': history.POLICY,
        'input_ledgers': inputs, 'players': [records[id] for id in sorted(records)],
        'combined_original_ledgers_independently_replayed': True}
    history.merge({}, result)
    if any(registry.sha256_file(ROOT / item['path']) != item['sha256'] for item in inputs):
        raise ValueError('original history input changed during merge')
    pipeline.write_canonical_json(output, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = combine(args.input, args.output)
    print(json.dumps({'histories': len(result['players']), 'parsed': sum(
        row['status'] == 'raw-history-parsed' for row in result['players'])}))
