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


def test_profile_can_search_published_surname_without_changing_identity(release, monkeypatch):
    monkeypatch.setattr(subject.pipeline, 'read_json_file', lambda _: {
        'players': [dict(carrier_id=19, name='Rubén de la Red')]})
    args = subject.driver_args(release, carrier=19, label='ruben', token='Red',
                               search_text='DE LA RED')
    steps = [args[i + 1] for i, value in enumerate(args[:-1]) if value == '--post-step']
    assert len([step for step in steps if step.startswith('name_ruben_')]) == len('DE LA RED')
    assert not any('CP1252:' in step for step in steps)
    assert args[args.index('--expected-profile-token') + 1] == 'Red'


@pytest.mark.parametrize('text', ['', 'x\n', 'x' * 65])
def test_profile_search_rejects_empty_controls_or_overlong_text(release, text):
    with pytest.raises(ValueError, match='printable player-search'):
        subject.driver_args(release, carrier=19, label='ruben', token='Red', search_text=text)


def test_search_override_cannot_change_a_startup_route(release):
    with pytest.raises(ValueError, match='profile carrier'):
        subject.driver_args(release, search_text='DE LA RED')


def plymouth_selector():
    return dict(club_carrier_id=385, team_name='Plymouth Argyle',
                division_select_x=562, division_select_y=302,
                team_select_x=209, team_select_y=360)


def test_explicit_club_route_binds_native_carrier_and_generic_driver(release, monkeypatch):
    from scripts import season_duplicate_ownership_plan_v1 as layers
    monkeypatch.setattr(layers, 'package_layers', lambda _: [
        ('main', {'clubs': [dict(carrier_id=385, name='Plymouth Argyle')]}, None)])
    args = subject.driver_args(release, selector=plymouth_selector())
    assert args[args.index('--team-name') + 1] == 'Plymouth Argyle'
    assert args[args.index('--team-select-x') + 1] == '209'
    assert args[args.index('--proof-mode') + 1] == 'generic_club_route_capture'
    with pytest.raises(ValueError, match='exact registered recipe club'):
        subject.driver_args(release, selector=dict(plymouth_selector(), team_name='Stoke City'))


@pytest.mark.parametrize('field,value', [('team_select_x', True),
    ('team_select_y', 480), ('division_select_x', -1)])
def test_explicit_club_selector_refuses_bad_coordinates_before_recipe(release, field, value):
    with pytest.raises(ValueError, match='coordinate'):
        subject.driver_args(release, selector=dict(plymouth_selector(), **{field: value}))


@pytest.mark.parametrize('fault', [None, 'name', 'coordinates', 'observed', 'mode'])
def test_explicit_club_summary_cannot_accept_stoke_or_wrong_grid(release, fault):
    selector = plymouth_selector()
    summary = dict(success=True, release_manifest_sha256='manifest',
        output_inventory_fingerprint='inventory', phase_reached='return_from_line_up',
        mode='generic-club-route-capture', team_name='Plymouth Argyle',
        team_selection={k: selector[k] for k in ('division_select_x', 'division_select_y', 'team_select_x', 'team_select_y')},
        route_summaries={'line_up': {'team_identity': dict(expected='Plymouth Argyle',
            expected_normalized='plymouth argyle', observed_normalized='plymouth argyle', matched=True)}})
    if fault == 'name': summary['team_name'] = 'Stoke City'
    if fault == 'coordinates': summary['team_selection']['team_select_x'] = 306
    if fault == 'observed': summary['route_summaries']['line_up']['team_identity']['observed_normalized'] = 'stoke city'
    if fault == 'mode': summary['mode'] = 'stoke-route-capture'
    assert subject.summary_matches(summary, release, selector=selector) is (fault is None)


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


def test_explicit_second_namesake_search_row_is_not_silently_first(release, monkeypatch):
    monkeypatch.setattr(subject.pipeline, 'read_json_file', lambda _: {
        'players': [dict(carrier_id=16454, name='Yildirim')]})
    args = subject.driver_args(release, carrier=16454, label='yildirim', token='Yildirim', search_result_row=2)
    assert 'select_yildirim_row|native_input_click|120,182,1|1.0' in args


@pytest.mark.parametrize('row', [0, 11, -1, 1.5, True])
def test_invalid_search_row_refuses_before_recipe_access(release, monkeypatch, row):
    monkeypatch.setattr(subject.pipeline, 'read_json_file', lambda _: pytest.fail('recipe accessed'))
    with pytest.raises(ValueError, match='visible search result row'):
        subject.driver_args(release, carrier=1, label='player', token='Player', search_result_row=row)


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
    summary = dict(success=success, player_profile={'expected_name_token_satisfied': matched,
        'expected_name_token': 'riera', 'player_name_ocr_normalized': 'albert riera'})
    assert subject.summary_matches(summary, release, profile=True) is (success and matched)


@pytest.mark.parametrize('expected,name,accepted', [
    ('red', 'frederik v', False), ('red', 'brede hangeland', False),
    ('de la red', 'ruben de la red', True), ('haim', 'ben haim', True),
    ('', 'frederik v', False)])
def test_profile_match_requires_complete_name_words(release, expected, name, accepted):
    summary = dict(success=True, player_profile=dict(expected_name_token_satisfied=True,
        expected_name_token=expected, player_name_ocr_normalized=name))
    assert subject.summary_matches(summary, release, profile=True) is accepted


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
    with pytest.raises(ValueError, match=r'8\s?GiB'):
        subject.capture('2000-01', 'release', 'safe_tag')
    assert not (tmp_path / '.local').exists()
    assert (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes() == b'sealed'
