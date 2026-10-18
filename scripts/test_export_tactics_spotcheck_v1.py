import hashlib

import pytest

from scripts import export_tactics_spotcheck_v1 as exporter


def test_original_frame_must_have_eleven_hash_bound_phase_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, 'ROOT', tmp_path)
    path = tmp_path / '.local/runlogs/pm99_runner/test/frame.png'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'original runner frame')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    proof = {'players': [{'phase': 'attack', 'screenshot': str(path),
                           'screenshot_sha256': digest} for _ in range(11)]}
    assert exporter.checked_frame(proof, 'attack') == (path, digest)
    path.write_bytes(b'altered')
    with pytest.raises(ValueError, match='changed'):
        exporter.checked_frame(proof, 'attack')
    proof['players'].pop()
    with pytest.raises(ValueError, match='eleven'):
        exporter.checked_frame(proof, 'attack')


def test_review_pack_refuses_to_overwrite(tmp_path):
    with pytest.raises(ValueError, match='never overwrite'):
        exporter.export(tmp_path, tmp_path)
