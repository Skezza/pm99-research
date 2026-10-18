"""Adversarial publication ordering/counter tests; native writers tested separately."""
from pathlib import Path
import pytest
from scripts import checkpoint_remaining_donor_roles_20261016 as subject


def fixture(tmp_path,monkeypatch):
    root=tmp_path/'batch';root.mkdir()
    monkeypatch.setattr(subject,'ROOT',root)
    seasons=['2000-01']+[f'{y}-{str(y+1)[-2:]}' for y in range(2001,2026)]
    monkeypatch.setattr(subject.registry,'supported_seasons',lambda:seasons)
    previous=dict(current_release_bindings=[dict(season=s,release_id='old',manifest_sha256='sha') for s in seasons])
    def read(path):
        if Path(path).name=='release-delivery-checklist-v47.json':return previous
        if Path(path).name=='final-delivery-summary.json':return dict(native_role_records_changed=664)
        raise AssertionError('unexpected read before whole-batch prevalidation: '+str(path))
    monkeypatch.setattr(subject.pipeline,'read_json_file',read)
    checked=[];writes=[]
    def verify(s):
        checked.append(s)
        return dict(season=s,native_role_changes=0)
    monkeypatch.setattr(subject,'verify',verify)
    monkeypatch.setattr(subject.publisher,'register_completed_delta',lambda *args:writes.append(args))
    return seasons,checked,writes


def test_one_failed_late_season_prevents_all_publication(tmp_path,monkeypatch):
    seasons,checked,writes=fixture(tmp_path,monkeypatch)
    def verify(s):
        checked.append(s)
        if s==seasons[-1]:raise ValueError('unverified last original runner image')
        return dict(season=s,native_role_changes=1)
    monkeypatch.setattr(subject,'verify',verify)
    with pytest.raises(ValueError,match='last original'):
        subject.run()
    assert checked==seasons[1:]
    assert writes==[]


def test_frozen_denominator_failure_prevents_all_publication(tmp_path,monkeypatch):
    seasons,checked,writes=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='denominator'):
        subject.run()
    assert checked==seasons[1:]
    assert writes==[]


def test_wrong_season_scope_prevents_any_verification_or_publication(tmp_path,monkeypatch):
    seasons,checked,writes=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(subject.registry,'supported_seasons',lambda:seasons[:-1])
    with pytest.raises(ValueError,match='exact25'):
        subject.run()
    assert checked==writes==[]


def test_completed_checkpoint_cannot_publish_twice(tmp_path,monkeypatch):
    seasons,checked,writes=fixture(tmp_path,monkeypatch)
    (tmp_path/'release-delivery-checklist-v48.json').touch()
    with pytest.raises(ValueError,match='must not repeat'):
        subject.run()
    assert checked==writes==[]
