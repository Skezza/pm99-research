import datetime as dt

import pytest

from scripts import season_historical_snapshot_opening_review_v1 as review


def fixture(name='FC Barcelona', country='Spain', id=131):
    return ('2594471', dt.date(2015, 8, 23), id, name, 'Luis Enrique',
            '4-3-3', 'https://source/match/2594471', 'ES1', country)


def test_harmless_fc_spelling_and_country_are_exact_not_fuzzy(monkeypatch):
    monkeypatch.setattr(review.roster, 'club_group', lambda c: c['country'])
    index = review.index_rows([fixture()])
    assert review.only_candidate({'name': 'Barcelona', 'country': 'spain'}, index)['source_club_id'] == 131
    assert review.only_candidate({'name': 'Barcelona', 'country': 'italy'}, index) is None
    index = review.index_rows([fixture('RCD Espanyol')])
    assert review.only_candidate({'name': 'Espanyol', 'country': 'spain'}, index) is None


def test_english_source_group_and_ambiguous_historical_identity(monkeypatch):
    monkeypatch.setattr(review.roster, 'club_group', lambda c: c['country'])
    index = review.index_rows([fixture('Manchester United', 'England', 985)])
    club = {'name': 'Manchester United', 'country': 'england'}
    assert review.only_candidate(club, index)['source_club_id'] == 985
    index = review.index_rows([fixture('Manchester United', 'England', 985), fixture('Manchester United FC', 'England', 123)])
    assert review.only_candidate(club, index) is None


def test_independent_query_earliest_domestic_game_not_cup_or_current_profile():
    duckdb = pytest.importorskip('duckdb')
    connection = duckdb.connect(':memory:')
    try:
        connection.execute('''CREATE TABLE games(game_id VARCHAR,date DATE,competition_id VARCHAR,
            home_club_id INTEGER,home_club_name VARCHAR,home_club_manager_name VARCHAR,home_club_formation VARCHAR,
            away_club_id INTEGER,away_club_name VARCHAR,away_club_manager_name VARCHAR,away_club_formation VARCHAR,
            url VARCHAR,season INTEGER,competition_type VARCHAR)''')
        connection.execute("CREATE TABLE competitions(competition_id VARCHAR,country_name VARCHAR)")
        connection.execute("INSERT INTO competitions VALUES ('ES1','Spain')")
        for game,date,coach,kind in [('2','2015-08-23','Opening Coach','domestic_league'),
                                     ('3','2015-09-01','Later Coach','domestic_league'),
                                     ('1','2015-08-01','Cup Coach','domestic_cup')]:
            connection.execute('INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                [game,date,'ES1',131,'FC Barcelona',coach,'4-3-3',621,'Athletic Bilbao','Other Coach','4-4-2','https://source/'+game,2015,kind])
        rows = connection.execute(review.QUERY, [2015,2015]).fetchall()
        assert len(rows) == 2
        barcelona = next(row for row in rows if row[2] == 131)
        assert barcelona[0] == '2' and barcelona[4] == 'Opening Coach'
    finally:
        connection.close()
