"""Positive original-provider career brackets, not annual-squad membership.

Use already captured August match people, or opt-in annual discovery, and
exact URL/hash-bound numeric biographies. Annual discovery only nominates
an identity: a literal birthday, broad role and explicit career interval at
the original team ID must agree. No missing date, name-only club match,
zero-app absence argument or speculative reserve is admitted.
"""
import copy
from datetime import date, datetime
import re

from bs4 import BeautifulSoup
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import capture_soccerbase_august_squads_v1 as source

POLICY = 'original-Soccerbase-August-person-numeric-club-dated-career-reserve-v1'


def career_interval(raw, team_id, day):
    cutoff = date.fromisoformat(day)
    intervals = []
    for row in BeautifulSoup(raw, 'lxml').select('tr'):
        cells = row.find_all('td', recursive=False)
        if len(cells) < 4:
            continue
        links = cells[0].select('a[href]')
        if len(links) != 1 or links[0]['href'] != f'/teams/team.sd?team_id={team_id}':
            continue
        start_text, end_text = [c.get_text(' ', strip=True) for c in cells[1:3]]
        try:
            start = datetime.strptime(start_text, '%d %b, %y').date()
            end = datetime.strptime(end_text, '%d %b, %y').date()
        except ValueError:
            # Present/current and unknown dates are deliberately insufficient
            # for a frozen historical contract; no guessed exit date.
            continue
        if start <= cutoff <= end:
            intervals.append(dict(from_date=start.isoformat(), to_date=end.isoformat(),
                provider_team_id=team_id, fixture_date=day))
    if len(intervals) != 1:
        raise ValueError('one explicit original numeric-club career bracket required')
    return intervals[0]


def read_profile(path, *, person_id, team_id, day):
    receipt_path = path.with_suffix(path.suffix + '.source.json')
    receipt = pipeline.read_json_file(receipt_path)
    url = f'https://www.soccerbase.com/players/player.sd?player_id={person_id}'
    raw = path.read_bytes()
    if receipt.get('url') != url or receipt.get('sha256') != registry.sha256_file(path):
        raise ValueError('original reserve profile URL/hash changed')
    facts = source.player_profile(raw, fallback_name='', fallback_position='?')
    if not facts['birth_date'] or facts['position'] not in ('G','D','M','F'):
        raise ValueError('reserve literal biography date/role unresolved')
    interval = career_interval(raw, team_id, day)
    person = dict(name=facts['name'], birth_date=facts['birth_date'],
        source_player_id=f'soccerbase:{person_id}', provider_player_id=person_id,
        source_provider='soccerbase', source_profile_url=url)
    proof = dict(status='raw-source-reparsed', local_path=registry.relative_workspace_path(path),
        source_sha256=registry.sha256_file(path), url=url,
        receipt_path=registry.relative_workspace_path(receipt_path), receipt_sha256=registry.sha256_file(receipt_path))
    return dict(source_person=person, source_player=facts, raw_evidence=proof,
        membership='positive-original-provider-dated-opening-reserve',
        original_provider_career_interval=interval, reserve_policy=POLICY)


def candidates(season, capture, actual, selected, *, annual=None):
    found = re.fullmatch(r'soccerbase/team/([1-9][0-9]*)/august',capture['source_path'])
    if not found or actual['source_capture']['source_path'] != capture['source_path']:
        raise ValueError('reserve team differs from original fixture')
    team_id = int(found.group(1))
    root = registry.ROOT / f'.local/season-{season}/soccerbase-august-cache-v1/player'
    used = {p['source_player']['name'].casefold() for p in selected}
    pending = {p['name'].casefold():p for p in capture['players'] if p['name'].casefold() not in used}
    if len(pending) != sum(p['name'].casefold() not in used for p in capture['players']):
        raise ValueError('August capture has ambiguous repeated reserve names')
    # The annual is discovery only: admission still requires the original
    # numeric-club career bracket at the exact opening date. This allows an
    # injured/non-appearing August squad member without treating every annual
    # signing as an opening member. Never amend the old capture-only route.
    annual_candidates={}
    if annual is not None:
        for row in annual['players']:
            key=row['name'].casefold()
            if key in used or key in pending or not row.get('birth_date') or row.get('position') not in ('G','D','M','F'):
                continue
            if key in annual_candidates:
                raise ValueError('annual reserve discovery repeats a full name')
            annual_candidates[key]=row
    result = []
    for path in sorted(root.glob('*.html')):
        # Restrict first by original profile facts; membership is established
        # only by the numerical club/date parser below, never this name filter.
        facts = source.player_profile(path.read_bytes(), fallback_name='', fallback_position='?')
        expected = pending.get(facts['name'].casefold())
        if expected is not None:
            if facts != expected:continue
        else:
            expected=annual_candidates.get(facts['name'].casefold())
            if expected is None or (facts.get('birth_date'),facts.get('position')) != (
                    expected['birth_date'],expected['position']):continue
        try:
            row = read_profile(path,person_id=int(path.stem),team_id=team_id,day=actual['fixture']['date'])
        except ValueError as exc:
            if str(exc) in ('one explicit original numeric-club career bracket required',
                           'reserve literal biography date/role unresolved'):
                continue
            raise
        result.append(row)
    names = [r['source_player']['name'].casefold() for r in result]
    if len(set(names)) != len(names):
        raise ValueError('original provider has conflicting same-name reserve biographies')
    needs_backup_keeper = sum(r['source_player'].get('position')=='G' for r in selected)<2
    return sorted(result,key=lambda r:(
        0 if needs_backup_keeper and r['source_player']['position']=='G' else 1,
        r['source_person']['provider_player_id']))


def verify_reserve(row, actual):
    from scripts import season_soccerbase_duplicate_source_policy_v1 as policy
    match = re.fullmatch(r'soccerbase/team/([1-9][0-9]*)/august',actual['source_capture']['source_path'])
    id = row.get('source_person',{}).get('provider_player_id')
    if match is None or type(id) is not int or row.get('reserve_policy') != POLICY:
        raise ValueError('unsupported original-provider reserve authority')
    raw = row.get('raw_evidence',{})
    path = registry.ROOT / raw['local_path']
    if path.name != f'{id}.html':
        raise ValueError('reserve path belongs to another numerical person')
    observed = read_profile(path,person_id=id,team_id=int(match.group(1)),day=actual['fixture']['date'])
    if observed != row:
        raise ValueError('original reserve biography/bracket does not reproduce')
    return copy.deepcopy(observed)
