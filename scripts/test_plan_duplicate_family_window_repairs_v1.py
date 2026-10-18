import pytest
from scripts import plan_duplicate_family_window_repairs_v1 as plan


def replacement(provider=None):
    person={'name':'Full Name','birth_date':'1995-01-02','source_player_id':99}
    if provider:person['source_provider']=provider
    return {'source_person':person,'source_player':{'name':'Full Name'}}


@pytest.mark.parametrize('problem',[None,'used-id','used-identity','unbridged-name','same-DOB-provider'])
def test_new_name_policy_never_bypasses_existing_identity_and_provider_protection(problem):
    row=replacement('soccerbase' if problem=='same-DOB-provider' else None)
    ids={99} if problem=='used-id' else set()
    identities={(plan.roster.normalise('Full Name'),'1995-01-02')} if problem=='used-identity' else set()
    dates={'1995-01-02'} if problem=='same-DOB-provider' else set()
    names={plan.roster.normalise('Full Name')} if problem=='unbridged-name' else set()
    assert plan.unused(row,ids,identities,dates,names,True)==(problem is None)


def test_no_name_window_cohort_requires_no_game_or_source_work(monkeypatch):
    monkeypatch.setattr(plan.registry,'load_preferred_release',lambda s:pytest.fail('unrelated game read'))
    assert not plan.native_feasible({'unresolved':[]},{})
