"""No partial publication from missing evidence, scope drift or stale parents."""
from types import SimpleNamespace
import pytest
from scripts import checkpoint_cached_managers_20261016 as subject


def fixture(tmp_path,monkeypatch):
    root=tmp_path/'batch';root.mkdir()
    monkeypatch.setattr(subject,'ROOT',root)
    seasons=[f'{y}-{str(y+1)[-2:]}' for y in range(2000,2026)]
    monkeypatch.setattr(subject.registry,'supported_seasons',lambda:seasons)
    previous=dict(current_release_bindings=[dict(season=s,release_id='parent',manifest_sha256='hash') for s in seasons])
    monkeypatch.setattr(subject.pipeline,'read_json_file',lambda p:previous)
    checked=[];writes=[]
    def verify(s):
        checked.append(s)
        return dict(season=s,canonical_manager_updates=1)
    monkeypatch.setattr(subject,'verify',verify)
    monkeypatch.setattr(subject.publisher,'register_completed_delta',lambda *args:writes.append(args))
    return seasons,checked,writes


def test_last_unreviewed_season_prevents_all_manager_publication(tmp_path,monkeypatch):
    seasons,checked,writes=fixture(tmp_path,monkeypatch)
    def verify(s):
        checked.append(s)
        if s==seasons[-1]:raise ValueError('last actual manager-game screenshot unreviewed')
        return dict(season=s,canonical_manager_updates=20)
    monkeypatch.setattr(subject,'verify',verify)
    with pytest.raises(ValueError,match='unreviewed'):
        subject.run()
    assert checked==[s for s in seasons if s!='2015-16']
    assert writes==[]


def test_frozen_proposal_count_drift_prevents_publication(tmp_path,monkeypatch):
    seasons,checked,writes=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='495'):
        subject.run()
    assert len(checked)==25 and '2015-16' not in checked
    assert writes==[]


def test_changed_legacy_parent_is_not_silently_approved(tmp_path,monkeypatch):
    seasons,checked,writes=fixture(tmp_path,monkeypatch)
    def verify(s):
        checked.append(s)
        return dict(season=s,canonical_manager_updates=15 if s==seasons[-1] else 20)
    monkeypatch.setattr(subject,'verify',verify)
    monkeypatch.setattr(subject.registry,'load_preferred_release',lambda s:SimpleNamespace(
        release_id='unexpected' if s=='2015-16' else 'parent',manifest_sha256='hash'))
    with pytest.raises(ValueError,match='unexpected preferred'):
        subject.run()
    assert writes==[]


def test_wrong_scope_prevents_any_verification_or_publication(tmp_path,monkeypatch):
    seasons,checked,writes=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(subject.registry,'supported_seasons',lambda:seasons[:-1])
    with pytest.raises(ValueError,match='exact25'):
        subject.run()
    assert checked==writes==[]


def test_completed_checkpoint_cannot_publish_twice(tmp_path,monkeypatch):
    seasons,checked,writes=fixture(tmp_path,monkeypatch)
    (tmp_path/'release-delivery-checklist-v49.json').touch()
    with pytest.raises(ValueError,match='must not repeat'):
        subject.run()
    assert checked==writes==[]


def test_future_fixture_is_refused_before_original_source_or_game_processing(monkeypatch):
    monkeypatch.setattr(subject.registry,'load_registered_release',lambda *a:SimpleNamespace())
    monkeypatch.setattr(subject.pipeline,'read_json_file',lambda p:dict(updates=[
        dict(first_fixture_date='2020-08-08',club='Internacional')]))
    monkeypatch.setattr(subject.source,'prepare',lambda *a:pytest.fail('future report must not be accepted by the old partial country list'))
    with pytest.raises(ValueError,match='outside the actual requested game year'):
        subject.verify('2019-20')
