"""Portable synthetic API tests for the typed PL/Sky profile crosswalk.

No local corpus or retained source package is required. The optional Beagrie
check is isolated in its own skip-on-absence test.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import season_opening_profile_crosswalk_admission_v3 as module


def _write_binding(root, key, body, url, *, webtool=False, reference_id=None):
    source_dir = root / 'source-fixtures'
    source_dir.mkdir(parents=True, exist_ok=True)
    path = source_dir / f'{key}.body'
    path.write_bytes(body)
    body_sha = hashlib.sha256(body).hexdigest()
    receipt = {
        'schema': module.WEBTOOL_SCHEMA if webtool else module.HTTP_SCHEMA,
        'sha256': body_sha,
        'requested_url': url,
        'final_url': url,
        'representation': 'web-tool synthetic text extraction, not an HTTP body' if webtool
            else 'original HTTP response body; bytes saved unchanged',
    }
    if webtool:
        receipt['web_tool_reference_id'] = reference_id
    else:
        receipt['status'] = 200
    receipt_path = source_dir / f'{key}.receipt.json'
    receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding='utf-8')
    binding = {
        'path': path.relative_to(root).as_posix(),
        'sha256': body_sha,
        'url': url,
        'receipt_path': receipt_path.relative_to(root).as_posix(),
        'receipt_sha256': hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
    }
    if webtool:
        binding['web_tool_reference_id'] = reference_id
    return binding


def _synthetic_case(root, *, year, player_id, pl_id, name, dob, nationality, demonym,
                    profile_position='Midfielder', competition='FR1', club_id=77):
    slug = name.casefold().replace(' ', '-')
    season = f'{year}-{(year + 1) % 100:02d}'
    date = f'{year}-08-02'
    pl_url = f'https://www.premierleague.com/en/players/{pl_id}/{slug}/overview'
    sky_url = f'https://www.skysports.com/football/player/{pl_id + 100000}/{slug}'
    pl_html = f'''<html><head><title>{name} Club {profile_position}, Profile &amp; Stats | Premier League</title>
<link rel="canonical" href="{pl_url}"><meta name="description" content="{profile_position} {name} profile."></head>
<body><div data-widget="player-profile/player-profile-tabs" data-player-id="{pl_id}" data-player-name="{name}"></div></body></html>'''.encode()
    day, month, year_part = dob[8:10], dob[5:7], dob[:4]
    sky_html = f'''<html><head><title>{name} | Player Profile | Sky Sports Football</title>
<meta property="og:url" content="{sky_url}"></head><body>
<span itemprop="name">{name}</span><span itemprop="birthDate">{day}/{month}/{year_part}</span>
<div class="row-table details"><p>Position: {profile_position}</p></div></body></html>'''.encode()
    pl_tool = f'''{name} Club {profile_position}, Profile &amp; Stats | Premier League ({pl_url})
\uE208cite\uE000testsearch-{player_id}\uE201
Image: {name}
# {name}
{profile_position}
Follow
* ### Nationality
Image: {nationality} Country Flag
{nationality}
* ### Date of Birth
{day}/{month}/{year_part}
'''
    full_name = name
    reference = f'''L125: Full name | {full_name}
L126: Date of birth | ({dob}) {int(day)} {['January','February','March','April','May','June','July','August','September','October','November','December'][int(month)-1]} {year_part}
L153: {full_name} (born {int(day)} {['January','February','March','April','May','June','July','August','September','October','November','December'][int(month)-1]} {year_part}) is a {demonym} former professional footballer.
'''
    evidence = {
        'premier_league_profile': _write_binding(root, f'pl-{player_id}', pl_html, pl_url),
        'sky_profile': _write_binding(root, f'sky-{player_id}', sky_html, sky_url),
        'premier_league_webtool': _write_binding(root, f'pl-extract-{player_id}', pl_tool.encode(),
                                                  pl_url, webtool=True,
                                                  reference_id=f'testsearch-{player_id}'),
        'nationality_reference': _write_binding(root, f'reference-{player_id}', reference.encode(),
                                                 f'https://en.wikipedia.org/wiki/{slug.title().replace("-", "_")}',
                                                 webtool=True, reference_id=f'testview-{player_id}'),
    }

    match_id = player_id + 500000
    report_url = f'https://www.transfermarkt.co.uk/spielbericht/index/spielbericht/{match_id}'
    schedule_url = f'https://www.transfermarkt.co.uk/sample-fc/spielplan/verein/{club_id}/saison_id/{year}'
    report = f'synthetic original report {name}'.encode()
    schedule = f'<html><link rel="canonical" href="{schedule_url}"></html>'.encode()
    capture = {
        'season_start_year': year,
        'source': {'base_url': 'https://www.transfermarkt.co.uk', 'cache_files': [
            {'cache_path': f'report/{match_id}.html', 'url': report_url,
             'sha256': hashlib.sha256(report).hexdigest()},
            {'cache_path': f'schedule/{year}/{club_id}.html', 'url': schedule_url,
             'sha256': hashlib.sha256(schedule).hexdigest()},
        ]},
        'clubs': [{'source_selector': {'transfermarkt_club_id': club_id,
                                       'transfermarkt_name': 'sample-fc'},
                   'source_competition_code': competition, 'schedule_url': schedule_url,
                   'first_league_fixture_date': date, 'lineup_source_url': report_url,
                   'source_match_id': match_id}],
    }
    capture_path = root / f'capture-{year}-{player_id}.json'
    capture_path.write_text(json.dumps(capture), encoding='utf-8')
    report_path = root / f'report-{year}-{player_id}.html'
    report_path.write_bytes(report)
    schedule_path = root / f'schedule-{year}-{player_id}.html'
    schedule_path.write_bytes(schedule)
    evidence['match_fixture'] = {
        'date': date, 'provider_club_id': club_id, 'competition': competition,
        'season_start_year': year, 'membership_mode': 'classic-played-substitutes',
        'fixture_basis': 'recorded-first-league-fixture',
        'path': report_path.relative_to(root).as_posix(),
        'sha256': hashlib.sha256(report).hexdigest(), 'url': report_url,
        'first_league_capture': {'path': capture_path.relative_to(root).as_posix(),
            'sha256': hashlib.sha256(capture_path.read_bytes()).hexdigest(),
            'url': 'https://www.transfermarkt.co.uk'},
        'schedule_source': {'path': schedule_path.relative_to(root).as_posix(),
            'sha256': hashlib.sha256(schedule).hexdigest(), 'url': schedule_url},
    }
    selection = {
        'admission_policy': module.POLICY, 'provider_player_id': player_id,
        'premier_league_player_id': pl_id, 'name': name,
        'reference_full_name': full_name, 'birth_date': dob,
        'profile_position': profile_position, 'position': 'M',
        'nationality_label': nationality, 'nationality': {'France':'FRA','Spain':'ESP'}[nationality],
        'editorial_role_policy': module.ROLE_POLICY, 'editorial_fine_role': 13,
        'native_display_name': name, 'match': 'match_fixture',
        'premier_league_profile': 'premier_league_profile', 'sky_profile': 'sky_profile',
        'nationality_reference': 'nationality_reference',
        'premier_league_webtool': 'premier_league_webtool',
    }
    return selection, evidence, season, {'id': f'club-{club_id}', 'carrier_id': club_id,
                                         'name': 'Sample FC'}


@pytest.mark.parametrize(('year', 'player_id', 'pl_id', 'name', 'dob', 'country', 'demonym'), [
    (2003, 99001, 8899, 'Alex Sample', '1982-03-04', 'France', 'French'),
    (2010, 99002, 8898, 'Bea Example', '1986-11-20', 'Spain', 'Spanish'),
])
def test_synthetic_profile_crosswalk_admits_different_person_and_year(
        tmp_path, year, player_id, pl_id, name, dob, country, demonym):
    selection, evidence, season, club = _synthetic_case(
        tmp_path, year=year, player_id=player_id, pl_id=pl_id, name=name, dob=dob,
        nationality=country, demonym=demonym)
    original_root = module.ROOT
    module.ROOT = tmp_path
    xi = [{'source_player_id': str(n), 'display_name': f'Player {n}'} for n in range(11)]
    used = [{'source_player_id': str(player_id), 'display_name': name,
             'source_url': f'https://www.transfermarkt.co.uk/player/{player_id}'}]
    try:
        with patch.object(module.exchange, 'verify_first_league_fixture'), \
             patch.object(module.exchange, 'verify_match_club'), \
             patch.object(module.exchange, 'match_people', return_value=(xi, used)):
            result = module.verify(selection, evidence, season, club)
            person = module.new_person(selection, evidence, season, club)
        assert result['membership_date'] == evidence['match_fixture']['date']
        assert result['membership']['provider_player_id'] == str(player_id)
        assert result['nationality'] == selection['nationality']
        assert person['source_person']['name'] == name
        assert person['source_person']['birth_date'] == dob
        assert person['source_player']['height_cm'] is None
        assert person['raw_evidence']['editorial_fine_role']['role_is_historical_fact'] is False
    finally:
        module.ROOT = original_root


def _reject(selection, evidence, season, club, *, root):
    original_root = module.ROOT
    module.ROOT = root
    try:
        with patch.object(module.exchange, 'verify_first_league_fixture'), \
             patch.object(module.exchange, 'verify_match_club'), \
             patch.object(module.exchange, 'match_people', return_value=(
                 [{'source_player_id': str(n), 'display_name': f'Player {n}'} for n in range(11)],
                 [{'source_player_id': str(selection['provider_player_id']),
                   'display_name': selection['name']}])):
            with pytest.raises((ValueError, KeyError, TypeError)):
                module.verify(selection, evidence, season, club)
    finally:
        module.ROOT = original_root


def test_synthetic_negative_wrong_dob_wrong_name_wrong_fixture_year(tmp_path):
    selection, evidence, season, club = _synthetic_case(
        tmp_path, year=2003, player_id=99001, pl_id=8899, name='Alex Sample',
        dob='1982-03-04', nationality='France', demonym='French')
    changed = copy.deepcopy(selection)
    changed['birth_date'] = '1982-03-05'
    _reject(changed, evidence, season, club, root=tmp_path)
    changed = copy.deepcopy(selection)
    changed['name'] = 'Alex Other'
    _reject(changed, evidence, season, club, root=tmp_path)
    changed = copy.deepcopy(evidence)
    changed['match_fixture']['season_start_year'] = 2004
    _reject(selection, changed, season, club, root=tmp_path)
    _reject(selection, evidence, '2004-05', club, root=tmp_path)


def test_synthetic_negative_wrong_person_id_and_receipt_hash(tmp_path):
    selection, evidence, season, club = _synthetic_case(
        tmp_path, year=2010, player_id=99002, pl_id=8898, name='Bea Example',
        dob='1986-11-20', nationality='Spain', demonym='Spanish')
    wrong_rows = [{'source_player_id': str(n), 'display_name': f'Player {n}'} for n in range(11)]
    with patch.object(module.exchange, 'verify_first_league_fixture'), \
         patch.object(module.exchange, 'verify_match_club'), \
         patch.object(module.exchange, 'match_people', return_value=(wrong_rows, [
             {'source_player_id': '12345', 'display_name': 'Bea Example'}])):
        old_root = module.ROOT
        module.ROOT = tmp_path
        try:
            with pytest.raises(ValueError, match='numeric Transfermarkt ID'):
                module.verify(selection, evidence, season, club)
        finally:
            module.ROOT = old_root

    changed = copy.deepcopy(evidence)
    changed['sky_profile']['sha256'] = '0' * 64
    _reject(selection, changed, season, club, root=tmp_path)


def test_actual_beagrie_profile_source_optional():
    root = module.registry.ROOT
    input_path = root / '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/hearts-locke-order-correction-v1/beagrie-profile-admission-v1/beagrie-profile-admission-input-v2.json'
    if not input_path.is_file():
        pytest.skip('retained Beagrie corpus is not available in this checkout')
    source_data = json.loads(input_path.read_text(encoding='utf-8'))
    original_root = module.ROOT
    module.ROOT = root
    try:
        with patch.object(module.exchange, 'verify_first_league_fixture'), \
             patch.object(module.exchange, 'verify_match_club'), \
             patch.object(module.exchange, 'match_people', return_value=(
                 [{'source_player_id': str(n), 'display_name': f'Player {n}'} for n in range(11)],
                 [{'source_player_id': str(source_data['selection']['provider_player_id']),
                   'display_name': source_data['selection']['name']}])):
            result = module.verify(source_data['selection'], source_data['evidence'],
                                   source_data['season'],
                                   {'id':'english-club-301','carrier_id':301,'name':'Bradford City'})
        assert result['name'] == 'Peter Beagrie'
        assert result['membership']['provider_player_id'] == '138385'
    finally:
        module.ROOT = original_root


@pytest.mark.parametrize('problem', ['extra_fact', 'noncanonical_pl_route', 'spoofed_tm_host'])
def test_source_family_and_selection_guards_with_consistent_receipts(tmp_path, problem):
    selection, evidence, season, club = _synthetic_case(
        tmp_path, year=2003, player_id=99001, pl_id=8899, name='Alex Sample',
        dob='1982-03-04', nationality='France', demonym='French')
    if problem == 'extra_fact':
        selection['height_cm'] = 180
    elif problem == 'spoofed_tm_host':
        evidence['match_fixture']['url'] = evidence['match_fixture']['url'].replace(
            'www.transfermarkt.co.uk', 'eviltransfermarkt.co.uk')
    else:
        old = evidence['premier_league_webtool']
        url = old['url'] + '?unapproved=1'
        body = (tmp_path / old['path']).read_bytes().replace(old['url'].encode(), url.encode())
        evidence['premier_league_webtool'] = _write_binding(
            tmp_path, 'noncanonical-profile', body, url, webtool=True,
            reference_id=old['web_tool_reference_id'])
    _reject(selection, evidence, season, club, root=tmp_path)


def test_actual_paired_locke_beagrie_probe_receipt_optional():
    root = module.registry.ROOT
    receipt_path = root / '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/hearts-locke-order-correction-v1/beagrie-profile-admission-v1/paired-locke-beagrie-r322-inmemory-receipt-v1.json'
    plan_path = root / '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/hearts-locke-order-correction-v1/beagrie-profile-admission-v1/paired-locke-beagrie-r322-inmemory-plan-v1.json'
    if not receipt_path.is_file() or not plan_path.is_file():
        pytest.skip('retained paired Locke/Beagrie corpus probe is not available')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    assert receipt['result'] == 'PASS_PREPARE_VERIFY_BIND_APPLY_IN_MEMORY'
    assert receipt['plan_sha256'] == hashlib.sha256(plan_path.read_bytes()).hexdigest()
    assert receipt['moves']['person'] == 'Gary Locke'
    assert receipt['new_person']['name'] == 'Peter Beagrie'
    assert receipt['preserved_cottbus_mckenna']['native_payload_exact'] is True
    assert receipt['recipe_preservation']['eq_exact'] is True
    assert plan['season'] == receipt['season'] == '2000-01'
