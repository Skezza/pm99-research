import copy
import pytest
from scripts import checkpoint_frozen_fixture_reserve_v1 as subject


def fixture():
    return dict(work_items=[dict(id='roster-duplicates',frozen_baseline=dict(cross_club_groups=2809))],
        cross_club_dispositions=[dict(case_id='closed'+str(i)) for i in range(13)],remaining_cross_club_cases=2796)


def test_counter_is_derived_from_the_original_denominator_and_unique_dispositions():
    previous=fixture();original=copy.deepcopy(previous)
    assert subject.next_count(previous,[dict(case_id='new')])==2795
    assert subject.next_count(previous,[dict(case_id='new'),dict(case_id='another')])==2794
    assert previous==original


@pytest.mark.parametrize('fault',['changed-counter','duplicate-new','repeated-closed','already-closed','empty'])
def test_rejects_resets_or_double_counting(fault):
    previous=fixture();proofs=[dict(case_id='new')]
    if fault=='changed-counter':previous['remaining_cross_club_cases']=2809
    elif fault=='duplicate-new':proofs*=2
    elif fault=='repeated-closed':previous['cross_club_dispositions'].append(dict(case_id='closed1'))
    elif fault=='already-closed':proofs=[dict(case_id='closed1')]
    elif fault=='empty':proofs=[]
    with pytest.raises(ValueError,match='fixed frozen counter'):subject.next_count(previous,proofs)
