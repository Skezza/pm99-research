from types import SimpleNamespace

import pytest

from scripts import capture_public_fixture_batch_20261017 as subject


def test_capture_refuses_missing_source_proof(monkeypatch, tmp_path):
    monkeypatch.setattr(subject.build, 'ROOT', tmp_path)
    monkeypatch.setattr(subject, 'Path', lambda *args: tmp_path / 'absent-process')
    with pytest.raises(ValueError, match='whole SOURCE proof'):
        subject.main(123)


def test_capture_uses_only_completed_exeter_game(monkeypatch, tmp_path):
    folder = tmp_path / '2024-25'
    folder.mkdir()
    (folder / 'complete-SOURCE-replay.json').touch()
    monkeypatch.setattr(subject.build, 'ROOT', tmp_path)
    monkeypatch.setattr(subject, 'Path', lambda *args: tmp_path / 'absent-process')
    calls = []
    capture = SimpleNamespace(run=lambda year: calls.append(year))
    monkeypatch.setattr(subject, 'capture', capture)
    subject.main(123)
    assert calls == ['2024-25']
    assert capture.ROOT == tmp_path
    assert capture.RELEASE == subject.build.RELEASE
    assert capture.tag('2024-25') == 'public_original_fixture_2024_25_r124a_20261017'


def test_wait_never_restarts_or_accepts_reused_pid(monkeypatch, tmp_path):
    process = tmp_path / 'process'
    process.write_bytes(b'an-unrelated-process')
    class ProcPath:
        def __truediv__(self, value):
            return self
        def exists(self):
            return True
        def read_bytes(self):
            return process.read_bytes()
    monkeypatch.setattr(subject, 'Path', lambda *args: ProcPath())
    with pytest.raises(ValueError, match='another process'):
        subject.main(123)
