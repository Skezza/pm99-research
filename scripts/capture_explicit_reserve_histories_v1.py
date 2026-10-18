#!/usr/bin/env python3
"""Fetch only explicit source-backed reserve IDs, reusing immutable originals.

No game/package writes. Claims must be full-name/DOB identities independently
replayed from the bound public person input; IDs never come from name guesses.
"""
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_published_transfer_history_v1 as original
from scripts import season_public_identity_and_history_inputs_v1 as public
from scripts import season_published_person_identity_v1 as people_source
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.season_art_transaction_v1 import atomic_bytes


def confirm_claims(claims, people):
    ids = set()
    for claim in claims:
        id = claim['source_player_id']
        if type(id) is not int or id <= 0 or id in ids:
            raise ValueError('reserve claims need unique positive provider IDs')
        observed = transfer.unique_person({'name': claim['name'],
            'facts': {'birth_date': claim['birth_date']}}, people)
        if observed is None or observed['source_player_id'] != id:
            raise ValueError('reserve claim lacks one original full-name/DOB identity')
        ids.add(id)
    return sorted(ids)


def capture(claims, people_path, cache, output):
    if output.exists():
        raise ValueError('reserve history ledger is immutable')
    binding = public.binding(people_path, people_source.POLICY)
    people, _, _ = public.merge_bound({}, {}, {'published_person_supplement': binding})
    results = []
    for id in confirm_claims(claims, people):
        url = original.BASE + str(id)
        path = cache / 'history' / f'{id}.json'
        receipt = path.with_suffix('.source.json')
        try:
            if path.exists():
                raw = path.read_bytes()
                if json.loads(receipt.read_text()) != {'url': url,
                        'sha256': hashlib.sha256(raw).hexdigest()}:
                    raise ValueError('cached reserve history URL/SHA differs')
            else:
                with urlopen(Request(url, headers={'Accept': 'application/json',
                        'User-Agent': 'Mozilla/5.0'}), timeout=25) as response:
                    if response.geturl() != url:
                        raise ValueError('reserve history redirected to another provider/identity')
                    raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    raise ValueError('reserve history exceeds bounded cache size')
                json.loads(raw)
                atomic_bytes(path, raw)
                pipeline.write_canonical_json(receipt, {'url': url,
                    'sha256': hashlib.sha256(raw).hexdigest()})
                time.sleep(1)
            row = {'player_id': id, 'status': 'raw-history-parsed', 'source_url': url,
                'raw_path': registry.relative_workspace_path(path),
                'raw_sha256': hashlib.sha256(raw).hexdigest(),
                'source_receipt_path': registry.relative_workspace_path(receipt),
                'events': original.parse(json.loads(raw), id)}
        except (ValueError, OSError) as exc:
            row = {'player_id': id, 'status': 'source-history-gap',
                'source_url': url, 'reason': str(exc)}
            if not path.exists():
                time.sleep(1)
        results.append(row)
        print(json.dumps({'player_id': id, 'status': row['status']}), flush=True)
    pipeline.write_canonical_json(output, {'schema_version': original.SCHEMA,
        'policy': original.POLICY, 'published_person_binding': binding,
        'request_scope': 'explicit original full-name/DOB reserve identities only',
        'claims': claims, 'players': results, 'native_games_modified': 0})
