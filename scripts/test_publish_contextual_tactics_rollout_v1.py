import pytest

from scripts import publish_contextual_tactics_rollout_v1 as publisher


def test_publication_is_blocked_before_output_when_runtime_coverage_is_missing(tmp_path, monkeypatch):
    def fail(*args):
        raise ValueError('unproved formation families: 3-5-2')
    monkeypatch.setattr(publisher.runtime, 'verify_coverage', fail)
    with pytest.raises(ValueError, match='unproved formation'):
        publisher.completion_gates(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_bad_release_id_is_rejected_before_output(tmp_path):
    with pytest.raises(ValueError, match='release ID'):
        publisher.publish('2015-16', tmp_path, {}, release_id='../overwrite')
    assert list(tmp_path.iterdir()) == []
