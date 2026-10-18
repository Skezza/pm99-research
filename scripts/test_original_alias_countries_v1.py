from bs4 import BeautifulSoup
import pytest
from scripts import season_original_alias_countries_v1 as subject


def common(country='Scotland',name='Kris Commons'):
    return BeautifulSoup(f'<h1>{name}</h1><p>Born 30 Aug, 1983</p><table>'
        f'<tr><th>Nationality</th><td>{country}</td></tr><tr><td>Stoke</td><td>01 Aug, 00</td>'
        '<td>01 Jul, 04</td><td>Trainee</td></tr></table>','html.parser')


def test_literal_full_identity_bound_profile_nationality_not_birthplace():
    assert subject.literal(common(),'2001-02')=='SCO'


@pytest.mark.parametrize('page',[common('England'),common(name='Another Commons')])
def test_wrong_identity_or_country_not_silently_accepted(page):
    with pytest.raises(ValueError):subject.literal(page,'2001-02')


def belgian(text='Jurgen Vandeurzen (born 26 January 1974) is a former Belgian professional footballer'):
    return BeautifulSoup('<span class="bday">1974-01-26</span><p>'+text+'</p>','html.parser')


def test_explicit_belgian_statement_is_positive_nationality_evidence():
    assert subject.literal(belgian(),'2002-03')=='BEL'


@pytest.mark.parametrize('text',['Jurgen Vandeurzen was born in Belgium',
    'Another Vandeurzen (born 26 January 1974) is a former Belgian professional footballer'])
def test_birthplace_or_namesake_not_a_literal_nationality_witness(text):
    with pytest.raises(ValueError):subject.literal(belgian(text),'2002-03')


def test_duplicate_biographical_nationality_statements_refuse_ambiguity():
    p=belgian();p.append(belgian().p)
    with pytest.raises(ValueError):subject.literal(p,'2002-03')
