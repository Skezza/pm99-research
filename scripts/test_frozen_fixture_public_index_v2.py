from pathlib import Path
import pytest
from scripts import season_frozen_fixture_reserve_v1 as original
from scripts import season_frozen_fixture_reserve_v2 as subject


def test_v2_has_distinct_input_and_plan_policies_so_v1_plans_are_not_reinterpreted():
    assert subject.SCHEMA!=original.SCHEMA
    assert subject.INPUT_SCHEMA!=original.INPUT_SCHEMA
    with pytest.raises(ValueError,match='did not independently reproduce'):
        subject.verify_plan(None,dict(schema_version=original.SCHEMA))


def test_public_index_requires_the_bound_original_response_replayer(monkeypatch,tmp_path):
    seed={'original':{1:dict(name='Original Actor')}};events={};snapshot={'pin':'original'}
    monkeypatch.setattr(subject.registry,'ROOT',tmp_path)
    calls=[]
    monkeypatch.setattr(subject.context,'load_snapshot',lambda db,pin:(seed,events,snapshot))
    binding=dict(path='published-person-identities-r2.json',sha256='original-bound-digest',policy=subject.published_people.POLICY)
    monkeypatch.setattr(subject.public,'binding',lambda path,policy: calls.append((path,policy)) or binding)
    merged={'original-and-replayed':{2:dict(name='Retired Actor')}};report={'accepted':2}
    def replay(index,history,inputs):
        assert index is seed and history is events
        assert inputs==dict(published_person_supplement=binding)
        return merged,events,report
    monkeypatch.setattr(subject.public,'merge_bound',replay)
    actual,pin,inputs,replayed=subject.load_identity_index(Path('database'),Path('pin'))
    assert actual is merged and pin is snapshot and replayed is report
    assert inputs==dict(published_person_supplement=binding)
    assert calls==[(tmp_path/'.local/duplicate-ownership-v3/published-person-identities-r2.json',subject.published_people.POLICY)]


def test_failed_original_replay_is_not_silently_replaced_by_saved_derived_identities(monkeypatch):
    monkeypatch.setattr(subject.context,'load_snapshot',lambda *args:({}, {}, {}))
    monkeypatch.setattr(subject.public,'binding',lambda *args:dict(policy='bound'))
    def reject(*args):raise ValueError('original response hash changed')
    monkeypatch.setattr(subject.public,'merge_bound',reject)
    with pytest.raises(ValueError,match='original response hash changed'):
        subject.load_identity_index(Path('database'),Path('pin'))


def test_native_identity_and_retirement_guards_are_unchanged_from_v1():
    import inspect
    for name in ('heading_name','identity','guard_pair','retired_member_proof'):
        assert inspect.getsource(getattr(subject,name))==inspect.getsource(getattr(original,name))
