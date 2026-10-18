import pytest
import copy

from scripts import prepare_sartid_2000_source_allocation_v1 as source


def original():
    return ('<html><h3>Sartid - Partizan 3:2 (0:1)</h3>'
            '<p>19. avgust 2000. 17.30 Gledalaca: 15 000</p>'
            '<p>'+source.LINE+'</p><p>Partizan: original opponent list</p>'
            '<h3>Following fixture</h3>'+(' '*500)+'</html>').encode()


def test_round_two_remains_explicit_not_opening_day():
    result=source.parse_match(original())
    assert result['fixture_date']=='2000-08-19'
    assert result['first_league_xi'] is False
    assert result['round']==2
    assert len(result['starting_xi'])==11
    assert len(result['used_substitutes'])==3
    assert result['manager']=='Slobodan Dogandžić'


@pytest.mark.parametrize('old,new',[
    ('19. avgust 2000.','19. avgust 2001.'),
    ('Sartid - Partizan 3:2 (0:1)','Partizan - Sartid 3:1 (2:0)'),
    ('Slobodan Dogandžić','Jovica Škoro'),
    ('Lukić, Bulić','Bulić, Lukić'),
    ("75' Radosavljević","76' Radosavljević"),
])
def test_source_mutations_are_not_silently_accepted(old,new):
    with pytest.raises(ValueError): source.parse_match(original().decode().replace(old,new).encode())


def test_wrong_source_url_refused():
    with pytest.raises(ValueError): source.parse_match(original(),url=source.MATCH_URL.replace('0001','0102'))


def test_duplicate_fixture_refused():
    with pytest.raises(ValueError): source.parse_match(original()+original())


@pytest.fixture
def display_row(monkeypatch):
    bindings=[{'path':'fixture.html','sha256':'fixture-sha'},
              {'path':'catalogue.html','sha256':'catalogue-sha'}]
    catalogue=b'<html><a href="/nenad-lukic/profil/spieler/171101">Nenad Lukic</a></html>'
    monkeypatch.setattr(source,'source_rows',lambda key:
        (None,original(),bindings[0]) if key=='partizanopedia-2000-original-season'
        else (None,catalogue,bindings[1]))
    person=dict(source_player_id=171101,name='Nenad Lukic',birth_date='1968-10-14')
    monkeypatch.setattr(source.display,'read_batch',lambda batch: ({},{171101:copy.deepcopy(person)}))
    return dict(source_person=copy.deepcopy(person),original_fixture_display=dict(
        policy=source.DISPLAY_POLICY,match_person_index=0,published_label='Lukić',
        source_player_id=171101,original_bindings=copy.deepcopy(bindings),original_person_batch={}))


def test_published_fixture_label_is_not_a_new_canonical_name(display_row):
    assert source.fixture_display.candidates(display_row)[0]['name']=='Lukić'
    assert display_row['source_person']['name']=='Nenad Lukic'


@pytest.mark.parametrize('fault',['label','person','index','date','bindings','name'])
def test_display_bridge_cannot_reassign_actor_or_expand_name(display_row,fault):
    if fault=='label':display_row['original_fixture_display']['published_label']='N. Lukić'
    if fault=='person':display_row['original_fixture_display']['source_player_id']=49774
    if fault=='index':display_row['original_fixture_display']['match_person_index']=1
    if fault=='date':display_row['source_person']['birth_date']='1990-01-01'
    if fault=='bindings':display_row['original_fixture_display']['original_bindings'][0]['sha256']='changed'
    if fault=='name':display_row['source_person']['name']='Another Lukic'
    with pytest.raises(ValueError):source.fixture_candidates(display_row)
