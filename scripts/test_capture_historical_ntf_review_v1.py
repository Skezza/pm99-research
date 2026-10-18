import pytest
from scripts import capture_historical_ntf_review_v1 as ntf


def test_legal_suffix_is_not_fuzzy_club_or_person_matching():
    assert ntf.english_legal_name('Chelsea FC') == ntf.english_legal_name('Chelsea')
    assert ntf.english_legal_name('FC United of Manchester') != ntf.english_legal_name('Manchester United')
    assert ntf.english_legal_name('Manchester City') != ntf.english_legal_name('Manchester United')


def test_documented_comma_name_order_and_no_initial_guess():
    assert 'cristianoronaldo' in ntf.person_names('Ronaldo, Cristiano')
    assert 'cristianoronaldo' not in ntf.person_names('C. Ronaldo')
    assert 'edwinvandersar' in ntf.person_names('van der Sar, Edwin')


def test_ntf_unknown_position_still_counts_as_person_but_wrong_year_does_not():
    raw = b'''<title>Manchester United (2005/06) | National Football Teams</title>
    <tr itemprop="athlete"><td></td><td>Ronaldo, Cristiano</td><td>1985-02-05</td><td>Portugal</td><td>Unknown</td><td>2005/06</td><td>20</td><td>3</td></tr>'''
    assert ntf.parse_players(raw, '2005-06')[0]['nationality'] == 'Portugal'
    assert ntf.parse_players(raw.replace(b'<td>2005/06', b'<td>2006/07'), '2005-06') == []
    with pytest.raises(ValueError, match='outside'):
        ntf.parse_players(raw, '2004-05')
