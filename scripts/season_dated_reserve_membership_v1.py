"""Positive dated entry AND exit permit an August reserve, without a bench claim."""
from datetime import datetime, date
import re
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_historical_roster_audit_v1 as roster

POLICY = 'original-joined-row-and-independent-registration-exit-August-bracket-v1'
SKY_POLICY = 'published-August-Sky-full-name-bench-and-target-season-squad-v1'


def verify_sky(selection, evidence, *, season=None, club=None):
    """A positively named August bench, not an inferred contract or appearance.

    Sky publishes the given name in the initial span's title. Never substitute
    initials, page-wide surname matches or the opponent's team list. The dated
    annual squad independently links that full name to the biography's TM ID.
    The existing new-person verifier still checks the exact biography/DOB.
    """
    from scripts.capture_transfermarkt_opening_lineups_v1 import _club_key
    claim = selection['opening_contract']
    anchor = date.fromisoformat(claim['opening_date'])
    if (claim.get('policy') != SKY_POLICY or anchor.month != 8
            or (season is not None and int(season[:4]) != anchor.year)):
        raise ValueError('explicit target-August Sky team-sheet policy required')
    fixture = evidence[claim['fixture']]
    url = urlsplit(fixture['url'])
    if (url.scheme != 'https' or url.netloc != 'www.skysports.com'
            or not re.fullmatch(r'/football/[a-z0-9-]+/teams/[1-9][0-9]*/?', url.path)
            or url.query or url.fragment or fixture.get('date') != anchor.isoformat()):
        raise ValueError('exact Sky fixture origin/ID/date required')
    page = BeautifulSoup(exchange.original(fixture).read_bytes(), 'lxml')
    canonical = page.select_one('link[rel="canonical"]')
    if canonical is None or canonical.get('href', '').rstrip('/') != fixture['url'].rstrip('/'):
        raise ValueError('Sky original canonical fixture differs')
    times = page.select('time.sdc-site-match-header__detail-time')
    literal = times[0].get('aria-label', '') if len(times) == 1 else ''
    stamped = re.search(r'\b(\d{1,2})(?:st|nd|rd|th) ([A-Za-z]+) (\d{4})\b', literal)
    if stamped is None or datetime.strptime(' '.join(stamped.groups()), '%d %B %Y').date() != anchor:
        raise ValueError('Sky actual fixture date differs')
    name = claim['club_name']
    if not _club_key(name) or (club is not None and _club_key(club['name']) != _club_key(name)):
        raise ValueError('Sky source club does not identify native destination')
    headers = [a for a in page.select('.sdc-site-match-header__team-name-block')
               if _club_key(a.get_text(' ', strip=True)) == _club_key(name)]
    columns = [c for c in page.select('.sdc-site-team-lineup__col')
               if any(_club_key(img.get('alt', '')) == _club_key(name)
                      for img in c.select('.sdc-site-team-lineup__header--main img.sdc-site-team-lineup__team-badge'))]
    if len(headers) != 1 or len(columns) != 1:
        raise ValueError('one exact full-name Sky club header and lineup column required')
    def full_name(row):
        initial = row.select('.sdc-site-team-lineup__player-initial')
        surname = row.select('.sdc-site-team-lineup__player-surname')
        if len(initial) != 1 or len(surname) != 1:
            return None
        given = initial[0].get('title', '').strip()
        family = surname[0].get_text(' ', strip=True)
        if not given or len(given.replace('.', '').strip()) <= 1 or not family:
            return None
        return exchange.published_name_key(given + ' ' + family)
    wanted = exchange.published_name_key(selection['name'])
    all_rows = columns[0].select('dd.sdc-site-team-lineup__player-name')
    bench = columns[0].select('.sdc-site-team-lineup__players--subs dd.sdc-site-team-lineup__player-name')
    if sum(full_name(r) == wanted for r in all_rows) != 1 or sum(full_name(r) == wanted for r in bench) != 1:
        raise ValueError('exact full-name player must appear once on the target Sky bench')
    squad = evidence[claim['season_roster']]
    requested = urlsplit(squad['url'])
    cid, pid = claim['provider_club_id'], selection['provider_player_id']
    if (type(cid) is not int or type(pid) is not int or requested.scheme != 'https'
            or requested.netloc not in ('www.transfermarkt.co.uk', 'www.transfermarkt.com', 'www.transfermarkt.us')
            or not re.fullmatch(r'/[^/]+/kader/verein/' + str(cid) + '/saison_id/' + str(anchor.year) + r'(?:/plus/1)?/?', requested.path)):
        raise ValueError('exact target-year independent squad origin/club required')
    annual = BeautifulSoup(exchange.original(squad).read_bytes(), 'lxml')
    canon = annual.select_one('link[rel="canonical"]')
    declared = urlsplit(canon.get('href', '') if canon else '')
    title = annual.title.get_text(' ', strip=True) if annual.title else ''
    selected_years = [o.get('value') for o in annual.select('select[name="saison_id"] option[selected]')]
    periods = (f'{anchor.year}/{str(anchor.year+1)[-2:]}', f'{str(anchor.year)[-2:]}/{str(anchor.year+1)[-2:]}')
    if (not canon or (declared.scheme, declared.netloc) != (requested.scheme, requested.netloc)
            or not re.fullmatch(r'/[^/]+/kader/verein/' + str(cid) + '/?', declared.path)
            or _club_key(title.split(' - ')[0]) != _club_key(name)
            or selected_years != [str(anchor.year)]
            or not any(re.search(r'(?<![0-9])' + re.escape(p) + r'(?![0-9])', title) for p in periods)):
        raise ValueError('independent squad original club/year context differs')
    def person_links(row):
        return [a for a in row.select('a[href]') if re.fullmatch(
            r'/[^/]+/profil/spieler/' + str(pid) + '/?', urlsplit(a['href']).path)]
    rows = [r for r in annual.select('table.items > tbody > tr') if person_links(r)]
    if len(rows) != 1:
        raise ValueError('one exact independent numeric squad identity required')
    links = person_links(rows[0])
    if not any(exchange.published_name_key(a.get_text(' ', strip=True)) == wanted for a in links):
        raise ValueError('Sky full identity and independent squad numeric identity disagree')
    return anchor.isoformat()


def verify(selection, evidence, *, season=None, club=None):
    claim = selection['opening_contract']
    if claim.get('policy') == SKY_POLICY:
        return verify_sky(selection, evidence, season=season, club=club)
    anchor = date.fromisoformat(claim['opening_date'])
    year = anchor.year
    if (claim.get('policy') != POLICY or anchor.month != 8
            or (season is not None and int(season[:4]) != year)):
        raise ValueError('dated reserve needs explicit target August ownership policy')
    entry, leave = evidence[claim['entry']], evidence[claim['exit']]
    exchange.dated_source(entry)
    exchange.dated_source(leave)
    pid = selection['provider_player_id']
    cid = claim['provider_club_id']
    parsed = urlsplit(entry['url'])
    if (parsed.scheme != 'https' or parsed.hostname not in ('www.transfermarkt.co.uk', 'www.transfermarkt.com', 'www.transfermarkt.us')
            or not re.search(r'/kader/verein/' + str(cid) + '/saison_id/' + str(year) + r'(?:/|$)', parsed.path)
            or entry.get('person_row', {}).get('provider_player_id') != pid
            or leave.get('dfb_registration_row', {}).get('date_kind') != 'bis'):
        raise ValueError('dated reserve original club/player/exit origin differs')
    aliases = evidence[claim['club_identity_aliases']]
    expected_path = f'seasons/{year}-{str(year+1)[-2:]}/opening-lineup-club-identity-aliases-v1.json'
    if aliases['path'] != expected_path:
        raise ValueError('dated reserve club mapping must be the recorded season identity input')
    document = pipeline.read_json_file(exchange.original(aliases))
    matches = [a for a in document['aliases'] if a['source_selector'] == claim['source_selector']
               and a['transfermarkt_club_id'] == cid]
    if document.get('schema_version') != 'pm99-transfermarkt-opening-lineup-club-identity-aliases-v1' or len(matches) != 1:
        raise ValueError('dated reserve exact native/source club mapping absent')
    if club is not None and (claim['source_selector']['club_name'] not in (club['name'], club.get('full_name'))
            or roster.source_group(claim['source_selector']['country_catalog']) != roster.club_group(club)):
        raise ValueError('dated reserve source mapping identifies another native club/country')
    page = BeautifulSoup(exchange.original(entry).read_bytes(), 'lxml')
    canonical = page.select_one('link[rel="canonical"]')
    declared = urlsplit(canonical.get('href', '') if canonical else '')
    if (canonical is None or (declared.scheme, declared.netloc) != (parsed.scheme, parsed.netloc)
            or not re.search(r'/kader/verein/' + str(cid) + r'(?:/|$)', declared.path)):
        raise ValueError('dated reserve source canonical club differs')
    rows = [r for r in page.select('table.items > tbody > tr') if r.select_one('a[href*="/profil/spieler/' + str(pid) + '"]')]
    if len(rows) != 1:
        raise ValueError('dated reserve needs one exact published joined row')
    row = rows[0]
    link = row.select_one('a[href*="/profil/spieler/' + str(pid) + '"]')
    cells = row.find_all('td', recursive=False)
    born = re.search(r'\b\d{2}/\d{2}/\d{4}\b', cells[2].get_text(' ', strip=True))
    exit_claim = leave['dfb_registration_row']
    if (exchange.published_name_key(link.get_text(' ', strip=True)) != exchange.published_name_key(selection['name'])
            or born is None or datetime.strptime(born[0], '%d/%m/%Y').date().isoformat() != selection['birth_date']
            or exchange.published_name_key(exit_claim['full_name']) != exchange.published_name_key(selection['name'])
            or datetime.strptime(exit_claim['birthday_literal'], '%d.%m.%Y').date().isoformat() != selection['birth_date']
            or not date.fromisoformat(entry['event_date']) <= anchor < date.fromisoformat(leave['event_date'])):
        raise ValueError('dated reserve exact identity or positive entry/exit bracket differs')
    return anchor.isoformat()
