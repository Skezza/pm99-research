import csv
import io

import pytest

from scripts import season_italian_opening_dates_v2 as dates
from scripts import season_football_data_opening_dates_v1 as legacy

URL = 'https://www.football-data.co.uk/mmz4281/0001/I1.csv'


def rows(size=18):
    clubs = [f'Team {i:02}' for i in range(size)]
    return [{'Div': 'I1', 'Date': '01/10/00' if n == 0 else '02/10/00',
             'HomeTeam': h, 'AwayTeam': a, 'FTHG': '1', 'FTAG': '0'}
            for n, (h, a) in enumerate((h, a) for h in clubs for a in clubs if h != a)]


def encoded(values):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=['Div', 'Date', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG'])
    writer.writeheader()
    writer.writerows(values)
    return stream.getvalue().encode()


def test_complete_18_club_archive_only_establishes_fixture_date():
    raw = encoded(rows())
    result = dates.first_fixture(raw, '2000-01', 'Team 00', url=URL)
    assert result['fixture'] == {'date': '2000-10-01', 'home': 'Team 00',
                                 'away': 'Team 01', 'competition_code': 'I1'}
    assert result['policy'] == dates.POLICY
    assert result['starting_xi'] is None and result['substitutes'] is None
    assert result['manager'] is None and not result['ownership_established']
    with pytest.raises(ValueError):
        legacy.first_fixture(raw, '2000-01', 'I1', 'Team 00')


@pytest.mark.parametrize('problem', ['incomplete', 'duplicate', 'wrong-competition', 'wrong-year',
    'no-score', 'unplayed', 'same-team', 'no-team', 'unknown-club', 'two-first-fixtures',
    'wrong-season', 'wrong-url', '20-clubs'])
def test_bad_or_ambiguous_original_evidence_refuses(problem):
    values, season, club, url = rows(), '2000-01', 'Team 00', URL
    if problem == 'incomplete': values.pop()
    if problem == 'duplicate': values.append(dict(values[0]))
    if problem == 'wrong-competition': values[0]['Div'] = 'E0'
    if problem == 'wrong-year': values[0]['Date'] = '01/10/99'
    if problem == 'no-score': values[0]['FTAG'] = ''
    if problem == 'unplayed': values[0]['FTHG'] = 'abandoned'
    if problem == 'same-team': values[0]['AwayTeam'] = values[0]['HomeTeam']
    if problem == 'no-team': values[0]['AwayTeam'] = ''
    if problem == 'unknown-club': club = 'T. 00'
    if problem == 'two-first-fixtures': values[1]['Date'] = values[0]['Date']
    if problem == 'wrong-season': season = '2004-05'
    if problem == 'wrong-url': url = URL.replace('0001', '0102')
    if problem == '20-clubs': values = rows(20)
    with pytest.raises(ValueError):
        dates.first_fixture(encoded(values), season, club, url=url)


@pytest.mark.parametrize('raw', [b'', b'Div,Date,HomeTeam,HomeTeam,AwayTeam,FTHG,FTAG\n'])
def test_missing_or_duplicate_headers_refuse(raw):
    with pytest.raises(ValueError):
        dates.first_fixture(raw, '2000-01', 'Team 00', url=URL)
