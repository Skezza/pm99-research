"""Read same-row biography facts, without pretending a profile was fetched.

Annual membership is NOT August ownership. Callers still need independent
dated membership evidence and the existing native reserve/identity guards.
"""
from datetime import datetime, date
import json
import re
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup
from scripts import season_opening_identity_exchange_v1 as exchange
from scripts.capture_transfermarkt_opening_lineups_v1 import _club_key

FORMAT = 'original-target-year-transfermarkt-squad-person-row-v1'
HEADERS = ['#', 'Player', 'Date of birth/Age', 'Nat.', 'Current club',
           'Height', 'Foot', 'Joined', 'Signed from', 'Market value']
HOSTS = {'www.transfermarkt.com', 'www.transfermarkt.co.uk', 'www.transfermarkt.us'}
WIKIDATA_BIRTHDAY = 'wikidata-exact-provider-name-day-birthday-v1'
# Explicit provider-ID-scoped historical labels, not fuzzy city matching.
CLUB_LABEL_ALIASES = {(2655, 'Vicenza'): ('Vicenza Calcio', 'LR Vicenza')}


def club_label_keys(provider_club_id, native_name):
    return {_club_key(label) for label in
            (native_name, *CLUB_LABEL_ALIASES.get((provider_club_id, native_name), ()))}


def wikidata_birthday(value, name, provider_player_id):
    """Corroborate one already identified squad row; never prove ownership."""
    qid = value.get('wikidata_id')
    language = value.get('label_language')
    if (not isinstance(qid, str) or not re.fullmatch(r'Q[1-9][0-9]*', qid)
            or language not in ('en', 'it') or type(provider_player_id) is not int
            or provider_player_id <= 0
            or type(value.get('transfermarkt_player_id')) is not int
            or value.get('transfermarkt_player_id') != provider_player_id
            or value.get('url') != f'https://www.wikidata.org/wiki/Special:EntityData/{qid}.json'):
        raise ValueError('exact Wikidata entity and known squad provider identity required')
    document = json.loads(exchange.original(value).read_bytes())
    if set(document.get('entities', {})) != {qid}:
        raise ValueError('one exact retained Wikidata entity required')
    entity = document['entities'][qid]
    if (entity.get('id') != qid
            or entity.get('labels', {}).get(language, {}).get('value') != name):
        raise ValueError('Wikidata full name or entity identity differs from squad row')
    def unique(prop):
        rows = [r for r in entity.get('claims', {}).get(prop, [])
                if r.get('rank') in ('normal', 'preferred')]
        if len(rows) != 1 or rows[0].get('mainsnak', {}).get('snaktype') != 'value':
            raise ValueError('one unambiguous nondeprecated Wikidata ' + prop + ' required')
        return rows[0]['mainsnak'].get('datavalue', {}).get('value')
    if unique('P2446') != str(provider_player_id):
        raise ValueError('Wikidata provider ID differs from original squad row')
    birthday = unique('P569')
    if (not isinstance(birthday, dict) or birthday.get('precision') != 11
            or birthday.get('calendarmodel') != 'http://www.wikidata.org/entity/Q1985727'
            or birthday.get('before') != 0 or birthday.get('after') != 0
            or birthday.get('timezone') != 0
            or not re.fullmatch(r'\+\d{4}-\d{2}-\d{2}T00:00:00Z', str(birthday.get('time')))):
        raise ValueError('literal precise Gregorian Wikidata birthday required')
    return date.fromisoformat(birthday['time'][1:11]).isoformat()


def published_family_display(selection, evidence):
    """Read the complete explicit family component; keep the full source name."""
    squad = evidence[selection['squad_biography']]
    witness = squad['birth_date_witness']
    pid, name = selection['provider_player_id'], selection['name']
    if witness.get('format') != WIKIDATA_BIRTHDAY:
        raise ValueError('explicit family display requires the same Wikidata identity witness')
    if wikidata_birthday(witness, name, pid) != selection['birth_date']:
        raise ValueError('family display identity birthday differs')
    entity = json.loads(exchange.original(witness).read_bytes())['entities'][witness['wikidata_id']]
    claims = [r for r in entity.get('claims', {}).get('P734', [])
              if r.get('rank') in ('normal', 'preferred')]
    if (len(claims) != 1 or claims[0].get('mainsnak', {}).get('snaktype') != 'value'):
        raise ValueError('one explicit nondeprecated family-name claim required')
    family_id = claims[0]['mainsnak'].get('datavalue', {}).get('value', {}).get('id')
    family_source = evidence[selection['family_name_witness']]
    if (not isinstance(family_id, str) or not re.fullmatch(r'Q[1-9][0-9]*', family_id)
            or family_source.get('url') !=
                f'https://www.wikidata.org/wiki/Special:EntityData/{family_id}.json'):
        raise ValueError('family-name entity URL does not follow the original P734 claim')
    document = json.loads(exchange.original(family_source).read_bytes())
    if set(document.get('entities', {})) != {family_id}:
        raise ValueError('one exact family-name entity required')
    family = document['entities'][family_id]
    label = family.get('labels', {}).get(witness['label_language'], {}).get('value')
    if (family.get('id') != family_id or not isinstance(label, str) or not label.strip()
            or selection.get('native_display_name') != label
            or not name.endswith(' ' + label) or name == label):
        raise ValueError('native display must be the complete published family in the source full name')
    return label


def independent_birthday(value, name, provider_player_id=None):
    """A separately hosted, literal long date resolves DD/MM ambiguity."""
    if value.get('format') == WIKIDATA_BIRTHDAY:
        return wikidata_birthday(value, name, provider_player_id)
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
            or exchange.published_name_key(rows[0].find('td').get_text(' ', strip=True)) != exchange.published_name_key(name)
            or exchange.published_name_key(title.split(' | ')[0]) != exchange.published_name_key(name)):
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
            or not _club_key(club_name)
            or _club_key(title.split(' - ')[0]) not in club_label_keys(provider_club_id, club_name)
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
    if independent_birthday(value['birth_date_witness'], name, pid) != birthday:
        raise ValueError('independent literal birthday disagrees with squad row')
    nations = cells[3].select('img')
    labels = [i.get('title') for i in nations]
    if not labels or any(not label or i.get('alt') != label for i, label in zip(nations, labels)):
        raise ValueError('same-row explicit nationality flags required')
    if any(label not in exchange.SOURCE_COUNTRIES for label in labels):
        raise ValueError('unsupported original nationality label')
    height = cells[5].get_text(' ', strip=True)
    metric = re.fullmatch(r'([12]),(\d{2})m', height)
    if height not in ('', '-', 'N/A') and metric is None:
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
