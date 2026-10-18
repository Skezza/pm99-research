import pytest

from scripts import monagas_2002_original_august_v1 as source


def originals():
    rsssf = ('<html><title>Venezolan clubs in Copa Sudamericana</title><pre>'
        'Edition 2003 unrelated report Edition 2002 [August 28] '
        'Deportivo Táchira 0-2 Monagas SC At Estadio Pueblo Nuevo in San Cristóbal '
        + source.RSSSF_LINE + ' [September 6] At Estadio Alexander “comanche” Bottini in Maturín other report</pre>'
        + ' ' * 600 + '</html>').encode('cp1252')
    starters = ''.join(f'<a href="/person/profil/spieler/{id}">{name}</a>'
        for name, id in source.XI)
    bench = ''.join(f'<tr><td><a href="/person/profil/spieler/{id}">{name}</a></td></tr>'
        for name, id in source.UNUSED + [('Pedro Duval', 308346), ('Hugo González', 847531),
            ('César González', 56426), ('Alexis Acuña', 147681)])
    match = ('<html><title>Deportivo Táchira - Monagas SC, 28/08/2002 - '
        'Copa Sudamericana - Informe del partido | Transfermarkt</title>'
        '<div class="large-6 columns">Monagas SC Formación inicial:' + starters
        + '<table class="ersatzbank">' + bench + ' Entrenador: Eduardo Borrero</table></div>'
        + ' ' * 600 + '</html>').encode()
    return rsssf, match


def test_sixteen_dated_people_do_not_include_conflicting_reserve():
    parsed = source.parse(*originals())
    selected = parsed['starting_xi'] + parsed['used_substitutes'] + parsed['unused_substitutes']
    assert len(selected) == len({row['source_player_id'] for row in selected}) == 16
    assert 847531 not in {row['source_player_id'] for row in selected}
    assert parsed['manager'] == 'Eduardo Borrero'
    assert not parsed['first_league_xi'] and parsed['formation'] is None


@pytest.mark.parametrize('index,old,new', [
    (0, 'Edition 2002', 'Edition 2001'), (0, '[August 28]', '[September 28]'),
    (0, 'Coach: Eduardo Borrero;', 'Coach: Other;'),
    (0, 'Monagas SC', 'Different Club'),
    (1, '28/08/2002', '06/09/2002'), (1, 'Eduardo Borrero', 'César Farías'),
    (1, '847954', '999999'), (1, 'Hernán Sivira', 'Other Sivira'),
    (1, 'Monagas SC Formación inicial:', 'Deportivo Táchira Formación inicial:'),
])
def test_changed_original_evidence_is_refused(index, old, new):
    rows = list(originals())
    encoding = 'cp1252' if index == 0 else 'utf-8'
    rows[index] = rows[index].replace(old.encode(encoding), new.encode(encoding))
    with pytest.raises(ValueError):
        source.parse(*rows)


def test_other_fixture_bench_cannot_be_used():
    with pytest.raises(ValueError, match='URL'):
        source.parse(*originals(), urls=(source.RSSSF_URL, source.MATCH_URL + '?other=1'))


def test_duplicated_target_bench_is_ambiguous():
    rsssf, match = originals()
    start = match.index(b'<div class="large-6 columns">')
    end = match.index(b'</div>', start) + len(b'</div>')
    match = match + match[start:end]
    with pytest.raises(ValueError, match='ambiguous'):
        source.parse(rsssf, match)
