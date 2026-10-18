"""Capture target-season numbers; never adopt today's profile squad numbers."""
from bs4 import BeautifulSoup
from scripts.capture_stock_replacement_sources_20261010 import main as acquire
from scripts import season_historical_roster_audit_v1 as roster

KEY='arsenal-2021-season-shirt-numbers-original-20261016'
URL='https://en.wikipedia.org/wiki/2021%E2%80%9322_Arsenal_F.C._season'


def validate(raw,url):
    page=BeautifulSoup(raw,'html.parser')
    headings=[roster.normalise(h.get_text(' ',strip=True)) for h in page.select('h1')]
    if url!=URL or headings!=['202122arsenalfcseason']:
        raise ValueError('original season-shirt page heading/year differs')
    if not any('Aubameyang' in t.get_text(' ',strip=True) for t in page.select('table.wikitable')):
        raise ValueError('original historical season has no squad tables')


if __name__=='__main__':acquire(extra_sources=[(KEY,URL)],only_extra=True,validator=validate)
