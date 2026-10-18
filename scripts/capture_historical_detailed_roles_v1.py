#!/usr/bin/env python3
"""Capture dated detailed positions and identity facts from pinned club pages.

Uses existing first-fixture club IDs, not search guesses. This supplements
season membership evidence; it does NOT turn a whole-season squad into an
August squad. Offline replay reuses the exact URL/hash-bound cache.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bs4 import BeautifulSoup
from scripts.capture_ntf_historical_carrier_squads_v1 import Cache
from scripts.season_historical_roster_audit_v1 import historical_html_title, normalise, source_group, club_names
from scripts.season_historical_role_plan_v1 import HTML_ROLES
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline


def birth_date(text):
    match = re.fullmatch(r'(\d{2})/(\d{2})/(\d{4})(?:\s*\(\d+\))?', text.strip())
    if match:
        day, month, year = map(int, match.groups())
        return datetime.date(year, month, day).isoformat()
    match = re.fullmatch(r'([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})(?:\s*\(\d+\))?', text.strip())
    return datetime.datetime.strptime(' '.join(match.groups()), '%b %d %Y').date().isoformat() if match else None


def parse_complete_squad(payload):
    """Keep factual identities even when a page supplies only a broad role.

    A generic Forward is still a squad member, but not evidence for a wing
    or side. The narrower role-capture contract below remains unchanged.
    """
    soup = payload if isinstance(payload, BeautifulSoup) else BeautifulSoup(payload, 'html.parser')
    players = []
    for row in soup.select('table.items > tbody > tr'):
        cells = row.find_all('td', recursive=False)
        anchor = row.select_one('a[href*="/profil/spieler/"]')
        if anchor is None or len(cells) < 4:
            continue
        name = anchor.get_text(' ', strip=True)
        identity = re.search(r'/spieler/(\d+)', anchor['href'])
        role_label = normalise(cells[1].get_text(' ', strip=True)).removeprefix(normalise(name))
        if not identity or not name:
            continue
        try:
            dob = birth_date(cells[2].get_text(' ', strip=True))
        except ValueError:
            dob = None  # Invalid source dates stay missing; never silently corrected.
        number = cells[0].get_text(' ', strip=True)
        flags = [img.get('title') or img.get('alt') for img in cells[3].select('img.flaggenrahmen')]
        heights = [re.fullmatch(r'(\d)[,.](\d{2})\s*m', cell.get_text(' ', strip=True)) for cell in cells[4:]]
        height = next((int(m.group(1))*100+int(m.group(2)) for m in heights if m), None)
        players.append({'name': name, 'birth_date': dob, 'source_player_id': identity.group(1),
                        'source_position': role_label,
                        'fine_roles': [HTML_ROLES[role_label]] if role_label in HTML_ROLES else [],
                        'nationalities': flags, 'height_cm': height,
                        'shirt_number': int(number) if number.isdigit() else None})
    if len({p['source_player_id'] for p in players}) != len(players):
        raise ValueError('ambiguous duplicate source person in historical squad')
    return players


def parse(payload):
    return [row for row in parse_complete_squad(payload) if row['fine_roles']]


def club_identity_bound(payload, selector, title_name):
    if normalise(title_name) in club_names(source_group(selector['country_catalog']), selector['transfermarkt_club_name']):
        return True
    # Legal/Galician display-name variants are accepted by the independently
    # pinned season-competition club ID, not by a fuzzy name comparison.
    soup = BeautifulSoup(payload, 'html.parser')
    canonical = soup.select_one('link[rel=canonical]')
    match = re.search(r'/verein/(\d+)(?:/|$)', canonical.get('href', '')) if canonical else None
    return bool(match and int(match.group(1)) == int(selector['transfermarkt_club_id']))


def opening_path(season):
    path = ROOT / '.local/transfermarkt-opening-plans-current-v1' / season / 'opening-lineups.json'
    # The legacy 2015 lane has no opening-capture package. Stable club IDs
    # may be reused from another dated competition capture, but its fixtures
    # must never be presented as 2015 opening-lineup evidence.
    return path if path.exists() else ROOT / '.local/transfermarkt-opening-plans-current-v1/2025-26/opening-lineups.json'


def capture(season, *, cache_root, countries=(), offline=False, delay=1):
    path = opening_path(season)
    opening = json.loads(path.read_text())
    exact_opening = int(opening['season_start_year']) == int(season[:4])
    cache = Cache(cache_root, offline=offline, delay=delay, stop_on_http_block=True)
    clubs, gaps = [], []
    for row in opening['clubs']:
        selector = row['source_selector']
        country = selector['country_catalog']
        if countries and country not in countries:
            continue
        club_id = selector.get('transfermarkt_club_id')
        if not club_id:
            gaps.append({'club': selector['club_name'], 'reason': 'no independent club ID'})
            continue
        url = f'https://www.transfermarkt.com/club/kader/verein/{club_id}/saison_id/{season[:4]}/plus/1'
        key = f'squad/{season[:4]}/{country}/{club_id}.html'
        try:
            payload = cache.get(url, key)
            title_name, period = historical_html_title(payload, 'transfermarkt', season, source_group(country),
                                                       allow_calendar_ending_year=False)
            if not club_identity_bound(payload, selector, title_name):
                raise ValueError('historical page club title disagrees with pinned club identity')
            players = parse(payload)
            if not players:
                raise ValueError('no supported detailed-position rows')
            clubs.append({'club_name': selector['club_name'], 'source_club_name': title_name,
                'country_catalog': country, 'source_club_id': club_id, 'source_url': url,
                'original_document_period': period,
                'source_path': key, 'source_sha256': registry.sha256_file(cache_root / key),
                'club_id_binding': 'exact-season-competition' if exact_opening else 'stable-club-ID-other-season-NOT-opening-proof',
                'first_fixture_url': row.get('lineup_source_url') if exact_opening else None,
                'first_fixture_date': row.get('first_league_fixture_date') if exact_opening else None, 'players': players})
        except Exception as exc:
            gaps.append({'club': selector['club_name'], 'country': country, 'source_url': url, 'reason': str(exc)})
        print(json.dumps({'season': season, 'club': selector['club_name'], 'captured_clubs': len(clubs), 'gaps': len(gaps)}), flush=True)
    return {'schema_version': 'pm99-historical-detailed-roles-capture-v1', 'season': season,
            'requested_countries': sorted(set(countries) or {r['source_selector']['country_catalog'] for r in opening['clubs']}),
            'source_access_blocks': dict(cache.blocked_hosts),
            'club_id_capture_path': registry.relative_workspace_path(path),
            'opening_capture_sha256': registry.sha256_file(path), 'cache_root': registry.relative_workspace_path(cache_root),
            'scope': 'Detailed positions and factual identities, NOT August ownership', 'clubs': clubs, 'gaps': gaps}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season'); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cache-root', type=Path, required=True); parser.add_argument('--country', action='append', default=[])
    parser.add_argument('--offline', action='store_true'); parser.add_argument('--delay', type=float, default=1)
    parser.add_argument('--resume', action='store_true', help='Verify and reuse completed captures; no refetch')
    args = parser.parse_args()
    for season in registry.supported_seasons() if args.season == 'all' else [args.season]:
        destination = args.output / season / 'detailed-role-capture.json'
        if destination.exists():
            if not args.resume:
                raise ValueError('capture already exists; use --resume or a fresh output root')
            document = json.loads(destination.read_text())
            opening = opening_path(season)
            if document['season'] != season or document['opening_capture_sha256'] != registry.sha256_file(opening):
                raise ValueError('completed capture input binding changed')
            root = registry._workspace_path(document['cache_root'], label='historical role cache')
            for row in document['clubs']:
                relative = Path(row['source_path'])
                if relative.is_absolute() or '..' in relative.parts or registry.sha256_file(root / relative) != row['source_sha256']:
                    raise ValueError('completed capture source binding changed')
            requested = set(args.country)
            captured = {c['country_catalog'] for c in document['clubs']}
            available = {r['source_selector']['country_catalog'] for r in json.loads(opening.read_text())['clubs']}
            if requested and captured - requested or (not requested and available - captured):
                raise ValueError('completed capture used a narrower/different country scope; use a fresh output root')
            print(json.dumps({'season': season, 'status': 'verified-existing-capture', 'captured_clubs': len(document['clubs'])}), flush=True)
            continue
        result = capture(season, cache_root=args.cache_root / season, countries=args.country, offline=args.offline, delay=args.delay)
        destination.parent.mkdir(parents=True, exist_ok=True)
        pipeline.write_canonical_json(destination, result)


if __name__ == '__main__':
    main()
