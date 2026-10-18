"""Positive dated entry AND exit permit an August reserve, without a bench claim."""
from datetime import datetime, date
import re
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_historical_roster_audit_v1 as roster

POLICY = 'original-joined-row-and-independent-registration-exit-August-bracket-v1'


def verify(selection, evidence, *, season=None, club=None):
    claim = selection['opening_contract']
    anchor = date.fromisoformat(claim['opening_date'])
    year = anchor.year
    if (claim.get('policy') != POLICY or anchor.month != 8
            or (season is not None and int(season[:4]) != year)):
        raise ValueError('dated reserve needs explicit target August ownership policy')
    entry, leave = evidence[claim['entry']], evidence[claim['exit']]
    exchange.dated_source(entry)
    exchange.dated_source(leave)
    pid = selection['provider_player_id']
    cid = claim['provider_club_id']
    parsed = urlsplit(entry['url'])
    if (parsed.scheme != 'https' or parsed.hostname not in ('www.transfermarkt.co.uk', 'www.transfermarkt.com', 'www.transfermarkt.us')
            or not re.search(r'/kader/verein/' + str(cid) + '/saison_id/' + str(year) + r'(?:/|$)', parsed.path)
            or entry.get('person_row', {}).get('provider_player_id') != pid
            or leave.get('dfb_registration_row', {}).get('date_kind') != 'bis'):
        raise ValueError('dated reserve original club/player/exit origin differs')
    aliases = evidence[claim['club_identity_aliases']]
    expected_path = f'seasons/{year}-{str(year+1)[-2:]}/opening-lineup-club-identity-aliases-v1.json'
    if aliases['path'] != expected_path:
        raise ValueError('dated reserve club mapping must be the recorded season identity input')
    document = pipeline.read_json_file(exchange.original(aliases))
    matches = [a for a in document['aliases'] if a['source_selector'] == claim['source_selector']
               and a['transfermarkt_club_id'] == cid]
    if document.get('schema_version') != 'pm99-transfermarkt-opening-lineup-club-identity-aliases-v1' or len(matches) != 1:
        raise ValueError('dated reserve exact native/source club mapping absent')
    if club is not None and (claim['source_selector']['club_name'] not in (club['name'], club.get('full_name'))
            or roster.source_group(claim['source_selector']['country_catalog']) != roster.club_group(club)):
        raise ValueError('dated reserve source mapping identifies another native club/country')
    page = BeautifulSoup(exchange.original(entry).read_bytes(), 'lxml')
    canonical = page.select_one('link[rel="canonical"]')
    declared = urlsplit(canonical.get('href', '') if canonical else '')
    if (canonical is None or (declared.scheme, declared.netloc) != (parsed.scheme, parsed.netloc)
            or not re.search(r'/kader/verein/' + str(cid) + r'(?:/|$)', declared.path)):
        raise ValueError('dated reserve source canonical club differs')
    rows = [r for r in page.select('table.items > tbody > tr') if r.select_one('a[href*="/profil/spieler/' + str(pid) + '"]')]
    if len(rows) != 1:
        raise ValueError('dated reserve needs one exact published joined row')
    row = rows[0]
    link = row.select_one('a[href*="/profil/spieler/' + str(pid) + '"]')
    cells = row.find_all('td', recursive=False)
    born = re.search(r'\b\d{2}/\d{2}/\d{4}\b', cells[2].get_text(' ', strip=True))
    exit_claim = leave['dfb_registration_row']
    if (exchange.published_name_key(link.get_text(' ', strip=True)) != exchange.published_name_key(selection['name'])
            or born is None or datetime.strptime(born[0], '%d/%m/%Y').date().isoformat() != selection['birth_date']
            or exchange.published_name_key(exit_claim['full_name']) != exchange.published_name_key(selection['name'])
            or datetime.strptime(exit_claim['birthday_literal'], '%d.%m.%Y').date().isoformat() != selection['birth_date']
            or not date.fromisoformat(entry['event_date']) <= anchor < date.fromisoformat(leave['event_date'])):
        raise ValueError('dated reserve exact identity or positive entry/exit bracket differs')
    return anchor.isoformat()
