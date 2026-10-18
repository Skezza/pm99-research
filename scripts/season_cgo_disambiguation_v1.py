"""Do not infer either Congo from a provider's ambiguous CGO abbreviation.

Independent original biography must identify the exact full-name/DOB and a
single Congo national-team spell covering the target year. No current flag,
surname guess, future international affiliation or silent nationality override.
This gate verifies meaning only; it never rewrites a recipe or native byte.
"""
from datetime import date
from pathlib import Path
import re
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_historical_roster_audit_v1 as roster

SCHEMA='pm99-independent-CGO-country-disambiguation-v1'
CATALOG=registry.ROOT/'.local/consolidated-audit-20261009/cgo-disambiguation-20261017/catalog.json'
TEAMS={'Congo_national_football_team':'CGO','DR_Congo_national_football_team':'COD'}


def parse(raw,name,birthday,season):
    page=BeautifulSoup(raw,'lxml')
    headings=[h.get_text(' ',strip=True) for h in page.select('h1#firstHeading')]
    dates=[b.get_text(' ',strip=True) for b in page.select('table.infobox .bday')]
    if headings!=[name] or dates!=[birthday]:
        raise ValueError('independent Congo biography full-name/DOB identity differs')
    date.fromisoformat(birthday)
    year=int(season[:4]);periods=[];countries=set()
    for link in page.select('table.infobox a[href]'):
        key=unquote(urlparse(link['href']).path).rsplit('/',1)[-1]
        if key not in TEAMS:continue
        row=link.find_parent('tr')
        if row is None:raise ValueError('independent Congo national team lacks a dated row')
        text=row.get_text(' ',strip=True)
        years=re.findall(r'\b(19\d{2}|20\d{2})\s*[–−-]\s*(19\d{2}|20\d{2})\b',text)
        if not years:
            single=re.findall(r'\b(?:19|20)\d{2}\b',text)
            if len(single)==1:years=[(single[0],single[0])]
        if len(years)!=1:raise ValueError('independent Congo spell lacks one explicit closed date interval')
        start,end=map(int,years[0]);countries.add(TEAMS[key])
        if start<=year<=end:periods.append(dict(country=TEAMS[key],from_year=start,to_year=end))
    if len(countries)!=1 or not periods:
        raise ValueError('independent Congo affiliation is ambiguous or does not cover target season')
    return dict(country=next(iter(countries)),dated_national_team_spells=periods,
        establishes_country_identity_not_target_season_caps=True)


def verify(row,season,*,catalog=CATALOG):
    if row['nationality']!='CGO':return None
    if not catalog.is_file():
        raise ValueError('ambiguous provider CGO requires independent dated country disambiguation')
    document=pipeline.read_json_file(catalog)
    if document.get('schema')!=SCHEMA:
        raise ValueError('unsupported independent Congo disambiguation catalogue')
    person=row['source_person']
    found=[r for r in document['people'] if r['source_player_id']==person['source_player_id']]
    if len(found)!=1 or (found[0]['name'],found[0]['birth_date'])!=(person['name'],person['birth_date']):
        raise ValueError('ambiguous provider CGO has no independent exact-person country evidence')
    source=found[0]['source'];path=registry.ROOT/source['path'];receipt=registry.ROOT/source['receipt_path']
    metadata=pipeline.read_json_file(receipt)
    url='https://en.wikipedia.org/wiki/'+found[0]['wikipedia_slug']
    if (metadata.get('status')!='original-captured' or metadata.get('url')!=url
            or metadata.get('sha256')!=source['sha256'] or registry.sha256_file(path)!=source['sha256']
            or registry.sha256_file(receipt)!=source['receipt_sha256']):
        raise ValueError('independent original Congo biography URL/body/receipt changed')
    result=parse(path.read_bytes(),person['name'],person['birth_date'],season)
    if result['country']!=row['nationality']:
        raise ValueError('ambiguous provider CGO disagrees with independent dated country: '+result['country'])
    return dict(source_player_id=person['source_player_id'],name=person['name'],**result,
        original_source=source,catalog_sha256=registry.sha256_file(catalog),
        implementation_sha256=registry.sha256_file(Path(__file__)))
