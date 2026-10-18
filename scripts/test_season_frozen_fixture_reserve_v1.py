import copy
import pytest
from scripts import season_frozen_fixture_reserve_v1 as source


@pytest.mark.parametrize('heading,wanted',[
    ('#5 Tom Aldred','Tom Aldred'),('#20 Sergei Zenjov','Sergei Zenjov'),
    ('#0 Name','#0 Name'),('#100 Name','#100 Name'),('5 Name','5 Name'),
    ('#5Name','#5Name'),('Jean-Pierre Name','Jean-Pierre Name')])
def test_only_explicit_source_shirt_heading_decoration_is_removed(heading,wanted):
    assert source.heading_name(heading)==wanted


def pair():
    before=dict(id='a',club_id='blackpool',carrier_id=9520,name='Tom Aldred',source_name='Tom Aldred',facts=dict(birth_date='1990-09-11'))
    keep=dict(id='b',club_id='accrington',carrier_id=9580,name='#5 Tom Aldred',source_name='#5 Tom Aldred',facts=dict(birth_date='1990-09-11'))
    first=dict(name='Tom ALDRED',birth_date='1990-09-11',startup_order=12,position='D')
    second=dict(name='#5 TOM ALDRED',birth_date='1990-09-11',startup_order=4,position='D')
    owners={9520:{322},9580:{324}}
    club=dict(id='blackpool',carrier_id=322,roster_player_ids=['a'])
    retained=dict(id='accrington',carrier_id=324,roster_player_ids=['b'])
    return [before,keep,first,second,owners,club,retained,'Tom Aldred','1990-09-11']


def test_published_raw_heading_is_preserved_while_matching_the_exact_original_actor():
    args=pair();original=copy.deepcopy(args)
    source.guard_pair(*args)
    assert args==original
    assert args[1]['source_name']=='#5 Tom Aldred'


@pytest.mark.parametrize('fault',['starter','keeper','wrong-native-name','wrong-date','wrong-source-identity','wrong-owner','shared-owner','missing-declaration','same-club'])
def test_rejects_unsafe_pair_or_native_preimage(fault):
    args=pair();before,keep,first,second,owners,club,retained,_,_=args
    if fault=='starter':first['startup_order']=11
    elif fault=='keeper':first['position']='G'
    elif fault=='wrong-native-name':second['name']='Another Aldred'
    elif fault=='wrong-date':first['birth_date']='1990-09-12'
    elif fault=='wrong-source-identity':keep['source_name']='Another Aldred'
    elif fault=='wrong-owner':owners[9520]={324}
    elif fault=='shared-owner':owners[9520]={322,324}
    elif fault=='missing-declaration':club['roster_player_ids']=[]
    elif fault=='same-club':keep['club_id']='blackpool'
    with pytest.raises(ValueError):source.guard_pair(*args)


def test_new_plan_verifier_is_explicit_and_does_not_reinterpret_other_schemas(monkeypatch):
    from scripts import season_duplicate_ownership_delta_v1 as delta
    calls=[]
    monkeypatch.setattr(source,'verify_plan',lambda base,plan:calls.append((base,plan)))
    marker=object();plan=dict(schema_version=source.SCHEMA)
    delta.verify_plan(marker,plan)
    assert calls==[(marker,plan)]


def test_no_unclaimed_retired_member_is_needed_for_a_real_two_member_case():
    assert source.retired_member_proof(None,{},None,None,None)==[]


def test_retired_witness_cannot_hide_the_current_displaced_actor():
    decision=dict(displaced_carrier=9520,retained_carrier=9580,
        previously_retired_frozen_members=[dict(carrier_id=9520)])
    with pytest.raises(ValueError,match='hides a current pair member'):
        source.retired_member_proof(None,decision,dict(players=[]),None,None)


def test_retired_witness_cannot_invent_an_original_extra_owner():
    decision=dict(displaced_carrier=9520,retained_carrier=9580,
        previously_retired_frozen_members=[dict(carrier_id=999)])
    with pytest.raises(ValueError,match='not an original frozen case member'):
        source.retired_member_proof(None,decision,dict(players=[]),None,None)
