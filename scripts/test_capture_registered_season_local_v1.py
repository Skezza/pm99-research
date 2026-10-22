from types import SimpleNamespace

import pytest

from scripts import capture_registered_season_local_v1 as subject


@pytest.fixture
def release():
    return SimpleNamespace(season='2000-01', manifest_sha256='manifest',
                           locator={'game_inventory_fingerprint': 'inventory'},
                           package_path='recipe.json')


def test_startup_uses_current_driver_and_exact_release_binding(release):
    args = subject.driver_args(release)
    assert args[1].endswith('/stoke_season_driver.py')
    assert args[args.index('--release-manifest-sha256') + 1] == 'manifest'
    assert args[args.index('--output-inventory-fingerprint') + 1] == 'inventory'
    assert args[args.index('--team-name') + 1] == 'Stoke City'
    assert args[args.index('--team-select-x') + 1] == '306'
    assert '--capture-routes-only' in args
    assert '--capture-route' in args and args[-1] == '302'


def test_profile_uses_exact_native_recipe_identity_and_search_token(release, monkeypatch):
    monkeypatch.setattr(subject.pipeline, 'read_json_file', lambda _: {
        'players': [dict(carrier_id=10149, name='Gary Parkinson')]})
    args = subject.driver_args(release, carrier=10149, label='parkinson', token='Parkinson')
    assert args[1].endswith('/premier_offer_capture_driver.py')
    assert args[args.index('--expected-profile-token') + 1] == 'Parkinson'
    steps = [args[i + 1] for i, value in enumerate(args) if value == '--post-step']
    assert 'native_key|G|0.1' in steps[7]
    assert any('native_key|Space|' in s for s in steps)
    assert steps[-1] == 'profile_only_parkinson_done|native_inspect|ignored|0.5'


@pytest.mark.parametrize('label,token', [('../escape', 'Parkinson'), ('PARK', 'Parkinson'),
                                       ('parkinson', None), (None, 'Parkinson')])
def test_profile_requires_safe_label_and_explicit_token(release, label, token):
    with pytest.raises(ValueError, match='label'):
        subject.driver_args(release, carrier=10149, label=label, token=token)


@pytest.mark.parametrize('players', [[], [dict(carrier_id=1, name='Other')],
                                    [dict(carrier_id=10149, name='A'), dict(carrier_id=10149, name='B')]])
def test_profile_refuses_unknown_or_ambiguous_carrier(release, monkeypatch, players):
    monkeypatch.setattr(subject.pipeline, 'read_json_file', lambda _: {'players': players})
    with pytest.raises(ValueError, match='exact recipe carrier'):
        subject.driver_args(release, carrier=10149, label='parkinson', token='Parkinson')


def test_unsafe_capture_tag_rejected_before_any_release_or_docker_access(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('release was accessed before rejecting unsafe tag')
    monkeypatch.setattr(subject.registry, 'load_registered_release', forbidden)
    with pytest.raises(ValueError, match='unique capture tag'):
        subject.capture('2000-01', 'release', '../unsafe')


@pytest.mark.parametrize('fault', [None, 'manifest', 'inventory', 'phase', 'team', 'success'])
def test_startup_summary_requires_exact_release_phase_and_visible_stoke(release, fault):
    summary = dict(success=True, release_manifest_sha256='manifest',
        output_inventory_fingerprint='inventory', phase_reached='return_from_line_up',
        route_summaries={'line_up': {'team_identity': {'matched': True, 'observed_normalized': 'stoke city'}}})
    if fault == 'manifest': summary['release_manifest_sha256'] = 'another'
    if fault == 'inventory': summary['output_inventory_fingerprint'] = 'another'
    if fault == 'phase': summary['phase_reached'] = 'title'
    if fault == 'team': summary['route_summaries']['line_up']['team_identity']['observed_normalized'] = 'watford'
    if fault == 'success': summary['success'] = False
    assert subject.summary_matches(summary, release) is (fault is None)


@pytest.mark.parametrize('success,matched', [(True, True), (False, True), (True, False)])
def test_profile_summary_requires_success_and_identity_token(release, success, matched):
    summary = dict(success=success, player_profile={'expected_name_token_satisfied': matched})
    assert subject.summary_matches(summary, release, profile=True) is (success and matched)


def test_low_disk_refuses_before_copy_or_workspace_writes(release, monkeypatch, tmp_path):
    release.release_id = 'release'
    release.game_path = tmp_path / 'sealed'
    release.inventory_path = tmp_path / 'inventory.json'
    (release.game_path / 'DBDAT').mkdir(parents=True)
    (release.game_path / 'DBDAT/JUG98030.FDI').write_bytes(b'sealed')
    monkeypatch.setattr(subject.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(subject.registry, 'load_registered_release', lambda *a: release)
    monkeypatch.setattr(subject.pipeline, 'read_json_file', lambda _: {
        'files': [{'path': 'DBDAT/JUG98030.FDI'}]})
    monkeypatch.setattr(subject.pipeline, 'assert_tree_matches_inventory', lambda *a: None)
    monkeypatch.setattr(subject.shutil, 'disk_usage', lambda _: SimpleNamespace(free=subject.RESERVE))
    with pytest.raises(ValueError, match='8GiB'):
        subject.capture('2000-01', 'release', 'safe_tag')
    assert not (tmp_path / '.local').exists()
    assert (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes() == b'sealed'
