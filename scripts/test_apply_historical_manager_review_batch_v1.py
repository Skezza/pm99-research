import json
from types import SimpleNamespace

import pytest

from scripts import apply_historical_manager_review_batch_v1 as batch


def setup_report(tmp_path, monkeypatch, result='fail'):
    package = tmp_path / 'package.json'; package.write_text('{}')
    release = SimpleNamespace(release_id='revision', manifest_sha256='manifest', package_path=package, locator={})
    report = {'result': result, 'historical_revision_binding': {'release_id': 'revision',
        'release_manifest_sha256': 'manifest', 'package_sha256': batch.registry.sha256_file(package)}}
    path = tmp_path / 'qa.json'; path.write_text(json.dumps(report))
    monkeypatch.setattr(batch.registry, '_validate_runtime_attestation', lambda r: [])
    return release, path, report


def test_completed_failed_qa_allows_correction_without_approving_history(tmp_path, monkeypatch):
    release, path, _ = setup_report(tmp_path, monkeypatch)
    assert batch.previous_qa_finished(release, path)
    assert release.locator == {}


def test_passing_qa_must_finish_exact_registration_before_transition(tmp_path, monkeypatch):
    release, path, _ = setup_report(tmp_path, monkeypatch, 'pass')
    assert not batch.previous_qa_finished(release, path)
    release.locator['qa_report_sha256'] = batch.registry.sha256_file(path)
    assert batch.previous_qa_finished(release, path)


def test_wrong_revision_or_invalid_runtime_does_not_allow_transition(tmp_path, monkeypatch):
    release, path, report = setup_report(tmp_path, monkeypatch)
    monkeypatch.setattr(batch.registry, '_validate_runtime_attestation', lambda r: ['bad-hash'])
    assert not batch.previous_qa_finished(release, path)
    monkeypatch.setattr(batch.registry, '_validate_runtime_attestation', lambda r: [])
    report['historical_revision_binding']['release_id'] = 'other-revision'; path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match='does not bind'):
        batch.previous_qa_finished(release, path)


def test_completed_plan_is_immutable_and_identical_plan_is_reused(tmp_path):
    path = tmp_path / 'plan.json'
    batch.immutable(path, {'updates': []})
    original = path.stat().st_mtime_ns
    batch.immutable(path, {'updates': []})
    assert path.stat().st_mtime_ns == original
    with pytest.raises(ValueError, match='stale'):
        batch.immutable(path, {'updates': [1]})
