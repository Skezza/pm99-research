"""Strict optional crosswalk between an annual source row and its match sheet.

The helper validates evidence only; all IDs arrive in and are reproduced from
hash-bound source material. It does not allocate identities or edit game data.
"""
from datetime import datetime
import json
import hashlib
import re
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from scripts import season_release_registry_v1 as registry
from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import coupled_manager_timeline_admission_20261016 as club_aliases


def _file(binding):
    if not isinstance(binding, dict) or not isinstance(binding.get('path'), str):
        raise ValueError('fixture witness needs a workspace path/SHA binding')
    path = Path(binding['path'])
    if path.is_absolute():
        raise ValueError('fixture path must be workspace relative')
    current = registry.ROOT
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('fixture path cannot contain symlink components')
    resolved = (registry.ROOT / path).resolve()
    if (not resolved.is_relative_to(registry.ROOT.resolve()) or not path.is_file()):
        raise ValueError('fixture binding must be a retained workspace regular file')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding.get('sha256'):
        raise ValueError('fixture body SHA differs')
    return path, raw


def verify_annual_source_row_binding(annual, full_name, preallocation):
    """Replay the named annual row before accepting a match-sheet profile link.

    The annual squad row has no numeric Transfermarkt player ID. It independently
    binds the full name, old DOB, selector, and stable source-row hash; the
    match sheet then supplies the provider ID and confirms that named player in
    the requested club's opening XI. This does not claim a separate profile
    page body was captured.
    """
    if not isinstance(annual, dict) or not isinstance(preallocation, dict):
        raise ValueError('annual person source must be a parsed preallocation object')
    season = annual.get('season')
    selector = annual.get('selector')
    row_hash = annual.get('source_row_sha256')
    row_index = annual.get('source_row_index')
    old_dob = annual.get('source_birth_date')
    if (not isinstance(season, str) or not re.fullmatch(r'\d{4}-\d{2}', season)
            or not isinstance(selector, dict) or not isinstance(row_hash, str)
            or type(row_index) is not int or not isinstance(old_dob, str)):
        raise ValueError('annual person source binding lacks season/selector/row/DOB fields')
    start, end = season.split('-')
    if end != f'{(int(start) + 1) % 100:02d}' or preallocation.get('season', {}).get('label') != season.replace('-', '/'):
        raise ValueError('annual preallocation does not target the requested season')
    matches = [(club, row) for club in preallocation.get('source_clubs', [])
               for row in club.get('players', []) if row.get('source_row_sha256') == row_hash]
    if len(matches) != 1:
        raise ValueError('annual source row hash must resolve exactly once in preallocation')
    club, row = matches[0]
    if (row.get('source_row_index') != row_index
            or row.get('facts', {}).get('name') != full_name
            or row.get('facts', {}).get('birth_date') != old_dob):
        raise ValueError('fixture full name/DOB does not match the exact annual source row')
    if any(club.get('selector', {}).get(key) != selector.get(key)
           for key in ('club_name', 'country_catalog', 'competition_catalog', 'source_path', 'source_sha256')):
        raise ValueError('annual fixture club selector differs from its hashed source row')
    return {'season': season, 'source_row_sha256': row_hash,
            'source_row_index': row_index, 'full_name': full_name,
            'source_birth_date': old_dob, 'selector': selector}


def verify_report_bytes(raw, fixture, annual, full_name, aliases, titles, competition_map):
    """Pure parser for synthetic tests and retained report verification."""
    required = {'match_id', 'date', 'url', 'provider_club_id', 'provider_player_id',
                'provider_club_name', 'provider_competition_code'}
    if not isinstance(fixture, dict) or set(fixture) != required:
        raise ValueError('fixture record must use the exact typed field set')
    season = annual.get('season')
    if not isinstance(season, str) or not re.fullmatch(r'\d{4}-\d{2}', season):
        raise ValueError('annual fixture season is malformed')
    start, end = season.split('-')
    if end != f'{(int(start) + 1) % 100:02d}':
        raise ValueError('annual fixture season interval is inconsistent')
    date_value = datetime.strptime(fixture['date'], '%Y-%m-%d').date()
    if date_value.year not in (int(start), int(start) + 1):
        raise ValueError('fixture falls outside the annual season')
    if any(type(fixture[k]) is not int or fixture[k] <= 0
           for k in ('match_id', 'provider_club_id', 'provider_player_id')):
        raise ValueError('fixture/provider identifiers must be positive integers')
    url = urlsplit(fixture['url'])
    if (url.scheme != 'https' or url.hostname != 'www.transfermarkt.co.uk'
            or url.path != f"/spielbericht/index/spielbericht/{fixture['match_id']}"):
        raise ValueError('fixture URL is not the canonical match-sheet route')
    selector = annual.get('selector', {})
    country = selector.get('country_catalog')
    competition = selector.get('competition_catalog')
    club_name = selector.get('club_name')
    country_aliases, club_labels = aliases.get(fixture['provider_club_id'], (None, ()))
    if (country_aliases != country or club_name not in club_labels
            or fixture['provider_club_name'] not in club_labels
            or fixture['provider_club_name'] not in titles.get(fixture['provider_club_id'], '')):
        raise ValueError('annual/report club labels do not resolve through the existing alias map')
    comp_rows = [r for r in competition_map.get('competitions', [])
                 if r.get('country_catalog') == country and r.get('competition_catalog') == competition]
    if len(comp_rows) != 1 or comp_rows[0].get('source_competition_code') != fixture['provider_competition_code']:
        raise ValueError('annual competition selector does not map uniquely to the report competition ID')
    page = BeautifulSoup(raw, 'html.parser')
    title = page.title.get_text(' ', strip=True) if page.title else ''
    title_match = re.fullmatch(r'^.+?, (\d{2}/\d{2}/\d{4}) - (.+?) - Match sheet \| Transfermarkt$', title)
    if not title_match or datetime.strptime(title_match.group(1), '%d/%m/%Y').date() != date_value:
        raise ValueError('match title/date does not identify the requested fixture')
    keywords = page.select_one('meta[name="keywords"]')
    keyword_text = keywords.get('content', '') if keywords else ''
    keyword_tokens = {' '.join(token.split()) for token in keyword_text.split(',') if token.strip()}
    expected_season = f'{start[-2:]}/{end}'
    round_tokens = [token for token in keyword_tokens if re.fullmatch(r'\d+\. Spieltag', token)]
    if (round_tokens != ['1. Spieltag']
            or f'Saison {expected_season}' not in keyword_tokens
            or title_match.group(2) not in keyword_tokens):
        raise ValueError('report matchday, season, or competition title differs from annual fixture')
    competition_links = [a for a in page.select('a[href]')
                         if re.search(rf'/wettbewerb/{re.escape(fixture["provider_competition_code"])}'
                                      rf'/saison_id/{re.escape(start)}(?:/|$)', urlsplit(a.get('href', '')).path)]
    if not competition_links:
        raise ValueError('report does not publish the exact annual competition ID/season route')
    wanted = exchange.published_name_key(full_name)
    id_pattern = re.compile(r'/([^/]+)/profil/spieler/(\d+)(?:/|$)')
    perf_pattern = re.compile(r'/([^/]+)/leistungsdatendetails/spieler/(\d+)(?:/|$)')
    candidate_links = []
    for anchor in page.select('a[href]'):
        path = urlsplit(anchor.get('href', '')).path
        m = id_pattern.search(path)
        if m and int(m.group(2)) == fixture['provider_player_id']:
            if exchange.published_name_key(m.group(1).replace('-', ' ')) == wanted:
                candidate_links.append(anchor)
            continue
        m = perf_pattern.search(path)
        if (m and int(m.group(2)) == fixture['provider_player_id']
                and anchor.get('title')
                and exchange.published_name_key(anchor['title']) == wanted):
            candidate_links.append(anchor)
    if not candidate_links:
        raise ValueError('numeric provider ID does not publish the annual full name')
    team_boxes = []
    for box in page.select('div.large-6'):
        team_links = [a for a in box.select('a[href]')
                      if re.search(r'/startseite/verein/' + str(fixture['provider_club_id'])
                                   + r'(?:/|$)', urlsplit(a['href']).path)]
        ids = {int(m.group(1)) for a in box.select('a[href]')
               if (m := re.search(r'/startseite/verein/(\d+)(?:/|$)', urlsplit(a['href']).path))}
        team_labels = {' '.join(a.get_text(' ', strip=True).split()) for a in team_links}
        if ids != {fixture['provider_club_id']} or fixture['provider_club_name'] not in team_labels:
            continue
        in_xi = False
        for anchor in candidate_links:
            player_container = anchor.find_parent(class_='formation-player-container')
            lineup = player_container.find_parent(class_='aufstellung-vereinsseite') if player_container else None
            if lineup is not None and box in lineup.parents:
                in_xi = True
        if in_xi:
            team_boxes.append(box)
    if len(team_boxes) != 1:
        raise ValueError('provider person must be in exactly one requested club starting XI box')
    return {'provider_club_id': fixture['provider_club_id'],
            'provider_player_id': fixture['provider_player_id'],
            'match_id': fixture['match_id'], 'fixture_date': fixture['date'],
            'provider_competition_code': fixture['provider_competition_code'],
            'full_name': full_name,
            'identity_link_source': 'match-sheet-numeric-player-link-and-profile-name-slug'}


def verify_opening_fixture(fixture, annual, full_name):
    """Validate retained fixture body and both existing selector alias maps."""
    required = {'match_id', 'date', 'path', 'sha256', 'url', 'provider_club_id',
                'provider_player_id', 'provider_club_name', 'provider_competition_code',
                'club_alias_module_sha256', 'competition_map'}
    if not isinstance(fixture, dict) or set(fixture) != required:
        raise ValueError('retained fixture binding field set differs')
    alias_path = registry.ROOT/'scripts/coupled_manager_timeline_admission_20261016.py'
    alias_sha = registry.sha256_file(alias_path)
    if alias_sha != fixture['club_alias_module_sha256']:
        raise ValueError('existing provider-club alias-map SHA differs')
    annual_competition_map = annual.get('competition_map')
    if fixture['competition_map'] != annual_competition_map:
        raise ValueError('competition map must bind the exact annual source selector artifact')
    _, competition_map_bytes = _file(annual_competition_map)
    competition_map = json.loads(competition_map_bytes)
    _, preallocation_bytes = _file(annual['preallocation'])
    source_row = verify_annual_source_row_binding(annual, full_name, json.loads(preallocation_bytes))
    _, raw = _file({'path': fixture['path'], 'sha256': fixture['sha256']})
    result = verify_report_bytes(raw, {k:v for k,v in fixture.items() if k not in {
        'path','sha256','club_alias_module_sha256','competition_map'}}, annual, full_name,
        club_aliases.ALIASES, club_aliases.TITLES, competition_map)
    result['club_alias_map_sha256'] = alias_sha
    result['competition_map_sha256'] = fixture['competition_map']['sha256']
    result['annual_source_row'] = source_row
    result['annual_preallocation_sha256'] = annual['preallocation']['sha256']
    return result
