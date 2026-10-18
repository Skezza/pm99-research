#!/usr/bin/env python3
"""Corroborate explicit club-local DOB conflicts; never fuzzy-match a person.

Only the exact article/profile heading and its one structured birth-date field
are used. Current team, age, pictures, nationality and position are ignored.
Keep original pages and URL/SHA receipts; no recipe or native game is changed.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_historical_transfer_review_v1 as transfer
from scripts.season_art_transaction_v1 import atomic_bytes


def parse(payload, name, provider):
    page = BeautifulSoup(payload, 'lxml')
    headings = [h.get_text(' ', strip=True) for h in page.select('h1')]
    if len(headings) != 1 or transfer._normalise(headings[0]) != transfer._normalise(name):
        raise ValueError('independent biography heading does not identify the exact full-name person')
    if provider == 'wikipedia':
        values = {n.get_text(' ', strip=True) for n in page.select('table.infobox .bday')}
        if len(values) != 1:
            raise ValueError('independent biography lacks one structured infobox birth date')
        value = next(iter(values))
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError('independent biography birth date is not an exact ISO date')
        return dt.date.fromisoformat(value).isoformat()
    if provider == 'england-profile':
        values = []
        for term in page.find_all('dt'):
            if term.get_text(' ', strip=True).casefold() != 'dob':
                continue
            item = term.find_next_sibling('dd')
            match = re.fullmatch(r'(\d{2} [A-Za-z]+ \d{4})(?:\s*\(\d+YRS\))?',
                                item.get_text(' ', strip=True) if item else '')
            if not match:
                raise ValueError('official birth-date field has an unsupported format')
            values.append(dt.datetime.strptime(match.group(1), '%d %B %Y').date().isoformat())
        if len(values) != 1:
            raise ValueError('official profile lacks one exact birth-date field')
        return values[0]
    raise ValueError('unsupported birth-date corroboration reader')


def validate_url(provider, url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError('corroboration requires an exact public HTTPS article/profile URL')
    allowed = ((provider == 'wikipedia' and parsed.netloc == 'en.wikipedia.org' and parsed.path.startswith('/wiki/'))
        or (provider == 'england-profile' and parsed.netloc == 'www.englandfootball.com'
            and parsed.path.startswith('/england/mens-senior-team/squad/')))
    if not allowed:
        raise ValueError('corroboration URL does not match the selected original publisher')


def capture(plan_path, pages, cache, output):
    if output.exists():
        raise ValueError('birth-date corroboration is immutable')
    digest = registry.sha256_file(plan_path)
    plan = json.loads(plan_path.read_text())
    if plan.get('schema_version') != 'pm99-source-repaired-opening-club-roster-plan-v1':
        raise ValueError('unsupported bounded club reconciliation plan')
    claims = {r['source_player_id']: r for r in plan['local_DOB_conflicts']}
    people = {r['source_player_id']: r['source_person'] for r in plan['desired_matchday_people']}
    if set(pages) != set(claims):
        raise ValueError('corroboration pages must cover exactly the explicit local DOB conflicts')
    rows = []
    for id in sorted(claims):
        provider, url = pages[id]
        validate_url(provider, url)
        key = hashlib.sha256(url.encode()).hexdigest()
        path, receipt = cache / (key + '.html'), cache / (key + '.source.json')
        if path.exists():
            raw = path.read_bytes()
            if json.loads(receipt.read_text()) != {'url': url, 'sha256': hashlib.sha256(raw).hexdigest()}:
                raise ValueError('cached independent biography URL/SHA changed')
        else:
            with urlopen(Request(url, headers={'User-Agent': 'PM99 historical player facts research',
                    'Accept-Language': 'en-GB'}), timeout=25) as response:
                if response.geturl() != url:
                    raise ValueError('independent biography redirected to another identity or publisher')
                raw = response.read(2 * 1024 * 1024 + 1)
            if not 1000 <= len(raw) <= 2 * 1024 * 1024:
                raise ValueError('independent biography exceeds bounded size or is truncated')
            atomic_bytes(path, raw)
            pipeline.write_canonical_json(receipt, {'url': url, 'sha256': hashlib.sha256(raw).hexdigest()})
            time.sleep(1)
        observed = parse(raw, claims[id]['source_name'], provider)
        if observed != claims[id]['after'] or observed != people[id]['birth_date']:
            raise ValueError('original public person and independent biography birth dates disagree')
        rows.append({**claims[id], 'source_corroboration_passed': True,
            'native_game_modified': False, 'corroboration': {'provider': provider, 'url': url,
                'path': registry.relative_workspace_path(path), 'sha256': registry.sha256_file(path),
                'receipt_path': registry.relative_workspace_path(receipt), 'observed_birth_date': observed}})
    if registry.sha256_file(plan_path) != digest:
        raise ValueError('club DOB conflict plan changed during independent corroboration')
    pipeline.write_canonical_json(output, {'schema_version': 'pm99-bounded-named-DOB-corroboration-v1',
        'club_plan': {'path': registry.relative_workspace_path(plan_path), 'sha256': digest},
        'reader': {'path': registry.relative_workspace_path(Path(__file__)),
            'sha256': registry.sha256_file(Path(__file__))}, 'rows': rows,
        'scope': 'explicit local birth-date conflicts only; no global identity-join waiver or native writes'})
    print(json.dumps({'independently_corroborated_DOB_conflicts': len(rows), 'native_game_modified': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--club-plan', type=Path, required=True)
    parser.add_argument('--page', action='append', required=True, help='SOURCE_PLAYER_ID=PROVIDER=HTTPS_URL')
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    pages = {}
    for value in args.page:
        id, provider, url = value.split('=', 2)
        if int(id) in pages:
            parser.error('a player has more than one selected corroboration page')
        pages[int(id)] = (provider, url)
    capture(args.club_plan, pages, args.cache, args.output)
