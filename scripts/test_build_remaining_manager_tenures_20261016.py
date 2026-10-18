"""The private builder cannot silently skip source or parent admission."""
from types import SimpleNamespace
import os
import pytest
from scripts import build_remaining_manager_tenures_20261016 as subject


def fixture(tmp_path, monkeypatch, updates):
    root = tmp_path / 'batch'; root.mkdir()
    plan_path = tmp_path / 'plan.json'; plan_path.write_text('source-bound-plan')
    plan = dict(release_id='parent', updates=updates)
    row = dict(season='2001-02', source_plan=dict(path='plan.json', sha256=subject.registry.sha256_file(plan_path)))
    monkeypatch.setattr(subject, 'ROOT', root)
    monkeypatch.setattr(subject.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(subject.pipeline, 'read_json_file', lambda p: dict(seasons=[row]) if p.name == 'source-admission-summary.json' else plan)
    base = SimpleNamespace(release_id='parent', manifest_sha256='original')
    monkeypatch.setattr(subject.registry, 'load_registered_release', lambda *a: base)
    monkeypatch.setattr(subject.registry, 'load_preferred_release', lambda *a: base)
    monkeypatch.setattr(subject.source, 'prepare', lambda *a: plan)
    calls = []
    monkeypatch.setattr(subject.core, 'build', lambda *a, **kw: calls.append((a, kw)))
    return row, plan, calls


def test_unchanged_season_is_not_rebuilt(tmp_path, monkeypatch):
    _, _, calls = fixture(tmp_path, monkeypatch, [])
    subject.build('2001-02')
    assert calls == []


def test_current_exact_parent_is_forwarded_to_actual_builder(tmp_path, monkeypatch):
    _, _, calls = fixture(tmp_path, monkeypatch, [dict(manager_id='m')])
    subject.build('2001-02')
    assert len(calls) == 1 and calls[0][1]['source_release_id'] == 'parent'


def test_changed_admitted_plan_cannot_build(tmp_path, monkeypatch):
    row, _, calls = fixture(tmp_path, monkeypatch, [dict(manager_id='m')])
    row['source_plan']['sha256'] = 'changed'
    with pytest.raises(ValueError, match='source plan changed'):
        subject.build('2001-02')
    assert calls == []


def test_intervening_preferred_fix_is_not_discarded(tmp_path, monkeypatch):
    _, _, calls = fixture(tmp_path, monkeypatch, [dict(manager_id='m')])
    monkeypatch.setattr(subject.registry, 'load_preferred_release', lambda *a: SimpleNamespace(release_id='new-fix'))
    with pytest.raises(ValueError, match='preserve intervening'):
        subject.build('2001-02')
    assert calls == []


def test_changed_parent_manifest_is_refused(tmp_path, monkeypatch):
    _, _, calls = fixture(tmp_path, monkeypatch, [dict(manager_id='m')])
    monkeypatch.setattr(subject.registry, 'load_preferred_release', lambda *a: SimpleNamespace(release_id='parent',manifest_sha256='changed'))
    with pytest.raises(ValueError, match='manifest changed'):
        subject.build('2001-02')
    assert calls == []


def test_failed_original_source_replay_blocks_native_work(tmp_path, monkeypatch):
    _, _, calls = fixture(tmp_path, monkeypatch, [dict(manager_id='m')])
    monkeypatch.setattr(subject.source, 'prepare', lambda *a: dict(updates=[]))
    with pytest.raises(ValueError, match='no longer reproduce'):
        subject.build('2001-02')
    assert calls == []


def test_duplicate_season_admission_is_refused(tmp_path, monkeypatch):
    row, _, calls = fixture(tmp_path, monkeypatch, [])
    monkeypatch.setattr(subject.pipeline, 'read_json_file', lambda *a: dict(seasons=[row,row]))
    with pytest.raises(ValueError, match='exactly one'):
        subject.build('2001-02')
    assert calls == []


def test_stopped_source_without_completed_admission_never_builds(tmp_path,monkeypatch):
    monkeypatch.setattr(subject,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='without full admission'):
        subject.wait_for_admission(999999999)


def test_finished_source_can_be_used_without_restarting_it(tmp_path,monkeypatch):
    monkeypatch.setattr(subject,'ROOT',tmp_path)
    (tmp_path/'source-admission-summary.json').write_text('{}')
    subject.wait_for_admission(999999999)


def test_reused_pid_does_not_wait_on_an_unrelated_process(tmp_path,monkeypatch):
    monkeypatch.setattr(subject,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='PID identity changed'):
        subject.wait_for_admission(os.getpid())
