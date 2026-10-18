import pytest

from scripts import borac_2003_original_opening_v1 as opening


def sources():
    groups = {
        'Golmani:': [('Djuric', 'Branko', '16.02.1976.')],
        'Odbrana:': [('Stevic', 'Sasa', '31.05.1981.'),
            ('Dragutinovic', 'Dragan', '17.01.1980.'), ('Jelic', 'Vitomir', '25.01.1982.'),
            ('Stevanovic', 'Ivan', '24.06.1983.'), ('Jasic', 'Vladimir', '04.01.1984.')],
        'Sredina:': [('Pavlovic', 'Bojan', '01.02.1985.'),
            ('Spasojevic', 'Vladan', '11.10.1980.'), ('Nedeljkovic', 'Zvonko', '17.11.1979.'),
            ('Zivkovic', 'Bojan', '10.11.1981.')],
        'Napad:': [('Bruncevic', 'Sead', '15.05.1977.'),
            ('Nesic', 'Dragan', '05.01.1979.'), ('Avramovic', 'Ivica', '30.08.1976.')],
    }
    groups['Napad:'] += [(f'Other{i}', 'Player', '01.01.1980.') for i in range(20)]
    rows = []
    for group, players in groups.items():
        rows.append(f'<tr><td colspan="3"><b>{group}</b></td></tr>')
        for family, given, birthday in players:
            rows.append(f'<tr><td><a href="borac/{family.lower()}.htm">'
                f'{family}, {given}</a></td><td>{birthday}</td><td>Scg</td></tr>')
    catalogue = ('<title>FK Borac Cacak</title><p>2002/03 1.mesto II/Z '
        'Trener: Miodrag Bozovic</p><table>' + ''.join(rows) + '</table>').encode()
    match = ('<title>Untitled Document</title><p>'
        'PARTIZAN BEOGRAD - BORAC CACAK 6:1 (2:0) ' + opening.LINE +
        ' NAPREDAK KRUSEVAC - CRVENA ZVEZDA BEOGRAD 2:1 (0:1) '
        'Prva Savezna Liga - 1.Kolo -</p>' + ' ' * 500).encode()
    manager = ('<title>Borac bring in Bozovic | UEFA.com</title><p>'
        'Tuesday, September 23, 2003 '
        'Newly promoted FK Borac have sacked coach Radovan Guduric and replaced him with Miodrag Bozovic. '
        'Borac have taken only one point from their first five matches</p>' + ' ' * 500).encode()
    dated = ('<h3>Prvenstvo:</h3><h3>Partizan - Borac Čačak 6:1 (2:0)</h3>'
        '<p>9. avgust 2003. Gledalaca: 8 000</p><p>Partizan: Original</p><p>'
        + opening.DATED_LINE + '</p><p>Strelci: Original</p>' + ' ' * 500).encode()
    return catalogue, match, manager, dated


def test_unique_full_names_dob_and_broad_roles_from_original():
    result = opening.parse(*sources())
    assert len(result['starting_xi']) == 11
    assert result['fixture_date'] == '2003-08-09'
    assert result['starting_xi'][0]['name'] == 'Branko Djuric'
    assert result['starting_xi'][0]['birth_date'] == '1976-02-16'
    assert result['starting_xi'][0]['position'] == 'G'
    assert [(p['name'], p['minute']) for p in result['used_substitutes']] == [
        ('Dragan Nesic', 75), ('Ivica Avramovic', 83)]


def test_later_manager_and_annual_presence_are_not_opening_approval():
    result = opening.parse(*sources())
    assert result['manager'] == 'Radovan Gudurić'
    assert result['superseded_catalogue_manager'] == 'Miodrag Božović'
    assert result['unused_substitutes'] is None
    assert not result['publication_authorised'] and result['native_writes'] == 0
    assert not any(p['opening_reserve_membership_approved'] for p in result['annual_identity_catalogue'])


@pytest.mark.parametrize('index,before,after', [
    (0, b'FK Borac Cacak', b'FK Borac Banja Luka'),
    (0, b'16.02.1976.', b'31.02.1976.'),
    (0, b'Golmani:', b'Napad:'),
    (0, b'Scg', b'-'),
    (1, b'1.Kolo', b'2.Kolo'),
    (1, b'(75. Nesic -)', b'(75. Unknown -)'),
    (2, b'September 23, 2003', b'September 23, 2004'),
    (2, b'Radovan Guduric', b'Miodrag Bozovic'),
    (2, b'first five matches', b'first fifteen matches'),
    (3, b'9. avgust 2003.', b'16. avgust 2003.'),
    (3, b"(75'", b"(70'"),
])
def test_changed_or_incomplete_original_is_rejected(index, before, after):
    values = list(sources())
    values[index] = values[index].replace(before, after)
    with pytest.raises(ValueError):
        opening.parse(*values)


def test_foreign_archive_url_is_rejected():
    with pytest.raises(ValueError, match='archive URL'):
        opening.catalogue(sources()[0], 'https://example.com/borac.htm')
