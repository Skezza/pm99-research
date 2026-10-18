import pytest
import copy
from scripts import mladost_2001_original_august_v1 as source


def original():
    return ('<html>'+' '*550+'<h3>Mladost Apatin - Partizan 1:3 (1:1)</h3>'
        '<p>26. avgust 2001.  Gledalaca: 7 000</p><p>'+source.LINE+
        '</p><h3>Later match</h3></html>').encode()


def test_round_two_not_opening_day():
    result=source.parse_match(original())
    assert result['fixture_date']=='2001-08-26'
    assert result['first_league_xi'] is False
    assert len(result['starting_xi'])==11
    assert len(result['used_substitutes'])==3
    assert result['manager']=='Dragi Bogić'
    assert result['unused_substitutes'] is None


@pytest.mark.parametrize('before,after',[
    ('26. avgust','18. avgust'),('2001.','2002.'),('Dragi Bogić','Unknown Coach'),
    ('Žakula','Another Keeper'),("46' Savić","46' Someone"),
    ('1:3 (1:1)','1:2 (0:1)'),('7 000','7000')])
def test_mutated_fixture_refused(before,after):
    with pytest.raises(ValueError):source.parse_match(original().decode().replace(before,after).encode())


def test_wrong_source_url_refused():
    with pytest.raises(ValueError):source.parse_match(original(),url='https://example.com/0102.html')


def test_repeated_section_refused():
    with pytest.raises(ValueError):source.parse_match(original()+original())


def fake_source(monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(source,'source_rows',lambda key:(Path('fixture.html'),original(),{'path':'fixture.html','sha256':'a'*64}))
    monkeypatch.setattr(source.pipeline,'read_json_file',lambda path:{'url':source.URL})


@pytest.mark.parametrize('index',sorted(source.UNRESOLVED))
def test_literal_actor_has_no_namesake_biography(monkeypatch,index):
    fake_source(monkeypatch)
    actor=source.unresolved_actor(index)
    assert actor['birth_date'] is None and actor['given_name'] is None
    assert actor['family_name']==actor['name']
    assert source.verify_actor(actor).startswith('person-original-fixture-')


@pytest.mark.parametrize('field,value',[
    ('name','Marjan Ciric'),('given_name','Marjan'),('family_name','Ciric'),
    ('birth_date','1985-04-21'),('source_player_id',41762),('source_provider','transfermarkt')])
def test_unresolved_ciric_cannot_import_a_namesake(monkeypatch,field,value):
    fake_source(monkeypatch);actor=source.unresolved_actor(10);actor[field]=value
    with pytest.raises(ValueError):source.verify_actor(actor)


@pytest.mark.parametrize('index',[0,1,4,5,8,11,14,-1,True,None])
def test_unreviewed_actor_indices_refused(monkeypatch,index):
    fake_source(monkeypatch)
    with pytest.raises(ValueError):source.unresolved_actor(index)


def test_mladost_kit_namespace_does_not_overwrite_italchacao():
    from scripts.season_foreign_fixed_roster_delta_v1 import kit_source_artifact
    a=kit_source_artifact('2001-02',{},carrier=706)
    b=kit_source_artifact('2001-02',{})
    assert a['id']!=b['id'] and a['relative_path']!=b['relative_path']


def test_seed_catalogue_change_cannot_silently_render(monkeypatch,tmp_path):
    from scripts import prepare_mladost_2001_seed_kits_v1 as seed
    monkeypatch.setattr(seed,'catalogue',lambda:{'original':'exact'})
    with pytest.raises(ValueError):seed.render_seed({'original':'changed'},tmp_path)
