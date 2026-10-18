import pytest
from scripts import season_external_soccerbase_birthday_v1 as subject


def page(name='Lewis Noice',born='September 27, 1995',club='Eastleigh FC',season='2015-16',role='G - Goalkeeper'):
    return f'<h1>{name}</h1><p>{name}<br>Born: {born}<br>Position: {role}</p><table><tr>' \
        '<th>Year</th><th>Country</th><th>Level</th><th>League</th><th>Team</th></tr>' \
        f'<tr><td>{season}</td><td>England</td><td>V</td><td>National League</td><td>{club}</td></tr></table>'


def parse(raw):
    return subject.statscrew(raw,'Lewis Noice','Eastleigh','G',dict(from_date='2014-07-01',to_date='2017-07-01'))


def test_literal_date_tied_to_exact_full_name_role_and_club_career():
    assert parse(page())['birth_date']=='1995-09-27'


@pytest.mark.parametrize('kwargs',[dict(name='Another Noice'),dict(club='Forest Green'),dict(season='2024-25'),
    dict(season='2015-17'),dict(role='D - Defender')])
def test_namesakes_wrong_clubs_seasons_roles_are_not_secondary_evidence(kwargs):
    with pytest.raises(ValueError):parse(page(**kwargs))


def test_duplicate_birthday_is_not_arbitrarily_selected():
    with pytest.raises(ValueError):parse(page()+page())


def test_known_original_date_cannot_be_overridden():
    with pytest.raises(ValueError,match='cannot override known dates'):
        subject.resolve(dict(secondary_birthday_policy=subject.POLICY),dict(birth_date='1996-01-01'),{})
