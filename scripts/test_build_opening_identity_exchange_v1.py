import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import build_opening_identity_exchange_v1 as subject


GiB = 1024 ** 3


def test_invalid_or_pairwise_colliding_output_ids_refuse_before_request_read(tmp_path, monkeypatch):
    def should_not_read(_path):
        raise AssertionError('request read started before ID admission')

    monkeypatch.setattr(subject.pipeline, 'read_json_file', should_not_read)
    invalid_pairs = [
        ('../escape', 'replay'),
        ('UpperCase', 'replay'),
        ('x' * 97, 'replay'),
        ('same', 'same'),
    ]
    for release_id, replay_id in invalid_pairs:
        with pytest.raises(ValueError, match='distinct lowercase'):
            subject.deliver(tmp_path / 'missing-request.json', release_id, replay_id,
                            tmp_path / 'evidence')
    assert not (tmp_path / 'evidence').exists()


def _stub_pre_publish_delivery(tmp_path, monkeypatch, *, request):
    source_package = tmp_path / 'source-package.json'
    source_package.write_text('{}')
    source_game = tmp_path / 'source-game'
    source_dat = source_game / 'DBDAT/JUG98030.FDI'
    source_dat.parent.mkdir(parents=True)
    source_dat.write_bytes(b'fake indexed roster')
    base = SimpleNamespace(
        season=request['season'], release_id=request['release_id'],
        package_path=source_package, game_path=source_game,
    )
    monkeypatch.setattr(subject.pipeline, 'read_json_file', lambda _path: request)
    monkeypatch.setattr(subject.registry, 'load_registered_release', lambda *_args: base)
    monkeypatch.setattr(subject.source, 'prepare', lambda *_args: {'test-plan': True})
    monkeypatch.setattr(subject.source, 'filename', lambda _plan: 'plan.json')

    def retain(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{}')

    monkeypatch.setattr(subject, 'retained', retain)
    monkeypatch.setattr(subject.registry, 'locator_path',
                        lambda _season, release_id: tmp_path / 'locators' / release_id)
    published = []
    monkeypatch.setattr(subject.publisher, 'publish', lambda *args, **kwargs: published.append(args))
    return base, published


def test_low_disk_reserve_refuses_before_publisher_write(tmp_path, monkeypatch):
    request = {'season': '2000-01', 'release_id': 'source-release', 'orders': []}
    _, published = _stub_pre_publish_delivery(tmp_path, monkeypatch, request=request)
    monkeypatch.setattr(subject.shutil, 'disk_usage',
                        lambda _path: SimpleNamespace(free=8 * GiB - 1))
    with pytest.raises(ValueError, match='8GiB reserve'):
        subject.deliver(tmp_path / 'request.json', 'child-release', 'replay-release',
                        tmp_path / 'evidence')
    assert published == []
    assert not (tmp_path / 'locators/child-release').exists()


def test_exact_eight_gibibyte_reserve_is_admitted(monkeypatch):
    monkeypatch.setattr(subject.shutil, 'disk_usage',
                        lambda _path: SimpleNamespace(free=8 * GiB))
    subject.reserve_space()


def test_order_changing_request_refuses_before_any_publisher_or_evidence_write(tmp_path, monkeypatch):
    request = {
        'season': '2000-01', 'release_id': 'source-release',
        'orders': [{'club_carrier_id': 225, 'full_order': [1, 2, 3]}],
    }
    published = []
    monkeypatch.setattr(subject.pipeline, 'read_json_file', lambda _path: request)
    monkeypatch.setattr(subject.publisher, 'publish', lambda *args, **kwargs: published.append(args))
    monkeypatch.setattr(subject.registry, 'load_registered_release',
                        lambda *_args: (_ for _ in ()).throw(AssertionError('base release loaded')))
    evidence_dir = tmp_path / 'evidence'
    with pytest.raises(ValueError, match='preserves all startup orders'):
        subject.deliver(tmp_path / 'request.json', 'child-release', 'replay-release', evidence_dir)
    assert published == []
    assert not evidence_dir.exists()


def test_replay_id_cannot_collide_with_registered_source_release_before_publish(tmp_path, monkeypatch):
    request = {'season': '2000-01', 'release_id': 'source-release', 'orders': []}
    _, published = _stub_pre_publish_delivery(tmp_path, monkeypatch, request=request)
    monkeypatch.setattr(subject.shutil, 'disk_usage',
                        lambda _path: SimpleNamespace(free=8 * GiB))
    with pytest.raises(ValueError, match='source release'):
        subject.deliver(tmp_path / 'request.json', 'child-release', 'source-release',
                        tmp_path / 'evidence')
    assert published == []


def test_unreceipted_existing_replay_refuses_before_base_load_or_publish(tmp_path, monkeypatch):
    request = {'season': '2000-01', 'release_id': 'source-release', 'orders': []}
    _, published = _stub_pre_publish_delivery(tmp_path, monkeypatch, request=request)
    existing_replay = tmp_path / 'locators' / 'replay-release'
    existing_replay.mkdir(parents=True)
    base_loads = []

    def load_base(*args):
        base_loads.append(args)
        raise AssertionError('existing replay must be inspected before base loading')

    monkeypatch.setattr(subject.registry, 'load_registered_release', load_base)
    evidence_dir = tmp_path / 'evidence'
    with pytest.raises(ValueError, match='unreceipted replay'):
        subject.deliver(tmp_path / 'request.json', 'child-release', 'replay-release', evidence_dir)
    assert base_loads == []
    assert published == []
    assert not evidence_dir.exists()


@pytest.mark.parametrize('receipt_text', [
    '{not-json',
    json.dumps({
        'season': '1999-00', 'release_id': 'replay-release',
        'complete_game_inventory_identical': True, 'complete_recipe_identical': True,
    }),
    json.dumps({
        'season': '2000-01', 'release_id': 'another-replay',
        'complete_game_inventory_identical': True, 'complete_recipe_identical': True,
    }),
    json.dumps({
        'season': '2000-01', 'release_id': 'replay-release',
        'complete_game_inventory_identical': False, 'complete_recipe_identical': True,
    }),
])
def test_malformed_or_wrong_bound_existing_receipt_refuses_before_publish(
        tmp_path, monkeypatch, receipt_text):
    request = {'season': '2000-01', 'release_id': 'source-release', 'orders': []}
    _, published = _stub_pre_publish_delivery(tmp_path, monkeypatch, request=request)
    evidence_dir = tmp_path / 'evidence'
    evidence_dir.mkdir()
    (evidence_dir / 'complete-SOURCE-replay.json').write_text(receipt_text)
    (tmp_path / 'locators' / 'replay-release').mkdir(parents=True)

    def read_json(path):
        if Path(path) == tmp_path / 'request.json':
            return request
        return json.loads(Path(path).read_text())

    monkeypatch.setattr(subject.pipeline, 'read_json_file', read_json)
    base_loads = []

    def load_base(*args):
        base_loads.append(args)
        raise AssertionError('receipt must validate before base loading')

    monkeypatch.setattr(subject.registry, 'load_registered_release', load_base)
    with pytest.raises((ValueError, json.JSONDecodeError)):
        subject.deliver(tmp_path / 'request.json', 'child-release', 'replay-release', evidence_dir)
    assert base_loads == []
    assert published == []
