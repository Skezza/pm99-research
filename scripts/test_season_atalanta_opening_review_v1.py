"""Fail-closed identity tests, not synthetic historical evidence."""
import pytest

from scripts.season_atalanta_opening_review_v1 import adriano_bridge, biography


def original(*, birthday='1982-04-03', full='Adriano Pereira da Silva',
             caption='Adriano', years='2005–2007', club='Atalanta', extra=''):
    return f'''<h1>Adriano (footballer, born April 1982)</h1>
    <table class="infobox"><caption class="infobox-title">{caption}</caption>
    <tr><th>Full name</th><td>{full}</td></tr>
    <tr><td><span class="bday">{birthday}</span></td></tr>
    <tr><th class="infobox-header">Senior career*</th></tr>
    <tr><th>Years</th><th>Team</th></tr>
    <tr><th>{years}</th><td>{club}</td></tr>{extra}
    <tr><th class="infobox-header">Managerial career</th></tr>
    <tr><th>2000–2010</th><td>Other club</td></tr></table>'''.encode()


SOURCE = {'name': 'Adriano Pereira', 'birth_date': '1982-04-03', 'position': 'D'}


def test_literal_alias_and_interior_year():
    result = adriano_bridge(original(), SOURCE)
    assert result['sporting_names'] == ['Adriano']
    assert result['exact_transfer_date_claimed'] is False
    assert len(result['senior_career']) == 1


@pytest.mark.parametrize('kwargs', [
    {'birthday': '1982-04-04'}, {'full': 'Adriano Ferreira Pinto'},
    {'caption': 'Adriano Ferreira Pinto'}, {'years': '2006–2007'},
    {'years': '2005–2006'}, {'club': 'Palermo'}, {'club': '→ Atalanta (loan)'},
    {'years': '2005–'}, {'years': '2007–2005'},
    {'extra': '<tr><th>2006</th><td>Other club</td></tr>'},
])
def test_different_identity_boundary_loan_or_ambiguous_owner_refused(kwargs):
    with pytest.raises(ValueError):
        adriano_bridge(original(**kwargs), SOURCE)


def test_source_broad_role_must_agree():
    with pytest.raises(ValueError):
        adriano_bridge(original(), dict(SOURCE, position='M'))


def test_different_article_title_refused():
    with pytest.raises(ValueError):
        biography(original(), 'Adriano Ferreira Pinto')


def test_duplicate_infobox_refused():
    with pytest.raises(ValueError):
        adriano_bridge(original() + '<table class="infobox"></table>'.encode(), SOURCE)
