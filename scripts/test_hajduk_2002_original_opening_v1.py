import pytest

from scripts import hajduk_2002_original_opening_v1 as opening


def sources():
    report = ('<p>PARTIZAN: Radakovic - ' + opening.LINE +
              ' IGRAC UTAKMICE: Goran Trobok (Partizan). RADNICKI: Soldatovic 7</p>')
    dated = ('<h3>Partizan - Hajduk Kula 5:1 (3:1)</h3>'
             '<p>10. avgust 2002. Gledalaca: 800</p><p>Partizan: original</p>'
             '<p>' + opening.DATED_LINE + '</p><p>Strelci: original</p>'
             '<h3>Radnički Obrenovac - Partizan 1:2 (1:2)</h3>')
    coach = ('<p>Sunday, September 1, 2002 '
             'Miloljub Ostojic has resigned as coach of Yugoslavian first division side FK Hajduk Kula. '
             'Kula are 13th after four matches under Ostojic, who was appointed in June</p>')
    return tuple(('<html>' + s + '<!--' + 'padding' * 90 + '--></html>').encode()
                 for s in (report, dated, coach))


def test_original_labels_not_namesake_identities():
    result = opening.parse(*sources())
    assert len(result['starting_xi']) == 11
    assert [p['published_match_name'] for p in result['starting_xi']] == opening.XI
    assert all(p['full_identity'] is None for p in result['starting_xi'])
    assert result['fixture_date'] == '2002-08-10'
    assert result['manager'] == 'Miloljub Ostojić'


def test_disagreeing_secondary_lineup_never_manufactures_reserves():
    result = opening.parse(*sources())
    assert result['used_substitutes'] == [dict(published_match_name='Vojnic', minute=46, full_identity=None)]
    assert result['unused_substitutes'] is None
    assert result['source_disagreements'][0]['original_line'] == opening.DATED_LINE
    assert not result['publication_authorised'] and result['native_writes'] == 0


@pytest.mark.parametrize('index,before,after', [
    (0, 'Trajkovic 5', 'Branislav Trajkovic 5'),
    (0, '(46. Vojnic 5)', '(46. Vuksanovic 5)'),
    (1, '10. avgust 2002.', '17. avgust 2002.'),
    (1, ', Zelić', ''),
    (2, 'September 1, 2002', 'September 1, 2003'),
    (2, 'four matches', 'twenty matches'),
])
def test_changed_identity_date_disagreement_or_manager_refused(index, before, after):
    raw = list(sources())
    raw[index] = raw[index].replace(before.encode(), after.encode())
    with pytest.raises(ValueError):
        opening.parse(*raw)


def test_duplicate_original_match_refused():
    raw = list(sources())
    raw[0] += opening.LINE.encode()
    with pytest.raises(ValueError, match='ambiguous'):
        opening.parse(*raw)


def test_wrong_source_url_refused():
    with pytest.raises(ValueError, match='URLs'):
        opening.parse(*sources(), urls=('https://example.org', opening.DATED_URL, opening.MANAGER_URL))
