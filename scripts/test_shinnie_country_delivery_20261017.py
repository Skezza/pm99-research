from types import SimpleNamespace

import pytest

from scripts import deliver_shinnie_country_20261017 as delivery
from scripts import capture_shinnie_country_20261017 as capture


def test_country_publication_refuses_existing_checklist(monkeypatch, tmp_path):
    root = tmp_path / 'country'
    root.mkdir()
    (tmp_path / 'release-delivery-checklist-v64.json').touch()
    monkeypatch.setattr(delivery.build, 'ROOT', root)
    with pytest.raises(ValueError, match='must not repeat'):
        delivery.main(63)


def test_country_publication_refuses_intervening_default_changes(monkeypatch, tmp_path):
    monkeypatch.setattr(delivery.build, 'ROOT', tmp_path / 'country')
    monkeypatch.setattr(delivery.pipeline, 'read_json_file',
                        lambda path: {'current_release_bindings': ['previous']})
    monkeypatch.setattr(delivery, 'bindings', lambda: ['intervening'])
    with pytest.raises(ValueError, match='current defaults differ'):
        delivery.main(63)


def test_country_publication_refuses_stale_parent_even_if_ledger_matches(monkeypatch, tmp_path):
    monkeypatch.setattr(delivery.build, 'ROOT', tmp_path / 'country')
    monkeypatch.setattr(delivery.pipeline, 'read_json_file',
                        lambda path: {'current_release_bindings': ['previous']})
    monkeypatch.setattr(delivery, 'bindings', lambda: ['previous'])
    monkeypatch.setattr(delivery.registry, 'load_registered_release',
                        lambda *args: SimpleNamespace(manifest_sha256='parent'))
    monkeypatch.setattr(delivery.registry, 'load_preferred_release',
                        lambda *args: SimpleNamespace(manifest_sha256='newer'))
    with pytest.raises(ValueError, match='parent advanced'):
        delivery.main(63)


def test_country_capture_wait_rejects_reused_pid(monkeypatch):
    class ProcPath:
        def __truediv__(self, value):
            return self
        def exists(self):
            return True
        def read_bytes(self):
            return b'another-process'
    monkeypatch.setattr(capture, 'Path', lambda *args: ProcPath())
    with pytest.raises(ValueError, match='PID identity changed'):
        capture.wait_owned(1, 'owned-module')
