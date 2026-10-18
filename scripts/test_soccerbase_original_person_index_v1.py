import copy
import hashlib
import json
import pytest
from scripts import season_soccerbase_duplicate_source_policy_v1 as policy
from scripts import season_soccerbase_original_opening_v1 as original
from scripts import season_release_registry_v1 as registry
from scripts import replay_original_soccerbase_openings_v1 as replay


def row(tmp_path,id=555,name='Retired Fullname',dob='01 Jan, 1980'):
    raw=f'<h1>{name}</h1><table><tr><th>Age</th><td>46 (Born {dob})</td></tr></table>'.encode()
    url=f'https://www.soccerbase.com/players/player.sd?player_id={id}'
    native={'provider_player_id':id,'source_player_id':'soccerbase:'+str(id)}
    person=original.profile(raw,native,url)
    path=tmp_path/f'{id}-{hashlib.sha256(raw).hexdigest()[:8]}.html';path.write_bytes(raw)
    receipt=path.with_suffix('.source.json')
    digest=hashlib.sha256(raw).hexdigest();receipt.write_text(json.dumps({'url':url,'sha256':digest}))
    proof={'path':path.name,'sha256':digest,'source_receipt_path':receipt.name,
        'source_receipt_sha256':hashlib.sha256(receipt.read_bytes()).hexdigest(),'url':url}
    return {'status':'original-first-fixture-reparsed','identity_bridges':{'starting_xi':[
        {'soccerbase_person':person,'transfermarkt_person':None}], 'published_bench':[]},'raw_sources':[proof]}


def doc(rows):return {'seasons':[{'clubs':rows}]}


def test_original_provider_identity_has_no_invented_tm_number_or_ownership(tmp_path,monkeypatch):
    monkeypatch.setattr(registry,'ROOT',tmp_path);r=row(tmp_path)
    people,summary=policy.extend_original_people({},doc([r]))
    person=people[('retiredfullname','1980-01-01')]['soccerbase:555']
    assert person['source_provider']=='soccerbase'
    assert policy.person_id(person)=='person-soccerbase-555'
    assert not summary['ownership_established']
    # The source review still does not falsely label this a TM identity.
    assert replay.bridge(r['identity_bridges']['starting_xi'][0]['soccerbase_person'],people)['transfermarkt_person'] is None


@pytest.mark.parametrize('problem',['bytes','receipt-url','parsed-name','parsed-dob'])
def test_forged_biography_or_identity_never_enters_native_person_index(tmp_path,monkeypatch,problem):
    monkeypatch.setattr(registry,'ROOT',tmp_path);r=row(tmp_path)
    proof=r['raw_sources'][0];p=r['identity_bridges']['starting_xi'][0]['soccerbase_person']
    if problem=='bytes':(tmp_path/proof['path']).write_bytes(b'changed')
    if problem=='receipt-url':(tmp_path/proof['source_receipt_path']).write_text('{}')
    if problem=='parsed-name':p['name']='Invented Fullname'
    if problem=='parsed-dob':p['birth_date']='1981-01-01'
    with pytest.raises(ValueError):policy.extend_original_people({},doc([r]))


@pytest.mark.parametrize('problem',['same-provider-DOB-conflict','shared-name-DOB','known-TM-identity','ambiguous-TM-identity'])
def test_conflicts_and_known_people_do_not_receive_competing_provider_ids(tmp_path,monkeypatch,problem):
    monkeypatch.setattr(registry,'ROOT',tmp_path);r=row(tmp_path);rows=[r];before={}
    if problem=='same-provider-DOB-conflict':rows.append(row(tmp_path,dob='02 Jan, 1980'))
    if problem=='shared-name-DOB':rows.append(row(tmp_path,id=556))
    if problem in ('known-TM-identity','ambiguous-TM-identity'):
        before[('retiredfullname','1980-01-01')]={99:{'source_player_id':99,'birth_date':'1980-01-01'}}
        if problem=='ambiguous-TM-identity':before[('retiredfullname','1980-01-01')][100]={'source_player_id':100,'birth_date':'1980-01-01'}
    after,summary=policy.extend_original_people(before,doc(rows))
    assert after==before and not summary['added']


@pytest.mark.parametrize('person',[{'source_player_id':'555'}, {'source_player_id':'soccerbase:555'},
    {'source_player_id':'transfermarkt:555','source_provider':'soccerbase'},
    {'source_player_id':-555,'source_provider':'soccerbase'}])
def test_native_stable_person_id_requires_the_true_declared_provider(person):
    with pytest.raises(ValueError):policy.person_id(person)


def test_native_fallback_date_declarations_are_not_hashed_as_dates_or_ignored_names():
    players=[{'name':'Known Date','facts':{'birth_date':'1980-01-01'}},
        {'name':'Display Alias','source_name':'Undated Fullname','facts':{'birth_date':{'policy':'preserve-existing-mode1'}}},
        {'name':'No Date','facts':{'birth_date':None}}]
    before=copy.deepcopy(players);dates,names=policy.existing_identity_protection(players)
    assert dates=={'1980-01-01'} and names=={'undatedfullname','nodate'}
    assert players==before
