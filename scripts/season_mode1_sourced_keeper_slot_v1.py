"""Source-bound correction of a reserve keeper wrongly omitted from slot one.

Only the original first played league XI/bench pair authorizes the reciprocal
two-byte change. Unrelated duplicate starter orders remain explicit problems.
"""
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from app.player_initial_order import OrderReplacement, patch_owned_mode1_reserve_keeper_slot
from app.fdi_indexed import IndexedFDIFile
from app.eq_jug_linked import parse_eq_external_team_roster_payload
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_football_data_opening_dates_v1 as dates
from scripts import season_within_club_reserve_repair_v1 as roster
from scripts import season_historical_roster_audit_v1 as annual
from scripts import season_package_v2 as packages

SCHEMA = 'pm99-mode1-original-first-fixture-reserve-keeper-slot-v1'
PREFIX = 'mode1-sourced-keeper-slot-'
FILENAME = 'mode1-sourced-keeper-slot.json'


def original(binding):
    path = registry.ROOT / binding['path']
    registry.relative_workspace_path(path)
    if registry.sha256_file(path) != binding['sha256']:
        raise ValueError('original keeper-slot source bytes changed')
    return path


def report(raw, url, club, opponent, day):
    parsed = urlparse(url)
    if (parsed.scheme != 'https' or parsed.netloc != 'www.skysports.com'
            or not parsed.path.startswith('/football/') or '/teams/' not in parsed.path
            or parsed.query or parsed.fragment):
        raise ValueError('keeper XI needs an original Sky Sports teams report URL')
    page = BeautifulSoup(raw, 'lxml')
    titles = page.select('head > title')
    expected = 'Starting Lineups - ' + club + ' vs ' + opponent + ' | ' + datetime.fromisoformat(day).strftime('%d.%m.%Y')
    if len(titles) != 1 or titles[0].get_text(strip=True) != expected:
        raise ValueError('original report title differs from the exact played fixture')
    columns = [h.parent.parent for h in page.select('h4.sdc-site-team-lineup__team-name')
               if h.get_text(' ', strip=True) == club]
    if len(columns) != 1:
        raise ValueError('original report needs one exact club lineup')
    column = columns[0]
    tables = column.select('dl.sdc-site-team-lineup__players')
    starters = [t for t in tables if 'sdc-site-team-lineup__players--subs' not in t.get('class', [])]
    benches = [t for t in tables if 'sdc-site-team-lineup__players--subs' in t.get('class', [])]
    if len(starters) != 1 or len(benches) != 1:
        raise ValueError('original XI and bench are missing or ambiguous')

    def names(table):
        output = []
        for item in table.select('dd.sdc-site-team-lineup__player-name'):
            surname = item.select('span.sdc-site-team-lineup__player-surname')
            initials = item.select('span.sdc-site-team-lineup__player-initial')
            if len(surname) != 1 or len(initials) > 1:
                raise ValueError('ambiguous original named player')
            given = initials[0].get('title', '').strip() if initials else ''
            if initials and (not given or given[0].casefold() != initials[0].get_text(strip=True).casefold()):
                raise ValueError('original player full given name is not published')
            output.append((given + ' ' + surname[0].get_text(' ', strip=True)).strip())
        if len(output) != len(set(output)):
            raise ValueError('original lineup repeats a name')
        return output
    xi, bench = names(starters[0]), names(benches[0])
    if len(xi) != 11 or not bench or set(xi) & set(bench):
        raise ValueError('original report lacks eleven distinct starters and a separate bench')
    return {'fixture_date': day, 'starting_xi_names': xi, 'bench_names': bench,
            'name_policy': 'literal published full given-name title plus surname; no initial expansion',
            'complete_native_XI_repair_claimed': False}


def prepare(release, keeper_id, outfielder_id, bindings):
    package = json.loads(release.package_path.read_text())
    players = {p['carrier_id']: p for p in package['players']}
    keeper, outfielder = players[keeper_id], players[outfielder_id]
    if keeper['club_id'] != outfielder['club_id'] or keeper_id == outfielder_id:
        raise ValueError('keeper pair must be distinct same-club recipe players')
    club = next(c for c in package['clubs'] if c['id'] == keeper['club_id'])
    if club['opening'].get('policy') != 'preserve-existing-mode1':
        raise ValueError('reserve keeper policy is mode1 only')
    results = original(bindings['league_results'])
    receipt = json.loads(original(bindings['league_results_receipt']).read_text())
    for key in ('requested_url', 'response_url'):
        dates.validate_url(receipt[key], release.season, 'I1')
    if receipt['sha256'] != registry.sha256_file(results):
        raise ValueError('original results receipt does not bind the CSV')
    first = dates.first_fixture(results.read_bytes(), release.season, 'I1', club['name'])
    fixture = first['fixture']
    if fixture['home'] != club['name']:
        raise ValueError('this policy currently requires a literal home-club report title')
    evidence = report(original(bindings['lineup_report']).read_bytes(), bindings['report_url'],
                      club['name'], fixture['away'], fixture['date'])
    capture, proof = roster.annual_capture(release.season, club)
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    rows = []
    for player, membership in ((outfielder, 'bench_names'), (keeper, 'starting_xi_names')):
        name = player.get('source_name') or player['name']
        if evidence[membership].count(name) != 1:
            raise ValueError('literal original full name does not establish the keeper/bench pair')
        matches = [p for p in capture['players'] if annual.normalise(p['name']) == annual.normalise(name)]
        native = roster.native_facts(jug, player['carrier_id'])
        if (len(matches) != 1 or matches[0]['birth_date'] != native['birth_date']
                or matches[0]['position'] != native['position']):
            raise ValueError('annual full identity/DOB/position disagrees with native keeper pair')
        rows.append({'player_id': player['id'], 'carrier_id': player['carrier_id'],
                     'source_name': name, 'native_name': native['name'], 'birth_date': native['birth_date'],
                     'position': native['position'], 'before': native['startup_order']})
    if rows[0]['before'] != 1 or rows[1]['before'] <= 11 or rows[1]['position'] != 'G':
        raise ValueError('expected misplaced outfielder and reserve keeper are absent')
    rows[0]['after'], rows[1]['after'] = rows[1]['before'], 1
    plan = {'schema_version': SCHEMA, 'season': release.season, 'source_release_id': release.release_id,
            'package_sha256': registry.sha256_file(release.package_path),
            'jug_sha256': registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
            'eq_sha256': registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'),
            'club_id': club['id'], 'club_carrier_id': club['carrier_id'], 'club': club['name'],
            'bindings': bindings, 'first_fixture': first, 'original_XI_bench': evidence,
            'annual_capture': capture, 'annual_proof': proof, 'players': rows,
            'complete_native_XI_repair_claimed': False}
    apply(jug, (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes(), plan)
    return plan


def apply(jug, eq, plan):
    if plan.get('schema_version') != SCHEMA or len(plan['players']) != 2:
        raise ValueError('unsupported reserve keeper source plan')
    members = target_members(eq, plan['club_carrier_id'])
    if not {p['carrier_id'] for p in plan['players']} <= members:
        raise ValueError('source keeper pair no longer belongs to the target native club')
    rows = [OrderReplacement(p['carrier_id'], p['native_name'], p['before'], p['after']) for p in plan['players']]
    return patch_owned_mode1_reserve_keeper_slot(jug, eq, rows)


def target_members(eq, carrier):
    entries = [e for e in IndexedFDIFile.from_bytes(eq).entries if e.record_id == carrier]
    if len(entries) != 1:
        raise ValueError('keeper source target club is absent or ambiguous')
    entry = entries[0]
    roster = parse_eq_external_team_roster_payload(eq[entry.payload_offset:entry.payload_offset + entry.payload_length], {})
    if roster is None or roster.mode_byte != 1 or any(r.flag for r in roster.rows):
        raise ValueError('keeper source target needs one visible mode1 roster')
    return {r.player_record_id for r in roster.rows}


def validate_recipe_scope(package, plan):
    clubs = [c for c in package['clubs'] if c['id'] == plan['club_id']]
    if len(clubs) != 1 or (clubs[0]['carrier_id'], clubs[0]['name']) != (plan['club_carrier_id'], plan['club']):
        raise ValueError('recipe keeper source club changed')
    people = {p['id']: p for p in package['players']}
    for row in plan['players']:
        player = people.get(row['player_id'])
        if (player is None or row['player_id'] not in clubs[0]['roster_player_ids']
                or (player['carrier_id'], player['club_id'], player.get('source_name') or player['name']) !=
                   (row['carrier_id'], plan['club_id'], row['source_name'])):
            raise ValueError('recipe keeper source person or membership changed')
        literal = player['facts'].get('birth_date')
        if isinstance(literal, str) and literal != row['birth_date']:
            raise ValueError('recipe keeper source birth date changed')


def verify_bound(release, plan):
    if (plan['source_release_id'], plan['package_sha256'], plan['jug_sha256'], plan['eq_sha256']) != (
            release.release_id, registry.sha256_file(release.package_path),
            registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
            registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI')):
        raise ValueError('keeper source plan no longer binds the baseline')
    if prepare(release, plan['players'][1]['carrier_id'], plan['players'][0]['carrier_id'], plan['bindings']) != plan:
        raise ValueError('original keeper slot source plan does not independently reproduce')


def bind(package, plan):
    validate_recipe_scope(package, plan)
    output = copy.deepcopy(package)
    identity = PREFIX + plan['season'] + '-' + str(plan['club_carrier_id'])
    output['artifacts'].append({'id': identity, 'kind': 'season-input', 'relative_path': FILENAME,
        'sha256': hashlib.sha256(pipeline.canonical_json_bytes(plan) + b'\n').hexdigest(), 'media_type': 'application/json'})
    output['artifacts'].sort(key=lambda a: a['id'])
    packages.validate_package(output)
    return output


def replay(jug, eq, package, package_path):
    changed = []
    for artifact in package['artifacts']:
        if not artifact['id'].startswith(PREFIX):
            continue
        relative = Path(artifact['relative_path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe keeper plan path')
        path = package_path.parent / relative
        if registry.sha256_file(path) != artifact['sha256']:
            raise ValueError('recipe keeper source plan hash changed')
        plan = json.loads(path.read_text())
        season = str(package['season']['start_year']) + '-' + str(package['season']['end_year'])[-2:]
        if plan['season'] != season:
            raise ValueError('recipe keeper source plan season differs')
        validate_recipe_scope(package, plan)
        for row in plan['players']:
            facts = roster.native_facts(jug, row['carrier_id'])
            if (facts['birth_date'], facts['position']) != (row['birth_date'], row['position']):
                raise ValueError('compiled keeper source birthday or position changed')
        baseline = registry.load_registered_release(plan['season'], plan['source_release_id'])
        verify_bound(baseline, plan)
        jug = apply(jug, eq, plan)
        changed.append({'club': plan['club'], 'players': plan['players']})
    return jug, changed
