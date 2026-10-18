import pytest
from experiments import roster_flag_runtime_pilot_v1 as pilot
from scripts.test_season_package_compiler_v2 import _indexed_fdi,_synthetic_eq_decoded_payload


def fixture():
    original=_indexed_fdi([(351,'',_synthetic_eq_decoded_payload())])
    e=pilot.IndexedFDIFile.from_bytes(original).entries[0]
    raw=original[e.payload_offset:e.payload_offset+e.payload_length]
    roster=pilot.parse_eq_external_team_roster_payload(raw,{})
    first=roster.rows[0];result=bytearray(original)
    result[e.payload_offset+first.raw_row_offset]=1
    return bytes(result),first.player_record_id,e.payload_offset+first.raw_row_offset


def test_private_roster_control_changes_only_exact_flag_byte():
    original,id,offset=fixture();changed,proof=pilot.patch_flags(original,351,[id])
    assert proof['changed_offsets']==[offset]
    assert original[:offset]==changed[:offset] and original[offset+1:]==changed[offset+1:]
    assert original[offset]==1 and changed[offset]==0
    assert proof['membership_and_order_unchanged']


@pytest.mark.parametrize('problem',['duplicate','missing','wrong-carrier','already-zero'])
def test_private_roster_control_refuses_guesses_or_ambiguous_targets(problem):
    original,id,offset=fixture();players=[id];carrier=351
    if problem=='duplicate':players=[id,id]
    if problem=='missing':players=[999999]
    if problem=='wrong-carrier':carrier=352
    if problem=='already-zero':original=original[:offset]+b'\0'+original[offset+1:]
    with pytest.raises(ValueError):pilot.patch_flags(original,carrier,players)
