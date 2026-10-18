import csv
import datetime as dt
import io
import pytest
from scripts import season_football_data_opening_dates_v1 as dates


def rows():
    clubs = [f'Team {i:02}' for i in range(20)]
    result = []
    for home in clubs:
        for away in clubs:
            if home == away:
                continue
            n = len(result)
            day = dt.date(2003, 8, 9) + dt.timedelta(days=0 if n == 0 else 1 + n % 200)
            result.append({'Div': 'E3', 'Date': day.strftime('%d/%m/%y'),
                'HomeTeam': home, 'AwayTeam': away, 'FTHG': '1', 'FTAG': '0'})
    return result


def encoded(values):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=['Div','Date','HomeTeam','AwayTeam','FTHG','FTAG'])
    writer.writeheader(); writer.writerows(values)
    return stream.getvalue().encode()


def test_complete_original_competition_establishes_dates_not_player_claims():
    result = dates.first_fixture(encoded(rows()), '2003-04', 'E3', 'Team 00')
    assert result['fixture']['date'] == '2003-08-09'
    assert result['fixture']['away'] == 'Team 01'
    assert result['starting_xi'] is None and result['substitutes'] is None
    assert not result['ownership_established']


def test_Turkish_exclusion_exception_never_certifies_full_opening_coverage():
    clubs=[f'Team {i:02}' for i in range(17)]
    values=[{'Div':'T1','Date':('09/08/09' if n==0 else '10/08/09'),
             'HomeTeam':h,'AwayTeam':a,'FTHG':'1','FTAG':'0'}
            for n,(h,a) in enumerate((h,a) for h in clubs for a in clubs if h!=a)]
    result=dates.first_fixture(encoded(values),'2009-10','T1','Team 00')
    assert result['policy'].endswith('needs-independent-first-round-proof-v1')
    assert not result['ownership_established'] and result['starting_xi'] is None
    # The 17-team allowance is not transferable to another season or country.
    with pytest.raises(ValueError):dates.parse(encoded(values),'2008-09','T1')
    for row in values:row['Div']='E0'
    with pytest.raises(ValueError):dates.parse(encoded(values),'2009-10','E0')


def test_italian_archive_has_a_separate_policy_without_changing_English_evidence():
    values = rows()
    for row in values:
        row['Div'] = 'I1'
    result = dates.first_fixture(encoded(values), '2003-04', 'I1', 'Team 00')
    assert result['policy'] == dates.ITALIAN_POLICY
    dates.validate_url('https://www.football-data.co.uk/mmz4281/0304/I1.csv', '2003-04', 'I1')
    assert dates.first_fixture(encoded(rows()), '2003-04', 'E3', 'Team 00')['policy'] == dates.POLICY
    values.pop()
    with pytest.raises(ValueError):
        dates.first_fixture(encoded(values), '2003-04', 'I1', 'Team 00')


@pytest.mark.parametrize('problem', ['incomplete', 'abandoned-season', 'duplicate', 'other-competition',
    'no-score', 'invalid-score', 'wrong-year', 'same-team', 'no-team', 'initial-label', 'two-opening-games'])
def test_bad_incomplete_or_ambiguous_original_archives_are_refused(problem):
    values, club = rows(), 'Team 00'
    if problem == 'incomplete': values.pop()
    if problem == 'abandoned-season': values = values[:200]
    if problem == 'duplicate': values.append(dict(values[0]))
    if problem == 'other-competition': values[0]['Div'] = 'E2'
    if problem == 'no-score': values[0]['FTHG'] = ''
    if problem == 'invalid-score': values[0]['FTAG'] = 'abandoned'
    if problem == 'wrong-year': values[0]['Date'] = '09/08/02'
    if problem == 'same-team': values[0]['AwayTeam'] = values[0]['HomeTeam']
    if problem == 'no-team': values[0]['HomeTeam'] = ''
    if problem == 'initial-label': club = 'T. 00'
    if problem == 'two-opening-games': values[1]['Date'] = values[0]['Date']
    with pytest.raises(ValueError): dates.first_fixture(encoded(values), '2003-04', 'E3', club)


def test_reviewed_same_publisher_bare_host_redirect_is_allowed():
    for host in ('www.football-data.co.uk', 'football-data.co.uk'):
        dates.validate_url(f'https://{host}/mmz4281/0304/E3.csv', '2003-04', 'E3')


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-8-sig', 'cp1252'])
def test_published_accented_names_are_decoded_without_loss(encoding):
    values = rows()
    for row in values:
        for key in ('HomeTeam', 'AwayTeam'):
            if row[key] == 'Team 00':
                row[key] = 'Björk’s Team'
    raw = encoded(values).decode('utf-8').encode(encoding)
    result = dates.first_fixture(raw, '2003-04', 'E3', 'Björk’s Team')
    assert result['fixture']['home'] == 'Björk’s Team'
    assert result['starting_xi'] is None


def test_unknown_legacy_encoding_never_gets_replacement_characters():
    raw = encoded(rows()).replace(b'Team 00', b'Team \x81\x81')
    with pytest.raises(UnicodeDecodeError):
        dates.parse(raw, '2003-04', 'E3')


@pytest.mark.parametrize('url,season,code', [
    ('http://football-data.co.uk/mmz4281/0304/E3.csv','2003-04','E3'),
    ('https://other.example/mmz4281/0304/E3.csv','2003-04','E3'),
    ('https://football-data.co.uk/mmz4281/0203/E3.csv','2003-04','E3'),
    ('https://football-data.co.uk/mmz4281/0304/E2.csv','2003-04','E3'),
    ('https://football-data.co.uk/mmz4281/0304/E3.csv?other=1','2003-04','E3'),
    ('https://user@football-data.co.uk/mmz4281/0304/E3.csv','2003-04','E3'),
    ('https://football-data.co.uk/mmz4281/0304/E3.csv','2003-05','E3'),
    ('https://football-data.co.uk/mmz4281/0304/E3.csv','2003-04','XX')])
def test_original_URL_must_identify_the_exact_publisher_season_and_competition(url,season,code):
    with pytest.raises(ValueError): dates.validate_url(url,season,code)
