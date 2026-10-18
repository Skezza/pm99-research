import copy
import pytest
from scripts import season_common_date_ownership_v1 as checker
from scripts import season_soccerbase_duplicate_source_policy_v1 as source
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_public_identity_and_history_inputs_v1 as public
from scripts.test_season_common_date_ownership_v1 import supplemented_claim


def bound_plan(tmp_path,monkeypatch):
    plan=supplemented_claim(tmp_path,monkeypatch)
    plan['bindings'].update(published_person_supplement={'path':'original-public-people'},
        published_transfer_supplement={'path':'original-transfers'},
        soccerbase_opening_sources={'policy':source.POLICY,'person_policy':source.PERSON_POLICY})
    monkeypatch.setattr(public,'merge_bound',lambda people,events,bindings:(people,events,{}))
    monkeypatch.setattr(source,'bound_people',lambda people,bindings:(people,{}))
    monkeypatch.setattr(source,'attach',lambda bindings,season,clubs,captures,people,events,existing,**kwargs:(existing,[]))
    row=plan['updates'][0];row['carrier_id']=2
    monkeypatch.setattr(source,'native_starters',lambda release,club,native:({100,101},native))
    return plan


def test_explicit_original_source_opt_in_keeps_existing_claim_replay(tmp_path,monkeypatch):
    checker.verify_plan_claims(None,bound_plan(tmp_path,monkeypatch))


def test_real_native_starting_slot_is_protected_even_without_recipe_xi(tmp_path,monkeypatch):
    plan=bound_plan(tmp_path,monkeypatch)
    monkeypatch.setattr(source,'native_starters',lambda *args:({2,101},None))
    with pytest.raises(ValueError,match='actual native opening starter'):checker.verify_plan_claims(None,plan)


def test_changed_original_source_reconstruction_invalidates_saved_ownership_claim(tmp_path,monkeypatch):
    plan=bound_plan(tmp_path,monkeypatch)
    def changed(bindings,season,clubs,captures,people,events,existing,**kwargs):
        evidence=copy.deepcopy(existing);evidence['displaced']['date']='2005-08-14'
        return evidence,[]
    monkeypatch.setattr(source,'attach',changed)
    with pytest.raises(ValueError):checker.verify_plan_claims(None,plan)


def test_missing_explicit_identity_policy_cannot_activate_source_route(tmp_path,monkeypatch):
    plan=bound_plan(tmp_path,monkeypatch)
    del plan['bindings']['soccerbase_opening_sources']['person_policy']
    with pytest.raises(ValueError,match='explicit bound'):checker.verify_plan_claims(None,plan)
