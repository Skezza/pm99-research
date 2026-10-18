from types import SimpleNamespace
import pytest
from scripts import checkpoint_shtanyuk_alias_delivery_20261016 as subject


def fixture(tmp_path,monkeypatch):
    root=tmp_path/'batch';root.mkdir();monkeypatch.setattr(subject.batch,'ROOT',root)
    previous=dict(current_release_bindings=[dict(season=s,release_id='parent',manifest_sha256='old') for s in subject.SEASONS])
    monkeypatch.setattr(subject.pipeline,'read_json_file',lambda path:previous)
    writes=[];checks=[]
    monkeypatch.setattr(subject.publisher,'register_completed_delta',lambda *args:writes.append(args))
    def verify(season):
        checks.append(season)
        return dict(season=season,manifest_sha256='candidate',selected_replacement_carriers=[1] if season=='2001-02' else [2,3])
    monkeypatch.setattr(subject,'verify',verify)
    return root,checks,writes


def test_last_unreviewed_actor_blocks_every_default_change(tmp_path,monkeypatch):
    _,checks,writes=fixture(tmp_path,monkeypatch)
    def verify(season):
        checks.append(season)
        if season=='2002-03':raise ValueError('last original profile not reviewed')
        return dict(season=season,selected_replacement_carriers=[1])
    monkeypatch.setattr(subject,'verify',verify)
    with pytest.raises(ValueError,match='not reviewed'):subject.run()
    assert checks==list(subject.SEASONS) and writes==[]


def test_completed_publication_cannot_repeat(tmp_path,monkeypatch):
    _,checks,writes=fixture(tmp_path,monkeypatch)
    (tmp_path/'release-delivery-checklist-v56.json').touch()
    with pytest.raises(ValueError,match='must not repeat'):subject.run()
    assert checks==writes==[]


def test_replacement_counter_drift_not_accepted(tmp_path,monkeypatch):
    _,_,writes=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(subject,'verify',lambda s:dict(season=s,selected_replacement_carriers=[1]))
    with pytest.raises(ValueError,match='actor count drift'):subject.run()
    assert writes==[]


def test_intervening_other_fix_is_not_overwritten(tmp_path,monkeypatch):
    _,_,writes=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(subject.registry,'supported_seasons',lambda:list(subject.SEASONS))
    monkeypatch.setattr(subject.registry,'load_preferred_release',lambda s:SimpleNamespace(release_id='another-fix',manifest_sha256='changed'))
    with pytest.raises(ValueError,match='preserve intervening'):subject.run()
    assert writes==[]


def test_original_backup_failure_blocks_all_default_changes(tmp_path,monkeypatch):
    _,_,writes=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(subject,'check_bindings',lambda *args:None)
    def fail():raise ValueError('original backup bytes changed')
    monkeypatch.setattr(subject.managers,'verify_original2015',fail)
    with pytest.raises(ValueError,match='backup bytes changed'):subject.run()
    assert writes==[]


def test_own_partial_promotion_is_accepted_but_no_unselected_promotion(monkeypatch):
    originals={'2001-02':dict(release_id='parent',manifest_sha256='old'),
        '2002-03':dict(release_id='parent',manifest_sha256='old')}
    monkeypatch.setattr(subject.registry,'supported_seasons',lambda:list(originals))
    monkeypatch.setattr(subject.registry,'load_preferred_release',lambda s:SimpleNamespace(
        release_id=subject.batch.RELEASE if s=='2001-02' else 'parent',
        manifest_sha256='candidate' if s=='2001-02' else 'old'))
    subject.check_bindings(originals,{'2001-02':dict(manifest_sha256='candidate')})
    with pytest.raises(ValueError,match='preserve intervening'):subject.check_bindings(originals,{})
