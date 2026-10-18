import copy
import hashlib
import json
import pytest

from scripts import season_whole_club_keeper_exchange_v1 as module
from scripts import season_pipeline_v2 as pipeline
from scripts.test_prepare_duplicate_club_disposition_v1 import exchange_allocation


def fixture(tmp_path):
    from scripts.prepare_duplicate_club_disposition_v1 import keeper_exchange
    allocation=exchange_allocation()
    for r in allocation:
        n=r['native_startup_order_before'];r['player_id']=f'player-{n}'
        r['replacement']['source_player'].update(name=f'Real Person {n}',birth_date='1990-01-01')
        r['replacement']['source_person']={'source_player_id':1000+n}
    exchange=keeper_exchange(allocation);after={r['carrier_id']:r['after'] for r in exchange}
    for r in allocation:r['native_startup_order_after']=after.get(r['carrier_id'],r['native_startup_order_before'])
    source={'schema_version':'pm99-whole-club-collision-diagnostic-only-v1','collision_inspection_only':True,
        'allow_keeper_order_exchange':True,'native_opening_slot_policy':
        'complete-sourced-XI-with-bounded-owned-mode1-reciprocal-keeper-order-exchange-v1',
        'season':'2021-22','before_club':{'id':'club','carrier_id':3323},'new_club':'Weymouth',
        'desired_people':[r['replacement'] for r in allocation],'allocation':allocation,'startup_order_exchange':exchange}
    path=tmp_path/'source.json';pipeline.write_canonical_json(path,{'whole_club_original_source':source})
    identity='duplicate-ownership-plan-2021-22-proof'
    club={'id':'club','carrier_id':3323,'name':'Weymouth','roster_player_ids':[r['player_id'] for r in allocation],
        'proof':{'artifact_id':identity}}
    package={'season':{'start_year':2021,'end_year':2022},'clubs':[club],
        'players':[{'id':r['player_id'],'carrier_id':r['carrier_id'],'club_id':'club',
            'name':r['display']['display_name'],'source_name':r['replacement']['source_player']['name'],
            'facts':{'birth_date':'1990-01-01','primary_position':r['replacement']['source_player']['position']}}
            for r in allocation],
        'artifacts':[{'id':identity,'relative_path':'source.json','sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]}
    return package,club,source


def test_complete_explicit_source_drives_replay_and_inputs_remain_unchanged(tmp_path,monkeypatch):
    package,club,source=fixture(tmp_path);before=copy.deepcopy(package);calls=[]
    def patch(jug,eq,rows):
        calls.append(rows)
        assert jug==b'JUG' and eq==b'EQ' and [(r.before,r.after) for r in rows]==[(1,7),(7,1)]
        return b'NEW'
    monkeypatch.setattr(module,'patch_owned_mode1_keeper_exchange',patch)
    monkeypatch.setattr(module,'bound_native_replacements',lambda jug,rows:[
        module.OrderReplacement(r['carrier_id'],r['expected_name'],r['before'],r['after']) for r in rows])
    output,changes=module.replay(b'JUG',b'EQ',package,tmp_path/'package.json')
    assert output==b'NEW' and len(changes)==len(calls)==1 and package==before


@pytest.mark.parametrize('problem',['wrong-season','wrong-club','missing-slot','duplicate-carrier',
    'wrong-DOB','wrong-position','changed-name','changed-order','invented-exchange','singleton'])
def test_stale_recipe_or_relaxed_source_refuses(problem,tmp_path):
    package,club,source=fixture(tmp_path)
    if problem=='wrong-season':source['season']='2020-21'
    if problem=='wrong-club':club['carrier_id']=3329
    if problem=='missing-slot':club['roster_player_ids'].pop()
    if problem=='duplicate-carrier':source['allocation'][-1]['carrier_id']=101
    if problem=='wrong-DOB':package['players'][0]['facts']['birth_date']='1991-01-01'
    if problem=='wrong-position':package['players'][0]['facts']['primary_position']='F'
    if problem=='changed-name':package['players'][0]['source_name']='Someone Else'
    if problem=='changed-order':source['allocation'][-1]['native_startup_order_after']=11
    if problem=='invented-exchange':source['startup_order_exchange'][0]['after']=2
    if problem=='singleton':source['schema_version']='singleton'
    with pytest.raises(ValueError):module.validate_scope(package,club,source)


@pytest.mark.parametrize('problem',['hash','path','missing-artifact'])
def test_unbound_source_cannot_activate_replay(problem,tmp_path):
    package,club,source=fixture(tmp_path)
    if problem=='hash':package['artifacts'][0]['sha256']='0'*64
    if problem=='path':package['artifacts'][0]['relative_path']='../unowned.json'
    if problem=='missing-artifact':package['artifacts']=[]
    with pytest.raises(ValueError):module.replay(b'JUG',b'EQ',package,tmp_path/'package.json')


def test_native_uppercase_surname_is_bound_without_accepting_another_identity():
    from scripts.test_season_package_compiler_v2 import _indexed_fdi,_dd6361_player_payload
    from app.player_initial_order import read_initial_order
    data=_indexed_fdi([(2,'',_dd6361_player_payload(2))])
    entry=module.IndexedFDIFile.from_bytes(data).entries[0]
    actual=read_initial_order(entry.decode_payload(data)).name
    row={'carrier_id':2,'expected_name':actual.lower(),'before':2,'after':1}
    assert module.bound_native_replacements(data,[row])[0].expected_name==actual
    row['expected_name']='A Different Player'
    with pytest.raises(ValueError,match='native name differs'):module.bound_native_replacements(data,[row])
