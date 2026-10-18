import copy
import pytest
from scripts import review_duplicate_replacement_chains_v1 as chains
from scripts import season_historical_transfer_review_v1 as transfer


def scene(monkeypatch):
    def person(id,name,day):return {'source_player_id':id,'name':name,'birth_date':day,'given_name':None,'family_name':None}
    c=person(99,'Actual Reserve','1990-01-02');e=person(100,'Unused Reserve','1991-02-03')
    def player(id,club,name,born):return {'id':id,'carrier_id':1 if id=='wrong-a' else 2,'club_id':club,
        'name':name,'source_name':name,'facts':{'birth_date':born,'primary_position':'F'}}
    first=player('wrong-a','club-b','Duplicated Original','1988-01-01')
    second=player('wrong-c','club-d',c['name'],c['birth_date'])
    def replacement(p,club):return {'source_person':p,'source_player':{'name':p['name'],'birth_date':p['birth_date'],'position':'M'},
        'opening_eligibility':{'method':'positive-first-fixture-substitute-id','date':'2021-08-07','source_club_id':club},
        'raw_evidence':{'status':'raw-source-reparsed'}}
    ctx={'clubs':{'club-b':{'id':'club-b','name':'B','division':'english-premier'},
                  'club-d':{'id':'club-d','name':'D','division':'english-premier'}},
        'players':{first['id']:first,second['id']:second},'layer_by_id':{'wrong-a':'main','wrong-c':'main'},
        'carrier_layers':{1:{'main'},2:{'main'}},'blocked_slots':set(),'reserved_people':set(),
        'occupied':{99:[second]},'occupied_identities':set(),'occupied_dates':set(),'undated_names':set(),
        'people':{(transfer._normalise(p['name']),p['birth_date']):{p['source_player_id']:p} for p in (c,e)},
        'events':{99:[{'date':'2021-07-01','from_club_id':1,'to_club_id':44,'from_club':'Prior','to_club':'B'},
                      {'date':'2022-01-01','from_club_id':44,'to_club_id':2,'from_club':'B','to_club':'Later'}]},
        'evidence':{'club-b':{'source_club_id':44,'date':'2021-08-07','starting_xi':{},'substitutes':{'99':'Actual Reserve'},
                'match_page_date_independently_published':True},
            'club-d':{'source_club_id':55,'date':'2021-08-07','starting_xi':{},'substitutes':{'100':'Unused Reserve'},
                'match_page_date_independently_published':True}},'captures':[],'verifier':None,
        'reserve_cache':{'club-b':[replacement(c,44)],'club-d':[replacement(e,55)]},
        'actual_starter_cache':{'club-b':set(),'club-d':set()}}
    monkeypatch.setattr(chains,'fitted',lambda ctx,loser,r:{'display_name':r['source_player']['name']})
    return ctx,first,second


def test_two_slot_chain_has_positive_ownership_and_no_native_write(monkeypatch):
    ctx,first,second=scene(monkeypatch);before=copy.deepcopy(ctx)
    route=chains.path(ctx,first,set(),{98},3)
    assert [e['before']['id'] for e in route]==['wrong-a','wrong-c']
    assert [e['replacement']['source_person']['source_player_id'] for e in route]==[99,100]
    proof=route[0]['paired_existing_copy']
    assert proof['prospective_owner_slot']=='wrong-a'
    assert proof['prospective_owner_is_new_replacement_not_current_native_identity']
    assert all(i['source_owner_club_id']==44 for i in proof['transfer_intervals'])
    assert all(e['native_write'] is False and not e['actual_native_starter'] for e in route)
    assert ctx==before


@pytest.mark.parametrize('problem',['root-native-starter','child-native-starter','root-declared-starter',
    'child-declared-starter','shared-carrier','other-layer','reserved-root','reserved-person','visited-root',
    'cycle','no-child-source','two-existing-copies','already-correct-local','root-keeper','child-keeper',
    'unknown-role','undated-name','DOB-collision','unbridged-Soccerbase-DOB-collision','no-positive-owner',
    'missing-transfer-exit','contradictory-transfer-chain','different-opening-ownership','name-does-not-fit',
    'too-short-chain-budget','missing-native-XI-proof'])
def test_chain_never_waives_identity_source_starting_keeper_or_window_guards(monkeypatch,problem):
    ctx,first,second=scene(monkeypatch)
    r=ctx['reserve_cache']['club-b'][0]
    if problem=='root-native-starter':ctx['actual_starter_cache']['club-b'].add(1)
    if problem=='child-native-starter':ctx['actual_starter_cache']['club-d'].add(2)
    if problem=='root-declared-starter':ctx['clubs']['club-b']['opening']={'starting_xi_player_ids':['wrong-a']}
    if problem=='child-declared-starter':ctx['clubs']['club-d']['opening']={'starting_xi_player_ids':['wrong-c']}
    if problem=='shared-carrier':ctx['carrier_layers'][2].add('english')
    if problem=='other-layer':ctx['layer_by_id']['wrong-c']='english'
    if problem=='reserved-root':ctx['blocked_slots'].add('wrong-a')
    if problem=='reserved-person':ctx['reserved_people'].add(99)
    if problem=='cycle':ctx['reserve_cache']['club-d'][0]['source_person']['source_player_id']=98
    if problem=='no-child-source':del ctx['evidence']['club-d']
    if problem=='two-existing-copies':ctx['occupied'][99].append(copy.deepcopy(second))
    if problem=='already-correct-local':second['club_id']='club-b'
    if problem=='root-keeper':first['facts']['primary_position']='G'
    if problem=='child-keeper':second['facts']['primary_position']='G'
    if problem=='unknown-role':r['source_player']['position']='?'
    if problem=='undated-name':ctx['undated_names'].add(chains.roster.normalise(r['source_player']['name']))
    if problem=='DOB-collision':ctx['occupied_identities'].add((chains.roster.normalise('Unused Reserve'),'1991-02-03'))
    if problem=='unbridged-Soccerbase-DOB-collision':r['source_person']['source_provider']='soccerbase';ctx['occupied_dates'].add('1990-01-02')
    if problem=='no-positive-owner':ctx['evidence']['club-b']['substitutes'].clear()
    if problem=='missing-transfer-exit':ctx['events'][99].pop()
    if problem=='contradictory-transfer-chain':ctx['events'][99][-1]['from_club_id']=66
    if problem=='different-opening-ownership':ctx['evidence']['club-d']['date']='2022-02-01'
    if problem=='name-does-not-fit':monkeypatch.setattr(chains,'fitted',lambda *args:None)
    if problem=='missing-native-XI-proof':
        def no_xi(*args):raise ValueError('cannot prove actual XI')
        monkeypatch.setattr(chains.context,'actual_starters',no_xi)
    visited={'wrong-a'} if problem=='visited-root' else set()
    budget=1 if problem=='too-short-chain-budget' else 3
    assert chains.path(ctx,first,visited,{98},budget) is None


def test_cached_chain_name_fit_is_exact_existing_native_writer_and_indexes_once(monkeypatch):
    from scripts.test_season_duplicate_ownership_delta_v1 import fixture
    from scripts.test_season_package_compiler_v2 import _indexed_fdi,_dd6361_player_payload
    from scripts import season_duplicate_ownership_delta_v1 as delta
    package,proposal=fixture('dd6361');row=proposal['updates'][0]
    original=_indexed_fdi([(row['carrier_id'],'',_dd6361_player_payload(row['carrier_id']))])
    index={e.record_id:e for e in chains.IndexedFDIFile.from_bytes(original).entries}
    ctx={'native_original':original,'native_index':index,'display_claims':{}}
    expected=delta.fit_display_names(original,delta.updated_package(package,proposal),proposal)[0]
    actual=chains.fitted(ctx,row['before'],row['replacement'])
    assert actual==expected
    actual['display_name']='Do not mutate cached proof'
    assert chains.fitted(ctx,row['before'],row['replacement'])==expected
