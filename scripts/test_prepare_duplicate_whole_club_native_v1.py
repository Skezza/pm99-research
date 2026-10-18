import copy
import pytest
from scripts import prepare_duplicate_whole_club_native_v1 as mod
from scripts.test_season_package_compiler_v2 import (
    _indexed_fdi,_synthetic_mode1_eq_decoded_payload,_synthetic_eq_decoded_payload,
)


def native_roster(mode=1,excluded=False):
    decoded=(_synthetic_mode1_eq_decoded_payload() if mode==1 else _synthetic_eq_decoded_payload())
    raw=bytearray(mod.delta.compiler.xor_encode(decoded))
    parsed=mod.parse_eq_external_team_roster_payload(raw,{})
    for row in parsed.rows:raw[row.raw_row_offset]=0
    if excluded:raw[parsed.rows[3].raw_row_offset]=1
    data=_indexed_fdi([(100,'club',mod.delta.compiler.xor_decode(raw)),
                       (200,'other',mod.delta.compiler.xor_decode(raw))])
    return data,bytes(raw)


def test_order_rewrite_preserves_all_opaque_bytes_other_records_and_fixed_carriers():
    data,raw=native_roster();ordered=list(range(16,0,-1))
    result=mod.rewrite_roster(data,100,ordered)
    index=mod.IndexedFDIFile.from_bytes(result)
    selected=next(e for e in index.entries if e.record_id==100)
    next_raw=result[selected.payload_offset:selected.payload_offset+selected.payload_length]
    parsed=mod.parse_eq_external_team_roster_payload(next_raw,{})
    assert [r.player_record_id for r in parsed.rows]==ordered
    assert all(r.flag==0 for r in parsed.rows)
    first=parsed.rows[0].raw_row_offset
    assert next_raw[:first]==raw[:first]
    old=mod.IndexedFDIFile.from_bytes(data)
    other=next(e for e in old.entries if e.record_id==200)
    other_after=next(e for e in index.entries if e.record_id==200)
    assert other.decode_payload(data)==other_after.decode_payload(result)
    assert mod.rewrite_roster(result,100,ordered)==result


@pytest.mark.parametrize('bad_order',[list(range(1,16)),list(range(1,17))+[17],list(range(2,18)),[1]*16])
def test_fixed_capacity_and_carrier_set_cannot_be_changed(bad_order):
    data,_=native_roster()
    with pytest.raises(ValueError,match='exact fixed carrier set'):mod.rewrite_roster(data,100,bad_order)


def test_native_availability_is_not_silently_cleared_or_moved():
    data,_=native_roster(excluded=True)
    with pytest.raises(ValueError,match='availability flags'):mod.rewrite_roster(data,100,list(range(16,0,-1)))


def test_playable_team_cannot_use_nonplayable_whole_club_route():
    data,_=native_roster(mode=0)
    with pytest.raises(ValueError,match='non-playable mode1'):mod.rewrite_roster(data,100,list(range(16,0,-1)))


def proposal_fixture():
    players=[{'id':f'p{i}','carrier_id':i,'club_id':'club'} for i in range(1,19)]
    club={'id':'club','name':'Old','carrier_id':3323,'roster_player_ids':[p['id'] for p in players]}
    desired=[{'source_person':{'source_player_id':i+100,'name':f'Player {i}'},
        'source_player':{'name':f'Player {i}','position':'G' if i in (1,12) else 'D'},
        'membership':'starting_xi' if i<=11 else 'published_bench' if i<=16 else 'positive-annual-and-dated-opening-reserve'}
        for i in range(1,19)]
    allocation=[{'player_id':p['id'],'carrier_id':p['carrier_id'],'before_recipe':copy.deepcopy(p),
        'replacement':copy.deepcopy(r),'display':{'source_name':r['source_player']['name']}}
        for p,r in zip(players,desired)]
    return {'clubs':[club],'players':players},{'before_club':copy.deepcopy(club),'desired_people':desired,'allocation':allocation}


def test_complete_allocation_validation_is_readonly():
    package,proposal=proposal_fixture();before=copy.deepcopy((package,proposal))
    club,slots=mod.validate_allocation(package,proposal)
    assert len(slots)==18 and club['id']=='club'
    assert (package,proposal)==before


@pytest.mark.parametrize('corruption',['missing','duplicate-carrier','other-person','stale-slot','other-club','two-keepers'])
def test_full_club_transaction_rejects_incomplete_or_changed_source(corruption):
    package,proposal=proposal_fixture()
    if corruption=='missing':proposal['allocation'].pop()
    if corruption=='duplicate-carrier':proposal['allocation'][1]['carrier_id']=1
    if corruption=='other-person':proposal['allocation'][0]['replacement']['source_person']['source_player_id']=999
    if corruption=='stale-slot':proposal['allocation'][0]['before_recipe']['id']='wrong'
    if corruption=='other-club':package['players'][0]['club_id']='other'
    if corruption=='two-keepers':
        proposal['desired_people'][1]['source_player']['position']='G'
        proposal['allocation'][1]['replacement']=copy.deepcopy(proposal['desired_people'][1])
    with pytest.raises(ValueError):mod.validate_allocation(package,proposal)


def test_changed_raw_source_is_refused_before_it_can_be_used(tmp_path,monkeypatch):
    monkeypatch.setattr(mod.registry,'ROOT',tmp_path)
    path=tmp_path/'original.html';path.write_bytes(b'altered')
    with pytest.raises(ValueError,match='source binding changed'):
        mod.original({'path':'original.html','sha256':'a'*64})


def test_all_unselected_native_records_must_remain_byte_identical():
    before=_indexed_fdi([(1,'a',b'unchanged'),(2,'b',b'old')])
    good=_indexed_fdi([(1,'a',b'unchanged'),(2,'b',b'new')])
    mod.preserve_other_records(before,good,{2})
    with pytest.raises(ValueError,match='unrelated native record'):
        mod.preserve_other_records(before,_indexed_fdi([(1,'a',b'wrong'),(2,'b',b'new')]),{2})
    with pytest.raises(ValueError,match='fixed native carrier directory'):
        mod.preserve_other_records(before,_indexed_fdi([(1,'a',b'unchanged'),(3,'b',b'new')]),{2})


def test_real_package_composition_keeps_mode1_contract_and_places_actual_XI_in_source_artifact():
    from scripts.test_season_package_compiler_v2 import _native_package
    package=_native_package();club=package['clubs'][0]
    club['division']='preserve-existing-mode1-membership'
    club['opening']={'policy':'preserve-existing-mode1','proof':copy.deepcopy(club['proof'])}
    desired=[];allocation=[]
    for i,p in enumerate(package['players']):
        replacement={'source_person':{'source_player_id':i+100,'name':f'Genuine Player{i}',
            'birth_date':f'1990-01-{i+1:02d}'},'source_player':{'name':f'Genuine Player{i}',
            'birth_date':f'1990-01-{i+1:02d}','position':'G' if i in (0,11) else 'D',
            'nationality':'ENG','height_cm':180,'weight_kg':75},
            'membership':'starting_xi' if i<11 else 'published_bench'}
        desired.append(replacement)
        allocation.append({'player_id':p['id'],'carrier_id':p['carrier_id'],'before_recipe':copy.deepcopy(p),
            'replacement':copy.deepcopy(replacement),'display':{'source_name':replacement['source_player']['name'],
            'display_name':f'Player{i}'}})
    proposal={'season':'2015-16','before_club':copy.deepcopy(club),'new_club':'Real New Club',
        'desired_people':desired,'allocation':allocation,'original_opening':{'fixture':{'date':'2015-08-08'}}}
    before=copy.deepcopy(package)
    result,composition=mod.compile_recipe(package,proposal)
    assert package==before
    assert result['clubs'][0]['opening']==before['clubs'][0]['opening']
    assert result['clubs'][0]['roster_player_ids']==[r['player_id'] for r in allocation]
    assert result['clubs'][0]['name']=='Real New Club'
    assert composition['whole_club_original_source']==proposal
    assert [p['name'] for p in result['players']]==[f'Player{i}' for i in range(16)]
    assert result['assets']['kits']==before['assets']['kits']
    assert result['managers']==before['managers']
    assert result==mod.compile_recipe(package,proposal)[0]
