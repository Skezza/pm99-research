import pytest

from scripts import arsenal_2021_shirt_source_v1 as subject


def match_fixture():
    starters=''.join(f'<div class="formation-player-container"><a href="/p/profil/spieler/{i}">P</a>'
        f'<div class="tm-shirt-number">{i}</div></div>' for i in range(1,12))
    bench=''.join(f'<tr><td><div class="tm-shirt-number">{i}</div></td>'
        f'<td><a href="/p/profil/spieler/{i}">P</a></td></tr>' for i in range(12,21))
    return ('<div class="large-6"><a href="/club/startseite/verein/11/">Arsenal</a>'
        +starters+'<table class="ersatzbank">'+bench+'</table></div>').encode()


def test_numbers_are_from_numeric_player_rows_not_native_order():
    numbers,groups=subject.matchday(match_fixture())
    assert numbers=={i:i for i in range(1,21)}
    assert list(map(len,groups))==[11,9]


@pytest.mark.parametrize('raw',[
    match_fixture().replace(b'/verein/11/',b'/verein/1148/'),
    match_fixture()+match_fixture(),
    match_fixture().replace(b'>20</div>',b'>1</div>'),
    match_fixture().replace(b'>20</div>',b'>0</div>'),
    match_fixture().replace(b'/spieler/20',b'/spieler/19'),
])
def test_wrong_side_duplicate_player_or_number_fails_closed(raw):
    with pytest.raises(ValueError):subject.matchday(raw)


def season_fixture(birthday='1993-06-13'):
    return ('<h1>2021–22 Arsenal F.C. season</h1><table class="wikitable">'
        '<tr><th>No.</th><th>Player</th><th>Date of birth (age)</th></tr>'
        '<tr><td>5</td><td><a href="./Thomas_Partey">Thomas Partey</a></td>'
        f'<td>({birthday}) 13 June 1993</td></tr>'
        '<tr><td>14</td><td>Aubameyang</td><td>not selected</td></tr></table>').encode()


def test_reserve_number_requires_full_original_name_and_dob():
    people={230784:dict(name='Thomas Partey',birth_date='1993-06-13')}
    rows=subject.reserve_numbers(season_fixture(),people,{230784:{'thomaspartey'}})
    assert rows=={230784:dict(number=5,source_name='Thomas Partey',birth_date='1993-06-13')}
    with pytest.raises(ValueError,match='birthday'):
        subject.reserve_numbers(season_fixture('1994-06-13'),people,{230784:{'thomaspartey'}})


def test_contemporary_or_other_season_page_cannot_supply_historical_number():
    with pytest.raises(ValueError,match='heading/year'):
        subject.reserve_numbers(season_fixture().replace(b'2021',b'2025'),{}, {})
