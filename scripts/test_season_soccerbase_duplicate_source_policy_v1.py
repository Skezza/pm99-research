import copy
import pytest
from scripts import season_soccerbase_duplicate_source_policy_v1 as policy


def entity(id=10):
    return {'source_club_id':id,'country_id':189,'club_type_id':1,
        'is_national_team':False,'main_club_id':str(id),'published_names':['Boreham Wood FC']}


def actual():
    def player(id):
        return {'transfermarkt_person':{'source_player_id':id,'birth_date':'1990-01-01'},
            'soccerbase_person':{'source_player_id':'soccerbase:'+str(id+1000),
                'name':'Full Person '+str(id),'birth_date':'1990-01-01',
                'source_profile_url':'https://www.soccerbase.com/players/player.sd?player_id='+str(id+1000)},
            'dated_match_position':'D','published_match_name':'F Person'}
    bench=player(12)
    return {'club':'Boreham W','fixture':{'date':'2021-08-21'},'identity_gaps':[],
        'identity_bridges':{'starting_xi':[player(i) for i in range(1,12)],'published_bench':[bench]},
        'source_capture':{'source_path':'soccerbase/team/364/august'},
        'original_match':{'provider_club_id':'soccerbase:364'},
        'raw_sources':[{'url':bench['soccerbase_person']['source_profile_url'],
                        'path':'original/profile.html','sha256':'abc'}]}


def events(owner=10):
    return [{'date':'2021-07-01','from_club_id':20,'to_club_id':owner,
             'from_club':'Prior','to_club':'Owner'},
            {'date':'2022-07-01','from_club_id':owner,'to_club_id':30,
             'from_club':'Owner','to_club':'Next'}]


def test_name_candidate_needs_independent_dated_starter_corroboration():
    row=actual();entities={10:entity()}
    assert policy.discover_club_id('Boreham W',entities)==10
    with pytest.raises(ValueError):policy.confirm_club_mapping(row,entities,{})
    with pytest.raises(ValueError):policy.confirm_club_mapping(row,entities,{1:events()})
    witness=policy.confirm_club_mapping(row,entities,{1:events(),2:events()})
    result=policy.evidence(row,witness)
    assert len(result['starting_xi'])==11 and len(result['substitutes'])==1
    assert policy.verified_date(result)
    assert not result['match_page_date_independently_published']
    replacement=result['soccerbase_verified_replacements'][0]
    assert replacement['source_player']['position']=='D'
    assert replacement['source_player']['nationality'] is None


@pytest.mark.parametrize('targeted', [True, False])
def test_targeted_only_season_does_not_require_an_invented_legacy_capture_pin(tmp_path, monkeypatch, targeted):
    import json
    from scripts import season_pipeline_v2 as pipeline
    row=actual();row['status']='original-first-fixture-reparsed'
    row['represented_native_clubs']=[{'club_id':'a','carrier_id':3305,'club':'Boreham W'}]
    if targeted:row['source_capture']['targeted_original_capture']={'path':'own.json','sha256':'raw'}
    document={'policy':policy.replay.POLICY,'snapshot_binding':{'path':'snapshot'},
        'published_person_binding':{'path':'people'},'seasons':[{'season':'2021-22','clubs':[row]}]}
    review=tmp_path/'review.json';pipeline.write_canonical_json(review,document)
    entity_path=tmp_path/'entities.json';entity_path.write_text('{}')
    bindings={'snapshot':document['snapshot_binding'],'published_person_supplement':document['published_person_binding'],
        'soccerbase_opening_sources':{'policy':policy.POLICY,
        'review':{'path':str(review),'sha256':policy.registry.sha256_file(review)},
        'club_entities':{'path':str(entity_path),'sha256':policy.registry.sha256_file(entity_path)}}}
    monkeypatch.setattr(policy.club_entities,'read_entities',lambda path:{10:entity()})
    calls=[]
    def reconstruct(saved,season,capture,people):
        calls.append(capture)
        assert capture is None and saved==row
        return actual()
    monkeypatch.setattr(policy,'reconstruct',reconstruct)
    args=(bindings,'2021-22',[{'id':'a','carrier_id':3305,'name':'Boreham W'}],[],{},
        {1:events(),2:events()},{})
    if not targeted:
        with pytest.raises(ValueError,match='lacks its capture input'):policy.attach(*args)
        assert calls==[]
    else:
        result,gaps=policy.attach(*args)
        assert len(result['a']['starting_xi'])==11 and gaps==[] and calls==[None]


def test_weymouth_explicit_published_fc_label_still_requires_dated_starters():
    row = actual(); row['club'] = 'Weymouth'
    e = entity(); e.update(source_club_id=3822, main_club_id='3822', published_names=['Weymouth FC'])
    assert policy.discover_club_id('Weymouth', {3822: e}) == 3822
    with pytest.raises(ValueError):
        policy.confirm_club_mapping(row, {3822: e}, {})
    assert policy.confirm_club_mapping(row, {3822: e}, {1: events(3822), 2: events(3822)})['source_club_id'] == 3822
    e['published_names'] = ['Weymouth Womens FC']
    with pytest.raises(ValueError):
        policy.confirm_club_mapping(row, {3822: e}, {1: events(3822), 2: events(3822)})


@pytest.mark.parametrize('kind',['unproved-club-ambiguity','different-country','reserve-team','current-main',
    'contrary-starter','incomplete-brackets','same-day-entry','unbridged-player'])
def test_wrong_lifecycle_current_identity_and_insufficient_chronology_refuse(kind):
    row=actual();entities={10:entity()};history={1:events(),2:events()}
    if kind=='unproved-club-ambiguity':entities[11]=entity(11);history={}
    if kind=='different-country':entities[10]['country_id']=999
    if kind=='reserve-team':entities[10]['club_type_id']=5
    if kind=='current-main':entities[10]['main_club_id']='20'
    if kind=='contrary-starter':history[3]=events(50)
    if kind=='incomplete-brackets':history[2]=events()[:1]
    if kind=='same-day-entry':history[2][0]['date']='2021-08-21'
    if kind=='unbridged-player':row['identity_bridges']['starting_xi'][1]['transfermarkt_person']=None
    with pytest.raises(ValueError):policy.confirm_club_mapping(row,entities,history)


def test_same_published_name_can_be_disambiguated_only_by_original_dated_starters():
    entities={10:entity(),11:entity(11)}
    with pytest.raises(ValueError):policy.discover_club_id('Boreham W',entities)
    witness=policy.confirm_club_mapping(actual(),entities,{1:events(),2:events()})
    assert witness['source_club_id']==10 and witness['candidate_club_ids']==[10,11]


def test_retired_club_is_not_disqualified_by_current_inactive_status():
    e=entity();e.update(club_type_id=0,main_club_id='0')
    with pytest.raises(ValueError):policy.confirm_club_mapping(actual(),{10:e},{})
    assert policy.confirm_club_mapping(actual(),{10:e},{1:events(),2:events()})['source_club_id']==10


@pytest.mark.parametrize('kind',['identity-gap','short-xi','duplicate-xi','same-bench-person','wrong-date'])
def test_complete_identity_bridge_and_explicit_eleven_are_mandatory(kind):
    row=actual();witness={'source_club_id':10,'date':'2021-08-21'}
    if kind=='identity-gap':row['identity_gaps']=[{'reason':'DOB missing'}]
    if kind=='short-xi':row['identity_bridges']['starting_xi'].pop()
    if kind=='duplicate-xi':row['identity_bridges']['starting_xi'][1]=row['identity_bridges']['starting_xi'][0]
    if kind=='same-bench-person':row['identity_bridges']['published_bench'][0]=row['identity_bridges']['starting_xi'][0]
    if kind=='wrong-date':witness['date']='2021-08-22'
    with pytest.raises(ValueError):policy.evidence(row,witness)


def test_unknown_bench_role_is_logged_not_invented_as_replacement():
    row=actual();row['identity_bridges']['published_bench'][0]['dated_match_position']=None
    result=policy.evidence(row,{'source_club_id':10,'date':'2021-08-21'})
    assert len(result['substitutes'])==1 and not result['soccerbase_verified_replacements']


def test_unbridged_person_stays_namespaced_and_protects_possible_same_dob_ids():
    row=actual();row['identity_bridges']['published_bench'][0]['transfermarkt_person']=None
    row['identity_gaps']=[{'reason':'no-unique-independent-full-name-DOB-provider-bridge'}]
    witness={'source_club_id':10,'date':'2021-08-21'}
    with pytest.raises(ValueError):policy.evidence(row,witness)
    people={('anothername','1990-01-01'):{99:{'source_player_id':99,'birth_date':'1990-01-01'}},
            ('other','1991-01-01'):{100:{'source_player_id':100,'birth_date':'1991-01-01'}}}
    result=policy.evidence(row,witness,people)
    assert list(result['substitutes'])==['soccerbase:1012']
    assert result['unresolved_person_id_candidates']==['99']
    assert not result['soccerbase_verified_replacements']


def test_unbound_provider_source_policy_cannot_authorise_native_writes():
    plan={'updates':[{'owner_evidence':{'source_provider_policy':policy.POLICY}}]}
    with pytest.raises(ValueError):policy.validate_binding(plan)
    policy.validate_binding({'updates':[]})


@pytest.mark.parametrize('problem',['wrong-person','wrong-dob','wrong-provider','unpublished-field'])
def test_original_match_alias_has_exact_provider_person_and_birth_date(problem):
    result=policy.evidence(actual(),{'source_club_id':10,'date':'2021-08-21'})
    replacement=result['soccerbase_verified_replacements'][0]
    assert policy.explicit_display_names(replacement)==[{'field':'dated-match-label','name':'F Person'}]
    alias=replacement['source_display_aliases']
    if problem=='wrong-person':alias['source_person_id']=999
    if problem=='wrong-dob':alias['birth_date']='1980-01-01'
    if problem=='wrong-provider':alias['source_provider_person_id']='transfermarkt:1012'
    if problem=='unpublished-field':alias['names'][0]['field']='AI-truncation'
    with pytest.raises(ValueError):policy.explicit_display_names(replacement)


def test_other_or_forged_schedule_flag_is_not_a_verified_date():
    assert not policy.verified_date({'fixture_date_published_on_original_schedule':True})
    assert not policy.verified_date({'source_provider_policy':policy.POLICY,
        'fixture_date_published_on_original_schedule':True,'date':'2021-08-21',
        'soccerbase_original_fixture':{'date':'2021-08-22'}})


def test_native_starting_guard_reads_encoded_eq_and_actual_order_not_recipe_absence(monkeypatch):
    from types import SimpleNamespace
    from scripts import season_contextual_tactics_v1 as tactics
    entry=SimpleNamespace(payload_offset=2,payload_length=4)
    native=(b'xxEQRAWyy',b'JUG',{3305:entry},{100:'indexed'})
    calls=[]
    def read(encoded,jug,index):
        calls.append((encoded,jug,index))
        assert encoded==b'EQRA'
        return [(i,'Player') for i in range(100,111)]
    monkeypatch.setattr(tactics,'native_xi',read)
    club={'carrier_id':3305,'opening':{'policy':'preserve-existing-mode1'}}
    starters,reused=policy.native_starters(None,club,native)
    assert starters==set(range(100,111)) and reused is native and len(calls)==1


def test_unreadable_nonplayable_native_xi_refuses_instead_of_assuming_no_starters(monkeypatch):
    from types import SimpleNamespace
    from scripts import season_contextual_tactics_v1 as tactics
    entry=SimpleNamespace(payload_offset=0,payload_length=4)
    native=(b'EQRA',b'JUG',{3305:entry},{})
    def refuse(*args):raise ValueError('unreadable native tactics roster')
    monkeypatch.setattr(tactics,'native_xi',refuse)
    with pytest.raises(ValueError):policy.native_starters(None,{'carrier_id':3305},native)
