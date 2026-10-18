import json
from types import SimpleNamespace

import pytest

from scripts import publish_manager_display_delta_v1 as publisher


def test_unsafe_release_id_is_rejected_before_any_game_or_recipe_write(tmp_path):
    with pytest.raises(ValueError, match='unsafe release'):
        publisher.publish('2016-17', tmp_path, {}, release_id='../overwrite')
    assert list(tmp_path.iterdir()) == []


def test_missing_field_proof_blocks_publication(tmp_path):
    with pytest.raises(FileNotFoundError):
        publisher.gates(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_disposable_field_probe_cannot_be_promoted(tmp_path):
    (tmp_path / 'candidate-receipt.json').write_text(json.dumps({'field_probe': True}))
    with pytest.raises(ValueError, match='not a normal delta'):
        publisher.audit(tmp_path, SimpleNamespace(release_id='source'))


def test_completed_field_proof_cannot_be_silently_replaced(tmp_path, monkeypatch):
    path = tmp_path / 'championships-field-proof-v1.json'
    path.write_text(json.dumps({'candidate': '/candidate', 'run': '/run', 'frame': '/frame', 'old': True}))
    monkeypatch.setattr(publisher, 'verify', lambda *_a, **_kw: {'changed': True})
    with pytest.raises(ValueError, match='proof changed'):
        publisher.gates(tmp_path)


def test_unpublished_refresh_cannot_mutate_a_registered_game(tmp_path, monkeypatch):
    monkeypatch.setattr(publisher.registry, 'load_preferred_release', lambda _: SimpleNamespace(release_id='already-live'))
    with pytest.raises(ValueError, match='registered game'):
        publisher.refresh_unpublished_workspace('2016-17', 'already-live', tmp_path / 'workspace',
                                                tmp_path / 'registry', {}, None, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_unpublished_refresh_cannot_mutate_an_attested_game(tmp_path, monkeypatch):
    monkeypatch.setattr(publisher.registry, 'load_preferred_release', lambda _: SimpleNamespace(release_id='baseline'))
    destination = tmp_path / 'registry'; destination.mkdir()
    (destination / 'locator.json').write_text(json.dumps({'attestation_path': '/proof'}))
    with pytest.raises(ValueError, match='attested game'):
        publisher.refresh_unpublished_workspace('2016-17', 'not-live', tmp_path / 'workspace',
                                                destination, {}, None, tmp_path)
