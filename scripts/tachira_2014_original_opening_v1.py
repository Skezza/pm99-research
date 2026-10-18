"""Parse the dated club press report, never a current sidebar or guessed XI.

This closed-world adapter permits a complete original article containing passive
Cloudflare JavaScript. Generic transfer-source challenge guards remain intact.
It does not accept an interstitial, approve native allocation or assign roles.
"""
import json
import re
from bs4 import BeautifulSoup

URL = 'https://www.lavinotinto.com/triplete-de-rivas-hizo-ganar-al-tachira/'


def parse(payload, url=URL):
    if url != URL or not 1000 <= len(payload) <= 2 * 1024 ** 2:
        raise ValueError('unexpected club press source URL or size')
    page = BeautifulSoup(payload, 'html.parser')
    canonical = page.select('link[rel="canonical"]')
    if len(canonical) != 1 or canonical[0].get('href') != URL:
        raise ValueError('club press original canonical differs')
    titles = page.select('h1')
    if len(titles) != 1 or titles[0].get_text(' ', strip=True) != 'Triplete de Rivas hizo ganar al Táchira':
        raise ValueError('missing original article title; challenge/sidebar not evidence')
    articles = []
    for script in page.select('script[type="application/ld+json"]'):
        data = json.loads(script.string or script.get_text())
        articles.extend(d for d in data.get('@graph', []) if d.get('@type') == 'NewsArticle')
    if len(articles) != 1 or not articles[0].get('datePublished', '').startswith('2014-08-10T'):
        raise ValueError('original publication date missing or another season')
    contents = page.select('.entry-content')
    if len(contents) != 1:
        raise ValueError('original article body missing or ambiguous')
    paragraphs = [p.get_text(' ', strip=True) for p in contents[0].find_all('p', recursive=False)]
    if 'Ficha Técnica:' not in paragraphs:
        raise ValueError('no dated technical match report')
    i = paragraphs.index('Ficha Técnica:')
    target = re.fullmatch(r'\(3\) Deportivo Táchira F\.C\.: (.+)\. D\.T\.: (.+)\.', paragraphs[i + 1])
    bench = re.fullmatch(r'Suplentes sin jugar: (.+)\.', paragraphs[i + 2])
    if target is None or bench is None:
        raise ValueError('original XI/unused bench format differs')
    xi, used = [], []
    for token in target[1].split(', '):
        substitutions = re.findall(r'\(([^()]+)\)', token)
        for entry in substitutions:
            if entry == 'C':
                continue
            sub = re.fullmatch(r'(.+) (\d+)[´′\']', entry)
            if sub is None:
                raise ValueError('unrecognised match substitution')
            used.append(dict(name=sub[1], minute=int(sub[2])))
        xi.append(re.sub(r'\s*\([^()]+\)', '', token).strip())
    unused = bench[1].split(', ')
    people = xi + [p['name'] for p in used] + unused
    text = ' '.join(paragraphs)
    if (len(xi) != 11 or len(used) != 3 or len(unused) != 4 or len(set(people)) != 18
            or 'Jornada 1, Torneo Apertura 2014, Liga Movistar 2014-2015.' not in text
            or 'Estadio: Pueblo Nuevo, San Cristóbal, estado Táchira.' not in text
            or 'Prensa Deportivo Táchira' not in text
            or not paragraphs[i + 3].startswith('(0) Atlético Venezuela C.F.:')):
        raise ValueError('opening fixture/complete18/club attribution differ')
    return dict(season='2014-15', fixture_date='2014-08-10', round=1,
        club='Deportivo Táchira', opponent='Atlético Venezuela', result='3-0',
        starting_xi=xi, used_substitutes=used, unused_substitutes=unused,
        manager=target[2], ground='Pueblo Nuevo', source_url=URL,
        source_credit='Prensa Deportivo Táchira / LaVinotinto',
        source_contains_full18=True, native_writes=0, publication_authorised=False,
        limitation='Published names only; stable person identity, roles, DOB, secondary facts, cross-club ownership, fixed16 allocation and runtime still required.')


def validate(payload, url):
    parse(payload, url)
