from types import SimpleNamespace
from pathlib import Path
import concurrent.futures
import threading
import time

import pytest

from scripts import capture_registered_season_runtime_v1 as capture


def test_candidate_command_binds_candidate_files_and_inventory_not_preferred(monkeypatch):
    candidate = SimpleNamespace(game_path=Path('/candidate/game'), release_manifest_path=Path('/candidate/manifest'),
        manifest_sha256='candidate-manifest', locator={'game_inventory_fingerprint': 'candidate-inventory'})
    monkeypatch.setattr(capture.registry, 'load_preferred_release', lambda s: pytest.fail('must not change or use preferred'))
    monkeypatch.setattr(capture.registry, 'load_registered_release', lambda s, id: candidate)
    checks = []
    monkeypatch.setattr(capture.registry, 'validate_preferred_release', lambda s, **k: checks.append(k) or {'valid': True})
    monkeypatch.setattr(capture, '_selector', lambda s: dict(team_name='Stoke City', team_select_x=306,
        team_select_y=360, division_select_x=562, division_select_y=302))
    command, _ = capture.capture_command(season='2000-01', worker='tiny-m73', run_tag='candidate', release_id='r57')
    assert command[command.index('--dbdat-dir')+1] == '/candidate/game/DBDAT'
    assert command[command.index('--release-manifest-sha256')+1] == 'candidate-manifest'
    assert command[command.index('--output-inventory-fingerprint')+1] == 'candidate-inventory'
    assert checks == [{'level': 'playable', 'release_id': 'r57'}]


def test_expected_release_rejects_an_old_season_before_launch_or_attestation(monkeypatch):
    monkeypatch.setattr(capture.registry, 'load_preferred_release', lambda _: SimpleNamespace(release_id='old'))
    args = SimpleNamespace(expect_release_id='new', execute=True, attest=True)
    with pytest.raises(capture.CaptureError, match='no game launched'):
        capture.capture_one(season='2015-16', args=args)


def test_expected_release_does_not_bypass_immutable_attestation_checks(monkeypatch):
    monkeypatch.setattr(capture.registry, 'load_preferred_release', lambda _: SimpleNamespace(
        release_id='new', attestation_path='existing', release_manifest_path=None, manifest_sha256=None))
    calls = []
    def validate(*args, **kwargs):
        calls.append(kwargs)
        raise capture.CaptureError('immutable checks required')
    monkeypatch.setattr(capture.registry, 'validate_preferred_release', validate)
    args = SimpleNamespace(expect_release_id='new', execute=True, attest=True)
    with pytest.raises(capture.CaptureError, match='immutable checks required'):
        capture.capture_one(season='2015-16', args=args)
    assert calls == [{'level': 'playable'}]


def test_overlapping_batches_serialize_one_season_and_reuse_completed_proof(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, 'ROOT', tmp_path)
    entered, release, second_attempt = threading.Event(), threading.Event(), threading.Event()
    state = {'complete': False, 'launches': 0}
    def inner(*, season, args):
        if state['complete']:
            return 'reused'
        state['launches'] += 1
        entered.set()
        assert release.wait(2)
        state['complete'] = True
        return 'launched'
    monkeypatch.setattr(capture, '_capture_one_unlocked', inner)
    args = SimpleNamespace(execute=True)
    def second():
        second_attempt.set()
        return capture.capture_one(season='2015-16', args=args)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(capture.capture_one, season='2015-16', args=args)
        assert entered.wait(2)
        other = pool.submit(second)
        assert second_attempt.wait(2)
        time.sleep(0.02)
        release.set()
        assert first.result() == 'launched'
        assert other.result() == 'reused'
    assert state['launches'] == 1
