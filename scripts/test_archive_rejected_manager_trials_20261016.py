from pathlib import Path
import pytest
from scripts import archive_rejected_manager_trials_20261016 as subject


def setup(monkeypatch,tmp_path,decision,selected=None):
    monkeypatch.setattr(subject.current,'ROOT',tmp_path)
    monkeypatch.setattr(subject.registry,'supported_seasons',lambda:['2000-01','2002-03','2015-16'])
    if selected is not None:
        p=tmp_path/'2000-01';p.mkdir();(p/'selected-delivery.json').touch()
    def read(path):
        if path.name=='selected-delivery.json':return selected
        if path.parent.name=='2002-03':return dict(reuse_exact_existing_private_plan=True)
        return decision
    monkeypatch.setattr(subject.pipeline,'read_json_file',read)


def test_reused_safe_trial_and_legacy2015_are_never_cleanup_targets(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path,dict(reuse_exact_existing_private_plan=False,deferred=[1]))
    rows,skip=subject.targets()
    assert rows==[dict(season='2000-01',release_id=subject.prior.BASE)]
    assert skip==['2002-03']


def test_selected_old_candidate_cannot_be_deleted(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path,dict(reuse_exact_existing_private_plan=False,deferred=[1]),
        dict(release_id=subject.prior.RELEASE))
    with pytest.raises(ValueError,match='selected exact private coach'):subject.targets()


def test_no_explicit_rejection_means_no_retirement(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path,dict(reuse_exact_existing_private_plan=False,deferred=[]))
    with pytest.raises(ValueError,match='explicit rejected'):subject.targets()
