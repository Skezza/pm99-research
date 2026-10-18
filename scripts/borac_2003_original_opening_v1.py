"""Read archived opening evidence without approving an annual reserve squad.

Archive capture dates are not football-season dates. The archived club page
was updated after the opening: its manager must not be used for August.
"""
import datetime as dt
import re

from bs4 import BeautifulSoup

CATALOGUE_URL = 'https://web.archive.org/web/20090625043628id_/http://dekisa.tripod.com:80/borac.htm'
MATCH_URL = 'https://web.archive.org/web/20250223132829id_/https://dekisa.tripod.com/12004.htm'
MANAGER_URL = 'https://www.uefa.com/news-media/news/0195-0f8edd4009a3-a8f9a3e6d56c-1000--borac-bring-in-bozovic/'
GROUPS = {'Golmani:': 'G', 'Odbrana:': 'D', 'Sredina:': 'M', 'Napad:': 'F'}
XI = ['Djuric', 'Stevic', 'Dragutinovic', 'Jelic', 'Stevanovic',
      'Pavlovic', 'Spasojevic', 'Nedeljkovic', 'Zivkovic', 'Jasic', 'Bruncevic']
LINE = ('BORAC: Djuric 5, Stevic 5, Dragutinovic 6, Jelic 5, Stevanovic 6, '
        'Pavlovic 5 (75. Nesic -), Spasojevic 6, Nedeljkovic 5, Zivkovic 5, '
        'Jasic 5, Bruncevic 5 (83. Avramovic -).')
DATED_LINE = ("Borac Čačak: Đurić, Stevanović, Jašić, Stević, Dragutinović, Jelić, "
    "Živković, Nedeljković, Brunčević (83' Avramović), Spasojević, Pavlović (75' Nešić)")


def text(raw):
    if not isinstance(raw, bytes) or not 500 <= len(raw) <= 2 * 1024 ** 2:
        raise ValueError('unexpected original payload type or size')
    return BeautifulSoup(raw, 'html.parser')


def catalogue(raw, url=CATALOGUE_URL):
    if url != CATALOGUE_URL:
        raise ValueError('unexpected original archive URL')
    page = text(raw)
    if page.title is None or page.title.get_text(strip=True) != 'FK Borac Cacak':
        raise ValueError('original catalogue identifies another club')
    flat = re.sub(r'\s+', ' ', page.get_text(' ', strip=True))
    if '2002/03 1.mesto II/Z' not in flat or 'Trener: Miodrag Bozovic' not in flat:
        raise ValueError('original catalogue context changed')
    result = []
    labels = [n for n in page.find_all('b') if n.get_text(' ', strip=True) in GROUPS]
    if [n.get_text(' ', strip=True) for n in labels] != list(GROUPS):
        raise ValueError('missing, reordered or repeated original position group')
    table = labels[0].find_parent('table')
    if any(n.find_parent('table') is not table for n in labels):
        raise ValueError('original position groups belong to different tables')
    role = None
    for row in table.find_all('tr', recursive=False):
        headers = [n.get_text(' ', strip=True) for n in row.find_all('b')
                   if n.get_text(' ', strip=True) in GROUPS]
        if headers:
            if len(headers) != 1:
                raise ValueError('ambiguous original position header')
            role = GROUPS[headers[0]]
        links = row.select('a[href^="borac/"]')
        if not links:
            continue
        cells = row.find_all('td', recursive=False)
        if role is None or len(links) != 1 or len(cells) != 3:
            raise ValueError('ambiguous original person row')
        label = re.sub(r'\s+', ' ', links[0].get_text(' ', strip=True))
        match = re.fullmatch(r'(?:\((\d+)\) )?([^,]+), ([^,]+)', label)
        if match is None or cells[2].get_text(strip=True) != 'Scg':
            raise ValueError('original name or country missing')
        number, family, given = match.groups()
        try:
            birthday = dt.datetime.strptime(cells[1].get_text(strip=True), '%d.%m.%Y.').date()
        except ValueError as exc:
            raise ValueError('original birthday missing or invalid') from exc
        result.append(dict(name=given + ' ' + family, family_name=family,
            birth_date=birthday.isoformat(), position=role,
            published_country='Scg', shirt_number=int(number) if number else None,
            original_person_url='http://dekisa.tripod.com/' + links[0]['href'],
            opening_reserve_membership_approved=False))
    if len(result) != 33 or len({p['original_person_url'] for p in result}) != 33:
        raise ValueError('original catalogue incomplete or repeated')
    return result


def parse(catalogue_raw, match_raw, manager_raw, dated_match_raw):
    people = catalogue(catalogue_raw)
    match = re.sub(r'\s+', ' ', text(match_raw).get_text(' ', strip=True))
    markers = ['PARTIZAN BEOGRAD - BORAC CACAK 6:1 (2:0)', LINE,
               'NAPREDAK KRUSEVAC - CRVENA ZVEZDA BEOGRAD 2:1 (0:1)',
               'Prva Savezna Liga - 1.Kolo -']
    if any(match.count(marker) != 1 for marker in markers):
        raise ValueError('original first-round fixture or XI changed')
    if not match.index(markers[0]) < match.index(LINE) < match.index(markers[2]):
        raise ValueError('original XI belongs to another fixture')
    dated = text(dated_match_raw)
    headings = [h for h in dated.select('h3') if h.get_text(' ', strip=True) == 'Prvenstvo:']
    if len(headings) != 1:
        raise ValueError('independent league section missing or repeated')
    nodes = list(headings[0].find_all_next(['h1', 'h2', 'h3', 'p']))
    if (len(nodes) < 5 or nodes[0].name != 'h3'
            or nodes[0].get_text(' ', strip=True) != 'Partizan - Borac Čačak 6:1 (2:0)'
            or nodes[1].name != 'p'
            or re.sub(r'\s+', ' ', nodes[1].get_text(' ', strip=True)) != '9. avgust 2003. Gledalaca: 8 000'
            or nodes[3].name != 'p'
            or nodes[3].get_text(' ', strip=True) != DATED_LINE):
        raise ValueError('independent first date or original people disagree')
    manager = re.sub(r'\s+', ' ', text(manager_raw).get_text(' ', strip=True))
    if ('Tuesday, September 23, 2003' not in manager
            or 'Newly promoted FK Borac have sacked coach Radovan Guduric and replaced him with Miodrag Bozovic.' not in manager
            or 'Borac have taken only one point from their first five matches' not in manager):
        raise ValueError('dated opening-manager chronology not confirmed')

    def join(label):
        found = [p for p in people if p['family_name'] == label]
        if len(found) != 1:
            raise ValueError('original match surname has no unique full published identity')
        return dict(found[0], published_match_name=label,
                    opening_reserve_membership_approved=False)

    starters = [join(label) for label in XI]
    substitutes = [dict(join(label), minute=minute) for label, minute in [('Nesic', 75), ('Avramovic', 83)]]
    if len({p['original_person_url'] for p in starters + substitutes}) != 13:
        raise ValueError('original opening people repeat')
    return dict(season='2003-04', fixture_date='2003-08-09', club='Borac Čačak', opponent='Partizan', result='1-6',
        starting_xi=starters, used_substitutes=substitutes, unused_substitutes=None,
        manager='Radovan Gudurić', superseded_catalogue_manager='Miodrag Božović',
        annual_identity_catalogue=people, native_writes=0, publication_authorised=False,
        limitations=['Five additional positively dated opening reserves remain required.',
            'Archive capture date and page copyright are not roster snapshot dates.',
            'Catalogue broad roles and secondary facts are not a finer-position historical approval.'])
