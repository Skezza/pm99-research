import pytest
from experiments import factory_name_window_recovery_probe_v1 as probe
from scripts import season_package_compiler_v2 as compiler
from scripts.test_season_package_compiler_v2 import _dd6360_player_payload


def shortened():
    factory=_dd6360_player_payload(2)
    name=compiler._player_name(factory,record_id=2)
    current,_=probe._patch_indexed_dd6360_variable_name(factory,name,'Q')
    return factory,current


def test_recovery_is_exact_reversible_fixed_carrier_but_not_publication_approval():
    factory,current=shortened()
    recovered,claim=probe.recover_candidate(factory,current)
    assert recovered==factory and claim['recovered_name_bytes']>0
    assert claim['exact_shrink_roundtrip'] and claim['semantic_readback_unchanged']
    assert not claim['runtime_verified'] and not claim['publication_authorised']


def test_existing_semantic_changes_not_replaced_with_factory_player_fields():
    factory,current=shortened();current=bytearray(current)
    end=compiler._native_dd6360_role_start(current)
    current[end+8]=30^0x61
    current[end+12]=15^0x61
    current[end+16]=190^0x61
    current[end+17]=90^0x61
    current=bytes(current);recovered,claim=probe.recover_candidate(factory,current)
    assert compiler._read_native_dd6360_fields(recovered,claim['original_suffix_cursor'])==compiler._read_native_dd6360_fields(current,end)
    assert recovered!=factory


def test_title_case_surname_storage_survives_roundtrip_despite_uppercase_display():
    factory=_dd6360_player_payload(2)
    current,_=probe._patch_indexed_dd6360_variable_name(factory,
        compiler._player_name(factory,record_id=2),'Joe Ab')
    recovered,claim=probe.recover_candidate(factory,current)
    roundtrip,_=probe._patch_indexed_dd6360_variable_name(recovered,
        probe._stored_case_display(factory),'Joe Ab')
    assert roundtrip==current and claim['semantic_readback_unchanged']


@pytest.mark.parametrize('problem',['family','prefix','length','tail','no-gain'])
def test_no_unknown_field_loss_other_person_layout_or_unproven_growth(problem):
    factory,current=shortened()
    if problem=='family':factory=factory[:2]+b'\xdd\x63\x61'+factory[5:]
    if problem=='prefix':factory=bytes([factory[0]^1])+factory[1:]
    if problem=='length':factory+=b'\x61'
    if problem=='tail':current=current[:-1]+b'\x62'
    if problem=='no-gain':factory=current
    with pytest.raises(ValueError):probe.recover_candidate(factory,current)
