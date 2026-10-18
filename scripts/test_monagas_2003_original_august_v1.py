import pytest

from scripts import monagas_2003_original_august_v1 as source


def original():
    body = ('Edition 2003 [July 31] Monagas SC 1-2 Deportivo Italchacao '
            'At Estadio Alexander “comanche” Bottini in Maturín. ' + source.JULY +
            ' [August 5] Deportivo Italchacao 1-0 Monagas SC '
            'At Estadio Brígido Iriarte in Caracas ' + source.AUGUST +
            ' First Round: [August 14] another match Edition 2002 earlier edition')
    return ('<html><title>Venezolan clubs in Copa Sudamericana</title><pre>' +
            body + '</pre></html>').encode('cp1252')


def test_original_august_union_is_exact_fixed16_not_a_league_opener():
    parsed = source.parse(original())
    assert len(parsed['starting_xi']) == 11
    assert len(parsed['used_substitutes']) == 3
    assert len(parsed['additional_opening_people']) == 2
    assert parsed['first_league_xi'] is False
    assert parsed['native_writes'] == 0
    assert parsed['starting_xi'][4]['published_match_name'] == 'Enermis Rodríguez'
    assert parsed['fixture_date'] == '2003-08-05'


@pytest.mark.parametrize('before,after', [
    ('Edition 2003', 'Edition 2004'), ('[August 5]', '[September 5]'),
    ('José Fasciana', 'José Bottini'), ('Ronald Ojeda, 75', 'Ronald Ojeda, 70'),
    ('Daniel Lanata;', 'Eduardo Borrero;'), ('Monagas SC 1-2', 'Monagas SC 2-1'),
    ('Estadio Brígido Iriarte', 'Estadio Olímpico'),
])
def test_wrong_period_person_manager_date_result_or_ground_refused(before, after):
    with pytest.raises(ValueError):
        source.parse(original().replace(before.encode('cp1252'), after.encode('cp1252')))


def test_other_original_url_refused():
    with pytest.raises(ValueError, match='URL'):
        source.parse(original(), url='https://rsssf.org/current-squad')


def test_different_season_fixture_cannot_replace_target_section():
    body = original().replace(source.AUGUST.encode('cp1252'), b'no target roster')
    body = body.replace(b'Edition 2002', b'Edition 2002 ' + source.AUGUST.encode('cp1252'))
    with pytest.raises(ValueError, match='target fixture'):
        source.parse(body)
