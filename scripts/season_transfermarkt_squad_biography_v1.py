"""Read same-row biography facts, without pretending a profile was fetched.

Annual membership is NOT August ownership. Callers still need independent
dated membership evidence and the existing native reserve/identity guards.
"""
from datetime import datetime
import re
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup
from scripts import season_opening_identity_exchange_v1 as exchange
from scripts.capture_transfermarkt_opening_lineups_v1 import _club_key

FORMAT = 'original-target-year-transfermarkt-squad-person-row-v1'
HEADERS = ['#', 'Player', 'Date of birth/Age', 'Nat.', 'Current club',
           'Height', 'Foot', 'Joined', 'Signed from', 'Market value']
HOSTS = {'www.transfermarkt.com', 'www.transfermarkt.co.uk', 'www.transfermarkt.us'}


def independent_birthday(value, name):
    """A separately hosted, literal long date resolves DD/MM ambiguity."""
    url = urlsplit(value['url'])
    pid = value.get('provider_player_id')
    if (value.get('format') != 'soccerbase-real-name-long-birthday-v1'
            or type(pid) is not int or pid <= 0 or url.scheme != 'https'
            or url.netloc != 'www.soccerbase.com' or url.path != '/players/player.sd'
            or parse_qs(url.query) != {'player_id': [str(pid)]} or url.fragment):
        raise ValueError('independent exact Soccerbase biography required')
    page = BeautifulSoup(exchange.original(value).read_bytes(), 'lxml')
    title = page.title.get_text(' ', strip=True) if page.title else ''
    rows = [r for r in page.select('tr') if r.find('th') is not None
            and r.find('th').get_text(' ', strip=True) == 'Real name']
    if (len(rows) != 1 or rows[0].find('td') is None
            or rows[0].find('td').get_text(' ', strip=True) != name
            or title.split(' | ')[0] != name):
        raise ValueError('independent biography full identity differs')
    table = rows[0].find_parent('table')
    ages = [r for r in table.select('tr') if r.find('th') is not None
            and r.find('th').get_text(' ', strip=True) == 'Age'] if table else []
    text = ages[0].get_text(' ', strip=True) if len(ages) == 1 else ''
    born = re.search(r'\(Born (\d{1,2} [A-Z][a-z]{2}, \d{4})\)', text)
    if born is None:
        raise ValueError('independent literal birthday absent or ambiguous')
    return datetime.strptime(born[1], '%d %b, %Y').date().isoformat()


def read(value, pid, *, season, club_name, provider_club_id):
    if value.get('format') != FORMAT or type(pid) is not int or pid <= 0:
        raise ValueError('explicit squad-row biography format and numeric person required')
    year = int(season[:4])
    if season != f'{year}-{str(year + 1)[-2:]}' or type(provider_club_id) is not int or provider_club_id <= 0:
        raise ValueError('exact season and numeric club required')
    url = urlsplit(value['url'])
    club_path = r'/[^/]+/kader/verein/' + str(provider_club_id)
    if (url.scheme != 'https' or url.netloc not in HOSTS or url.query or url.fragment
            or not re.fullmatch(club_path + '/saison_id/' + str(year) + r'(?:/plus/1)?/?', url.path)):
        raise ValueError('exact target-year squad origin/club required')
    page = BeautifulSoup(exchange.original(value).read_bytes(), 'lxml')
    canon = page.select_one('link[rel="canonical"]')
    declared = urlsplit(canon.get('href', '') if canon else '')
    title = page.title.get_text(' ', strip=True) if page.title else ''
    years = [o.get('value') for o in page.select('select[name="saison_id"] option[selected]')]
    period = f'{str(year)[-2:]}/{str(year + 1)[-2:]}'
    if ((declared.scheme, declared.netloc) != (url.scheme, url.netloc)
            or not re.fullmatch(club_path + '/?', declared.path) or declared.query or declared.fragment
            or not _club_key(club_name) or _club_key(title.split(' - ')[0]) != _club_key(club_name)
            or years != [str(year)] or not re.search(r'(?<!\d)' + re.escape(period) + r'(?!\d)', title)):
        raise ValueError('original squad club/year context differs')
    tables = page.select('table.items')
    if len(tables) != 1 or [h.get_text(' ', strip=True) for h in tables[0].select('thead th')] != HEADERS:
        raise ValueError('explicit original detailed squad column contract required')
    def links(row):
        return [a for a in row.select('a[href]') if re.fullmatch(
            r'/[^/]+/profil/spieler/' + str(pid) + '/?', urlsplit(a['href']).path)]
    rows = [r for r in tables[0].select(':scope > tbody > tr') if links(r)]
    if len(rows) != 1:
        raise ValueError('one exact original numeric person row required')
    cells = rows[0].find_all('td', recursive=False)
    if len(cells) != len(HEADERS):
        raise ValueError('person row columns shifted or absent')
    person_links = links(cells[1])
    ids = {re.search(r'/profil/spieler/([1-9][0-9]*)(?:/|$)', urlsplit(a['href']).path)[1]
           for a in cells[1].select('a[href]') if re.search(
               r'/profil/spieler/([1-9][0-9]*)(?:/|$)', urlsplit(a['href']).path)}
    names = {a.get_text(' ', strip=True) for a in person_links}
    if ids != {str(pid)} or len(names) != 1 or not next(iter(names), ''):
        raise ValueError('same-row full name and numeric identity disagree')
    name = next(iter(names))
    for a in person_links:
        target = urlsplit(a['href'])
        if ((target.scheme or target.netloc) and (target.scheme, target.netloc) != (url.scheme, url.netloc)):
            raise ValueError('same-row identity link has another origin')
    images = cells[1].select('img')
    if not images or any(i.get('alt') != name or i.get('title') != name for i in images):
        raise ValueError('same-row portrait label contradicts full identity')
    parts = [r.get_text(' ', strip=True) for r in cells[1].select('table > tr, table > tbody > tr')]
    if len(parts) != 2 or parts[0] != name or not parts[1]:
        raise ValueError('same-row detailed position absent or ambiguous')
    if re.sub(r'[^a-z]', '', parts[1].casefold()) not in exchange.HTML_ROLES:
        raise ValueError('unsupported original detailed position')
    born = re.fullmatch(r'(\d{2}/\d{2}/\d{4})\s*\(\d{1,3}\)', cells[2].get_text(' ', strip=True))
    if born is None:
        raise ValueError('literal DD/MM/YYYY birthday column required')
    birthday = datetime.strptime(born[1], '%d/%m/%Y').date().isoformat()
    if independent_birthday(value['birth_date_witness'], name) != birthday:
        raise ValueError('independent literal birthday disagrees with squad row')
    nations = cells[3].select('img')
    labels = [i.get('title') for i in nations]
    if not labels or any(not label or i.get('alt') != label for i, label in zip(nations, labels)):
        raise ValueError('same-row explicit nationality flags required')
    if any(label not in exchange.SOURCE_COUNTRIES for label in labels):
        raise ValueError('unsupported original nationality label')
    height = cells[5].get_text(' ', strip=True)
    metric = re.fullmatch(r'([12]),(\d{2})m', height)
    if height not in ('', '-') and metric is None:
        raise ValueError('malformed original metric height')
    shirt = cells[0].get_text(' ', strip=True)
    if shirt not in ('', '-') and not re.fullmatch(r'[1-9][0-9]?', shirt):
        raise ValueError('malformed original shirt number')
    return dict(published_full_name=name, published_birth_date=birthday,
        published_profile_position=parts[1], published_nationality_label=' / '.join(labels),
        published_height_cm=int(metric[1]) * 100 + int(metric[2]) if metric else None,
        published_shirt_number=int(shirt) if shirt not in ('', '-') else None,
        linked_profile_url=urljoin(value['url'], person_links[0]['href']),
        biography_source_kind=FORMAT, profile_page_captured=False)
