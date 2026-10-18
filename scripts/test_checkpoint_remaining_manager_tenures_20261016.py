"""A source claim or partial runner pass must never count as game delivery."""
from types import SimpleNamespace
import pytest
from scripts import checkpoint_remaining_manager_tenures_20261016 as subject


def fixture(tmp_path, monkeypatch):
    root = tmp_path / 'batch'; root.mkdir()
    monkeypatch.setattr(subject.batch, 'ROOT', root)
    seasons = ['2000-01', '2001-02']
    originals = [dict(season=s, release_id='parent', manifest_sha256='old') for s in seasons]
    admission = dict(original_deferred_cases_admitted=36, admitted_cases=36,
        seasons=[dict(season=s, corrections=18) for s in seasons])
    previous = dict(current_release_bindings=originals)
    monkeypatch.setattr(subject.registry, 'supported_seasons', lambda: seasons)
    monkeypatch.setattr(subject.pipeline, 'read_json_file', lambda p: admission if p.name=='source-admission-summary.json' else previous)
    writes=[]; checks=[]
    monkeypatch.setattr(subject.publisher, 'register_completed_delta', lambda *a: writes.append(a))
    def verify(season):
        checks.append(season)
        return dict(season=season, canonical_manager_updates=18, manifest_sha256='candidate')
    monkeypatch.setattr(subject, 'verify', verify)
    return root, admission, checks, writes


def test_last_missing_runner_review_blocks_every_preferred_change(tmp_path, monkeypatch):
    _, _, checks, writes = fixture(tmp_path, monkeypatch)
    def verify(season):
        checks.append(season)
        if season=='2001-02':
            raise ValueError('original runner frame not reviewed')
        return dict(season=season, canonical_manager_updates=18)
    monkeypatch.setattr(subject,'verify',verify)
    with pytest.raises(ValueError,match='not reviewed'):
        subject.run()
    assert checks==['2000-01','2001-02'] and writes==[]


def test_missing_original_deferred_case_blocks_publication(tmp_path, monkeypatch):
    _, admission, checks, writes = fixture(tmp_path, monkeypatch)
    admission['original_deferred_cases_admitted']=35
    with pytest.raises(ValueError,match='remaining36'):
        subject.run()
    assert checks==writes==[]


def test_source_scope_must_match_all_supported_seasons(tmp_path, monkeypatch):
    _, admission, checks, writes = fixture(tmp_path, monkeypatch)
    admission['seasons'].pop()
    with pytest.raises(ValueError,match='all26'):
        subject.run()
    assert checks==writes==[]


def test_update_counter_drift_is_not_accepted(tmp_path, monkeypatch):
    _, admission, _, writes = fixture(tmp_path, monkeypatch)
    admission['admitted_cases']=37
    with pytest.raises(ValueError,match='update count'):
        subject.run()
    assert writes==[]


def test_intervening_preferred_game_is_not_overwritten(tmp_path, monkeypatch):
    _, _, _, writes = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(subject.registry,'load_preferred_release',lambda s:SimpleNamespace(
        release_id='another-fix',manifest_sha256='changed'))
    with pytest.raises(ValueError,match='preserve intervening'):
        subject.run()
    assert writes==[]


def test_completed_delivery_cannot_be_repeated(tmp_path, monkeypatch):
    _, _, checks, writes = fixture(tmp_path, monkeypatch)
    (tmp_path/'release-delivery-checklist-v55.json').touch()
    with pytest.raises(ValueError,match='must not repeat'):
        subject.run()
    assert checks==writes==[]


def test_failed_original_backup_check_blocks_all_preferred_changes(tmp_path,monkeypatch):
    _,_,_,writes=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(subject.registry,'load_preferred_release',lambda s:SimpleNamespace(
        release_id='parent',manifest_sha256='old'))
    def fail():raise ValueError('retained original backup changed')
    monkeypatch.setattr(subject,'verify_original2015',fail)
    with pytest.raises(ValueError,match='original backup changed'):
        subject.run()
    assert writes==[]


def test_original_backup_requires_exact_unique_retained_release(monkeypatch):
    monkeypatch.setattr(subject.pipeline,'read_json_file',lambda p:dict(releases=[]))
    with pytest.raises(ValueError,match='retention missing or ambiguous'):
        subject.verify_original2015()


def test_matching_metadata_cannot_hide_changed_original_game_bytes(tmp_path,monkeypatch):
    row=dict(season='2015-16',release_id='legacy-world-2015-16',locator_path='original-locator.json',
        locator_sha256='sealed',inventory_sha256='sealed')
    monkeypatch.setattr(subject.registry,'ROOT',tmp_path)
    monkeypatch.setattr(subject.pipeline,'read_json_file',lambda p:
        dict(releases=[row]) if p.name=='retained-season-releases-v1.json' else dict(files=[]))
    monkeypatch.setattr(subject.registry,'load_registered_release',lambda *a:SimpleNamespace(
        inventory_path=tmp_path/'original-inventory.json',game_path=tmp_path/'game'))
    monkeypatch.setattr(subject.registry,'sha256_file',lambda p:'sealed')
    def fail(*args):raise ValueError('original game bytes differ')
    monkeypatch.setattr(subject.pipeline,'assert_tree_matches_inventory',fail)
    with pytest.raises(ValueError,match='original game bytes differ'):
        subject.verify_original2015()
