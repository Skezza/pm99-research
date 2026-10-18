import pytest

from scripts import review_factory_duplicate_name_capacity_v1 as review


def test_capacity_review_uses_native_safe_family_form_not_bare_particle_surname(monkeypatch):
    claim={'components':[{'name':'di Giacomo'}]}
    person={'source_player_id':99,'birth_date':'1995-05-09'}
    monkeypatch.setattr(review.family,'native_candidates',lambda c,p:[
        {'field':'full-family-from-original-shortName','name':'P. di Giacomo'}])
    monkeypatch.setattr(review.family,'verify',lambda *a:pytest.fail('bare family is not native-safe'))
    monkeypatch.setattr(review,'_stored_case_display',lambda p:'Factory Person')
    attempted=[]
    monkeypatch.setattr(review,'_patch_indexed_dd6360_variable_name',
        lambda raw,old,new:attempted.append(new))
    result=review.fitting_native_names(b'candidate',claim,person)
    assert attempted==['P. di Giacomo']
    assert result==[{'source_person_id':99,'display_name':'P. di Giacomo','original_family_claim':claim}]


def test_capacity_refusal_is_not_replaced_with_a_shortened_surname(monkeypatch):
    monkeypatch.setattr(review.family,'native_candidates',lambda *a:[{'name':'R. van der Sar'}])
    monkeypatch.setattr(review,'_stored_case_display',lambda p:'Factory Person')
    def refuse(*args):raise ValueError('native window too small')
    monkeypatch.setattr(review,'_patch_indexed_dd6360_variable_name',refuse)
    assert review.fitting_native_names(b'candidate',{}, {'source_player_id':99})==[]
