"""Resolve an original Wikipedia country-link alias without changing V3 code.

The old source modules are release-bound. Retain a separate exact original
redirect witness so a later corrective source policy can fix Mfuyi safely.
This module never writes a recipe/game or approves a pending private release.
"""
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from scripts import season_cgo_disambiguation_v2 as old
from scripts.capture_stock_replacement_sources_20261010 import ROOT as CACHE

ALIAS='https://en.wikipedia.org/wiki/Congo_DR_national_football_team'
CANONICAL='https://en.wikipedia.org/wiki/DR_Congo_national_football_team'
KEY='cgo-DR-country-redirect-original-wikipedia'


def raw_source(source):
    path=old.registry.ROOT/source['path'];receipt=old.registry.ROOT/source['receipt_path']
    metadata=old.pipeline.read_json_file(receipt)
    if (metadata.get('status')!='original-captured' or metadata['url']!=source['url']
            or old.registry.sha256_file(path)!=source['sha256']
            or metadata['sha256']!=source['sha256']
            or old.registry.sha256_file(receipt)!=source['receipt_sha256']):
        raise ValueError('original country alias witness URL/body/receipt changed')
    return path.read_bytes()


def parse(biography,team,name,birthday,season):
    page=BeautifulSoup(biography,'lxml');country=BeautifulSoup(team,'lxml')
    if ([h.get_text(' ',strip=True) for h in page.select('h1#firstHeading')]!=[name]
            or [b.get_text(' ',strip=True) for b in page.select('table.infobox .bday')]!=[birthday]):
        raise ValueError('country alias original person full-name/DOB differs')
    if ([h.get_text(' ',strip=True) for h in country.select('h1#firstHeading')]!=['DR Congo national football team']
            or [a.get('href') for a in country.select('link[rel="canonical"]')]!=[CANONICAL]
            or [tr.get_text(' ',strip=True) for tr in country.select('table.infobox tr')
                if tr.find('th') and tr.find('th').get_text(' ',strip=True)=='FIFA code']!=['FIFA code COD']):
        raise ValueError('original country-link redirect does not independently identify COD')
    rows=[];countries=set();year=int(season[:4])
    for link in page.select('table.infobox a[href]'):
        path=urlparse(link['href']).path
        key=path.rsplit('/',1)[-1]
        if key in old.prior.TEAMS:
            countries.add(old.prior.TEAMS[key])
        if key!='Congo_DR_national_football_team':continue
        countries.add('COD')
        tr=link.find_parent('tr');cells=tr.find_all(['td','th'],recursive=False) if tr else []
        if not cells:raise ValueError('original country alias has no dated team row')
        literal=cells[0].get_text(' ',strip=True)
        # This bounded new route deliberately admits the observed single-year
        # original witness, not an inferred present-day national affiliation.
        if not old.re.fullmatch(r'(?:19|20)\d{2}',literal) or int(literal)>year:
            raise ValueError('original country alias is undated or future')
        rows.append(dict(from_year=int(literal),country='COD',literal_country_link=link['href']))
    if countries!={'COD'} or len(rows)!=1:
        raise ValueError('original country alias is absent or conflicts with another Congo')
    return dict(country='COD',dated_prior_association=rows[0],exclusive_citizenship_or_target_year_caps_claimed=False)


def verify(row,season):
    if row['nationality']!='CGO':raise ValueError('only ambiguous original CGO requires this alias witness')
    document=old.pipeline.read_json_file(old.CATALOG);person=row['source_person']
    hits=[r for r in document['rows'] if r['source_player_id']==person['source_player_id']]
    if len(hits)!=1 or hits[0]['source_person']!=person:
        raise ValueError('original country alias person identity differs')
    path=CACHE/(KEY+'.html');receipt=CACHE/(KEY+'.source.json')
    metadata=old.pipeline.read_json_file(receipt)
    source=dict(path=old.registry.relative_workspace_path(path),sha256=metadata.get('sha256'),
        receipt_path=old.registry.relative_workspace_path(receipt),receipt_sha256=old.registry.sha256_file(receipt),url=ALIAS)
    result=parse(raw_source(hits[0]['source']),raw_source(source),person['name'],person['birth_date'],season)
    return dict(schema='pm99-independent-country-redirect-witness-v1',**result,
        original_biography=hits[0]['source'],original_country_redirect=source,
        source_player_id=person['source_player_id'],country_meaning_resolved_not_native_delivery=True)
