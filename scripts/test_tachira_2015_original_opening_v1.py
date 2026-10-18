import pytest
from scripts import tachira_2015_original_opening_v1 as source


def row(id, role, *, sub=False):
    return (f'<div class="{"ficha-sub-row" if sub else "ficha-row"}">'
        f'<div class="row-icon" title="{role}"></div>'
        f'<a href="../equipos/jugador.php?id={id}">Player{id}</a>'
        '<img alt="Venezuela">' + ('<div class="sub-number">78\'</div>' if sub else '') + '</div>')


def document():
    return ('<html><head><title>ForoVinotinto | dan 1-2 dta</title></head><body>'
        '<section class="ficha-container"><div class="ficha-partido-info">'
        'Estadio José Antonio Anzoátegui, Puerto la Cruz. 11 de Julio del 2015. 7:00pm '
        'Torneo de Adecuación - Ronda RegularJornada 1</div>'
        '<a id="par-homeTeam" desktop="Deportivo Anzoátegui"></a>'
        '<a id="par-awayTeam" desktop="Deportivo Táchira"></a>'
        '<div class="ficha-partido-resultado">1-2</div>'
        '<div id="away-titulares"><div class="ficha-title">Titulares</div>'
        + ''.join(row(id, 'Portero' if id==1 else 'Defensa') for id in range(1,12)) + '</div>'
        '<div id="away-titulares"><div class="ficha-title">Suplentes</div>'
        + ''.join(row(id,'Volante',sub=True) for id in range(12,15)) + '</div>'
        '<div id="away-titulares"><div class="ficha-title">Director Técnico</div>'
        '<a href="../equipos/jugador.php?id=1561">Daniel Farías</a></div></section>'
        '<script>/* passive /cdn-cgi/challenge-platform */</script></body></html>').encode()


def test_actual_match_dom_not_passive_script_controls_evidence():
    actual = source.parse(document())
    assert actual['fixture_date']=='2015-07-11'
    assert len(actual['starting_xi'])==11 and len(actual['used_substitutes'])==3
    assert actual['unused_substitutes'] is None and actual['formation'] is None
    assert actual['starting_xi'][0]['source_person_namespace']=='forovinotinto'
    assert actual['native_writes']==0 and not actual['publication_authorised']


@pytest.mark.parametrize('old,new', [
    ('11 de Julio del 2015','11 de Julio del 2016'),
    ('Ronda RegularJornada 1','Ronda RegularJornada 2'),
    ('Deportivo Anzoátegui','Different Club'),
    ('<div class="ficha-partido-resultado">1-2','<div class="ficha-partido-resultado">2-1'),
    ('Daniel Farías','Wrong Coach'),
    ('title="Portero"','title="Defensa"'),
    ('jugador.php?id=14','jugador.php?id=13'),
    ('title="Volante"','title="Unknown"'),
    ('section class="ficha-container"','section class="challenge-interstitial"'),
    ('ForoVinotinto | dan 1-2 dta','Just a moment...'),
])
def test_wrong_source_period_club_role_identity_or_interstitial_refused(old,new):
    with pytest.raises(ValueError):
        source.parse(document().decode().replace(old,new).encode())


def test_unexpected_source_url_refused():
    with pytest.raises(ValueError):
        source.parse(document(),'https://www.forovinotinto.com/historia/ficha.php?div=1&id=11209')
