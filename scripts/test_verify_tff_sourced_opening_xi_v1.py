"""Adversarial synthetic tests without proprietary game data."""
import pytest
from scripts import verify_tff_sourced_opening_xi_v1 as v
from scripts.test_season_package_compiler_v2 import _indexed_fdi, _dd6361_player_payload


def fixture():
    old, new = {}, {}
    for carrier in range(1,20):
        payload = bytearray(_dd6361_player_payload(carrier))
        payload[2:5] = b'\xdd\x63\x60'
        end = v.audit.native_player(bytes(payload),carrier)['name_end']
        payload[end] = carrier ^ 0x61
        payload[end+11] = (0 if carrier==1 else 1)^0x61
        old[carrier] = bytes(payload)
        new[carrier] = bytearray(payload)
    target = new[2]; end = v.audit.native_player(bytes(target),2)['name_end']
    target[end+2:end+8] = bytes(n^0x61 for n in (5,0,0,0,0,0))
    target[end+8] = 7^0x61
    target[end+12:end+18] = bytes(n^0x61 for n in (17,11,1978&255,1978>>8,183,78))
    ratings = {field:50+i for i,field in enumerate(v.SKILLS)}
    ratings['handling']=10
    for i,field in enumerate(v.SKILLS):target[end+18+i]=ratings[field]^0x61
    target[end+27]=10^0x61;target[-7]=10^0x61
    player={'carrier_id':2,'name':v.audit.native_player(bytes(target),2)['name'],
            'facts':{'birth_date':'1978-11-17','height_cm':183,'weight_kg':78,'nationality':'BRA'},'ratings':{'values':ratings}}
    plan={'orders':[{'carrier_id':i,'before':i,'after':i} for i in range(1,19)],
          'starting_xi':[{'carrier_id':i} for i in range(1,12)],
          'replacements':[{'carrier_id':2,'kind':'wrong-person-facts'}]}
    return old,new,{'players':[player]},plan,{'BRAZIL':7}


def packed(rows):return _indexed_fdi([(i,'',bytes(p)) for i,p in rows.items()])


def test_independent_loader_readback_and_scope():
    old,new,package,plan,countries=fixture()
    result=v.verify_players(packed(old),packed(new),package,plan,countries)
    assert result['changed_player_records']==[2]
    assert result['first_XI_positions']==['G']+['D']*10


@pytest.mark.parametrize('problem',['other-player','other-name','opaque','shirt','birthday','role','skill','handling','order','two-keepers','missing-carrier'])
def test_a_source_repair_cannot_hide_other_changes(problem):
    old,new,package,plan,countries=fixture()
    carrier=2
    if problem=='other-player':carrier=19
    if problem=='other-name':carrier=3
    end=v.audit.native_player(bytes(new[carrier]),carrier)['name_end']
    offset={'other-player':end+18,'other-name':end-1,'opaque':end+9,'shirt':7,
            'birthday':end+12,'role':end+2,'skill':end+18,'handling':len(new[carrier])-7,
            'order':end,'two-keepers':end+11}.get(problem)
    if problem=='missing-carrier':new.pop(19)
    elif problem=='two-keepers':new[carrier][offset]=0^0x61
    else:new[carrier][offset]^=1
    with pytest.raises(ValueError):v.verify_players(packed(old),packed(new),package,plan,countries)
