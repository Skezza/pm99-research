"""Read declared secondary facts from exact stable-ID target annual rows.

Never use current player-feed nationality/positions/photos as period facts.
Native SRB/MNE both resolve to the game's YUGOSLAVIA country representation.
Heights are explicitly rounded from the annual page's imperial display.
Unknown weights remain logged, not invented.
"""
import datetime as dt
import re
from decimal import Decimal, ROUND_HALF_UP

from bs4 import BeautifulSoup

POLICY = 'original-target-annual-stable-ID-confirmed-DOB-flag-and-rounded-height-v1'


def parse(raw, desired, *, expected_year=2004, expected_club_name='OFK Beograd', country_codes=None,
          expected_calendar_year=None, country_representation=None):
    from scripts.prepare_ofk_2004_source_allocation_v1 import annual_roles
    page = BeautifulSoup(raw, 'html.parser')
    if expected_calendar_year is None:
        annual_roles(raw, expected_year=expected_year, expected_club_name=expected_club_name)
    elif (page.title is None or not page.title.get_text().startswith(
            f'{expected_club_name} - Detailed squad {expected_calendar_year} (')):
        raise ValueError('original explicit-calendar fact catalogue identifies another club/year')
    selected = {r['source_person']['source_player_id']: r for r in desired}
    result = {}
    for tr in page.select('table.items > tbody > tr'):
        ids = {int(m.group(1)) for a in tr.select('a[href*="/profil/spieler/"]')
            if (m := re.search(r'/profil/spieler/(\d+)(?:/|$)', a.get('href', '')))}
        if len(ids) != 1: continue
        id = next(iter(ids))
        if id not in selected: continue
        cells = tr.find_all('td', recursive=False)
        if len(cells) != 10 or id in result:
            raise ValueError('original annual secondary-fact row shape/identity differs')
        published_dob = re.fullmatch(r'(\d{2})/(\d{2})/(\d{4}) \(\d+\)', cells[2].get_text(' ', strip=True))
        if published_dob is None:
            raise ValueError('selected annual secondary row lacks a literal DOB')
        day, month, year = map(int, published_dob.groups())
        birth_date = dt.date(year, month, day).isoformat()
        if birth_date != selected[id]['source_person']['birth_date']:
            raise ValueError('annual secondary facts identify a conflicting birthday')
        flags = cells[3].select('img.flaggenrahmen')
        if not flags: raise ValueError('selected annual secondary row has no declared country')
        primary = flags[0].get('title')
        mapping = {'Serbia': 'SRB', 'Montenegro': 'MNE', 'North Macedonia': 'MKD'} if country_codes is None else country_codes
        country = mapping.get(primary)
        if country is None: raise ValueError('selected annual primary country needs explicit mapping')
        height_text = cells[5].get_text(' ', strip=True)
        height_match = re.fullmatch(r'(\d) ft (\d{1,2}) in', height_text)
        height = None
        if height_match:
            feet, inches = map(int, height_match.groups())
            if not 0 <= inches < 12: raise ValueError('invalid annual height inches')
            height = int((Decimal(feet * 12 + inches) * Decimal('2.54')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            if not 140 <= height <= 220: raise ValueError('implausible annual adult height')
        elif height_text not in ('-', '', 'N/A'):
            raise ValueError('unrecognised annual height unit; do not infer a value')
        result[id] = dict(source_player_id=id, birth_date=birth_date, nationality=country,
            source_country_label=primary, height_cm=height, source_height_label=height_text,
            height_policy='rounded-original-imperial-display-not-exact-centimetre' if height else 'unpublished',
            weight_kg=None, weight_policy='unpublished-not-invented',
            country_representation=country_representation or 'native YUGOSLAVIA for SRB/MNE; MACEDONIA for MKD',
            source_policy=POLICY if expected_calendar_year is None else 'original-explicit-calendar-stable-ID-confirmed-DOB-flag-rounded-height-v1',
            limitation='A current publication of a target-season annual row, not a certified dated passport or weigh-in.'
                if expected_calendar_year is None else
                f'Published calendar{expected_calendar_year} row: identity/secondary facts only, NOT opening membership or a certified dated passport/weigh-in.')
    if set(result) != set(selected): raise ValueError('secondary source omits a selected fixed-roster person')
    return result
