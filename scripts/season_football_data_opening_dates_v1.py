"""Reparse original English, Italian and Turkish result archives as date evidence.

These records establish first *played league fixtures*, not XIs, benches,
managers, player identity, ownership or formations. Require an exact competition
code, exact CSV team label and a complete ordinary double round-robin season.
Short/abandoned seasons remain explicit gaps; no dates are filled by inference.
The explicit 2009 Turkish exclusion exception requires separate first-round proof.
"""
import csv
import datetime as dt
import io
import re
from urllib.parse import urlparse

POLICY = 'original-exact-English-competition-complete-double-round-robin-first-played-date-v1'
CODES = frozenset(('E0', 'E1', 'E2', 'E3', 'EC'))
ITALIAN_POLICY = 'original-exact-Italian-competition-complete-double-round-robin-first-played-date-v1'
TURKISH_POLICY = 'original-exact-Turkish-competition-complete-double-round-robin-first-played-date-v1'
CODES = CODES | {'I1', 'T1'}


def validate_url(url, season, code):
    if code not in CODES or not re.fullmatch(r'20\d{2}-\d{2}', season):
        raise ValueError('unsupported English archive competition or season')
    ending = int(season[:4]) + 1
    if ending % 100 != int(season[-2:]):
        raise ValueError('football season year pair is inconsistent')
    parsed = urlparse(url)
    relative = '/mmz4281/' + season[2:4] + season[-2:] + '/' + code + '.csv'
    if (parsed.scheme != 'https' or parsed.netloc not in ('www.football-data.co.uk', 'football-data.co.uk')
            or parsed.path != relative or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise ValueError('original football result URL does not identify the exact season and competition')


def parse(raw, season, code):
    if code not in CODES:
        raise ValueError('unsupported English archive competition')
    # Older original spreadsheets use Windows-1252 (referee names, smart
    # apostrophes and NBSP). Decode strictly; never replace undecodable bytes
    # or rewrite the captured source. UTF-8/BOM remains the first choice.
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('cp1252')
    rows = list(csv.DictReader(io.StringIO(text)))
    matches, pairs = [], set()
    required = {'Div', 'Date', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG'}
    for row in rows:
        if not any(v for v in row.values()):
            continue
        if not required <= set(row) or row['Div'] != code:
            raise ValueError('original results contain another or ambiguous competition')
        home, away = row['HomeTeam'], row['AwayTeam']
        if not home or not away or home == away or (home, away) in pairs:
            raise ValueError('original results repeat or ambiguously identify a league fixture')
        value = row['Date']
        fmt = '%d/%m/%y' if re.fullmatch(r'\d{2}/\d{2}/\d{2}', value) else '%d/%m/%Y'
        day = dt.datetime.strptime(value, fmt).date().isoformat()
        if not f'{season[:4]}-07-01' <= day <= f'{int(season[:4]) + 1}-06-30':
            raise ValueError('original played fixture is outside its exact football season')
        if not re.fullmatch(r'\d+', row['FTHG']) or not re.fullmatch(r'\d+', row['FTAG']):
            raise ValueError('original fixture lacks a recorded completed score')
        pairs.add((home, away))
        matches.append({'date': day, 'home': home, 'away': away, 'competition_code': code})
    clubs = {r[k] for r in matches for k in ('home', 'away')}
    # 2009/10 retains the complete 17-club played-results subleague after
    # Ankaraspor's exclusion. This is not a complete 18-club opening archive:
    # require separate original first-round evidence before using its date.
    sizes = ((17,) if season == '2009-10' else (18,)) if code == 'T1' else (20, 22, 24)
    if len(clubs) not in sizes or pairs != {(h, a) for h in clubs for a in clubs if h != a}:
        raise ValueError('original league archive is incomplete; first fixtures are not certified by this policy')
    return matches


def first_fixture(raw, season, code, exact_label):
    matches = parse(raw, season, code)
    candidates = [r for r in matches if exact_label in (r['home'], r['away'])]
    if not candidates:
        raise ValueError('exact published team label is absent from the original league archive')
    earliest = min(r['date'] for r in candidates)
    first = [r for r in candidates if r['date'] == earliest]
    if len(first) != 1:
        raise ValueError('original club has multiple played fixtures on its earliest date')
    policy = {'I1': ITALIAN_POLICY, 'T1': TURKISH_POLICY}.get(code, POLICY)
    if code == 'T1' and season == '2009-10':
        policy = 'original-Turkey-2009-17-club-played-subleague-date-needs-independent-first-round-proof-v1'
    return {'policy': policy, 'season': season, 'exact_published_club_label': exact_label,
        'fixture': first[0], 'source_scope': 'played league fixture date only',
        'starting_xi': None, 'substitutes': None, 'manager': None,
        'ownership_established': False}
