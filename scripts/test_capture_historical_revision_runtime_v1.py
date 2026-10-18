from types import SimpleNamespace
from scripts import capture_historical_revision_runtime_v1 as capture


def test_existing_proof_must_describe_requested_revision(monkeypatch):
    monkeypatch.setattr(capture.registry, 'load_preferred_release', lambda s: SimpleNamespace(release_id='old-version'))
    assert capture.collect_existing('2025-26', 'new-version')['exit_code'] == 2


def test_existing_proof_is_not_reused_if_artifact_hash_check_fails(monkeypatch):
    release = SimpleNamespace(release_id='new-version', manifest_sha256='a' * 64,
                              attestation_path=None, runtime_evidence_path=None)
    monkeypatch.setattr(capture.registry, 'load_preferred_release', lambda s: release)
    monkeypatch.setattr(capture.registry, '_validate_runtime_attestation', lambda r: [{'code': 'screenshot-changed'}])
    result = capture.collect_existing('2025-26', 'new-version')
    assert result['exit_code'] == 1
    assert not result['existing_proof_reused']
