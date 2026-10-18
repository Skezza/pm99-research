#!/usr/bin/env python3
"""Supplement English roster checks with dated NTF pages, without TM retries.

Existing URL/hash-bound snapshots are reused. Club joins are exact, with only
the English legal FC/AFC suffix treated as presentation. These whole-season
appearances are NOT proof that a player was at the club in August.
"""
import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts.capture_ntf_historical_carrier_squads_v1 import Cache
from scripts.capture_2015_missing_family_squads import BASE_URL, parse_league_links, _SquadParser

SCHEMA = 'pm99-historical-ntf-review-capture-v1'


def english_legal_name(value):
    return roster.normalise(re.sub(r'\s+(?:FC|AFC|F\.C\.|A\.F\.C\.)$', '', value, flags=re.I))


def person_names(value):
    names = {roster.normalise(value)}
    if value.count(',') == 1:
        surname, given = (part.strip() for part in value.split(','))
        if surname and given:
            names.add(roster.normalise(given + ' ' + surname))
    return names


def parse_players(payload, season):
    _, period = roster.historical_html_title(payload, 'ntf', season, 'england', allow_calendar_ending_year=False)
    parser = _SquadParser()
    parser.feed(payload.decode('utf-8', errors='replace'))
    players = {}
    for row in parser.rows:
        if len(row) < 8 or row[5] != period or not row[1]:
            continue
        try:
            dob = datetime.date.fromisoformat(row[2]).isoformat()
        except ValueError:
            continue
        player = {'name': row[1], 'birth_date': dob, 'nationality': row[3],
                  'source_position': row[4], 'shirt_number': None, 'height_cm': None, 'weight_kg': None}
        key = row[1], dob
        if key in players and players[key] != player:
            raise ValueError('conflicting repeated NTF person')
        players[key] = player
    return sorted(players.values(), key=lambda p: (p['name'], p['birth_date']))


def seed(cache, season):
    """Reuse only exact URL-bound receipts, never assume a filename is proof."""
    locations = [ROOT / '.local' / ('season-' + season),
                 ROOT / '.local/external-sources/historical-ntf-audit-v1' / season]
    for location in locations:
        if not location.exists():
            continue
        for receipt_path in location.rglob('*.html.source.json'):
            receipt = json.loads(receipt_path.read_text())
            url = receipt.get('url', '')
            club = re.fullmatch(re.escape(BASE_URL) + r'/club/(\d+)/(\d{4}(?:_1)?)/[^/]+\.html', url)
            index = re.fullmatch(re.escape(BASE_URL) + r'/leagues/59/(\d{4}(?:_1)?)/England\.html', url)
            if club and club[2].startswith(season[:4]):
                key = f'clubs/england/{club[1]}-{club[2]}.html'
            elif index and index[1].startswith(season[:4]):
                key = f'index/england/{index[1]}.html'
            else:
                continue
            source = receipt_path.with_name(receipt_path.name.removesuffix('.source.json'))
            if not source.exists():
                continue
            raw = source.read_bytes()
            if hashlib.sha256(raw).hexdigest() != receipt.get('sha256'):
                raise ValueError('old URL-bound source snapshot changed')
            destination = cache.root / key
            if destination.exists():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            destination.with_suffix('.html.source.json').write_bytes(pipeline.canonical_json_bytes(receipt))


def capture(season, cache, club_filter=()):
    release = registry.load_preferred_release(season)
    package = json.loads(release.package_path.read_text())
    clubs, _, _ = roster.add_legacy_english(package, season)
    targets = [c for c in clubs if roster.club_group(c) == 'england' and
               (not club_filter or any(english_legal_name(c['name']) == english_legal_name(n) for n in club_filter))]
    seed(cache, season)
    suffix = season[:4] + '_1'
    index_url = f'{BASE_URL}/leagues/59/{suffix}/England.html'
    index_key = f'index/england/{suffix}.html'
    raw = cache.get(index_url, index_key)
    expected = f'Leagues of England ({season[:4]}/{season[-2:]}) | National Football Teams'
    if roster.original_html_title(raw) != expected:
        raise ValueError('NTF index is not the requested English season')
    links = parse_league_links(raw)
    captured, gaps = [], []
    for club in targets:
        aliases = {english_legal_name(n) for n in (club['name'], club.get('full_name', '')) if n}
        aliases.update(roster.club_names('england', club['name'], club.get('full_name', '')))
        matches = {href: name for name, href in links if english_legal_name(name) in aliases
                   and re.fullmatch(r'/club/\d+/' + suffix + r'/[^/]+\.html', href)}
        if len(matches) != 1:
            gaps.append({'club_id': club['id'], 'club': club['name'], 'reason': 'no unique exact club in dated country index'})
            continue
        href, display = next(iter(matches.items()))
        club_id = re.search(r'/club/(\d+)/', href)[1]
        key, url = f'clubs/england/{club_id}-{suffix}.html', BASE_URL + href
        try:
            payload = cache.get(url, key)
            title, period = roster.historical_html_title(payload, 'ntf', season, 'england', allow_calendar_ending_year=False)
            if english_legal_name(title) != english_legal_name(display):
                raise ValueError('club page and dated index disagree')
            players = parse_players(payload, season)
            if not players:
                raise ValueError('no dated person rows')
            captured.append({'club_id': club['id'], 'club_name': club['name'], 'source_club_name': display,
                'country_catalog': 'england', 'source_path': key, 'source_url': url,
                'source_sha256': hashlib.sha256(payload).hexdigest(), 'period': period, 'players': players})
        except Exception as exc:
            gaps.append({'club_id': club['id'], 'club': club['name'], 'source_url': url, 'reason': str(exc)})
    return {'schema_version': SCHEMA, 'season': season, 'cache_root': registry.relative_workspace_path(cache.root),
            'package_sha256': registry.sha256_file(release.package_path),
            'requested_clubs': [c['id'] for c in targets],
            'index': {'source_path': index_key, 'source_url': index_url, 'source_sha256': hashlib.sha256(raw).hexdigest()},
            'scope': 'Dated whole-season appearances; NOT a complete squad or August ownership certification',
            'clubs': captured, 'gaps': gaps, 'source_access_blocks': dict(cache.blocked_hosts)}


def verified_rows(season, path):
    document = json.loads(path.read_text())
    if (document['schema_version'], document['season']) != (SCHEMA, season):
        raise ValueError('wrong NTF review capture')
    cache = registry._workspace_path(document['cache_root'], label='NTF review cache')
    index = document['index']
    relative_index = Path(index['source_path'])
    if relative_index.is_absolute() or '..' in relative_index.parts:
        raise ValueError('unsafe NTF index path')
    raw_index = cache / relative_index
    if registry.sha256_file(raw_index) != index['source_sha256']:
        raise ValueError('NTF dated index changed')
    expected_title = f'Leagues of England ({season[:4]}/{season[-2:]}) | National Football Teams'
    if roster.original_html_title(raw_index.read_bytes()) != expected_title:
        raise ValueError('NTF index season changed')
    indexed = {(name, BASE_URL + href) for name, href in parse_league_links(raw_index.read_bytes())}
    rows = []
    for club in document['clubs']:
        if (club['source_club_name'], club['source_url']) not in indexed:
            raise ValueError('NTF club is not in bound dated country index')
        relative = Path(club['source_path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe NTF source path')
        raw = cache / relative
        receipt = json.loads(raw.with_suffix('.html.source.json').read_text())
        if registry.sha256_file(raw) != club['source_sha256'] or receipt != {'url': club['source_url'], 'sha256': club['source_sha256']}:
            raise ValueError('NTF source URL/hash binding changed')
        name, _ = roster.historical_html_title(raw.read_bytes(), 'ntf', season, 'england', allow_calendar_ending_year=False)
        if english_legal_name(name) != english_legal_name(club['source_club_name']) or parse_players(raw.read_bytes(), season) != club['players']:
            raise ValueError('NTF original source reparse disagrees')
        for player in club['players']:
            rows.append({'facts': player, 'club': club['club_name'], 'club_id': club['club_id'], 'group': 'england',
                         'provider': 'independent-dated-NTF-review-reparse', 'source_url': club['source_url'],
                         'source_path': registry.relative_workspace_path(raw), 'source_sha256': club['source_sha256']})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season'); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cache-root', type=Path, required=True); parser.add_argument('--club', action='append', default=[])
    parser.add_argument('--offline', action='store_true'); parser.add_argument('--delay', type=float, default=1)
    args = parser.parse_args()
    for season in registry.supported_seasons() if args.season == 'all' else [args.season]:
        path = args.output / season / 'ntf-review-capture.json'
        if path.exists():
            raise ValueError('capture exists; choose fresh report root and reuse cache')
        document = capture(season, Cache(args.cache_root / season, offline=args.offline, delay=args.delay,
                            stop_on_http_block=True), args.club)
        path.parent.mkdir(parents=True, exist_ok=True)
        pipeline.write_canonical_json(path, document)
        print(json.dumps({'season': season, 'clubs': len(document['clubs']), 'gaps': len(document['gaps'])}), flush=True)


if __name__ == '__main__':
    main()
