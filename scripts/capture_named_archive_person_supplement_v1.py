#!/usr/bin/env python3
"""Resolve named archive biography gaps with original public person entities.

Discovery profile URLs supply query IDs only. Approval requires the publisher's
original entity ID, explicit full-name variant and confirmed birth date to agree
with the independently captured archive biography. No current attributes used.
Prior immutable responses are replayed, never fetched again or overwritten.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_11v11_opening_source_v1 as archive
from scripts import season_published_person_identity_v1 as source
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts.season_art_transaction_v1 import atomic_bytes


def validate_person(person, biography):
    if (person['birth_date'] != biography['birth_date'] or
            archive.normalise(biography['name']) not in
            {archive.normalise(n) for n in person['published_name_variants']}):
        raise ValueError('original published person ID/name/DOB conflicts with the named original archive biography')


def run(review_path, prior_path, queries, cache, output):
    if output.exists():
        raise ValueError('named archive person supplement is immutable')
    review = json.loads(review_path.read_text())
    if review['schema_version'] != 'pm99-original-11v11-opening-bridge-review-v1':
        raise ValueError('unsupported named archive bridge review')
    missing = {r['archive_player']['source_player_id']: r for r in review['players']
               if r['status'] == 'original-archive-identity-gap'}
    if set(queries) != set(missing) or len({id for id, _ in queries.values()}) != len(queries):
        raise ValueError('named queries must cover exactly the unresolved original archive biographies')
    prior_sha = registry.sha256_file(prior_path)
    prior = json.loads(prior_path.read_text())
    source.merge({}, prior)
    already = {id for row in prior['batches'] for id in row['requested_ids']}
    if already & {id for id, _ in queries.values()}:
        raise ValueError('named archive identities were already queried; replay their original response instead')
    biographies = {}
    for archive_id, (id, discovery_url) in queries.items():
        if not re.fullmatch(rf'https://www\.transfermarkt\.(?:com|co\.uk)/[^/?#]+/profil/spieler/{id}', discovery_url):
            raise ValueError('named query discovery URL does not identify its exact public publisher ID')
        row = missing[archive_id]
        original = row['original_biography']
        path = ROOT / original['path']
        if registry.sha256_file(path) != original['sha256'] or json.loads((ROOT / original['receipt_path']).read_text()) != {
                'url': original['url'], 'sha256': original['sha256']}:
            raise ValueError('named original archive biography URL/hash changed')
        biographies[id] = archive.profile_person(path.read_bytes(), row['archive_player'])
    ids = sorted(biographies)
    url = source.url(ids)
    key = hashlib.sha256(url.encode()).hexdigest()
    path, receipt = cache / 'people' / (key + '.json'), cache / 'people' / (key + '.source.json')
    if path.exists():
        raw = path.read_bytes()
        if json.loads(receipt.read_text()) != {'url': url, 'sha256': hashlib.sha256(raw).hexdigest()}:
            raise ValueError('original named person response receipt changed')
    else:
        if receipt.exists():
            raise ValueError('original named person receipt lacks its response')
        with urlopen(Request(url, headers={'Accept': 'application/json', 'Accept-Language': 'en-GB',
                'User-Agent': 'PM99 historical football research'}), timeout=25) as response:
            raw = response.read(3 * 1024 * 1024 + 1)
        if len(raw) > 3 * 1024 * 1024:
            raise ValueError('original named person batch exceeds bounded size')
        json.loads(raw)
        atomic_bytes(path, raw)
        pipeline.write_canonical_json(receipt, {'url': url, 'sha256': hashlib.sha256(raw).hexdigest()})
        time.sleep(1)
    people, gaps = source.parse(json.loads(raw), ids)
    if gaps or {p['source_player_id'] for p in people} != set(ids):
        raise ValueError('named original archive identity query lacks confirmed public entities')
    for person in people:
        validate_person(person, biographies[person['source_player_id']])
    result = copy.deepcopy(prior)
    result['batches'].append({'status': 'original-entities-parsed', 'requested_ids': ids,
        'source_url': url, 'raw_path': registry.relative_workspace_path(path),
        'raw_sha256': registry.sha256_file(path), 'source_receipt_path': registry.relative_workspace_path(receipt),
        'people': people, 'gaps': gaps})
    result['reused_original_person_ledger'] = {'path': registry.relative_workspace_path(prior_path),
        'sha256': prior_sha, 'raw_responses_independently_replayed': True}
    result['named_original_archive_inputs'] = {'path': registry.relative_workspace_path(review_path),
        'sha256': registry.sha256_file(review_path),
        'queries': [{'archive_id': aid, 'query_player_id': id, 'discovery_profile_url': url,
                    'original_archive_person': biographies[id]} for aid, (id, url) in sorted(queries.items())],
        'discovery_urls_supply_queries_not_historical_membership': True}
    source.merge({}, result)
    if registry.sha256_file(prior_path) != prior_sha:
        raise ValueError('prior original public person ledger changed during named capture')
    output.parent.mkdir(parents=True, exist_ok=True)
    pipeline.write_canonical_json(output, result)
    print(json.dumps({'new_confirmed_named_archive_people': len(people), 'new_requests': 1,
                      'original_person_ids': ids, 'native_corrections': 0}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-review', type=Path, required=True)
    parser.add_argument('--prior-ledger', type=Path, required=True)
    parser.add_argument('--person', action='append', required=True, help='ARCHIVE_ID=QUERY_ID=DISCOVERED_PROFILE_URL')
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    queries = {}
    for value in args.person:
        aid, id, url = value.split('=', 2)
        if aid in queries:
            parser.error('duplicate original archive identity query')
        queries[aid] = int(id), url
    run(args.archive_review, args.prior_ledger, queries, args.cache, args.output)
