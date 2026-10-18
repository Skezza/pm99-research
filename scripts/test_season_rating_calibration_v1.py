import datetime as dt
import pytest
from scripts import season_rating_calibration_v1 as c
from scripts import season_quality_only_delta_v1 as q

def player(name='Kyle Walker',dob='1990-05-28',position='D'):
    return dict(source_name=name,name=name,person_id='published-person',club_id='club',
        facts=dict(birth_date=dob,primary_position=position,height_cm=180,fine_roles=[1]))

def source():
    return dict(player_id='188377',edition=23,date='2022-09-26',dob='1990-05-28',positions='RB',
        values={k:80 for k in c.MAPPING}|dict(quality=85,speed=94,stamina=86,handling=6))

def test_no_future_fifa_used_for_2000():
    assert c.match(player(),2000,{(23,'kylewalker','1990-05-28'):{'188377':source()}}) is None

def test_proxy_bounded_and_correct_ageing():
    row=source();index={(23,'kylewalker','1990-05-28'):{'188377':row}}
    assert c.match(player(),2024,index)==row
    assert c.match(player(),2026,index) is None
    assert c.fifa_values(row,2024,'D')['speed']==90
    assert c.fifa_values(row,2024,'D')['quality']==83

def test_no_surname_or_dob_only_match():
    index={(23,'kylewalker','1990-05-28'):{'188377':source()}}
    assert c.match(player(name='Walker'),2024,index) is None
    assert c.match(player(dob='1990-05-29'),2024,index) is None

def test_ambiguous_identity_and_keeper_conflict_refuse():
    key=(23,'kylewalker','1990-05-28')
    assert c.match(player(),2024,{key:{'1':source(),'2':source()}}) is None
    assert c.match(player(position='G'),2024,{key:{'1':source()}}) is None

def test_goalkeeper_handling_not_age_damaged_or_outfield_capped():
    row=source();row['values']['handling']=85
    assert c.fifa_values(row,2024,'G')['handling']==85
    assert c.fifa_values(row,2024,'D')['handling']==20

def test_editorial_deterministic_and_no_carrier_dependence():
    p=player();a=c.editorial(p,80,False,dt.date(2024,8,1))
    p['carrier_id']=999
    assert c.editorial(p,80,False,dt.date(2024,8,1))==a
    assert a['handling']<=20

def test_unknown_fine_role_not_guessed_as_fullback():
    p=player();a=c.editorial(p,80,False,dt.date(2024,8,1))
    p['facts']['fine_roles']={'policy':'preserve-existing-mode1'}
    b=c.editorial(p,80,False,dt.date(2024,8,1))
    assert a['speed']==b['speed']+8

@pytest.mark.parametrize('family',['dd6360','dd6361'])
def test_native_only_ten_skills_may_change(monkeypatch,family):
    raw=bytearray(b'\x61'*100);raw[2:5]=bytes.fromhex(family)
    monkeypatch.setattr(q.roster,'native_player',lambda payload,carrier:dict(name_end=20))
    monkeypatch.setattr(q.compiler,'_read_native_dd6360_fields',lambda payload,end:{})
    row=dict(ratings=dict(values={k:75 for k in c.MAPPING}))
    patched=q.record_patch(bytes(raw),1,row,{})
    start=38 if family=='dd6360' else 84
    assert [i for i,(a,b) in enumerate(zip(raw,patched)) if a!=b]==list(range(start,start+10))
    assert [b^0x61 for b in patched[start:start+10]]==[75]*10

@pytest.mark.parametrize('invalid',[True,100,0,-1,'75'])
def test_invalid_native_abilities_refuse(monkeypatch,invalid):
    raw=bytearray(b'\x61'*100);raw[2:5]=bytes.fromhex('dd6361')
    monkeypatch.setattr(q.roster,'native_player',lambda payload,carrier:dict(name_end=20))
    values={k:75 for k in c.MAPPING};values['speed']=invalid
    with pytest.raises(ValueError):q.record_patch(bytes(raw),1,dict(ratings=dict(values=values)),{})
