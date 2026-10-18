import pytest
from scripts import jedinstvo_2005_original_opening_v1 as source


def document():
    return ('<h3>Prvenstvo:</h3><h3>Partizan - Jedinstvo Bijelo Polje 2:0 (1:0)</h3>'
        '<p>6. avgust 2005. Gledalaca: 5 000</p><p>Partizan: original home XI</p>'
        '<p>'+source.LINE+'</p><p>Strelci: 1:0 Ivan Tomić 23\' 2:0 Radović 58\'</p>'
        '<h3>Second fixture</h3>'+' '*1100).encode()


def test_exact_original_first14_not_invented_bench():
    actual=source.parse(document())
    assert len(actual['starting_xi'])==11 and len(actual['used_substitutes'])==3
    assert actual['unused_substitutes'] is None and actual['formation'] is None
    assert actual['manager']=='Sava Kovačević' and not actual['publication_authorised']


@pytest.mark.parametrize('old,new',[('6. avgust 2005.','6. avgust 2006.'),('Sava Kovačević','Wrong Coach'),
    ('Jovšić','Wrong Keeper'),('Ermin Drndar','Ekrem Drndar'),('87’ Franca','80’ Someone'),
    ('Partizan - Jedinstvo Bijelo Polje','Partizan - OFK'),('Prvenstvo:','Cup:')])
def test_wrong_period_club_identity_or_coach_rejected(old,new):
    with pytest.raises(ValueError):source.parse(document().decode().replace(old,new).encode())


def test_other_season_url_rejected():
    with pytest.raises(ValueError):source.parse(document(),'https://www.partizanopedia.rs/0405.html')


def test_original_layout_whitespace_is_not_a_different_date():
    assert source.parse(document().replace(b'2005. Gledalaca',b'2005.  Gledalaca'))['fixture_date']=='2005-08-06'
