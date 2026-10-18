import copy
import pytest
from scripts import prepare_italchacao_2001_verified_inputs_v1 as inputs


def catalogue():
    return b'''<title>Deportivo Italchacao - Detailed squad 01/02 (Detailed view) | Transfermarkt</title>
    <table class="items"><tbody><tr>
    <td>1</td><td><a href="/andre/profil/spieler/880823">Andre</a></td>
    <td>20/02/1976 (26)</td><td><img class="flaggenrahmen" title="Brazil"></td>
    <td>-</td><td>1,80m</td><td>-</td><td>-</td><td>-</td><td>-</td>
    </tr></tbody></table>'''


def official():
    period = ['JOS� FASCIANA 1 Venezuela','DANIEL DIEZ 3 Venezuela',
        'GREGORY LUZARDO 13 Venezuela','LEOPOLDO JIM�NEZ 14 Venezuela',
        'ARSENIO SANTEUGINI 16 Venezuela','H�CTOR BIDOGLIO - Venezuela',
        'GIOVANNY P�REZ 23 Venezuela','RAFAEL CASTELL�N 9 Venezuela',
        'JOS� LUIS VALLENILLA PACHECO - Venezuela','WILLIAM GONZ�LEZ - Venezuela',
        'MODESTO GONZ�LEZ - Venezuela','CLAUDIO SILVA, CARIOCA - Brasil']
    return ('<html>PLANTILLA APERTURA 2001/ APERTURA 2001 SQUAD '+
        ' '.join(period)+' '*500+'</html>').encode('utf8')


def desired():
    return [dict(source_person=dict(source_player_id=880823,birth_date='1976-02-20')),
        dict(source_person=dict(source_player_id=112276,birth_date='1977-06-08'))]


def test_metric_source_height_and_explicit_unknown_country():
    facts = inputs.secondary_facts(catalogue(), desired(), official())
    assert facts[880823]['height_cm'] == 180
    assert facts[880823]['nationality'] == 'BRA'
    assert facts[112276]['nationality'] == 'XXX'
    assert facts[112276]['height_cm'] is None


@pytest.mark.parametrize('old,new', [(b'01/02',b'02/03'),
    (b'20/02/1976',b'20/02/2006'),(b'Brazil',b'Unknown'),(b'1,80m',b'80 inches')])
def test_wrong_season_namesake_country_or_unit_refused(old,new):
    with pytest.raises(ValueError):
        inputs.secondary_facts(catalogue().replace(old,new),desired(),official())


def test_duplicate_stable_identity_row_refused():
    raw=catalogue().replace(b'</tbody>',catalogue().split(b'<tbody>')[1].split(b'</tbody>')[0]+b'</tbody>')
    with pytest.raises(ValueError,match='ambiguous'):
        inputs.secondary_facts(raw,desired(),official())
