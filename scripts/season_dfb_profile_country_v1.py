"""Exact canonical DFB biography country admission; reuse the nationality writer.

No birthplace, club-country, portrait, or target-season ownership inference.
"""
from datetime import datetime
import re
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from scripts.season_historical_roster_audit_v1 import normalise
from scripts.season_historical_player_facts_audit_v1 import country

PROVIDER = 'dfb-canonical-explicit-country-v1'
GERMAN_COUNTRIES = {'Niederlande': 'NED', 'Deutschland': 'GER', 'Schweiz': 'SUI'}


def parse_country(raw, source, *, actor_name, birth_date):
    url = source['url']
    parsed = urlsplit(url)
    if (source.get('provider') != PROVIDER or parsed.scheme != 'https'
            or parsed.netloc != 'datencenter.dfb.de' or parsed.query or parsed.fragment
            or not re.fullmatch(r'/datencenter/personen/[a-z0-9-]+/spieler', parsed.path)):
        raise ValueError('canonical German DFB player URL required')
    soup = BeautifulSoup(raw, 'lxml')
    links = soup.select('link[rel="canonical"]')
    if len(links) != 1 or links[0].get('href') != url:
        raise ValueError('DFB original canonical identity differs')
    values = {}
    for row in soup.select('tr'):
        cells = row.find_all(['th', 'td'], recursive=False)
        if len(cells) != 2:
            continue
        key = cells[0].get_text(' ', strip=True).rstrip(':')
        if key not in {'Name', 'Geburtstag', 'Nation'}:
            continue
        if key in values:
            raise ValueError('duplicate DFB identity or country fact')
        values[key] = cells[1].get_text(' ', strip=True)
    if set(values) != {'Name', 'Geburtstag', 'Nation'}:
        raise ValueError('DFB explicit name/DOB/Nation facts required')
    try:
        birthday = datetime.strptime(values['Geburtstag'], '%d.%m.%Y').date().isoformat()
    except ValueError as exc:
        raise ValueError('DFB explicit DOB is invalid') from exc
    if normalise(values['Name']) != normalise(actor_name) or birthday != birth_date:
        raise ValueError('DFB source exact name and DOB identify another player')
    code = GERMAN_COUNTRIES.get(values['Nation']) or country(values['Nation'])
    if code is None or code == 'XXX':
        raise ValueError('DFB explicit nation has no admitted country mapping')
    return dict(name=values['Name'], birth_date=birthday,
        published_country=values['Nation'], nationality=code,
        provider=PROVIDER, url=url, target_season_ownership_claimed=False)
