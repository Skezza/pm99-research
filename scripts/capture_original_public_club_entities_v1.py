#!/usr/bin/env python3
"""Cache explicit publisher club IDs/names for discovery, not season approval.

Ignore contemporary leagues, squads, managers, kits, market values and images.
Historical ownership still requires independent dated originals. Query IDs
originate in the separately recorded original transfer-history discovery.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts.season_art_transaction_v1 import atomic_bytes

BASE = 'https://tmapi.transfermarkt.technology/clubs'


def url(ids):
    return BASE + '?' + urlencode([('ids[]', str(i)) for i in ids])


def parse(original, requested):
    if original.get('success') is not True or not isinstance(original.get('data'), list):
        raise ValueError('original club endpoint lacks explicit entity list')
    rows, seen = [], set()
    for entity in original['data']:
        if not str(entity.get('id', '')).isdigit():
            raise ValueError('original club entity has no numeric identity')
        id = int(entity['id'])
        if id not in requested or id in seen:
            raise ValueError('original club response repeats or introduces unrequested ID')
        seen.add(id)
        details = entity.get('baseDetails')
        if not isinstance(details, dict) or not isinstance(entity.get('name'), str) or not entity['name'].strip():
            raise ValueError('original club lacks published name/base identity')
        names = [entity['name'].strip()]
        short = details.get('shortName')
        if isinstance(short, str) and short.strip() and short.strip() not in names:
            names.append(short.strip())
        rows.append({'source_club_id': id, 'published_names': names,
            'country_id': details.get('countryId'), 'main_club_id': details.get('mainClubId'),
            'is_national_team': details.get('isNationalTeam'), 'club_type_id': details.get('clubTypeId'),
            'historical_name_membership_or_ownership_approval': False})
    return rows, sorted(set(requested) - seen)


def run(discovery, cache, output):
    if output.exists():
        raise ValueError('public club discovery capture is immutable')
    original = json.loads(discovery.read_text())
    if original.get('schema_version') != 'pm99-original-history-club-query-discovery-v1':
        raise ValueError('unsupported original historical query discovery')
    ids = original['query_club_ids']
    if ids != sorted(set(ids)) or any(type(i) is not int or i < 1 for i in ids):
        raise ValueError('club query IDs must be exact unique positive integers')
    batches = []
    for start in range(0, len(ids), 100):
        requested = ids[start:start + 100]
        endpoint = url(requested)
        key = hashlib.sha256(endpoint.encode()).hexdigest()
        path, receipt = cache / (key + '.json'), cache / (key + '.source.json')
        if path.exists():
            raw = path.read_bytes()
            if json.loads(receipt.read_text()) != {'url': endpoint, 'sha256': hashlib.sha256(raw).hexdigest()}:
                raise ValueError('original public club receipt changed')
        else:
            if receipt.exists():
                raise ValueError('original club receipt lacks its response')
            with urlopen(Request(endpoint, headers={'User-Agent': 'PM99 historical football research',
                    'Accept': 'application/json'}), timeout=25) as response:
                raw = response.read(3 * 1024**2 + 1)
            if len(raw) > 3 * 1024**2:
                raise ValueError('original club response exceeds bounded size')
            json.loads(raw)
            atomic_bytes(path, raw)
            pipeline.write_canonical_json(receipt, {'url': endpoint, 'sha256': hashlib.sha256(raw).hexdigest()})
            time.sleep(1)
        entities, missing = parse(json.loads(raw), requested)
        batches.append({'requested_ids': requested, 'entities': entities, 'missing_ids': missing,
            'raw_path': registry.relative_workspace_path(path), 'raw_sha256': registry.sha256_file(path),
            'source_url': endpoint, 'receipt_path': registry.relative_workspace_path(receipt)})
        print(json.dumps({'captured_club_identities': len(entities), 'gaps': len(missing)}), flush=True)
    result = {'schema_version': 'pm99-original-public-club-entity-discovery-v1', 'batches': batches,
        'discovery': {'path': registry.relative_workspace_path(discovery), 'sha256': registry.sha256_file(discovery)},
        'native_corrections': 0, 'historical_roster_approval': False, 'credits': ['Transfermarkt']}
    output.parent.mkdir(parents=True, exist_ok=True)
    pipeline.write_canonical_json(output, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--discovery', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.discovery, args.cache, args.output)
