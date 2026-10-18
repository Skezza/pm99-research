"""Closed-world actual opening match11178; never assert missing bench members.

A complete historical ficha may contain passive security JavaScript. Validate
the actual dated match DOM before retaining it; generic challenge guards stay
unchanged. Foro person IDs are NOT Transfermarkt IDs or native carriers.
"""
import re
from bs4 import BeautifulSoup

URL = 'https://www.forovinotinto.com/historia/ficha.php?div=1&id=11178'
POSITIONS = {'Portero': 'G', 'Defensa': 'D', 'Volante': 'M', 'Delantero': 'F'}


def parse(payload, url=URL):
    if url != URL or not 1000 <= len(payload) <= 2*1024**2:
        raise ValueError('unexpected original match URL/size')
    page = BeautifulSoup(payload, 'html.parser')
    if page.title is None or page.title.get_text(' ',strip=True).casefold() != 'forovinotinto | dan 1-2 dta':
        raise ValueError('original match title absent or interstitial')
    sections = page.select('section.ficha-container')
    if len(sections) != 1:
        raise ValueError('actual dated match body missing or ambiguous')
    section = sections[0]
    info = section.select_one('.ficha-partido-info')
    text = info.get_text(' ',strip=True) if info else ''
    home, away = section.select_one('#par-homeTeam'), section.select_one('#par-awayTeam')
    score = section.select_one('.ficha-partido-resultado')
    if (info is None or '11 de Julio del 2015. 7:00pm' not in text
            or 'Torneo de Adecuación - Ronda RegularJornada 1' not in text
            or 'Estadio José Antonio Anzoátegui, Puerto la Cruz.' not in text
            or home is None or home.get('desktop') != 'Deportivo Anzoátegui'
            or away is None or away.get('desktop') != 'Deportivo Táchira'
            or score is None or score.get_text(strip=True) != '1-2'):
        raise ValueError('actual first fixture date/competition/clubs/result differs')
    columns = {}
    for node in section.select('#away-titulares'):
        heading = node.select_one('.ficha-title')
        title = heading.get_text(strip=True) if heading else ''
        if title in columns:
            raise ValueError('duplicate target match column')
        columns[title] = node
    if set(columns) != {'Titulares','Suplentes','Director Técnico'}:
        raise ValueError('target XI/substitution/manager columns incomplete')

    def person(row):
        links = row.select('a[href*="equipos/jugador.php?id="]')
        flag = row.select('img[alt]')
        roles = [n.get('title') for n in row.select('.row-icon[title]') if n.get('title') in POSITIONS]
        if len(links) != 1 or len(flag) != 1 or len(roles) != 1:
            raise ValueError('original player identity/role/flag ambiguous')
        link = links[0]
        match = re.fullmatch(r'\.\./equipos/jugador\.php\?id=(\d+)', link.get('href',''))
        if match is None:
            raise ValueError('original player link malformed')
        return dict(published_name=link.get_text(' ',strip=True), source_person_id=int(match[1]),
            source_person_namespace='forovinotinto', position=POSITIONS[roles[0]],
            published_nationality=flag[0]['alt'])

    xi = [person(row) for row in columns['Titulares'].select('.ficha-row')]
    bench = [person(row) for row in columns['Suplentes'].select('.ficha-sub-row')]
    for row, actual in zip(columns['Suplentes'].select('.ficha-sub-row'), bench):
        number = row.select_one('.sub-number')
        match = re.fullmatch(r"(\d+)'", number.get_text(strip=True) if number else '')
        if match is None:
            raise ValueError('actual substitution minute missing')
        actual['minute'] = int(match[1])
    manager_links = columns['Director Técnico'].select('a[href*="equipos/jugador.php?id="]')
    if (len(xi) != 11 or len(bench) != 3 or len({p['source_person_id'] for p in xi+bench}) != 14
            or xi[0]['position'] != 'G' or sum(p['position']=='G' for p in xi)!=1
            or len(manager_links)!=1 or manager_links[0].get_text(' ',strip=True)!='Daniel Farías'):
        raise ValueError('actual XI14 distinct people/keeper/dated manager differs')
    return dict(season='2015-16',fixture_date='2015-07-11',round=1,
        club='Deportivo Táchira',opponent='Deportivo Anzoátegui',result='1-2',
        starting_xi=xi,used_substitutes=bench,unused_substitutes=None,formation=None,
        manager='Daniel Farías',source_url=URL,source_credit='ForoVinotinto / Armando García',
        native_writes=0,publication_authorised=False,
        limitation='Original dated11 plus3 used substitutes only. No invented unused bench, formation or stable-ID cross-publisher equivalence. Fixed16 requires2 more positive opening members and independent biographies/allocation/native/runtime proof.')


def validate(payload, url):
    parse(payload, url)
