import json
import pytest
from scripts import tachira_2014_original_opening_v1 as source


def document():
    xi = [f'Person{i}' for i in range(11)]
    for i, name in [(5, 'BenchA'), (7, 'BenchB'), (9, 'BenchC')]:
        xi[i] += f' ({name} 60´)'
    body = [
        'Ficha Técnica:',
        '(3) Deportivo Táchira F.C.: ' + ', '.join(xi) + '. D.T.: Coach Name.',
        'Suplentes sin jugar: BenchD, BenchE, BenchF, BenchG.',
        '(0) Atlético Venezuela C.F.: Other team.',
        'Estadio: Pueblo Nuevo, San Cristóbal, estado Táchira.',
        'Jornada 1, Torneo Apertura 2014, Liga Movistar 2014-2015.',
        'Prensa Deportivo Táchira',
    ]
    metadata = json.dumps({'@graph': [{'@type': 'NewsArticle', 'datePublished': '2014-08-10T20:18:21-04:00'}]})
    return (f'<html><head><link rel="canonical" href="{source.URL}">'
            f'<script type="application/ld+json">{metadata}</script></head>'
            '<h1>Triplete de Rivas hizo ganar al Táchira</h1>'
            '<div class="entry-content">' + ''.join('<p>' + p + '</p>' for p in body)
            + '</div><script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>'
            + '<!--' + ' padding' * 120 + '--></html>').encode()


def test_full_dated_article_with_passive_security_script_is_evidence():
    result = source.parse(document())
    assert result['starting_xi'] == [f'Person{i}' for i in range(11)]
    assert len(result['used_substitutes']) == 3
    assert len(result['unused_substitutes']) == 4
    assert result['manager'] == 'Coach Name'
    assert not result['publication_authorised']
    assert result['native_writes'] == 0


@pytest.mark.parametrize('old,new', [
    ('2014-08-10T', '2015-08-10T'),
    ('Jornada 1,', 'Jornada 2,'),
    ('BenchG.', 'BenchD.'),
    ('(3) Deportivo Táchira F.C.:', '(3) Other FC:'),
    ('class="entry-content"', 'class="sidebar"'),
    ('Triplete de Rivas hizo ganar al Táchira', 'Just a moment...'),
])
def test_wrong_period_club_body_duplicate_or_challenge_refused(old, new):
    with pytest.raises(ValueError):
        source.parse(document().replace(old.encode(), new.encode()))


def test_unexpected_url_refused():
    with pytest.raises(ValueError, match='URL'):
        source.parse(document(), 'https://other.example/')
