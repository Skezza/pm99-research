#!/usr/bin/env python3
"""Recover retired player identities from the publisher's public person feed.

Use only stable ID, published full/short names and confirmed DOB. Ignore current
clubs, citizenship, positions, shirt numbers, ratings and contemporary photos.
IDs originate in hash-bound original historical opening-match reports.
"""
import argparse
import collections
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts.season_art_transaction_v1 import atomic_bytes

BASE = 'https://tmapi.transfermarkt.technology/players'
SCHEMA = 'pm99-original-published-person-identities-v1'
POLICY = 'published-full-and-short-name-exact-confirmed-DOB-no-current-facts-v1'


def url(ids):
    return BASE + '?' + urlencode([('ids[]', str(id)) for id in ids])


def parse(document, requested):
    if document.get('success') is not True or not isinstance(document.get('data'), list):
        raise ValueError('original player response lacks an entity list')
    people, gaps, seen = [], [], set()
    for raw in document['data']:
        if not str(raw.get('id', '')).isdigit():
            raise ValueError('original entity has no published numeric person ID')
        id = int(raw['id'])
        if id not in requested or id in seen:
            raise ValueError('unexpected or duplicate published player ID')
        seen.add(id)
        dates = raw.get('lifeDates', {})
        dob = dates.get('dateOfBirth')
        if dates.get('isDateOfBirthUnknown') is not False or not isinstance(dob, str):
            gaps.append({'player_id': id, 'reason': 'original-DOB-unpublished-or-unconfirmed'})
            continue
        dt.date.fromisoformat(dob)
        if not re.search(rf'/profil/spieler/{id}(?:/|$)', raw.get('relativeUrl', '')):
            raise ValueError('published profile URL identifies a different person')
        name = raw.get('name')
        if not isinstance(name, str) or not name.strip():
            raise ValueError('published player entity has no full name')
        aliases = {name.strip()}
        for field in ('shortName', 'artistName', 'displayName'):
            value = raw.get(field)
            if isinstance(value, str) and value.strip():
                aliases.add(value.strip())
        # Explicitly named public aliases are not an AI initial expansion.
        people.append({'source_player_id': id, 'name': name.strip(), 'given_name': None,
            'family_name': None, 'birth_date': dob, 'published_name_variants': sorted(aliases),
            'source_profile_url': 'https://www.transfermarkt.co.uk' + raw['relativeUrl']})
    gaps += [{'player_id': id, 'reason': 'original-player-entity-unpublished'} for id in sorted(set(requested) - seen)]
    return people, gaps


def merge(index, supplement):
    if supplement.get('schema_version') != SCHEMA or supplement.get('policy') != POLICY:
        raise ValueError('unsupported original person-identity supplement')
    result = {key: dict(values) for key, values in index.items()}
    known = collections.defaultdict(dict)
    for rows in index.values():
        for id, person in rows.items():
            known[id][person['birth_date']] = person
    accepted, refused = [], []
    for row in supplement['batches']:
        if row['status'] != 'original-entities-parsed':
            continue
        path = ROOT / row['raw_path']
        if registry.sha256_file(path) != row['raw_sha256']:
            raise ValueError('original person response changed')
        if row['source_url'] != url(row['requested_ids']):
            raise ValueError('original person endpoint or requested IDs differ')
        metadata = json.loads((ROOT / row['source_receipt_path']).read_text())
        if metadata != {'url': row['source_url'], 'sha256': row['raw_sha256']}:
            raise ValueError('original person URL/SHA receipt differs')
        parsed, gaps = parse(json.loads(path.read_text()), row['requested_ids'])
        if parsed != row['people'] or gaps != row['gaps']:
            raise ValueError('saved identities do not reproduce from original entities')
        for person in parsed:
            id, dob = person['source_player_id'], person['birth_date']
            if known.get(id) and set(known[id]) != {dob}:
                refused.append({'player_id': id, 'reason': 'original-DOB-conflicts-with-pinned-person'})
                continue
            canonical = copy.deepcopy(known[id][dob]) if known.get(id) else {
                k: v for k, v in person.items() if k != 'published_name_variants'}
            for alias in person['published_name_variants']:
                result.setdefault((transfer._normalise(alias), dob), {})[id] = canonical
            accepted.append(id)
    return result, {'accepted_player_ids': accepted, 'refused': refused,
                   'current_attributes_or_ownership_used': False}


def capture(opening_paths, cache, output, prior_path=None):
    if output.exists():
        raise ValueError('person evidence is immutable')
    ids, inputs = set(), []
    for path in opening_paths:
        document = json.loads(path.read_text())
        transfer.verify_opening_sources(document)
        inputs.append({'path': registry.relative_workspace_path(path), 'sha256': registry.sha256_file(path)})
        for row in document['clubs']:
            if row['status'] == 'original-first-fixture-reparsed':
                for field in ('starting_xi', 'substitutes'):
                    ids.update(int(id) for id in row['evidence'][field])
    batches, prior_binding = [], None
    if prior_path is not None:
        prior_digest = registry.sha256_file(prior_path)
        prior = json.loads(prior_path.read_text())
        # Reparse every retained original URL/SHA response. A saved parsed
        # identity alone is not sufficient evidence for incremental reuse.
        merge({}, prior)
        batches = copy.deepcopy([row for row in prior['batches']
                                 if row['status'] == 'original-entities-parsed'])
        covered = {id for row in batches for id in row['requested_ids']}
        ids.difference_update(covered)
        prior_binding = {'path': registry.relative_workspace_path(prior_path),
                         'sha256': prior_digest, 'raw_responses_independently_replayed': True}
    ordered = sorted(ids)
    for offset in range(0, len(ordered), 100):
        wanted = ordered[offset:offset + 100]
        source_url = url(wanted)
        key = hashlib.sha256(source_url.encode()).hexdigest()
        path = cache / 'people' / (key + '.json')
        receipt = path.with_suffix('.source.json')
        try:
            if path.exists():
                raw = path.read_bytes()
                if json.loads(receipt.read_text()) != {'url': source_url, 'sha256': hashlib.sha256(raw).hexdigest()}:
                    raise ValueError('cached original people URL/SHA changed')
            else:
                with urlopen(Request(source_url, headers={'Accept': 'application/json',
                        'Accept-Language': 'en-GB', 'User-Agent': 'Mozilla/5.0'}), timeout=25) as response:
                    raw = response.read()
                if len(raw) > 3 * 1024 * 1024:
                    raise ValueError('original entity batch exceeds bounded size')
                json.loads(raw)
                atomic_bytes(path, raw)
                pipeline.write_canonical_json(receipt, {'url': source_url, 'sha256': hashlib.sha256(raw).hexdigest()})
                time.sleep(1)
            people, gaps = parse(json.loads(raw), wanted)
            row = {'status': 'original-entities-parsed', 'requested_ids': wanted,
                'source_url': source_url, 'raw_path': registry.relative_workspace_path(path),
                'raw_sha256': hashlib.sha256(raw).hexdigest(),
                'source_receipt_path': registry.relative_workspace_path(receipt), 'people': people, 'gaps': gaps}
        except Exception as exc:
            row = {'status': 'original-person-source-gap', 'requested_ids': wanted,
                   'source_url': source_url, 'reason': str(exc)}
            time.sleep(1)
        batches.append(row)
        print(json.dumps({'offset': offset, 'requested_people': len(ordered),
            'status': row['status'], 'confirmed': len(row.get('people', [])),
            'gaps': len(row.get('gaps', []))}), flush=True)
    if prior_binding is not None and registry.sha256_file(prior_path) != prior_binding['sha256']:
        raise ValueError('prior public person ledger changed during incremental capture')
    result = {'schema_version': SCHEMA, 'policy': POLICY,
        'historical_opening_inputs': inputs, 'batches': batches,
        'discarded_fields': ['current club', 'nationality', 'positions', 'shirt number',
                             'market value', 'ratings', 'contemporary portrait']}
    if prior_binding is not None:
        result['reused_original_person_ledger'] = prior_binding
    pipeline.write_canonical_json(output, result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--opening-root', type=Path, required=True)
    parser.add_argument('--supplemental-opening', type=Path)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prior-ledger', type=Path,
                        help='replay existing original responses and fetch only newly sourced player IDs')
    args = parser.parse_args()
    paths = [args.opening_root / season / 'opening-review.json' for season in registry.supported_seasons()]
    if args.supplemental_opening:
        paths.append(args.supplemental_opening)
    capture(paths, args.cache, args.output, args.prior_ledger)
