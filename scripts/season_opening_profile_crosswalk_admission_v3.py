"""Generic typed PL/Sky/reference profile crosswalk plus TM fixture admission.

This isolated provider reuses the existing opening exchange's new-person
shape. Claims and retained source bindings live in the request; this module
contains no player, club, profile-ID, or season-specific facts.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_release_registry_v1 as registry
from scripts.capture_2015_source_tail_squads_v1 import NATIONALITY_CODES
from scripts.capture_2015_wikipedia_player_facts_v1 import DEMONYM_TO_PM99
from scripts.season_exact_fifa_role_delta_v1 import compatible

ROOT = registry.ROOT
POLICY = 'typed-pl-sky-secondary-reference-and-transfermarkt-fixture-crosswalk-v1'
ROLE_POLICY = 'editorial-compatible-profile-role-v1'
HTTP_SCHEMA = 'pm99-original-http-source-capture-v1'
WEBTOOL_SCHEMA = 'pm99-original-webtool-source-extraction-v1'
HTTP_KEYS = {'path', 'sha256', 'url', 'receipt_path', 'receipt_sha256'}
WEB_KEYS = HTTP_KEYS | {'web_tool_reference_id'}
SELECTION_KEYS = {
    'admission_policy', 'provider_player_id', 'premier_league_player_id',
    'name', 'reference_full_name', 'birth_date', 'profile_position',
    'position', 'nationality_label', 'nationality', 'editorial_role_policy',
    'editorial_fine_role', 'native_display_name', 'match',
    'premier_league_profile', 'sky_profile', 'nationality_reference',
    'premier_league_webtool',
}
EXCHANGE_ENVELOPE_KEYS = {'carrier_id', 'club_id', 'fine_roles'}
EVIDENCE_KEYS = {
    'premier_league_profile', 'sky_profile', 'nationality_reference',
    'premier_league_webtool', 'match_fixture',
}
PROFILE_POSITION_TO_BROAD = {
    'goalkeeper': 'G', 'goalkeeper/defender': 'G', 'keeper': 'G',
    'defender': 'D', 'defence': 'D', 'centre-back': 'D', 'full-back': 'D',
    'midfielder': 'M', 'midfield': 'M', 'winger': 'M',
    'forward': 'F', 'striker': 'F', 'attacker': 'F',
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _binding(value: object, *, webtool: bool = False) -> tuple[dict, Path, bytes, dict]:
    expected_keys = WEB_KEYS if webtool else HTTP_KEYS
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise ValueError('profile source binding has unknown or missing fields')
    path = (ROOT / value['path']).resolve(strict=True)
    receipt_path = (ROOT / value['receipt_path']).resolve(strict=True)
    if (not path.is_relative_to(ROOT.resolve()) or not receipt_path.is_relative_to(ROOT.resolve())
            or _sha(path) != value['sha256'] or _sha(receipt_path) != value['receipt_sha256']):
        raise ValueError('profile source or receipt hash/path differs')
    url = urlsplit(value['url'])
    if url.scheme != 'https' or not url.netloc:
        raise ValueError('profile source URL must be HTTPS')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    schema = WEBTOOL_SCHEMA if webtool else HTTP_SCHEMA
    if receipt.get('schema') != schema or receipt.get('sha256') != value['sha256']:
        raise ValueError('profile source receipt schema/body hash differs')
    receipt_url = receipt.get('requested_url', receipt.get('url'))
    if receipt_url != value['url'] or receipt.get('final_url') != value['url']:
        raise ValueError('profile source receipt URL differs')
    if webtool:
        if (receipt.get('web_tool_reference_id') != value['web_tool_reference_id']
                or 'not an HTTP body' not in receipt.get('representation', '')):
            raise ValueError('web-tool reference or representation differs')
    elif (receipt.get('status') != 200
          or receipt.get('representation') != 'original HTTP response body; bytes saved unchanged'):
        raise ValueError('profile source is not a retained original HTTP body')
    return value, path, path.read_bytes(), receipt


def _parse_pl(selection: dict, evidence: dict) -> dict:
    binding, path, raw, _ = _binding(evidence['premier_league_profile'])
    page = BeautifulSoup(raw, 'html.parser')
    canonical = page.select_one('link[rel="canonical"]')
    widget = page.select_one('[data-widget="player-profile/player-profile-tabs"]')
    title = page.title.get_text(' ', strip=True) if page.title else ''
    description = page.select_one('meta[name="description"]')
    description = description.get('content', '') if description else ''
    pid = str(selection['premier_league_player_id'])
    parsed_url = urlsplit(binding['url'])
    if (parsed_url.hostname not in {'www.premierleague.com', 'premierleague.com'}
            or not re.search(r'/players/' + re.escape(pid) + r'(?:/|$)', parsed_url.path)
            or canonical is None or canonical.get('href') != binding['url']
            or widget is None or widget.get('data-player-id') != pid
            or widget.get('data-player-name') != selection['name']
            or selection['profile_position'].casefold() not in title.casefold()
            or selection['name'] not in title or selection['name'] not in description):
        raise ValueError('official Premier League profile identity/position does not match request')
    return {'profile_id': int(pid), 'name': widget['data-player-name'],
            'position': selection['profile_position'], 'source_url': binding['url'],
            'source_path': str(path.relative_to(ROOT)), 'source_sha256': binding['sha256']}


def _parse_sky(selection: dict, evidence: dict) -> dict:
    binding, path, raw, _ = _binding(evidence['sky_profile'])
    page = BeautifulSoup(raw, 'html.parser')
    canonical = page.select_one('meta[property="og:url"]')
    names = [n.get_text(' ', strip=True) for n in page.select('[itemprop="name"]')]
    births = [n.get_text(' ', strip=True) for n in page.select('[itemprop="birthDate"]')]
    positions = [p.get_text(' ', strip=True).partition(':')[2].strip()
                 for p in page.select('.row-table.details p')
                 if p.get_text(' ', strip=True).startswith('Position:')]
    title = page.title.get_text(' ', strip=True) if page.title else ''
    expected_dob = datetime.strptime(selection['birth_date'], '%Y-%m-%d').strftime('%d/%m/%Y')
    if (urlsplit(binding['url']).hostname not in {'www.skysports.com', 'skysports.com'}
            or canonical is None or canonical.get('content') != binding['url']
            or title != f"{selection['name']} | Player Profile | Sky Sports Football"
            or names != [selection['name']] or births != [expected_dob]
            or positions != [selection['profile_position']]):
        raise ValueError('Sky full-name/DOB/profile-position facts differ')
    return {'name': names[0], 'birth_date': selection['birth_date'],
            'position': positions[0], 'source_url': binding['url'],
            'source_path': str(path.relative_to(ROOT)), 'source_sha256': binding['sha256']}


def _extract_webtool(value: object, *, field: str) -> tuple[dict, str]:
    binding, _, raw_bytes, _ = _binding(value, webtool=True)
    host = urlsplit(binding['url']).hostname or ''
    allowed = {'premierleague_webtool': {'www.premierleague.com', 'premierleague.com'},
               'reference': {'en.wikipedia.org'}}[field]
    if host not in allowed:
        raise ValueError('web-tool source URL is outside its declared source family')
    return binding, raw_bytes.decode('utf-8')


def _parse_pl_extract(selection: dict, evidence: dict) -> dict:
    binding, raw = _extract_webtool(evidence['premier_league_webtool'], field='premierleague_webtool')
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    pid = str(selection['premier_league_player_id'])
    expected_url = (f"https://www.premierleague.com/en/players/{pid}/" +
                    re.sub(r'[^a-z0-9-]+', '-', selection['name'].casefold()).strip('-') + '/overview')
    if binding['url'] != expected_url:
        raise ValueError('PL web-tool URL is not the exact canonical player profile route')
    if not any(line == '# ' + selection['name'] for line in lines):
        raise ValueError('PL web-tool excerpt lacks the exact profile heading')
    title = lines[0]
    if selection['name'] not in title or selection['profile_position'] not in title:
        raise ValueError('PL web-tool title does not bind name and position')
    if binding['url'] not in raw:
        raise ValueError('PL web-tool excerpt does not contain the bound profile URL')
    nat_ix = next((i for i, line in enumerate(lines) if line.lstrip('* #') == 'Nationality'), None)
    dob_ix = next((i for i, line in enumerate(lines) if line.lstrip('* #') == 'Date of Birth'), None)
    if nat_ix is None or dob_ix is None:
        raise ValueError('PL web-tool excerpt lacks nationality or DOB fields')
    nat_candidates = [re.sub(r'^Image:\s*|\s+Country Flag$', '', line).strip()
                      for line in lines[nat_ix + 1:dob_ix]
                      if line and not line.startswith('*')]
    nationality = next((x for x in reversed(nat_candidates) if x and x != 'Follow'), None)
    dob_candidates = [line for line in lines[dob_ix + 1:] if re.fullmatch(r'\d{2}/\d{2}/\d{4}', line)]
    if len(dob_candidates) != 1:
        raise ValueError('PL web-tool DOB field is ambiguous')
    dob = datetime.strptime(dob_candidates[0], '%d/%m/%Y').date().isoformat()
    if (dob != selection['birth_date'] or nationality != selection['nationality_label']
            or exchange.SOURCE_COUNTRIES.get(nationality) != selection['nationality']):
        raise ValueError('PL web-tool DOB/country differs from declared source facts')
    return {'name': selection['name'], 'birth_date': dob,
            'position': selection['profile_position'], 'nationality_label': nationality,
            'source_url': binding['url'], 'source_path': binding['path'],
            'source_sha256': binding['sha256'],
            'representation': 'web-tool search result excerpt, not HTTP body'}


def _parse_reference(selection: dict, evidence: dict) -> dict:
    binding, raw = _extract_webtool(evidence['nationality_reference'], field='reference')
    lines = [line.partition(': ')[2].strip() for line in raw.splitlines() if ': ' in line]
    full_line = next((line.split('|', 1)[1].strip() for line in lines if line.casefold().startswith('full name ')), '')
    dob_line = next((line.split('|', 1)[1].strip() for line in lines if line.casefold().startswith('date of birth ')), '')
    identity = next((line for line in lines if line.startswith(selection['reference_full_name'] + ' (born ')), '')
    match = re.fullmatch(r'(.+?)\s*\(born\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})\)\s+is an?\s+([A-Za-z -]+?)\s+former\b.*', identity)
    if not match or full_line != selection['reference_full_name'] or match.group(1) != selection['reference_full_name']:
        raise ValueError('secondary reference full-name clause differs')
    dob = datetime.strptime(match.group(2), '%d %B %Y').date().isoformat()
    dob_iso = re.search(r'\((\d{4}-\d{2}-\d{2})\)', dob_line)
    demonym = ' '.join(match.group(3).casefold().split())
    tokens = lambda value: re.findall(r'[a-z]+', value.casefold())
    source_tokens, display_tokens = tokens(match.group(1)), tokens(selection['name'])
    country = DEMONYM_TO_PM99.get(demonym)
    if (dob != selection['birth_date'] or dob_iso is None or dob_iso.group(1) != dob
            or len(source_tokens) < 2 or source_tokens[0] != display_tokens[0]
            or source_tokens[-1] != display_tokens[-1]
            or country != selection['nationality']):
        raise ValueError('secondary reference name/DOB/demonym facts differ')
    return {'full_name': match.group(1), 'birth_date': dob,
            'nationality_label': demonym, 'nationality': country,
            'source_url': binding['url'], 'source_path': binding['path'],
            'source_sha256': binding['sha256'],
            'representation': 'web-tool page-text extraction, not HTTP body'}


def _season_start_year(season: str) -> int:
    match = re.fullmatch(r'((?:19|20)\d{2})-((?:\d{2}))', season or '')
    if not match or int(match.group(2)) != (int(match.group(1)) + 1) % 100:
        raise ValueError('target season is not a valid year pair')
    return int(match.group(1))


def _verify_match(selection: dict, evidence: dict, season: str, club: dict) -> dict:
    fixture = evidence['match_fixture']
    year = _season_start_year(season)
    fixture_keys = {'date', 'provider_club_id', 'competition', 'season_start_year',
                    'membership_mode', 'fixture_basis', 'path', 'sha256', 'url',
                    'first_league_capture', 'schedule_source'}
    capture_keys = {'path', 'sha256', 'url'}
    schedule_keys = {'path', 'sha256', 'url'}
    if (set(fixture) != fixture_keys or set(fixture.get('first_league_capture', {})) != capture_keys
            or set(fixture.get('schedule_source', {})) != schedule_keys
            or type(fixture['provider_club_id']) is not int
            or type(fixture['season_start_year']) is not int
            or fixture['season_start_year'] != year
            or date.fromisoformat(fixture['date']).year != year
            or fixture['membership_mode'] != 'classic-played-substitutes'
            or fixture['fixture_basis'] != 'recorded-first-league-fixture'):
        raise ValueError('fixture is not a date/club/season-bound first-league match source')
    fixture_host = urlsplit(fixture['url']).hostname or ''
    if fixture_host != 'transfermarkt.co.uk' and not fixture_host.endswith('.transfermarkt.co.uk'):
        raise ValueError('fixture report must be from the retained Transfermarkt source family')
    capture_path = (ROOT / fixture['first_league_capture']['path']).resolve(strict=True)
    if not capture_path.is_relative_to(ROOT.resolve()) or _sha(capture_path) != fixture['first_league_capture']['sha256']:
        raise ValueError('first-league capture manifest hash differs')
    capture = json.loads(capture_path.read_text(encoding='utf-8'))
    if (capture.get('season_start_year') != year
            or capture.get('source', {}).get('base_url') != fixture['first_league_capture']['url']):
        raise ValueError('first-league capture year or base URL differs')
    rows = [row for row in capture.get('clubs', [])
            if row.get('source_selector', {}).get('transfermarkt_club_id') == fixture['provider_club_id']
            and row.get('source_competition_code') == fixture['competition']]
    if len(rows) != 1:
        raise ValueError('capture manifest lacks one exact provider club/competition row')
    schedule = fixture['schedule_source']
    schedule_url = urlsplit(schedule['url'])
    if (schedule['url'] != rows[0].get('schedule_url')
            or schedule_url.scheme != 'https'
            or schedule_url.hostname != fixture_host
            or not schedule_url.path.endswith(
                f"/verein/{fixture['provider_club_id']}/saison_id/{year}")):
        raise ValueError('schedule source does not match exact captured club and season')
    manifest_rows = {row.get('cache_path'): row for row in capture.get('source', {}).get('cache_files', [])}
    report_key = f"report/{rows[0].get('source_match_id')}.html"
    schedule_key = f"schedule/{year}/{fixture['provider_club_id']}.html"
    report_manifest = manifest_rows.get(report_key)
    schedule_manifest = manifest_rows.get(schedule_key)
    if (report_manifest is None or schedule_manifest is None
            or report_manifest.get('url') != fixture['url']
            or report_manifest.get('sha256') != fixture['sha256']
            or schedule_manifest.get('url') != schedule['url']
            or schedule_manifest.get('sha256') != schedule['sha256']):
        raise ValueError('fixture report or schedule is not bound by the captured source manifest')
    exchange.verify_first_league_fixture(fixture)
    exchange.verify_match_club(fixture, club['name'])
    xi, used = exchange.match_people(fixture)
    people = [row for row in used if row['source_player_id'] == str(selection['provider_player_id'])]
    if (len(xi) != 11 or len(people) != 1
            or exchange.published_name_key(people[0]['display_name']) !=
               exchange.published_name_key(selection['name'])):
        raise ValueError('numeric Transfermarkt ID is not the named used substitute for this club')
    return {'date': fixture['date'], 'basis': 'original first-league fixture; published used substitute',
            'provider_player_id': str(selection['provider_player_id']),
            'display_name': people[0]['display_name'], 'source_url': fixture['url'],
            'linked_profile_url': people[0].get('source_url'),
            'source_path': fixture['path'], 'source_sha256': fixture['sha256']}


def verify(selection: dict, evidence: dict, season: str, club: dict) -> dict:
    if (not isinstance(selection, dict)
            or selection.get('admission_policy') != POLICY or not isinstance(evidence, dict)):
        raise ValueError('typed PL/Sky/reference profile admission shape differs')
    keys = set(selection)
    if keys == SELECTION_KEYS:
        claims = dict(selection)
    elif keys == SELECTION_KEYS | EXCHANGE_ENVELOPE_KEYS:
        if (type(selection['carrier_id']) is not int
                or not isinstance(selection['club_id'], str)
                or selection['club_id'] != club.get('id')
                or selection['fine_roles'] != [selection['editorial_fine_role']]):
            raise ValueError('opening exchange envelope differs from typed editorial role or target club')
        claims = {key: selection[key] for key in SELECTION_KEYS}
    else:
        raise ValueError('typed PL/Sky/reference profile admission has unknown or missing claims')
    evidence_refs = {key: claims[ref_field] for key, ref_field in (
        ('premier_league_profile', 'premier_league_profile'),
        ('sky_profile', 'sky_profile'), ('nationality_reference', 'nationality_reference'),
        ('premier_league_webtool', 'premier_league_webtool'), ('match_fixture', 'match'))}
    if (any(not isinstance(ref, str) for ref in evidence_refs.values())
            or len(set(evidence_refs.values())) != len(EVIDENCE_KEYS)
            or any(ref not in evidence for ref in evidence_refs.values())):
        raise ValueError('typed profile request does not bind each source-family evidence key')
    evidence = {key: evidence[ref] for key, ref in evidence_refs.items()}
    selection = claims
    if (type(selection['provider_player_id']) is not int or selection['provider_player_id'] <= 0
            or type(selection['premier_league_player_id']) is not int or selection['premier_league_player_id'] <= 0
            or not isinstance(selection['name'], str) or not selection['name'].strip()
            or not isinstance(selection['reference_full_name'], str)
            or not isinstance(selection['birth_date'], str)
            or date.fromisoformat(selection['birth_date']).isoformat() != selection['birth_date']
            or not isinstance(selection['profile_position'], str)
            or not isinstance(selection['position'], str)
            or not isinstance(selection['nationality_label'], str)
            or not isinstance(selection['nationality'], str)
            or selection['native_display_name'] != selection['name']
            or selection['editorial_role_policy'] != ROLE_POLICY
            or type(selection['editorial_fine_role']) is not int
            or not compatible(selection['position'], selection['editorial_fine_role'])
            or PROFILE_POSITION_TO_BROAD.get(selection['profile_position'].casefold()) != selection['position']
            or NATIONALITY_CODES.get(selection['nationality_label']) != selection['nationality']):
        raise ValueError('typed profile claim fields or role/country mapping differ')
    if (selection['match'] != 'match_fixture'
            or selection['premier_league_profile'] != 'premier_league_profile'
            or selection['sky_profile'] != 'sky_profile'
            or selection['nationality_reference'] != 'nationality_reference'
            or selection['premier_league_webtool'] != 'premier_league_webtool'):
        raise ValueError('typed source-family evidence references differ')
    pl = _parse_pl(selection, evidence)
    sky = _parse_sky(selection, evidence)
    pl_extract = _parse_pl_extract(selection, evidence)
    reference = _parse_reference(selection, evidence)
    if ((pl['name'], pl['position']) != (selection['name'], selection['profile_position'])
            or (sky['name'], sky['birth_date'], sky['position']) !=
               (selection['name'], selection['birth_date'], selection['profile_position'])
            or (pl_extract['name'], pl_extract['birth_date'], pl_extract['position']) !=
               (selection['name'], selection['birth_date'], selection['profile_position'])
            or pl_extract['nationality_label'] != selection['nationality_label']
            or reference['nationality'] != selection['nationality']):
        raise ValueError('independent PL/Sky/reference facts disagree')
    membership = _verify_match(selection, evidence, season, club)
    return {'policy': POLICY, 'name': selection['name'], 'birth_date': selection['birth_date'],
            'position': selection['position'], 'nationality_label': selection['nationality_label'],
            'nationality': selection['nationality'], 'profile_position': selection['profile_position'],
            'premier_league_profile': pl, 'sky_profile': sky,
            'premier_league_webtool': pl_extract, 'nationality_reference': reference,
            'membership': membership, 'membership_date': membership['date']}


def opening_date(selection: dict, evidence: dict, season: str, club: dict) -> str:
    return verify(selection, evidence, season, club)['membership_date']


def new_person(selection: dict, evidence: dict, season: str, club: dict) -> dict:
    checked = verify(selection, evidence, season, club)
    return {
        'source_person': {'name': selection['name'], 'birth_date': selection['birth_date'],
                          'source_player_id': selection['provider_player_id'],
                          'source_provider': 'transfermarkt',
                          'source_profile_url': checked['membership']['linked_profile_url']},
        'source_player': {'name': selection['name'], 'birth_date': selection['birth_date'],
                          'position': selection['position'], 'nationality': selection['nationality'],
                          'height_cm': None, 'weight_kg': None, 'shirt_number': None},
        'raw_evidence': {
            'status': 'raw-source-reparsed-and-webtool-extraction-bound',
            'local_path': checked['premier_league_profile']['source_path'],
            'source_sha256': checked['premier_league_profile']['source_sha256'],
            'source_bindings': [checked[k] for k in (
                'premier_league_profile', 'sky_profile', 'premier_league_webtool',
                'nationality_reference', 'membership')],
            'editorial_fine_role': {'policy': selection['editorial_role_policy'],
                                    'value': selection['editorial_fine_role'],
                                    'role_is_historical_fact': False},
            'published_display_name': selection['native_display_name'],
            'unavailable_personal_fields': ['height_cm', 'weight_kg', 'shirt_number'],
        },
        'membership': 'original-published-opening-used-substitute',
    }
