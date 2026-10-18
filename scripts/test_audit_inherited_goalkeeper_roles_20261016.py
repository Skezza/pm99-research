import copy
import pytest
from scripts.audit_inherited_goalkeeper_roles_20261016 import selected


def case():
    return [dict(name='Andrei Kanchelskis',facts=dict(primary_position='M',fine_roles={'policy':'preserve-existing-mode1'})),
        dict(name='Andrei KANCHELSKIS',position='M'),[0,98,98,98,98,98],
        dict(name='Lionel CHARBONNIER',position='G')]


def test_exact_inherited_donor_keeper_role_on_new_outfielder_is_selected():
    args=case();before=copy.deepcopy(args)
    assert selected(*args) and args==before


@pytest.mark.parametrize('change',['original-person','whole-record-fallback','declared-specialism',
    'native-class-mismatch','not-GK-donor','existing-outfield-versatility','unassigned','wrong-native-name'])
def test_ambiguous_and_already_sourced_roles_are_not_selected(change):
    args=case()
    if change=='original-person':args[3]['name']=args[0]['name']
    if change=='whole-record-fallback':args[0]['policy']='preserve-existing-mode1'
    if change=='declared-specialism':args[0]['facts']['fine_roles']=[0]
    if change=='native-class-mismatch':args[1]['position']='G'
    if change=='not-GK-donor':args[3]['position']='M'
    if change=='existing-outfield-versatility':args[2]=[0,9,98,98,98,98]
    if change=='unassigned':args[2]=[98]*6
    if change=='wrong-native-name':args[1]['name']='Another Player'
    assert not selected(*args)
