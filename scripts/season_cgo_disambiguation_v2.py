"""Independently interpret ambiguous CGO, including explicitly ongoing spells.

V1 and its original catalogue remain unchanged. A dated prior country
association distinguishes the two Congos even after international retirement.
An original biography's ``2014–`` explicitly starts in 2014; it is not undated.
Never extrapolate a future debut backwards or use an undated/current flag.
This proves country meaning, not continuing caps, exclusive citizenship or
club ownership. A source disagreement still requires separate adjudication.
"""
from datetime import datetime
from pathlib import Path
import re
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup
from scripts import season_cgo_disambiguation_v1 as prior

pipeline = prior.pipeline
registry = prior.registry
CATALOG = registry.ROOT / '.local/consolidated-audit-20261009/cgo-biographies-v3-20261017/catalog.json'


def parse(raw, name, birthday, season, captured_at):
    page = BeautifulSoup(raw, 'lxml')
    if ([h.get_text(' ', strip=True) for h in page.select('h1#firstHeading')] != [name]
            or [b.get_text(' ', strip=True) for b in page.select('table.infobox .bday')] != [birthday]):
        raise ValueError('independent Congo biography full-name/DOB identity differs')
    capture = datetime.fromisoformat(captured_at.replace('Z', '+00:00'))
    if capture.tzinfo is None:
        raise ValueError('original biography capture timestamp lacks timezone')
    year = int(season[:4])
    if year > capture.year:
        raise ValueError('target season is later than original capture')
    countries, periods = set(), []
    for link in page.select('table.infobox a[href]'):
        key = unquote(urlparse(link['href']).path).rsplit('/', 1)[-1]
        if key not in prior.TEAMS:
            continue
        country = prior.TEAMS[key]
        countries.add(country)
        row = link.find_parent('tr')
        if row is None:
            raise ValueError('independent Congo national team lacks a dated row')
        cells = row.find_all(['td', 'th'], recursive=False)
        # Read the YEARS cell, never appearance totals or a nearby biography year.
        if not cells:
            raise ValueError('national-team row has no year cell')
        text = cells[0].get_text(' ', strip=True)
        match = re.fullmatch(r'((?:19|20)\d{2})\s*([–−-])\s*((?:19|20)\d{2})?', text)
        if match:
            start = int(match[1])
            end = int(match[3]) if match[3] else capture.year
            ongoing = match[3] is None
        elif re.fullmatch(r'(?:19|20)\d{2}', text):
            start = end = int(text)
            ongoing = False
        else:
            raise ValueError('independent Congo spell lacks an explicit year or interval')
        if end < start or end > capture.year:
            raise ValueError('independent Congo interval is reversed or extends beyond capture')
        if start <= year:
            periods.append(dict(country=country, from_year=start, to_year=None if ongoing else end,
                explicitly_ongoing_at_original_capture=ongoing,
                basis='dated-country-association-established-no-later-than-target-year',
                continuous_target_year_national_team_membership_claimed=False))
    if len(countries) != 1 or not periods:
        raise ValueError('independent Congo affiliation is ambiguous or not established by target season')
    return dict(country=next(iter(countries)), dated_national_team_spells=periods,
        country_association_not_target_season_caps_or_exclusive_citizenship=True)


def resolve(row, season, *, catalog=CATALOG):
    if row['nationality'] != 'CGO':
        return None
    document = pipeline.read_json_file(catalog)
    person = row['source_person']
    hits = [r for r in document['rows'] if r['source_player_id'] == person['source_player_id']]
    if len(hits) != 1 or hits[0]['source_person'] != person:
        raise ValueError('independent Congo catalogue exact-person identity differs')
    selected = hits[0]
    source = selected['source']
    path, receipt = (registry.ROOT / source[k] for k in ('path', 'receipt_path'))
    metadata = pipeline.read_json_file(receipt)
    if (selected['status'] != 'original-captured' or metadata.get('status') != 'original-captured'
            or selected['url'] != source['url'] or metadata.get('url') != source['url']
            or registry.sha256_file(path) != source['sha256']
            or metadata.get('sha256') != source['sha256']
            or registry.sha256_file(receipt) != source['receipt_sha256']):
        raise ValueError('independent original Congo biography URL/body/receipt changed')
    result = parse(path.read_bytes(), person['name'], person['birth_date'], season, metadata['utc'])
    return dict(schema='pm99-independent-CGO-country-disambiguation-v2',
        source_player_id=person['source_player_id'], name=person['name'], **result,
        original_source=source, catalog_sha256=registry.sha256_file(catalog),
        implementation_sha256=registry.sha256_file(Path(__file__)))


def verify(row, season, *, catalog=CATALOG):
    result = resolve(row, season, catalog=catalog)
    if result is not None and result['country'] != row['nationality']:
        raise ValueError('provider CGO disagrees with independently dated country: ' + result['country'])
    return result
