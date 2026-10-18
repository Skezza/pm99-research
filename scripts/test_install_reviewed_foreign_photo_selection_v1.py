import json
from types import SimpleNamespace

import pytest

from scripts import install_reviewed_foreign_photo_selection_v1 as install
from scripts import season_visual_patch_v1 as art


def inputs(tmp_path, monkeypatch, *, kit_confirmed=True, installed=False):
    package = tmp_path / 'package.json'
    package.write_text(json.dumps({'players': [{'carrier_id': 1, 'name': 'Player',
                                               'facts': {'birth_date': '2000-01-01'}}]}))
    bitmap = tmp_path / 'photo.bmp'
    bitmap.write_bytes(b'native-test-bitmap')
    game = tmp_path / 'game'
    if installed:
        target = game / 'DBDAT/MINIFOTO/J9600001.BMP'
        target.parent.mkdir(parents=True)
        target.write_bytes(bitmap.read_bytes())
    release = SimpleNamespace(package_path=package, game_path=game, release_id='base')
    archive = game / 'DBDAT/MINIFOTO.PKF'
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(b'unchanged-native-archive')
    monkeypatch.setattr(install.registry, 'load_preferred_release', lambda season: release)
    monkeypatch.setattr(install, 'ROOT', tmp_path)
    selection = tmp_path / 'selected/2025-26/selection.json'
    selection.parent.mkdir(parents=True)
    selection.write_text(json.dumps({'policy_version': 'football-face-v2', 'package_sha256': art.sha(package),
        'players': [{'status': 'source-and-framing-pass', 'carrier_id': 1, 'name': 'Player',
                     'birth_date': '2000-01-01', 'face_view': {'passed': True}, 'source_sha256': 'a'*64,
                     'bitmap_sha256': art.sha(bitmap), 'bitmap_path': str(bitmap)}]}))
    review = tmp_path / 'review.json'
    review.write_text(json.dumps({'rows': [{'season': '2025-26', 'carrier_id': 1, 'accepted': True,
        'football_kit_confirmed': kit_confirmed, 'source_sha256': 'a'*64, 'bitmap_sha256': art.sha(bitmap)}]}))
    return selection.parent.parent, review


def test_older_football_policy_still_requires_clothing_review(tmp_path, monkeypatch):
    selected, review = inputs(tmp_path, monkeypatch, kit_confirmed=False)
    with pytest.raises(ValueError, match='football clothing'):
        install.prepare('2025-26', selected, review, tmp_path / 'output')


def test_identical_portrait_is_not_reinstalled_and_empty_prepare_is_repeatable(tmp_path, monkeypatch):
    selected, review = inputs(tmp_path, monkeypatch, installed=True)
    for _ in range(2):
        assert install.prepare('2025-26', selected, review, tmp_path / 'output') == 0
    assert not (tmp_path / 'output/plan.json').exists()


def test_prepared_patch_resumes_without_regenerating_and_rejects_changed_review(tmp_path, monkeypatch):
    selected, review = inputs(tmp_path, monkeypatch)
    assert install.prepare('2025-26', selected, review, tmp_path / 'output') == 1
    assert install.prepare('2025-26', selected, review, tmp_path / 'output') == 1
    review.write_text('{}')
    with pytest.raises((ValueError, KeyError)):
        install.prepare('2025-26', selected, review, tmp_path / 'output')
