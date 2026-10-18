"""Provider IDs/headings/dated tenures are not replaced by a matching surname."""
from bs4 import BeautifulSoup
import pytest
from scripts import prepare_stoke_alias_identity_evidence_20261016 as subject


def profile(*,heading='Fixture Player',birth='01 Jan, 1980',joined='01 Aug, 00',left='01 Jul, 04'):
    return BeautifulSoup(f'<h1>{heading}</h1><p>Age 40 (Born {birth})</p><table>'
        f'<tr><td>Stoke</td><td>{joined}</td><td>{left}</td><td>Trainee</td></tr></table>','html.parser')


def test_exact_published_birthday_and_career_are_parsed():
    result=subject.soccerbase(profile(),'Fixture Player')
    assert result['birth_date']=='1980-01-01'
    assert result['Stoke']['joined']=='2000-08-01' and result['Stoke']['left']=='2004-07-01'


def test_same_surname_wrong_published_person_heading_is_refused():
    with pytest.raises(ValueError,match='person heading'):
        subject.soccerbase(profile(heading='Another Player'),'Fixture Player')


def test_multiple_profile_birthdays_are_not_silently_chosen():
    page=profile();page.append(BeautifulSoup('<p>Born 02 Feb, 1981</p>','html.parser'))
    with pytest.raises(ValueError,match='one explicit Soccerbase birthday'):
        subject.soccerbase(page,'Fixture Player')


def test_missing_career_is_not_inferred_from_the_current_club_name():
    page=profile();page.table.decompose()
    with pytest.raises(ValueError,match='dated Stoke tenure'):
        subject.soccerbase(page,'Fixture Player')


def test_a_late_tenure_is_preserved_as_late_not_rebased_into_august():
    result=subject.soccerbase(profile(joined='14 Mar, 03',left='05 May, 03'),'Fixture Player')
    assert result['Stoke']['joined']>'2002-08-10'


def test_duplicate_identity_field_is_refused():
    page=BeautifulSoup('<table><tr><td>Nationality</td><td>A</td></tr>'
        '<tr><td>Nationality</td><td>B</td></tr></table>','html.parser')
    with pytest.raises(ValueError,match='one explicit original identity field'):
        subject.unique_field(page,'Nationality')
