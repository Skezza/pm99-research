import copy

import pytest

from scripts import italchacao_2001_original_august_v1 as original


def html(text, encoding='cp1252'):
    # Preserved site mojibake is tested, not repaired into guessed accents.
    text = text.replace('�', 'ï¿½') if encoding == 'cp1252' else text
    return ('<html><p>' + text + '</p><!--' + 'padding' * 90 + '--></html>').encode(encoding)


def sources():
    return (html(original.CUP_LINE + ' Mie, 8 de Agosto de 2001 8 de Julio de 2001'),
            html(original.FRIENDLY_LINE + ' Dom, 12 de Agosto de 2001'),
            html('08-08-01 Nueva York NY/NJ MetroStars (USA) vs. Deportivo ItalChacao (VEN)'),
            html('19 de Agosto del 2001. Torneo Apertura 2001 - Jornada 1 '
                 'No hay información disponible sobre el banquillo de este equipo.', 'utf8'))


def people():
    return dict(schema_version='pm99-original-published-person-identities-v1',
        batches=[dict(people=[dict(source_player_id=id, name=alias,
            published_name_variants=[alias], birth_date='1970-01-01',
            current_club='Deliberately incorrect current club', current_position='Sweeper')
            for id, alias in original.ALIASES.items()])])


def test_no_first_league_lineup_or_native_permission_inferred():
    parsed = original.parse(*sources())
    assert parsed['league_starting_xi'] is None
    assert len(parsed['starting_xi']) == 11
    assert len(parsed['used_substitutes']) == 3
    assert len(parsed['additional_august_people']) == 2
    assert parsed['league_opening_date'] == '2001-08-19'
    assert not parsed['publication_authorised'] and parsed['native_writes'] == 0
    assert parsed['unused_substitutes'] is None and parsed['formation'] is None
    assert any('fit the fixed16 slots' in row for row in parsed['limitations'])
    assert not any('reserve goalkeeper needs' in row for row in parsed['limitations'])


def test_join_only_independent_names_and_dates_never_current_roles():
    rows = original.join_people(original.parse(*sources()), people())
    assert len(rows) == 16
    assert not any(r['current_roles_imported'] or r['current_club_imported'] for r in rows)
    assert 'current_position' not in str(rows) and 'Deliberately incorrect' not in str(rows)
    assert [r['source_player_id'] for r in rows if not r['birthday_approved']] == [347836]


@pytest.mark.parametrize('index,before,after', [
    (0, 'Gregory Luzardo', 'Unknown Luzardo'),
    (0, 'Mie, 8 de Agosto de 2001', 'Mie, 8 de Agosto de 2002'),
    (0, '8 de Julio de 2001', '8 de Agosto de 2001'),
    (1, 'Fernando Martï¿½nez', 'Different Martinez'),
    (1, 'Dom, 12 de Agosto de 2001', 'Dom, 12 de Agosto de 2002'),
    (2, '08-08-01', '08-09-01'),
    (3, '19 de Agosto del 2001.', '26 de Agosto del 2001.'),
])
def test_changed_original_date_or_player_refused(index, before, after):
    raw = list(sources())
    encoding = 'utf8' if index == 3 else 'cp1252'
    assert before.encode(encoding) in raw[index]
    raw[index] = raw[index].replace(before.encode(encoding), after.encode(encoding))
    with pytest.raises(ValueError):
        original.parse(*raw)


def test_surname_match_cannot_replace_full_independent_alias():
    doc = people()
    row = next(r for r in doc['batches'][0]['people'] if r['source_player_id'] == 172115)
    row['published_name_variants'] = ['Carlos Silva']
    with pytest.raises(ValueError, match='alias'):
        original.join_people(original.parse(*sources()), doc)


def test_duplicate_identity_refused():
    doc = people()
    doc['batches'][0]['people'].append(copy.deepcopy(doc['batches'][0]['people'][0]))
    with pytest.raises(ValueError, match='duplicate'):
        original.join_people(original.parse(*sources()), doc)


def test_falsely_complete_league_lineup_refused():
    parsed = original.parse(*sources())
    parsed['league_starting_xi'] = parsed['starting_xi']
    with pytest.raises(ValueError, match='falsely completed'):
        original.join_people(parsed, people())


def test_wrong_source_url_refused():
    with pytest.raises(ValueError, match='URLs'):
        original.parse(*sources(), urls=('https://example.org',) * 4)


def test_ambiguous_second_cup_lineup_refused():
    raw = list(sources())
    raw[0] += html(original.CUP_LINE)
    with pytest.raises(ValueError, match='ambiguous'):
        original.parse(*raw)
