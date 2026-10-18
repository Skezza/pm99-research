import copy
from types import SimpleNamespace

import pytest
from scripts import checkpoint_arsenal_owned_delivery_20261016 as subject


def counts():
    return (dict(remaining_cross_club_cases=2808,cross_club_dispositions=[dict(case_id='old')]),
        dict(dispositions=[dict(case_id=str(i)) for i in range(11)],manifest_sha256='actual',
            confirmed_frozen_cases_repaired=11))


def test_exact_eleven_new_frozen_cases_can_close():
    previous,cases=counts();subject.validate_case_count(previous,cases,'actual')


@pytest.mark.parametrize('fault',['old-counter','duplicate-row','already-closed','wrong-manifest','wrong-source-count'])
def test_counters_cannot_shrink_from_disappearance_or_double_counting(fault):
    previous,cases=counts()
    if fault=='old-counter':previous['remaining_cross_club_cases']=2807
    elif fault=='duplicate-row':cases['dispositions'].append(dict(cases['dispositions'][0]))
    elif fault=='already-closed':previous['cross_club_dispositions'].append(dict(cases['dispositions'][0]))
    elif fault=='wrong-manifest':cases['manifest_sha256']='other'
    else:cases['confirmed_frozen_cases_repaired']=12
    with pytest.raises(ValueError,match='reset/double-counted'):subject.validate_case_count(previous,cases,'actual')


@pytest.mark.parametrize('fault',['unselected','parent-manifest','unexpected-release','child-manifest'])
def test_preferred_transition_preserves_other25_and_exact_parent(monkeypatch,fault):
    parent=dict(season=subject.SEASON,release_id=subject.BASE,manifest_sha256='parent')
    other=dict(season='2000-01',release_id='existing',manifest_sha256='other')
    previous=dict(current_release_bindings=[parent,other]);current=copy.deepcopy([parent,other])
    if fault=='unselected':current[1]['manifest_sha256']='changed'
    elif fault=='parent-manifest':current[0]['manifest_sha256']='changed'
    elif fault=='unexpected-release':current[0]['release_id']='unexpected'
    else:current[0].update(release_id=subject.RELEASE,manifest_sha256='wrong-child')
    monkeypatch.setattr(subject,'bindings',lambda:current)
    with pytest.raises(ValueError):subject.checked_bindings(previous,SimpleNamespace(manifest_sha256='child'))
