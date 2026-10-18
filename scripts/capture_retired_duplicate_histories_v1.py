#!/usr/bin/env python3
"""Extend transfer evidence for newly confirmed retired duplicate identities.

Only exact source-name/DOB joins from immutable unresolved plans are queried.
Never fabricate an ownership plan to request an API record. Existing bound
raw responses are reused, and already-known IDs are excluded so an active
first history capture cannot race this extension.
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
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_published_person_identity_v1 as people_source
from scripts import season_published_transfer_history_v1 as history
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.season_art_transaction_v1 import atomic_bytes


def requests_from_plans(documents, people):
    known, claims = set(), {}
    for document in documents:
        for row in document['unresolved']:
            person = row.get('identity', {}).get('source_person')
            if person:
                known.add(person['source_player_id'])
    for document in documents:
        for row in document['unresolved']:
            claim = row.get('identity', {})
            if claim.get('source_person') or not claim.get('source_name'):
                continue
            person = transfer.unique_person({'name': claim['source_name'],
                'facts': {'birth_date': claim.get('birth_date')}}, people)
            if person is None or person['source_player_id'] in known:
                continue
            claims.setdefault(person['source_player_id'], []).append({
                'season': document['season'], 'source_name': claim['source_name'],
                'birth_date': claim.get('birth_date'), 'source_person': person})
    return claims


def capture(plan_roots, person_path, cache, output):
    if output.exists():
        raise ValueError('retired history evidence is immutable')
    paths = sorted({p for root in plan_roots for p in root.glob('*/ownership-plan.json')})
    input_plans = [{'path': registry.relative_workspace_path(p), 'sha256': registry.sha256_file(p)} for p in paths]
    person_digest = registry.sha256_file(person_path)
    documents = [json.loads(p.read_text()) for p in paths]
    people, _, _, pin = transfer.load_snapshot(
        ROOT / '.local/external-sources/transfermarkt-datasets/transfermarkt-datasets.duckdb',
        ROOT / '.local/season-pipeline-v2/world-2015-transfermarkt-opening-fixtures-20260831.json')
    people, merge_report = people_source.merge(people, json.loads(person_path.read_text()))
    claims = requests_from_plans(documents, people)
    results = []
    for id in sorted(claims):
        url = history.BASE + str(id)
        path = cache / 'history' / f'{id}.json'
        receipt = path.with_suffix('.source.json')
        try:
            if path.exists():
                raw = path.read_bytes()
                if json.loads(receipt.read_text()) != {'url': url, 'sha256': hashlib.sha256(raw).hexdigest()}:
                    raise ValueError('cached retired history URL/SHA changed')
            else:
                with urlopen(Request(url, headers={'Accept': 'application/json',
                        'Accept-Language': 'en-GB', 'User-Agent': 'Mozilla/5.0'}), timeout=25) as response:
                    raw = response.read()
                if len(raw) > 2 * 1024 * 1024:
                    raise ValueError('retired response exceeds bounded cache size')
                json.loads(raw)
                atomic_bytes(path, raw)
                pipeline.write_canonical_json(receipt, {'url': url, 'sha256': hashlib.sha256(raw).hexdigest()})
                time.sleep(1)
            row = {'player_id': id, 'status': 'raw-history-parsed', 'source_url': url,
                'raw_path': registry.relative_workspace_path(path),
                'raw_sha256': hashlib.sha256(raw).hexdigest(),
                'source_receipt_path': registry.relative_workspace_path(receipt),
                'events': history.parse(json.loads(raw), id)}
        except Exception as exc:
            row = {'player_id': id, 'status': 'source-history-gap', 'source_url': url, 'reason': str(exc)}
            if not path.exists():
                time.sleep(1)
        results.append(row)
        print(json.dumps({'completed': len(results), 'total': len(claims),
                          'player_id': id, 'status': row['status']}), flush=True)
    if (registry.sha256_file(person_path) != person_digest or
            any(registry.sha256_file(ROOT / item['path']) != item['sha256'] for item in input_plans)):
        raise ValueError('retired history query inputs changed during capture')
    pipeline.write_canonical_json(output, {'schema_version': history.SCHEMA, 'policy': history.POLICY,
        'request_scope': 'Newly confirmed retired identities from original unresolved source-name/DOB claims only',
        'snapshot': pin, 'person_input': {'path': registry.relative_workspace_path(person_path),
            'sha256': person_digest},
        'input_plans': input_plans,
        'person_merge_refusals': merge_report['refused'], 'identity_query_claims': claims, 'players': results})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-root', action='append', type=Path, required=True)
    parser.add_argument('--person-input', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    capture(args.plan_root, args.person_input, args.cache, args.output)
