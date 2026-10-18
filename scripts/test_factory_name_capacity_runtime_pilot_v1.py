import pytest
from experiments import factory_name_capacity_runtime_pilot_v1 as pilot
from experiments import factory_name_window_recovery_probe_v1 as recovery
from scripts import season_package_compiler_v2 as compiler
from scripts.test_season_package_compiler_v2 import _dd6360_player_payload


def test_private_runtime_pilot_restores_same_carrier_capacity_without_changing_native_facts():
    factory=_dd6360_player_payload(2)
    current,_=recovery._patch_indexed_dd6360_variable_name(factory,recovery._stored_case_display(factory),'Q')
    target=recovery._stored_case_display(factory)
    restored,proof=pilot.patch_name(factory,current,target)
    assert restored==factory
    assert proof['native_fields_before']==proof['native_fields_after']
    assert proof['opaque_suffix_preserved'] and proof['semantic_readback_unchanged']
    assert proof['current_suffix_cursor']<proof['pilot_suffix_cursor']<=proof['factory_suffix_cursor']


def test_pilot_rejects_name_that_already_fits_and_proves_nothing_about_restored_capacity():
    factory=_dd6360_player_payload(2)
    current,_=recovery._patch_indexed_dd6360_variable_name(factory,recovery._stored_case_display(factory),'Q')
    with pytest.raises(ValueError,match='already fitting'):
        pilot.patch_name(factory,current,'Q')


def test_pilot_cannot_exceed_original_factory_window():
    factory=_dd6360_player_payload(2)
    current,_=recovery._patch_indexed_dd6360_variable_name(factory,recovery._stored_case_display(factory),'Q')
    with pytest.raises(RuntimeError,match='stable native string window'):
        pilot.patch_name(factory,current,'X'*250)


def test_pilot_never_restores_factory_secondary_facts_over_current_season_facts():
    factory=_dd6360_player_payload(2)
    current,_=recovery._patch_indexed_dd6360_variable_name(factory,recovery._stored_case_display(factory),'Q')
    current=bytearray(current);end=compiler._native_dd6360_role_start(current)
    current[end+16]=190^0x61;current[end+27]=3^0x61
    restored,proof=pilot.patch_name(factory,bytes(current),recovery._stored_case_display(factory))
    assert proof['native_fields_after']['height_cm']==190
    assert proof['native_fields_after']['handling']==3
    assert restored!=factory
