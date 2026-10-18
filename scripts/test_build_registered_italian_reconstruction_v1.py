"""Interface tests for guarded known-good reconstruction, not factory compile."""
import copy
import json
from types import SimpleNamespace

import pytest

from scripts import build_registered_quality_release_v1 as build
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import season_italian_opening_layer_v1 as italian


def fixture(tmp_path, monkeypatch):
    source_dir = tmp_path / 'source'; source_dir.mkdir()
    previous_dir = tmp_path / 'previous'; previous_dir.mkdir()
    rebuilt_dir = tmp_path / 'rebuilt'; rebuilt_dir.mkdir()
    baseline = SimpleNamespace(season='2006-07', release_id='r50',
        package_path=source_dir / 'season-package.json', game_path=source_dir / 'game',
        inventory_path=source_dir / 'inventory.json')
    previous = SimpleNamespace(season='2006-07', release_id='r54',
        package_path=previous_dir / 'season-package.json', game_path=previous_dir / 'game',
        inventory_path=previous_dir / 'inventory.json')
    rebuilt = SimpleNamespace(season='2006-07', release_id='rebuilt',
        package_path=rebuilt_dir / 'season-package.json', game_path=rebuilt_dir / 'game',
        inventory_path=rebuilt_dir / 'inventory.json',
        release_manifest_path=rebuilt_dir / 'manifest.json')
    source_package = {'artifacts': [], 'unrelated_fact': 'unchanged'}
    expected = {'artifacts': [{'id': italian.PREFIX + '2006-07-223'}],
                'unrelated_fact': 'unchanged'}
    baseline.package_path.write_text(json.dumps(source_package))
    previous.package_path.write_text(json.dumps(expected))
    for release in [baseline, previous, rebuilt]:
        (release.game_path / 'DBDAT').mkdir(parents=True)
        (release.game_path / build.DATABASE_FILES[0]).write_bytes(b'same JUG')
        release.inventory_path.write_text(json.dumps({'bound_to': release.release_id}))
    rebuilt.release_manifest_path.write_bytes(b'rebuilt manifest')
    plan = {'season': '2006-07', 'source_release_id': 'r50'}
    descriptor = {'season': '2006-07', 'release_id': 'r50',
        'package_sha256': build.registry.sha256_file(baseline.package_path),
        'jug_sha256': build.registry.sha256_file(baseline.game_path / build.DATABASE_FILES[0]),
        'updates': [], 'unresolved': []}
    (previous_dir / 'role-delta-input.json').write_text(json.dumps(descriptor))
    (previous_dir / italian.FILENAME).write_text(json.dumps(plan))
    calls, inventory_calls = [], []
    monkeypatch.setattr(italian, 'layers', lambda package, path: [copy.deepcopy(plan)])
    monkeypatch.setattr(italian, 'bind', lambda package, parsed_plan: copy.deepcopy(expected))
    monkeypatch.setattr(build.registry, 'load_registered_release',
                        lambda season, id: baseline if id == 'r50' else rebuilt)
    monkeypatch.setattr(build.pipeline, 'assert_tree_matches_inventory',
                        lambda path, inventory: inventory_calls.append((path, inventory)))
    monkeypatch.setattr(publisher, 'publish', lambda *args, **kwargs:
                        calls.append((args, kwargs)) or {'release_id': kwargs['release_id']})
    return SimpleNamespace(previous=previous, baseline=baseline, rebuilt=rebuilt,
        expected=expected, plan=plan, descriptor=descriptor, calls=calls,
        inventory_calls=inventory_calls)


def test_exact_recipe_reconstructs_from_explicit_source_without_registering(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    result = build._build_italian_reconstruction(f.previous, release_id='rebuilt')
    assert f.calls == [(('2006-07', f.previous.package_path.parent / 'role-delta-input.json'),
        {'release_id': 'rebuilt', 'register': False,
         'italian_opening_plan_path': f.previous.package_path.parent / italian.FILENAME,
         'source_release_id': 'r50'})]
    assert f.inventory_calls == [
        (f.baseline.game_path, {'bound_to': 'r50'}),
        (f.previous.game_path, {'bound_to': 'r54'}),
        (f.rebuilt.game_path, {'bound_to': 'r54'})]
    assert result['release_manifest_sha256'] == build.registry.sha256_file(f.rebuilt.release_manifest_path)
    assert result['compilation_mode'] == 'source-bound-known-good-reconstruction-not-factory-compile'
    assert result['complete_game_inventory_identical'] is True
    assert result['source_release_id'] == 'r50'
    assert result['previous_release_id'] == 'r54'
    assert result['reused'] is False


def test_ordinary_recipe_does_not_enter_reconstruction(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    f.previous.package_path.write_text(json.dumps({'artifacts': [{'id': 'ordinary-input'}]}))
    monkeypatch.setattr(italian, 'layers', lambda *args: pytest.fail('ordinary package must not read Italian layers'))
    assert build._build_italian_reconstruction(f.previous, release_id='rebuilt') is None
    assert f.calls == f.inventory_calls == []


@pytest.mark.parametrize('edit', ['unrelated_fact', 'new_editorial_field', 'artifact'])
def test_any_unapproved_recipe_edit_refuses_before_publication(tmp_path, monkeypatch, edit):
    f = fixture(tmp_path, monkeypatch)
    changed = copy.deepcopy(f.expected)
    if edit == 'unrelated_fact': changed['unrelated_fact'] = 'editor change'
    if edit == 'new_editorial_field': changed['editorial'] = 'do not silently discard'
    if edit == 'artifact': changed['artifacts'].append({'id': 'new-input'})
    f.previous.package_path.write_text(json.dumps(changed))
    with pytest.raises(build.QualityBuildError, match='no edits discarded'):
        build._build_italian_reconstruction(f.previous, release_id='rebuilt')
    assert f.calls == f.inventory_calls == []


def test_source_layer_validation_failure_is_not_fallback_to_factory(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    def invalid(*args):
        raise ValueError('original source bytes or recipe-local plan changed')
    monkeypatch.setattr(italian, 'layers', invalid)
    with pytest.raises(ValueError, match='source bytes'):
        build._build_italian_reconstruction(f.previous, release_id='rebuilt')
    assert f.calls == []


@pytest.mark.parametrize('count', [0, 2])
def test_exactly_one_explicit_verified_layer_required(tmp_path, monkeypatch, count):
    f = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(italian, 'layers', lambda *args: [f.plan] * count)
    with pytest.raises(build.QualityBuildError, match='exactly one'):
        build._build_italian_reconstruction(f.previous, release_id='rebuilt')
    assert f.calls == []


@pytest.mark.parametrize('which', ['baseline', 'previous', 'rebuilt'])
def test_entire_game_inventory_drift_refuses_not_just_database_hashes(tmp_path, monkeypatch, which):
    f = fixture(tmp_path, monkeypatch)
    bad_path = getattr(f, which).game_path
    def check(path, inventory):
        if path == bad_path:
            raise ValueError('whole game inventory mismatch: bitmap or manager.ini')
    monkeypatch.setattr(build.pipeline, 'assert_tree_matches_inventory', check)
    with pytest.raises(ValueError, match='whole game inventory mismatch'):
        build._build_italian_reconstruction(f.previous, release_id='rebuilt')
    assert len(f.calls) == (1 if which == 'rebuilt' else 0)


@pytest.mark.parametrize('problem', ['missing', 'wrong-source', 'wrong-hash', 'nonempty-update'])
def test_inert_reconstruction_descriptor_is_mandatory_and_exact(tmp_path, monkeypatch, problem):
    f = fixture(tmp_path, monkeypatch)
    path = f.previous.package_path.parent / 'role-delta-input.json'
    value = copy.deepcopy(f.descriptor)
    if problem == 'missing': path.unlink()
    if problem == 'wrong-source': value['release_id'] = 'not-r50'
    if problem == 'wrong-hash': value['jug_sha256'] = '0' * 64
    if problem == 'nonempty-update': value['updates'] = [{'carrier_id': 1}]
    if problem != 'missing': path.write_text(json.dumps(value))
    with pytest.raises(build.QualityBuildError, match='descriptor missing or changed'):
        build._build_italian_reconstruction(f.previous, release_id='rebuilt')
    assert f.calls == []


def test_publication_failure_propagates_without_registration(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    def fail(*args, **kwargs):
        assert kwargs['register'] is False
        raise ValueError('native preimage changed')
    monkeypatch.setattr(publisher, 'publish', fail)
    with pytest.raises(ValueError, match='native preimage'):
        build._build_italian_reconstruction(f.previous, release_id='rebuilt')


def test_normal_build_dispatches_reconstruction_before_factory_composition(monkeypatch):
    isolate_newer_dispatchers(monkeypatch)
    previous = SimpleNamespace(season='2006-07', release_id='r54')
    expected = {'release_id': 'new-rebuild', 'compilation_mode': 'bounded'}
    calls = []
    monkeypatch.setattr(build.registry, 'load_preferred_release', lambda season: previous)
    monkeypatch.setattr(build, '_build_italian_reconstruction', lambda p, **kwargs:
                        calls.append((p, kwargs)) or expected)
    monkeypatch.setattr(build.composition, 'compose', lambda *args: pytest.fail('must not use factory composition'))
    assert build.build('2006-07', release_id='new-rebuild') == expected
    assert calls == [(previous, {'release_id': 'new-rebuild'})]


def test_normal_non_Italian_build_still_reaches_existing_factory_composition(tmp_path, monkeypatch):
    isolate_newer_dispatchers(monkeypatch)
    monkeypatch.setattr(build, 'ROOT', tmp_path)
    monkeypatch.setattr(build.registry, 'load_preferred_release', lambda season: SimpleNamespace())
    monkeypatch.setattr(build.registry, 'locator_path', lambda *args: tmp_path / 'locator' / 'entry.json')
    monkeypatch.setattr(build, '_build_italian_reconstruction', lambda *args, **kwargs: None)
    def factory(season):
        raise RuntimeError('existing strict factory entry reached')
    monkeypatch.setattr(build.composition, 'compose', factory)
    with pytest.raises(RuntimeError, match='strict factory'):
        build.build('2001-02', release_id='normal-build')


def isolate_newer_dispatchers(monkeypatch):
    # These synthetic releases test the older Italian/manager precedence,
    # not newer foreign/artwork/biographic transactions. Real release readers
    # require complete receipt paths; do not weaken them to accept stubs.
    from scripts import season_foreign_fixed_roster_delta_v1,season_visual_patch_reconstruction_v1
    from scripts import season_number_label_names_v2,season_original_person_birth_years_v1
    from scripts import season_cross_period_birth_years_v1,season_biographic_birth_years_v1
    from scripts import season_paired_whole_club_reconstruction_v1
    from scripts import season_donor_keeper_role_delta_v1,season_cross_club_reserve_repair_v1
    from scripts import season_2015_english_fifa_roles_v1,season_exact_fifa_role_delta_v2
    from scripts import season_exact_fifa_role_delta_v1,season_quality_only_delta_v1
    from scripts import season_original_alias_countries_v1,season_stoke_commons_number_v1
    from scripts import season_shtanyuk_2002_coupled_alias_v1,season_stoke_original_alias_reserve_v1
    from scripts import season_resolved_period_country_v3,season_original_country_policy_v2
    from scripts import season_exact_primary_position_delta_v1,season_exact_primary_position_delta_v2
    from scripts import season_morecambe_2000_owned_opening_v1
    for module in (season_foreign_fixed_roster_delta_v1,season_visual_patch_reconstruction_v1,
            season_number_label_names_v2,season_original_person_birth_years_v1,
            season_cross_period_birth_years_v1,season_biographic_birth_years_v1,
            season_paired_whole_club_reconstruction_v1,season_donor_keeper_role_delta_v1,
            season_cross_club_reserve_repair_v1,season_2015_english_fifa_roles_v1,
            season_exact_fifa_role_delta_v2,season_exact_fifa_role_delta_v1,season_quality_only_delta_v1,
            season_original_alias_countries_v1,season_stoke_commons_number_v1,
            season_shtanyuk_2002_coupled_alias_v1,season_stoke_original_alias_reserve_v1,
            season_resolved_period_country_v3,season_original_country_policy_v2,
            season_exact_primary_position_delta_v1,season_exact_primary_position_delta_v2,
            season_morecambe_2000_owned_opening_v1):
        monkeypatch.setattr(module,'reconstruction',lambda *a,**k:None)


def test_resume_returns_verified_completed_build_without_reconstructing(monkeypatch):
    completed = {'release_id': 'already-built', 'reused': True}
    monkeypatch.setattr(build, '_reuse_completed', lambda *args: completed)
    monkeypatch.setattr(build.registry, 'load_preferred_release',
                        lambda *args: pytest.fail('verified resume must not reload source'))
    monkeypatch.setattr(build, '_build_italian_reconstruction',
                        lambda *args, **kwargs: pytest.fail('verified resume must not regenerate'))
    assert build.build('2006-07', release_id='already-built', resume=True) == completed


@pytest.mark.parametrize('register,plan_path', [(True, 'Italian-plan.json'), (False, None)])
def test_explicit_source_publication_cannot_register_or_use_unrelated_lane(monkeypatch, register, plan_path):
    monkeypatch.setattr(publisher.registry, 'load_registered_release', lambda *args: SimpleNamespace())
    with pytest.raises(ValueError, match='unregistered Italian or manager-only replay'):
        publisher.publish('2006-07', None, release_id='rebuilt', register=register,
                          italian_opening_plan_path=plan_path, source_release_id='r50')
