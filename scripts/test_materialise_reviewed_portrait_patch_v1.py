import json
from types import SimpleNamespace

import pytest

from scripts import materialise_reviewed_portrait_patch_v1 as module


def fixture(tmp_path, monkeypatch):
    package_path = tmp_path / 'package.json'
    package_path.write_text(json.dumps({'players': [
        {'carrier_id': 1, 'name': 'Player One'}, {'carrier_id': 2, 'name': 'Player Two'}]}))
    game = tmp_path / 'game'
    (game / 'DBDAT').mkdir(parents=True)
    (game / 'DBDAT/MINIFOTO.PKF').write_bytes(bytes(120))
    release = SimpleNamespace(package_path=package_path, game_path=game, release_id='base')
    monkeypatch.setattr(module.registry, 'load_preferred_release', lambda _: release)
    manifest = {'season': '2014-15', 'inputs': {'package_canonical_sha256':
                  module.registry.canonical_document_sha256(package_path)},
                'players': [{'carrier_id': 1, 'name': 'Player One', 'status': 'native-no-photo'},
                            {'carrier_id': 2, 'name': 'Player Two', 'status': 'native-no-photo'}]}
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(manifest))
    return path, manifest, game


def test_blank_patch_is_small_and_does_not_modify_base(tmp_path, monkeypatch):
    path, _, game = fixture(tmp_path, monkeypatch)
    output = tmp_path / 'patch'
    result = module.materialise(path, output)
    assert result == {'players': 2, 'photos': 0, 'no_photo': 2}
    assert (game / 'DBDAT/MINIFOTO.PKF').read_bytes() == bytes(120)
    assert not (output / 'game').exists()


def test_duplicate_carriers_are_rejected_before_writes(tmp_path, monkeypatch):
    path, doc, _ = fixture(tmp_path, monkeypatch)
    doc['players'][1]['carrier_id'] = 1
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='exactly cover'):
        module.materialise(path, tmp_path / 'patch')
    assert not (tmp_path / 'patch').exists()


def test_wrong_identity_cannot_be_installed(tmp_path, monkeypatch):
    path, doc, _ = fixture(tmp_path, monkeypatch)
    doc['players'][0]['name'] = 'Another Player'
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='identity changed'):
        module.materialise(path, tmp_path / 'patch')


def test_pending_player_prevents_all_output_writes(tmp_path, monkeypatch):
    path, doc, _ = fixture(tmp_path, monkeypatch)
    doc['players'][0]['status'] = 'candidate'
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='pending players'):
        module.materialise(path, tmp_path / 'patch')
    assert not (tmp_path / 'patch').exists()
