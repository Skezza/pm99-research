"""Reparse targeted original first fixtures; saved claims are never authority.

This extends the existing Soccerbase ownership contract only with a different
immutable cache layout. All club lifecycle, provider identity, native-XI and
dated ownership guards remain in the established source policy.
"""
import copy
import json
import re
from bs4 import BeautifulSoup
from scripts import capture_duplicate_missing_soccerbase_openings_v1 as collector
from scripts import replay_original_soccerbase_openings_v1 as replay
from scripts import season_soccerbase_original_opening_v1 as original
from scripts import season_release_registry_v1 as registry

POLICY = 'targeted-original-Soccerbase-cache-layout-independent-replay-v1'
SCHEMA = 'pm99-targeted-original-Soccerbase-first-fixture-capture-v1'


def read_capture(binding):
    if binding.get('policy') != POLICY:
        raise ValueError('unsupported targeted original replay policy')
    path = registry.ROOT / binding['path']
    if registry.sha256_file(path) != binding['sha256']:
        raise ValueError('targeted original capture changed')
    saved = json.loads(path.read_text())
    if (saved.get('schema_version') != SCHEMA or saved.get('native_writes') != 0
            or saved.get('recipes_modified') != 0 or saved.get('historical_ownership_approved') is not False):
        raise ValueError('targeted original source must not claim native or ownership approval')
    return saved


def replay_capture(binding, season, people):
    saved = read_capture(binding)
    target = saved['target']
    if target['season'] != season:
        raise ValueError('targeted original first fixture belongs to another season')
    proofs = []; by_url = {}
    for proof in saved['raw_sources']:
        path = registry.ROOT / proof['path']; receipt = registry.ROOT / proof['receipt_path']
        if (registry.sha256_file(path) != proof['sha256']
                or registry.sha256_file(receipt) != proof['receipt_sha256']
                or json.loads(receipt.read_text()) != {'url': proof['url'], 'sha256': proof['sha256']}):
            raise ValueError('targeted original URL/SHA receipt changed')
        if proof['url'] in by_url:
            raise ValueError('targeted original URL is ambiguous')
        by_url[proof['url']] = path
        proofs.append({'path': proof['path'], 'sha256': proof['sha256'], 'url': proof['url'],
            'source_receipt_path': proof['receipt_path'], 'source_receipt_sha256': proof['receipt_sha256']})
    def raw(url):
        if url not in by_url:
            raise ValueError('targeted original lacks exact required URL')
        return by_url[url].read_bytes()
    team = saved['provider_team_id']; year = int(season[:4])
    discovery_url = f'https://www.soccerbase.com/teams/team.sd?team_id={team}&season_id=0&teamTabs=results'
    page = BeautifulSoup(raw(discovery_url), 'lxml')
    heading = page.select_one('h1')
    name = re.sub(r'\s+Results$', '', heading.get_text(' ', strip=True) if heading else '')
    if name != saved['published_club_name'] or not collector.provider_matches(name, target['club']):
        raise ValueError('targeted original provider identity does not match exact club aliases')
    options = [o for o in page.select('select#seasonSelect option')
        if o.get_text(' ', strip=True) == f'{year}/{year+1}']
    if len(options) != 1 or not str(options[0].get('value', '')).isdigit():
        raise ValueError('targeted original lacks exact historical season option')
    provider_season = int(options[0]['value'])
    if provider_season != saved['provider_season_id']:
        raise ValueError('targeted original season selector changed')
    team_url = f'https://www.soccerbase.com/teams/team.sd?team_id={team}&season_id={provider_season}&teamTabs=results'
    schedule = raw(team_url); page = BeautifulSoup(schedule, 'lxml')
    leagues = {x.get_text(' ', strip=True) for x in page.select('td.tournament a')} & collector.LEAGUES
    if leagues != {saved['competition']}:
        raise ValueError('targeted original historical league selection is ambiguous')
    fixture_policy=saved.get('first_fixture_policy')
    if fixture_policy not in (None,original.LATER_SCORE_POLICY):
        raise ValueError('unsupported targeted original first-fixture policy')
    fixture = original.first_fixture(schedule, team, season, saved['competition'], name, team_url,
        allow_later_unscored=fixture_policy==original.LATER_SCORE_POLICY)
    match_url = f"https://www.soccerbase.com/matches/additional_information.sd?id_game={fixture['game_id']}"
    sheet = original.match(raw(match_url), fixture, team, match_url, True)
    if fixture != saved['fixture'] or sheet != saved['original_match']:
        raise ValueError('targeted original fixture or first XI claim does not reproduce')
    groups = {'starting_xi': [], 'published_bench': []}; biographies = []; gaps = []
    for field in groups:
        for row in sheet[field]:
            url = f"https://www.soccerbase.com/players/player.sd?player_id={row['provider_player_id']}"
            bio = original.profile(raw(url), row, url)
            biographies.append({'membership': field, 'original_match_row': row, 'original_biography': bio})
            bridged = replay.bridge(bio, people)
            bridged.update(dated_match_position=row['position'], published_match_name=row['published_match_name'])
            groups[field].append(bridged)
            if bridged['transfermarkt_person'] is None:
                gaps.append({'source_player_id': row['source_player_id'],
                    'reason': 'no-unique-independent-full-name-DOB-provider-bridge'})
    if biographies != saved['biographies']:
        raise ValueError('targeted original full-name/DOB biography claims do not reproduce')
    if len(groups['starting_xi']) != 11:
        raise ValueError('targeted original does not identify all eleven starters')
    transfer_ids = [p['transfermarkt_person']['source_player_id'] for ps in groups.values()
        for p in ps if p['transfermarkt_person'] is not None]
    if len(transfer_ids) != len(set(transfer_ids)):
        raise ValueError('targeted original aliases conflate distinct provider people')
    return {'club': target['club'], 'status': 'original-first-fixture-reparsed',
        'source_capture': {'source_path': f'soccerbase/team/{team}/august',
            'source_sha256': registry.sha256_file(by_url[team_url]),
            'country_catalog': 'england', 'competition_catalog': saved['competition'],
            'competition_name': saved['competition'], 'targeted_original_capture': copy.deepcopy(binding)},
        'fixture': fixture, 'original_match': sheet, 'identity_bridges': groups,
        'identity_gaps': gaps, 'raw_sources': proofs, 'approved_for_native_ownership_repair': False}


def reconstruct(row, season, people):
    actual = replay_capture(row['source_capture']['targeted_original_capture'], season, people)
    if actual != {k: v for k, v in row.items() if k != 'represented_native_clubs'}:
        raise ValueError('targeted first-fixture review does not reproduce from originals')
    return actual
