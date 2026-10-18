"""Independently read original Soccerbase schedules and exact match sides.

Separate provider IDs stay namespaced. A schedule date is not falsely labelled
as a date published on a match fragment. The immutable fragment URL/game ID,
numeric team badge IDs, both score/name sides and explicit firstTeam tbody
must agree. This reader does not approve a native roster transaction.
"""
import datetime as dt
import hashlib
import copy
import re
from urllib.parse import parse_qs, urlparse
from bs4 import BeautifulSoup

POLICY = 'original-full-season-Soccerbase-schedule-exact-numeric-match-side-firstTeam-v1'
LATER_SCORE_POLICY = 'original-earliest-scheduled-league-fixture-completed-later-explicit-unscored-rows-logged-v2'
_PROFILE_CACHE = {}


def key(text):
    return re.sub(r'[^a-z0-9]', '', text.casefold())


def first_fixture(raw, team_id, season, competition, exact_name, original_url, *, allow_later_unscored=False):
    source = urlparse(original_url)
    query = parse_qs(source.query)
    if (source.scheme!='https' or source.netloc!='www.soccerbase.com'
            or source.path!='/teams/team.sd' or set(query)!={'team_id','season_id','teamTabs'}
            or query['team_id']!=[str(team_id)] or query['teamTabs']!=['results']
            or len(query['season_id'])!=1 or not query['season_id'][0].isdigit()):
        raise ValueError('original Soccerbase schedule URL lacks exact club/season identity')
    page = BeautifulSoup(raw, 'lxml')
    heading = page.select_one('h1')
    if not heading or key(heading.get_text(' ', strip=True)) != key(exact_name + ' Results'):
        raise ValueError('original Soccerbase schedule club heading differs')
    # Provider season IDs are not year-1870: e.g. 2021/22 is 154, not 151.
    # Bind the original requested ID to its independently published year label.
    year = int(season[:4]); expected = query['season_id'][0]
    selector = page.select_one('select#seasonSelect')
    options = selector.select('option') if selector else []
    current = [o for o in options if o.has_attr('selected')]
    published = [o for o in options if o.get('value')==expected]
    if (len(published)!=1 or published[0].get_text(' ',strip=True)!=f'{year}/{year+1}'
            or len(current)!=1 or current[0].get('value') not in ('0', expected)):
        raise ValueError('original Soccerbase selected season differs')
    fixtures = []
    for row in page.select('tr.match[id^=tgc]'):
        label = row.select_one('td.tournament a')
        if not label or key(label.get_text(' ', strip=True)) != key(competition):
            continue
        stamp = row.select_one('td.dateTime span.hide')
        date = re.fullmatch(r'(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}', stamp.get_text(' ', strip=True) if stamp else '')
        id = re.fullmatch(r'tgc(\d+)', row.get('id', ''))
        sides = []
        for side in ('homeTeam', 'awayTeam'):
            links = row.select(f'td.{side} a[href]')
            if len(links) != 1:
                raise ValueError('original Soccerbase schedule lacks two exact team identities')
            query = parse_qs(urlparse(links[0]['href']).query)
            ids = query.get('team_id', [])
            if (len(ids) != 1 or not ids[0].isdigit()
                    or query.get('season_id') != [expected]):
                raise ValueError('original Soccerbase schedule has ambiguous numeric team identity')
            sides.append({'team_id': int(ids[0]), 'name': links[0].get_text(' ', strip=True)})
        goals = row.select('td.score a.vs em')
        completed = len(goals)==2 and all(g.get_text(strip=True).isdigit() for g in goals)
        score_cells=row.select('td.score span.vs')
        declared_unscored=(allow_later_unscored and not goals and len(score_cells)==1
            and score_cells[0].get_text(strip=True)=='v')
        if not date or not id or (not completed and not declared_unscored):
            raise ValueError('original Soccerbase league fixture lacks date, ID or completed score')
        day = dt.date.fromisoformat(date.group(1)).isoformat()
        if not f'{year}-07-01' <= day <= f'{year+1}-06-30' or sum(s['team_id']==team_id for s in sides)!=1:
            raise ValueError('original Soccerbase fixture is outside its season or belongs to another club')
        fixtures.append({'date': day, 'game_id': int(id.group(1)), 'sides': sides,
                         'score': [int(g.get_text(strip=True)) for g in goals] if completed else None})
    if not fixtures or len({f['game_id'] for f in fixtures}) != len(fixtures):
        raise ValueError('original Soccerbase schedule lacks unique league fixtures')
    earliest = min(f['date'] for f in fixtures)
    opening = [f for f in fixtures if f['date']==earliest]
    if len(opening)!=1 or opening[0]['score'] is None:
        raise ValueError('original Soccerbase first league fixture is ambiguous')
    return opening[0]


def match(raw, fixture, team_id, original_url, allow_declared_unknown_details=False):
    parsed = urlparse(original_url)
    if (parsed.scheme!='https' or parsed.netloc!='www.soccerbase.com'
            or parsed.path!='/matches/additional_information.sd'
            or parse_qs(parsed.query)!={'id_game': [str(fixture['game_id'])]}):
        raise ValueError('original match fragment URL does not identify the exact scheduled game')
    page = BeautifulSoup(raw, 'lxml')
    numeric_badges = 0
    for i, side in enumerate(('teamA', 'teamB')):
        scores = page.select(f'div.gameInfo p.score span.{side}')
        badges = page.select(f'div.gameInfo span.bage{side[0].upper()+side[1:]} img[src]')
        if len(scores)!=1 or len(badges)!=1:
            raise ValueError('original Soccerbase fragment lacks both numeric club badge identities')
        badge = re.search(r'/teambadges/(\d+)\.png$', badges[0]['src'])
        declared_missing_badge = bool(allow_declared_unknown_details and
            re.search(r'/teambadges/default\.png$', badges[0]['src']))
        goal = scores[0].select('em')
        text = ' '.join(scores[0].find_all(string=True, recursive=False)).strip()
        if ((not badge and not declared_missing_badge)
                or (badge and int(badge.group(1))!=fixture['sides'][i]['team_id']) or len(goal)!=1
                or goal[0].get_text(strip=True)!=str(fixture['score'][i])
                or key(text)!=key(fixture['sides'][i]['name'])):
            raise ValueError('original Soccerbase report club sides/names/score disagree with schedule')
        numeric_badges += bool(badge)
    if allow_declared_unknown_details and numeric_badges == 0:
        raise ValueError('original Soccerbase report lacks any independently published numeric club badge')
    side = 'teamA' if fixture['sides'][0]['team_id']==team_id else 'teamB'
    if sum(s['team_id']==team_id for s in fixture['sides'])!=1:
        raise ValueError('requested club is not one unique original match side')
    columns = page.select(f'div.lineup div.{side}')
    if len(columns)!=1:
        raise ValueError('original Soccerbase fragment lacks one exact lineup side')
    bodies = columns[0].select('tbody.firstTeam')
    if len(bodies)!=1:
        raise ValueError('original Soccerbase fragment lacks one explicit starting-XI body')
    def players(body):
        result = []
        for row in body.select('tr'):
            links = row.select('a[href*="/players/player.sd?"]')
            if not links:
                continue
            if len(links)!=1:
                raise ValueError('original lineup row has multiple player identities')
            identity_url = urlparse(links[0]['href'])
            identity_query = parse_qs(identity_url.query)
            if (identity_url.netloc not in ('', 'www.soccerbase.com')
                    or identity_url.scheme not in ('', 'https')
                    or identity_url.path != '/players/player.sd'
                    or set(identity_query) != {'player_id'}):
                raise ValueError('original lineup player URL belongs to another provider or endpoint')
            ids = identity_query.get('player_id', [])
            cells = row.select('td')
            # The away-side table mirrors the column order. Read the unique
            # exact category cell, not an assumed left-to-right index.
            roles = [m for c in cells if (m := re.fullmatch(r'\(([GDMF])\)', c.get_text(strip=True)))]
            unknown_roles = [c for c in cells if c.get_text(strip=True)=='(-)']
            declared_missing_role = bool(allow_declared_unknown_details and
                                        not roles and len(unknown_roles)==1)
            if len(ids)!=1 or not ids[0].isdigit() or (len(roles)!=1 and not declared_missing_role):
                raise ValueError('original lineup row lacks one numeric identity and dated role')
            result.append({'source_player_id': 'soccerbase:'+ids[0], 'provider_player_id': int(ids[0]),
                'published_match_name': links[0].get_text(' ',strip=True),
                'position': roles[0].group(1) if roles else None})
        return result
    xi = players(bodies[0]); bench=[]
    for body in columns[0].select('tbody'):
        if body is not bodies[0]: bench.extend(players(body))
    if len(xi)!=11 or len({p['source_player_id'] for p in xi+bench})!=len(xi+bench):
        raise ValueError('original Soccerbase lineup lacks eleven unique starters or repeats bench identity')
    result = {'policy': POLICY, 'date': fixture['date'], 'provider_club_id': 'soccerbase:'+str(team_id),
        'starting_xi': xi, 'published_bench': bench,
        'fixture_date_published_on_original_schedule': True,
        'match_page_date_independently_published': False,
        'approved_for_native_ownership_repair': False}
    if allow_declared_unknown_details:
        result['policy'] = 'original-Soccerbase-schedule-game-ID-both-names-scores-and-available-badges-v2'
        result['numeric_club_badges_published'] = numeric_badges
        result['unknown_dated_positions'] = [p['source_player_id'] for p in xi+bench if p['position'] is None]
    return result


def profile(raw, player, original_url, *, allow_missing_birth_date=False):
    source = urlparse(original_url)
    if (source.scheme!='https' or source.netloc!='www.soccerbase.com'
            or source.path!='/players/player.sd'
            or parse_qs(source.query)!={'player_id':[str(player['provider_player_id'])]}
            or player['source_player_id']!='soccerbase:'+str(player['provider_player_id'])):
        raise ValueError('original Soccerbase biography URL differs from namespaced match person')
    # Cache only successful parsed facts, keyed by the actual original bytes
    # and exact provider URL/ID. Do not retain large HTML buffers. Changed
    # bytes always miss; URL/namespace validation above always runs.
    digest=hashlib.sha256(raw.encode() if isinstance(raw,str) else raw).hexdigest()
    cache_key=(type(raw).__name__,digest,player['provider_player_id'],original_url,allow_missing_birth_date)
    if cache_key in _PROFILE_CACHE:
        return copy.deepcopy(_PROFILE_CACHE[cache_key])
    page = BeautifulSoup(raw,'lxml'); headings=page.select('h1')
    if len(headings)!=1:
        raise ValueError('original Soccerbase biography lacks one published full name')
    heading=headings[0].get_text(' ',strip=True)
    name=re.sub(r'^\d{1,2}\.\s+', '', heading)
    matches=[]; unparsed_birth_value=False
    for row in page.select('tr'):
        cells = row.find_all(['th', 'td'], recursive=False)
        if len(cells) != 2:
            continue
        label = cells[0].get_text(' ', strip=True)
        value = cells[1].get_text(' ', strip=True)
        if label == 'Born':
            born = re.fullmatch(r'(\d{1,2} [A-Z][a-z]{2}, \d{4})', value)
            if born is None and value.casefold() not in ('','unknown','n/a','-'):
                unparsed_birth_value=True
        elif label == 'Age':
            # Read the explicitly published birth date, never calculate it
            # from the current age (which is not target-season evidence).
            born = re.fullmatch(r'\d+\s+\(Born (\d{1,2} [A-Z][a-z]{2}, \d{4})\)', value)
            if born is None and 'born' in value.casefold():
                unparsed_birth_value=True
        else:
            continue
        if born:
            matches.append(dt.datetime.strptime(born.group(1), '%d %b, %Y').date().isoformat())
    if ((len(matches)!=1 and not (allow_missing_birth_date and not matches and not unparsed_birth_value))
            or not name or re.fullmatch(r'[A-Za-z]\.?\s+.+',name)):
        raise ValueError('original Soccerbase biography lacks one full-name/DOB identity')
    result={'provider_player_id':player['provider_player_id'],'source_player_id':player['source_player_id'],
        'name':name,'published_heading':heading,'birth_date':matches[0] if matches else None,
        'source_profile_url':original_url,'ownership_established_by_biography':False}
    if len(_PROFILE_CACHE)>=4096:
        _PROFILE_CACHE.pop(next(iter(_PROFILE_CACHE)))
    _PROFILE_CACHE[cache_key]=copy.deepcopy(result)
    return result
