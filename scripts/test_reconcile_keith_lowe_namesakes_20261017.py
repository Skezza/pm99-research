"""Namesake evidence is exact and bounded, never a general duplicate waiver."""
import json
import pytest
from scripts import reconcile_keith_lowe_namesakes_20261017 as subject

@pytest.fixture
def prepared(tmp_path,monkeypatch):
    monkeypatch.setattr(subject.registry,'ROOT',tmp_path)
    witness={};actors=[];native={}
    for key,carrier,person,birthday,stamp,name in (
        ('english_namesake',9816,108814,'1998-07-13','13 Jul, 1998','Rob Atkinson'),
        ('guiseley_namesake',11058,38010,'1987-04-29','29 Apr, 1987','Robert Atkinson')):
        path=tmp_path/f'{person}.html'
        path.write_text(f'<h1>{name}</h1><table><tr><td>Born</td><td>{stamp}</td></tr></table>')
        witness[key]=dict(source_path=path.name,source_sha256=subject.registry.sha256_file(path),
            soccerbase_player_id=person,source_url=f'https://www.soccerbase.com/players/player.sd?player_id={person}')
        actors.append(dict(carrier_id=carrier,facts=dict(birth_date=birthday)))
        native[carrier]=dict(birth_date=birthday)
    path=tmp_path/'witness.json';path.write_text(json.dumps(witness))
    monkeypatch.setattr(subject,'WITNESS',path)
    monkeypatch.setattr(subject,'WITNESS_SHA',subject.registry.sha256_file(path))
    monkeypatch.setattr(subject.facts,'native_facts',lambda jug,carrier:native[carrier])
    return actors,native,path,witness

def test_independent_numeric_profiles_and_native_dates_distinguish_namesakes(prepared):
    actors,_,_,_=prepared
    proof=subject.validate_namesakes(actors,dict(carrier_id=11058),b'')
    assert proof['distinct_numeric_people_and_DOB']
    assert proof['English1998_opening_ownership_not_verified_by_this_identity_proof']
    assert {r['original_biography']['provider_player_id'] for r in proof['people']}=={108814,38010}

@pytest.mark.parametrize('fault',['other-carrier','same-DOB','native-DOB','changed-report','changed-body','wrong-URL'])
def test_rejects_unproved_collisions_or_changed_sources(prepared,monkeypatch,fault):
    actors,native,path,witness=prepared
    if fault=='other-carrier':actors[0]['carrier_id']=9999
    elif fault=='same-DOB':actors[0]['facts']['birth_date']='1987-04-29'
    elif fault=='native-DOB':native[9816]['birth_date']='1987-04-29'
    elif fault=='changed-report':path.write_text('{}')
    elif fault=='changed-body':(path.parent/'108814.html').write_text('<h1>wrong person</h1>')
    elif fault=='wrong-URL':
        witness['english_namesake']['source_url']='https://www.soccerbase.com/players/player.sd?player_id=38010'
        path.write_text(json.dumps(witness));monkeypatch.setattr(subject,'WITNESS_SHA',subject.registry.sha256_file(path))
    with pytest.raises(ValueError):subject.validate_namesakes(actors,dict(carrier_id=11058),b'')
