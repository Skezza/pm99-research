"""Original 18-club Serie A opening dates, without changing frozen v1 policy.

This explicit new policy covers only 2000/01 through 2003/04. It proves
played fixture dates, never lineups, ownership, managers or formations.
"""
import csv
import datetime as dt
import io
import re

from scripts import season_football_data_opening_dates_v1 as legacy

POLICY = 'original-Italian-18-club-complete-double-round-robin-opening-date-v2'
SEASONS = frozenset(('2000-01', '2001-02', '2002-03', '2003-04'))


def first_fixture(raw, season, exact_label, *, url):
    if season not in SEASONS:
        raise ValueError('18-club Italian policy requires an explicitly supported season')
    legacy.validate_url(url, season, 'I1')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('cp1252')
    required = {'Div', 'Date', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG'}
    matches, pairs = [], set()
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError('Italian archive has a missing or ambiguous header')
    for row in reader:
        if not any(row.values()):
            continue
        if not required <= row.keys() or row['Div'] != 'I1':
            raise ValueError('Italian archive has an ambiguous or different competition')
        home, away = row['HomeTeam'], row['AwayTeam']
        if not home or not away or home == away or (home, away) in pairs:
            raise ValueError('Italian archive repeats or ambiguously identifies a fixture')
        value = row['Date']
        if not re.fullmatch(r'\d{2}/\d{2}/(?:\d{2}|\d{4})', value):
            raise ValueError('Italian archive has an unsupported fixture date')
        day = dt.datetime.strptime(value, '%d/%m/%y' if len(value) == 8 else '%d/%m/%Y').date().isoformat()
        if not season[:4] + '-07-01' <= day <= str(int(season[:4]) + 1) + '-06-30':
            raise ValueError('Italian fixture is outside the target season')
        if not all(re.fullmatch(r'\d+', row[k]) for k in ('FTHG', 'FTAG')):
            raise ValueError('Italian fixture lacks a completed score')
        pairs.add((home, away))
        matches.append({'date': day, 'home': home, 'away': away, 'competition_code': 'I1'})
    clubs = {m[k] for m in matches for k in ('home', 'away')}
    if len(clubs) != 18 or pairs != {(h, a) for h in clubs for a in clubs if h != a}:
        raise ValueError('Italian archive is not a complete 18-club double round robin')
    candidates = [m for m in matches if exact_label in (m['home'], m['away'])]
    if not candidates:
        raise ValueError('exact published club label is absent')
    earliest = min(m['date'] for m in candidates)
    first = [m for m in candidates if m['date'] == earliest]
    if len(first) != 1:
        raise ValueError('club has multiple fixtures on its first played date')
    return {'policy': POLICY, 'season': season, 'exact_published_club_label': exact_label,
            'fixture': first[0], 'source_scope': 'played league fixture date only',
            'starting_xi': None, 'substitutes': None, 'manager': None,
            'ownership_established': False}
