"""Capture primary dated evidence for the Arsenal opening-squad transaction.

No surname expansion, current biography inference, roster publication or game
approval. The Genoa sheet is useful for the paired displaced foreign slot.
"""
import re
from bs4 import BeautifulSoup
from scripts.capture_stock_replacement_sources_20261010 import main as acquire

SOURCES={
    'genoa-2021-primary-opening-Inter20261016-v2':'https://www.inter.it/en/news/2021-08-21-inter-genoa-line-ups',
    'arsenal-2021-primary-August1-Chelsea20261016':'https://www.chelseafc.com/en/news/article/match-report--arsenal-vs-chelsea1',
    'arsenal-2021-primary-opening-injury-Brentford20261016':'https://www.brentfordfc.com/en/news/match-preview-brentford-vs-arsenal-589488',
}


def numbered(value):
    rows=[]
    for name in re.split(r'[;,]',value.rstrip('. ')):
        match=re.fullmatch(r'\s*([1-9][0-9]?)\s+([^0-9]+?)\s*',name)
        if match is None:raise ValueError('primary numbered match-name list differs')
        rows.append(dict(shirt_number=int(match[1]),published_match_name=match[2]))
    if len({r['shirt_number'] for r in rows})!=len(rows):raise ValueError('duplicate primary shirt number')
    return rows


def genoa(raw):
    page=BeautifulSoup(raw,'html.parser');text=' '.join(page.get_text(' ',strip=True).split())
    if 'Aug 21st 2021' not in text or 'The season starts today' not in text:
        raise ValueError('primary Genoa opener lacks its independently published date/round')
    match=re.search(r'GENOA \(3-5-2\)\s*:\s*(.*?)\s*Subs\s*:\s*(.*?)\s*Coach\s*:\s*Davide Ballardini\.',text)
    if match is None:raise ValueError('primary Genoa exact side/formation/coach differs')
    xi=numbered(match[1]);bench=numbered(match[2])
    if len(xi)!=11 or len(bench)!=12 or len({r['shirt_number'] for r in xi+bench})!=23:
        raise ValueError('primary Genoa opener must contain eleven plus twelve distinct substitutes')
    return dict(date='2021-08-21',club='Genoa',opponent='Inter',formation='3-5-2',
        manager='Davide Ballardini',starting_xi=xi,published_bench=bench)


def validate(raw,url):
    if url not in SOURCES.values():raise ValueError('unrecognised bounded primary source')
    text=' '.join(BeautifulSoup(raw,'html.parser').get_text(' ',strip=True).split())
    if url==SOURCES['genoa-2021-primary-opening-Inter20261016-v2']:
        genoa(raw)
    elif url==SOURCES['arsenal-2021-primary-August1-Chelsea20261016']:
        if not all(t in text for t in ('Arsenal (4-2-3-1):','Partey (Xhaka 40)',
            'Aubameyang (c)','Lacazette (Nketiah 71)')):
            raise ValueError('primary August friendly membership anchors differ')
        if not re.search(rb'2021-08-01',raw):
            raise ValueError('primary friendly lacks literal publication date in original metadata')
    elif not all(t in text for t in ('Eddie Nketiah (ankle)','Gabriel (knee)','Thomas Partey (ankle)')):
        raise ValueError('primary opener preview lacks its positive Arsenal absence list')


if __name__=='__main__':
    acquire(extra_sources=list(SOURCES.items()),only_extra=True,transport='urllib',validator=validate)
