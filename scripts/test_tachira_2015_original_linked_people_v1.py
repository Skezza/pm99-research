import pytest
from scripts import tachira_2015_original_linked_people_v1 as source


def document(id=177):
    name, dob = source.PEOPLE[id]
    year, month, day = dob.split('-')
    return (f'<title>ForoVinotinto | {name}</title><div class="player-card-data">'
        f'<h1>{name}</h1><span class="player-card-meta-line"><strong>Nacimiento:</strong> '
        f'{day}/{month}/{year} (41 años)</span></div>'
        '<script>/* passive /cdn-cgi/challenge-platform */</script>'+' '*1100).encode()


@pytest.mark.parametrize('id', list(source.PEOPLE))
def test_complete_linked_biography_not_passive_script(id):
    actual = source.parse(document(id), f'https://www.forovinotinto.com/equipos/jugador.php?id={id}')
    assert actual['birth_date'] == source.PEOPLE[id][1]
    assert actual['source_person_namespace'] == 'forovinotinto'
    assert not actual['publication_authorised']


@pytest.mark.parametrize('old,new', [
    ('Alan Liebenskind','Alan Different'), ('07/01/1985','08/01/1985'),
    ('Nacimiento:','Current age:'), ('player-card-data','challenge-interstitial'),
    ('<title>ForoVinotinto | Alan Liebenskind','<title>Just a moment...'),
    ('<h1>Alan Liebenskind</h1>','<h1>Alan Liebenskind</h1><h1>Other Person</h1>'),
])
def test_wrong_identity_date_or_interstitial_rejected(old,new):
    with pytest.raises(ValueError):
        source.parse(document().decode().replace(old,new).encode(),
            'https://www.forovinotinto.com/equipos/jugador.php?id=177')


def test_another_source_namespace_rejected():
    with pytest.raises(ValueError):
        source.parse(document(), 'https://www.transfermarkt.co.uk/player/profil/spieler/177')
