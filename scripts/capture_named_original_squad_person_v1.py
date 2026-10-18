#!/usr/bin/env python3
"""Confirm a discovered stable person ID against an original annual name/DOB.

The discovery URL only scopes a query. Full name, confirmed DOB and numeric
identity must independently agree in original publisher bytes. No current
attributes, opening membership or native publication are approved here.
"""
import argparse
import copy
import json
import hashlib
from pathlib import Path
import re
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts import prepare_duplicate_club_disposition_v1 as whole
from scripts import capture_ntf_historical_carrier_squads_v1 as acquisition
from scripts import capture_named_archive_person_supplement_v1 as named
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.season_art_transaction_v1 import atomic_bytes


def run(plan_path, season, club, name, discovery_url, output):
    if output.exists():
        raise ValueError('named original squad identity supplement is immutable')
    found = re.fullmatch(r'https://www\.transfermarkt\.(?:com|co\.uk)/[^/?#]+/profil/spieler/(\d+)', discovery_url)
    if not found:
        raise ValueError('discovery URL must identify one explicit publisher profile')
    id = int(found.group(1))
    captures, _ = whole.roster.load_sources(season)
    annuals = [c for c in captures if c['source_path'].endswith('.txt')
        and whole.roster.source_group(c['country_catalog']) == 'england'
        and whole.club_keys(club) & whole.club_keys(c['club_name'])]
    if len(annuals) != 1:
        raise ValueError('named identity requires one exact original annual squad')
    annual = annuals[0]; proof = whole.roster.SourceVerifier(season).verify(annual)
    if proof['status'] != 'raw-source-reparsed':
        raise ValueError('original annual squad did not independently reparse')
    people = [p for p in annual['players'] if whole.roster.normalise(p['name']) == whole.roster.normalise(name)]
    if len(people) != 1 or not isinstance(people[0].get('birth_date'), str):
        raise ValueError('named original squad lacks one exact confirmed name/DOB')
    plan = json.loads(plan_path.read_text()); old_binding = plan['bindings']['published_person_supplement']
    old_path = ROOT / old_binding['path']
    if registry.sha256_file(old_path) != old_binding['sha256']:
        raise ValueError('prior original person ledger changed')
    prior = json.loads(old_path.read_text()); whole.persons.merge({}, prior)
    if id in {i for b in prior['batches'] for i in b['requested_ids']}:
        raise ValueError('person already queried; reuse the retained publisher response')
    url = whole.persons.url([id]); path = output.parent / 'raw' / f'person-{id}.json'
    receipt = path.with_name(path.name + '.source.json')
    if path.exists():
        raw = path.read_bytes()
        if json.loads(receipt.read_text()) != {'url': url, 'sha256': hashlib.sha256(raw).hexdigest()}:
            raise ValueError('original named entity URL/SHA receipt changed')
    else:
        with urlopen(Request(url, headers={'Accept': 'application/json',
                'User-Agent': 'PM99 historical football research'}), timeout=25) as response:
            raw = response.read(3 * 1024**2 + 1)
        if len(raw) > 3 * 1024**2:
            raise ValueError('original entity response exceeds bounded size')
        json.loads(raw); atomic_bytes(path, raw)
        pipeline.write_canonical_json(receipt, {'url': url, 'sha256': hashlib.sha256(raw).hexdigest()})
        time.sleep(1)
    confirmed, gaps = whole.persons.parse(json.loads(raw), [id])
    if gaps or len(confirmed) != 1:
        raise ValueError('publisher did not confirm the exact queried identity')
    named.validate_person(confirmed[0], people[0])
    result = copy.deepcopy(prior)
    result['batches'].append({'status': 'original-entities-parsed', 'requested_ids': [id],
        'source_url': url, 'raw_path': registry.relative_workspace_path(path),
        'raw_sha256': registry.sha256_file(path),
        'source_receipt_path': registry.relative_workspace_path(path.with_name(path.name + '.source.json')),
        'people': confirmed, 'gaps': gaps})
    result['named_original_squad_extension'] = {'previous': old_binding, 'season': season,
        'club': club, 'original_annual': proof, 'original_player': people[0],
        'discovery_profile_url': discovery_url, 'native_writes': 0, 'opening_ownership_approved': False}
    whole.persons.merge({}, result)
    pipeline.write_canonical_json(output, result)
    print(json.dumps({'confirmed_exact_original_person_id': id, 'native_writes': 0}), flush=True)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True); p.add_argument('--season', required=True)
    p.add_argument('--club', required=True); p.add_argument('--name', required=True)
    p.add_argument('--discovery-url', required=True); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); run(a.plan, a.season, a.club, a.name, a.discovery_url, a.output)
