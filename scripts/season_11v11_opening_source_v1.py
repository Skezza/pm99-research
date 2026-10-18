"""Read original English match-archive openings without inventing TM identities.

An exact dated 46-match season schedule establishes the first league fixture.
Its desktop and mobile report representations must independently select the
same exact named team, XI, substitutions and unused bench names. Archive player
IDs remain explicitly namespaced; a later original-ID/DOB bridge is required
before an ownership planner can use these inputs.
"""
import datetime as dt
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from scripts.season_historical_roster_audit_v1 import normalise

BASE = 'https://www.11v11.com'
POLICY = 'original-exact-season-complete-schedule-and-agreeing-desktop-mobile-club-lineups-v1'


def first_fixture(raw, club, season, competition, expected_games=46):
    if not isinstance(expected_games, int) or isinstance(expected_games, bool) or expected_games < 1:
        raise ValueError('expected league match count must be an explicit positive integer')
    page = BeautifulSoup(raw, 'lxml')
    headings = [h.get_text(' ', strip=True) for h in page.select('h1')]
    ending = int(season[:4]) + 1
    expected_heading = f'{club} football club match record: {ending}'
    if len(headings) != 1 or normalise(headings[0]) != normalise(expected_heading):
        raise ValueError('original archive schedule does not identify the exact club and year')
    periods = [h.get_text(' ', strip=True) for h in page.select('h2.seasonTitle')]
    if periods != [season + ' season']:
        raise ValueError('original archive schedule does not identify the exact football season')
    rows = []
    for tr in page.find_all('tr'):
        cells = tr.find_all('td', recursive=False)
        if len(cells) != 5 or cells[-1].get_text(' ', strip=True) != competition:
            continue
        links = cells[1].select('a[href^="/matches/"]')
        if len(links) != 1:
            raise ValueError('original league schedule row has ambiguous match identity')
        link = links[0]
        day = dt.datetime.strptime(cells[0].get_text(' ', strip=True), '%d %b %Y').date().isoformat()
        teams = link.get_text(' ', strip=True).split(' v ')
        if len(teams) != 2 or sum(normalise(t) == normalise(club) for t in teams) != 1:
            raise ValueError('original league schedule row does not identify one exact club side')
        if not int(season[:4]) <= int(day[:4]) <= ending:
            raise ValueError('original league fixture is outside the named football season')
        rows.append({'date': day, 'url': urljoin(BASE, link['href']),
            'home': teams[0], 'away': teams[1], 'competition': competition})
    if len(rows) != expected_games or len({r['url'] for r in rows}) != len(rows):
        raise ValueError('original schedule must contain every expected unique league match before claiming the first')
    return min(rows, key=lambda r: (r['date'], r['url']))


def _players(container):
    rows = []
    for node in container.select('.player'):
        links = node.select('a[href^="/players/"]')
        if len(links) != 1:
            raise ValueError('archive player row has ambiguous original profile identity')
        link = links[0]
        match = re.fullmatch(r'/players/[^/?#]+-(\d+)/', link['href'])
        name = link.get_text(' ', strip=True)
        if not match or not name:
            raise ValueError('archive player row lacks an exact published name/profile')
        rows.append({'source_player_id': '11v11:' + match.group(1), 'name': name,
            'source_profile_url': urljoin(BASE, link['href'])})
    if len({r['source_player_id'] for r in rows}) != len(rows):
        raise ValueError('archive lineup repeats a player identity')
    return rows


def match_view(raw, club, fixture, view):
    page = BeautifulSoup(raw, 'lxml')
    expected_heading = f"{fixture['home']} v {fixture['away']}, " + dt.date.fromisoformat(fixture['date']).strftime('%d %B %Y')
    headings = [h.get_text(' ', strip=True) for h in page.select('h1')]
    if headings != [expected_heading]:
        raise ValueError('original report date/teams disagree with the first league schedule fixture')
    competitions = []
    for tr in page.select('.basicData tr'):
        cells = tr.find_all('td', recursive=False)
        if len(cells) == 2 and cells[0].get_text(' ', strip=True) == 'Competition':
            competitions.append(cells[1].get_text(' ', strip=True))
    if competitions != [fixture['competition']]:
        raise ValueError('original report has another or ambiguous competition')
    if view == 'desktop':
        roots = page.select('.teams-new.hide-mobile')
        if len(roots) != 1:
            raise ValueError('original report lacks one desktop representation')
        root = roots[0]
        headers = root.select('.headers h2.teamname')
    elif view == 'mobile':
        roots = page.select('.row.show-mobile')
        if len(roots) != 1:
            raise ValueError('original report lacks one mobile representation')
        root = roots[0]
        headers = root.select('h2.teamname')
    else:
        raise ValueError('unsupported original archive representation')
    matching = [h for h in headers if len(h.select('a[href^="/teams/"]')) == 1
                and normalise(h.select_one('a').get_text(' ', strip=True)) == normalise(club)]
    if len(matching) != 1:
        raise ValueError('original report representation does not identify one exact requested team')
    side = set(matching[0].parent.get('class', [])) & {'home', 'away'}
    if len(side) != 1:
        raise ValueError('original report team side is ambiguous')
    side = next(iter(side))
    containers = (root.select('.lineup > .' + side) if view == 'desktop'
                  else root.select('.lineup.' + side))
    xi, bench = [], []
    for node in containers:
        heading = node.find('h4', recursive=False)
        text = heading.get_text(' ', strip=True) if heading else ''
        if text == 'Starting lineup:': xi.append(_players(node))
        elif text == 'On the bench:': bench.append(_players(node))
    if len(xi) != 1 or len(xi[0]) != 11 or len(bench) > 1:
        raise ValueError('original report does not identify exactly eleven starters and one bench')
    bench = bench[0] if bench else []
    if {r['source_player_id'] for r in xi[0]} & {r['source_player_id'] for r in bench}:
        raise ValueError('archive bench and first XI overlap')
    comments = (root.select('.comments > .' + side) if view == 'desktop'
                else root.select('.comments.' + side))
    unused = []
    for comment in comments:
        text = comment.get_text(' ', strip=True)
        if text.startswith('Comments: Unused substitutes:'):
            text = text.removeprefix('Comments: Unused substitutes:').strip().rstrip('.')
            unused.extend(part.strip() for part in re.split(r',\s*|\s+and\s+', text) if part.strip())
        elif text.removeprefix('Comments:').strip():
            raise ValueError('unparsed original report comments require explicit reconciliation')
    subs = (root.select('.substitutions > .' + side) if view == 'desktop'
            else root.select('.substitutions.' + side))
    used = []
    for box in subs:
        for tr in box.find_all('tr'):
            incoming, outgoing = tr.select('.substitute'), tr.select('.substituted')
            if len(incoming) != 1 or len(outgoing) != 1:
                raise ValueError('original substitution event cannot be independently selected')
            used.append({'incoming_name': incoming[0].get_text(' ', strip=True),
                'outgoing_name': outgoing[0].get_text(' ', strip=True)})
    return {'starting_xi': xi[0], 'published_linked_bench': bench,
        'unused_substitute_names': unused, 'used_substitution_events': used}


def verify_pair(schedule, report, club, season, competition, expected_games=46):
    fixture = first_fixture(schedule, club, season, competition, expected_games)
    desktop = match_view(report, club, fixture, 'desktop')
    mobile = match_view(report, club, fixture, 'mobile')
    if desktop != mobile:
        raise ValueError('original desktop and mobile club lineup evidence disagrees')
    return {'policy': POLICY, 'club': club, 'season': season, 'fixture': fixture,
        **desktop, 'manager': None, 'formation': None,
        'identity_namespace': '11v11; no Transfermarkt IDs assigned',
        'approved_for_duplicate_ownership': False}


def profile_person(raw, player):
    """Only original full-name heading and exact structured birth-date field."""
    id_match = re.fullmatch(r'11v11:(\d+)', player['source_player_id'])
    url_match = re.fullmatch(r'https://www\.11v11\.com/players/[^/?#]+-(\d+)/', player['source_profile_url'])
    if not id_match or not url_match or id_match.group(1) != url_match.group(1):
        raise ValueError('archive biography URL does not identify its namespaced lineup player ID')
    page = BeautifulSoup(raw, 'lxml')
    headings = [h.get_text(' ', strip=True) for h in page.select('h1')]
    if len(headings) != 1 or normalise(headings[0]) != normalise(player['name']):
        raise ValueError('original archive biography does not identify the exact lineup name')
    dates = []
    for tr in page.find_all('tr'):
        cells = tr.find_all('td', recursive=False)
        if len(cells) == 2 and cells[0].get_text(' ', strip=True) == 'Date of birth':
            dates.append(cells[1].get_text(' ', strip=True))
    if len(dates) != 1 or not re.fullmatch(r'\d{1,2} [A-Za-z]+ \d{4}', dates[0]):
        raise ValueError('original archive biography lacks one exact structured birth date')
    return {'archive_player_id': player['source_player_id'], 'name': headings[0],
        'birth_date': dt.datetime.strptime(dates[0], '%d %B %Y').date().isoformat(),
        'source_profile_url': player['source_profile_url']}


def bridge_person(raw, player, people):
    """Match two publishers only through independently original full name/DOB.

    Keep both identity namespaces. A new source person cannot be manufactured,
    and a pinned conflicting DOB cannot be overridden by this bridge.
    """
    from scripts import season_historical_transfer_review_v1 as transfer
    original = profile_person(raw, player)
    person = transfer.unique_person({'name': original['name'], 'facts': original}, people)
    if person is None:
        raise ValueError('archive original full-name/DOB lacks one confirmed bound historical person')
    return {'original_archive_person': original, 'bound_historical_person': person,
        'method': 'original-archive-full-name-structured-DOB-to-unique-bound-published-person'}
