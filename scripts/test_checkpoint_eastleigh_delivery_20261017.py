import copy
import pytest
from scripts import checkpoint_eastleigh_delivery_20261017 as subject


def fixtures():
    previous=dict(remaining_cross_club_cases=2797,cross_club_dispositions=[dict(case_id='already-closed')])
    cases=dict(manifest_sha256='actual',confirmed_frozen_cases_repaired=1,
        Tom_Aldred_other_two_club_copies_still_open=True,
        dispositions=[dict(case_id='new-case',source_person_id=223790,retained_native_carrier=9574,replaced_native_carrier=11157)])
    return previous,cases


def test_accepts_only_one_new_exact_frozen_keeper_pair():
    previous,cases=fixtures();original=copy.deepcopy((previous,cases))
    subject.validate_case_count(previous,cases,'actual')
    assert (previous,cases)==original


@pytest.mark.parametrize('fault',['counter','duplicate','already-closed','manifest','wrong-person','wrong-retained','wrong-replaced','Aldred-claimed-closed'])
def test_rejects_counter_reset_or_unproved_case_closure(fault):
    previous,cases=fixtures();row=cases['dispositions'][0]
    if fault=='counter':previous['remaining_cross_club_cases']=2809
    elif fault=='duplicate':cases['dispositions']*=2
    elif fault=='already-closed':row['case_id']='already-closed'
    elif fault=='manifest':cases['manifest_sha256']='another-game'
    elif fault=='wrong-person':row['source_person_id']=95076
    elif fault=='wrong-retained':row['retained_native_carrier']=9580
    elif fault=='wrong-replaced':row['replaced_native_carrier']=11160
    elif fault=='Aldred-claimed-closed':cases['Tom_Aldred_other_two_club_copies_still_open']=False
    with pytest.raises(ValueError,match='exact frozen one-case'):subject.validate_case_count(previous,cases,'actual')


def test_native_json_tuple_array_representation_does_not_hide_or_invent_a_difference():
    actual=dict(players=[dict(carrier_id=i) for i in range(17)],XI=[(1,11157,'Flitney','G')])
    saved=dict(players=copy.deepcopy(actual['players']),XI=[[1,11157,'Flitney','G']])
    subject.validate_native_readback(actual,saved)
    saved['XI'][0][2]='Another keeper'
    with pytest.raises(ValueError,match='native readback differs'):subject.validate_native_readback(actual,saved)


def test_native_proof_still_requires_all17_players():
    actual=dict(players=[dict(carrier_id=i) for i in range(16)])
    with pytest.raises(ValueError,match='native readback differs'):subject.validate_native_readback(actual,copy.deepcopy(actual))
