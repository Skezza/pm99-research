import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts import season_trabzon_opening_layer_v1 as layer


def recipe():
    club = {'id': 'club-1002', 'carrier_id': 1002,
            'roster_player_ids': ['p8052', 'p32505']}
    package = {'clubs': [club, {'id': 'other', 'roster_player_ids': ['other']}],
               'players': [{'id': 'p8052', 'carrier_id': 8052},
                           {'id': 'p32505', 'carrier_id': 32505},
                           {'id': 'other', 'carrier_id': 11}],
               'artifacts': [{'id': 'existing-milan-layer', 'relative_path': 'milan.json'}],
               'portraits': [{'player_id': 'p32505'}, {'player_id': 'p8052'}]}
    plan = {'schema': layer.source.SCHEMA, 'season': '2000-01', 'club_id': 'club-1002',
            'before_club': copy.deepcopy(club)}
    return package, plan


def test_bind_changes_only_removed_person_and_source_artifact(monkeypatch):
    package, plan = recipe()
    original = copy.deepcopy(package)
    monkeypatch.setattr(layer.packages, 'validate_package', lambda p: None)
    result = layer.bind(package, plan)
    assert package == original
    assert result['clubs'][0]['roster_player_ids'] == ['p8052']
    assert result['players'] == [package['players'][0], package['players'][2]]
    assert result['clubs'][1] == package['clubs'][1]
    assert result['portraits'] == [{'player_id': 'p8052'}]
    assert result['artifacts'][0] == package['artifacts'][0]
    assert result['artifacts'][1]['sha256'] == hashlib.sha256(layer.packages.canonical_json_bytes(plan)).hexdigest()


@pytest.mark.parametrize('problem', ['wrong-club-preimage', 'missing-removed', 'shared-removed',
                                   'duplicate-layer', 'unsupported-season', 'unsupported-schema'])
def test_bind_refuses_unapproved_or_conflicting_recipe(monkeypatch, problem):
    package, plan = recipe()
    monkeypatch.setattr(layer.packages, 'validate_package', lambda p: None)
    if problem == 'wrong-club-preimage': package['clubs'][0]['name'] = 'edited'
    if problem == 'missing-removed':
        package['clubs'][0]['roster_player_ids'].remove('p32505')
        plan['before_club'] = copy.deepcopy(package['clubs'][0])
    if problem == 'shared-removed': package['clubs'][1]['roster_player_ids'].append('p32505')
    if problem == 'duplicate-layer': package['artifacts'].append({'id': layer.PREFIX + '2000-01-1002'})
    if problem == 'unsupported-season': plan['season'] = '2001-02'
    if problem == 'unsupported-schema': plan['schema'] = 'guessed'
    with pytest.raises(ValueError): layer.bind(package, plan)


def test_verify_independently_rederives_source_not_just_receipt_hash(monkeypatch):
    plan = {'schema': layer.source.SCHEMA, 'orders': []}
    monkeypatch.setattr(layer.source, 'prepare', lambda r: copy.deepcopy(plan))
    layer.verify('baseline', plan)
    tampered = dict(plan, orders=[{'carrier_id': 32505}])
    with pytest.raises(ValueError, match='does not reproduce'): layer.verify('baseline', tampered)


def test_apply_requires_exact_source_native_hashes_before_writer(monkeypatch):
    monkeypatch.setattr(layer.native, 'roster_rows', lambda eq, club: (None, b'raw', [(32505, 0)]))
    plan = dict(schema=layer.source.SCHEMA, club_carrier_id=1002, season='2000-01',
        removed_link=32505, before_rows=[[32505, 0]], after_rows=[], eq_sha256='stale', jug_sha256='stale')
    with pytest.raises(ValueError, match='baseline preimage changed'): layer.apply(b'jug', b'eq', plan)


def test_apply_refuses_non_reviewed_roster_preimage(monkeypatch):
    monkeypatch.setattr(layer.native, 'roster_rows', lambda eq, club: (None, b'raw', [(88, 0)]))
    plan = dict(schema=layer.source.SCHEMA, club_carrier_id=1002, season='2000-01',
        removed_link=32505, before_rows=[[32505, 0]], after_rows=[])
    with pytest.raises(ValueError, match='roster preimage changed'): layer.apply(b'jug', b'eq', plan)


def test_apply_refuses_other_club_or_removal_without_writing():
    plan = dict(schema=layer.source.SCHEMA, club_carrier_id=201, season='2000-01', removed_link=32505)
    with pytest.raises(ValueError, match='unsupported'): layer.apply(b'jug', b'eq', plan)


def reconstruction_fixture(tmp_path, monkeypatch):
    from scripts import season_pipeline_v2 as pipeline, publish_historical_role_delta_v1 as publisher
    source_dir = tmp_path / 'source'; source_dir.mkdir()
    previous_dir = tmp_path / 'previous'; previous_dir.mkdir()
    baseline = SimpleNamespace(season='2000-01', release_id='r54', package_path=source_dir/'package.json',
        game_path=source_dir/'game', inventory_path=source_dir/'inventory.json')
    previous = SimpleNamespace(season='2000-01', release_id='r57', package_path=previous_dir/'package.json',
        game_path=previous_dir/'game', inventory_path=previous_dir/'inventory.json')
    rebuilt = SimpleNamespace(game_path=tmp_path/'rebuilt', release_manifest_path=tmp_path/'manifest.json')
    plan = {'release_id': 'r54'}
    plan_path = previous_dir/layer.FILENAME
    plan_path.write_bytes(layer.packages.canonical_json_bytes(plan))
    expected = {'artifacts': [{'id': layer.PREFIX+'2000-01-1002', 'relative_path': layer.FILENAME,
        'sha256': layer.registry.sha256_file(plan_path)}], 'unchanged': 'all other recipe facts'}
    baseline.package_path.write_text(json.dumps({'source': True}))
    previous.package_path.write_text(json.dumps(expected))
    for release in (baseline, previous):
        (release.game_path/'DBDAT').mkdir(parents=True)
        (release.game_path/'DBDAT/JUG98030.FDI').write_bytes(b'bound')
        release.inventory_path.write_text(json.dumps({'release': release.release_id}))
    rebuilt.release_manifest_path.write_bytes(b'new manifest')
    descriptor = dict(season='2000-01', release_id='r54',
        package_sha256=layer.registry.sha256_file(baseline.package_path),
        jug_sha256=layer.registry.sha256_file(baseline.game_path/'DBDAT/JUG98030.FDI'), updates=[], unresolved=[])
    (previous_dir/'role-delta-input.json').write_text(json.dumps(descriptor))
    calls, inventories = [], []
    monkeypatch.setattr(layer, 'verify', lambda r, p: None)
    monkeypatch.setattr(layer, 'bind', lambda p, plan: copy.deepcopy(expected))
    monkeypatch.setattr(layer.registry, 'load_registered_release', lambda s, id: baseline if id=='r54' else rebuilt)
    monkeypatch.setattr(pipeline, 'assert_tree_matches_inventory', lambda path, i: inventories.append((path, i)))
    monkeypatch.setattr(publisher, 'publish', lambda *a, **k: calls.append((a, k)))
    return previous, expected, calls, inventories


def test_normal_reconstruction_preserves_entire_game_and_does_not_register(tmp_path, monkeypatch):
    previous, expected, calls, inventories = reconstruction_fixture(tmp_path, monkeypatch)
    result = layer.reconstruction(previous, 'rebuild')
    assert result['complete_game_inventory_identical']
    assert calls[0][1]['register'] is False
    assert calls[0][1]['source_release_id'] == 'r54'
    assert calls[0][1]['trabzon_opening_plan_path'].name == layer.FILENAME
    assert len(inventories) == 3


@pytest.mark.parametrize('problem', ['recipe-edit', 'artifact-hash', 'wrong-descriptor', 'missing-descriptor'])
def test_reconstruction_never_discards_edits_or_uses_stale_inputs(tmp_path, monkeypatch, problem):
    previous, expected, calls, inventories = reconstruction_fixture(tmp_path, monkeypatch)
    if problem == 'recipe-edit':
        changed = copy.deepcopy(expected); changed['unchanged'] = 'user edit'
        previous.package_path.write_text(json.dumps(changed))
    if problem == 'artifact-hash': (previous.package_path.parent/layer.FILENAME).write_text('{}')
    descriptor = previous.package_path.parent/'role-delta-input.json'
    if problem == 'wrong-descriptor': descriptor.write_text('{}')
    if problem == 'missing-descriptor': descriptor.unlink()
    with pytest.raises((ValueError, OSError)): layer.reconstruction(previous, 'rebuild')
    assert calls == []


def test_normal_build_dispatches_trabzon_before_factory_and_italian(monkeypatch):
    from scripts import build_registered_quality_release_v1 as builder
    previous = SimpleNamespace(season='2000-01')
    monkeypatch.setattr(builder.registry, 'load_preferred_release', lambda s: previous)
    expected = {'complete_game_inventory_identical': True}
    monkeypatch.setattr(layer, 'reconstruction', lambda p, id: expected)
    monkeypatch.setattr(builder, '_build_italian_reconstruction', lambda *a, **k: pytest.fail('wrong replay layer'))
    assert builder.build('2000-01', release_id='rebuild') == expected


def test_raw_factory_compile_must_not_silently_ignore_known_good_only_layer():
    layer.reject_factory_recipe({'artifacts': [{'id': 'ordinary'}]})
    with pytest.raises(ValueError, match='must not silently drop'):
        layer.reject_factory_recipe({'artifacts': [{'id': layer.PREFIX+'2000-01-1002'}]})


def test_factory_guard_runs_before_any_database_io(monkeypatch):
    from scripts import season_package_compiler_v2 as compiler
    monkeypatch.setattr(compiler, '_load_native_package', lambda p:
        ({'artifacts': [{'id': layer.PREFIX+'2000-01-1002'}]}, 'hash'))
    monkeypatch.setattr(compiler, '_ensure_clean_database_inputs', lambda **k: pytest.fail('no native files may be touched'))
    with pytest.raises(compiler.SeasonCompilerError, match='known-good reconstruction'):
        compiler.compile_package_to_tree(package_path='recipe', base_tree='base', materialisation_tree='output')


def test_v2_recipe_updates_only_explicit_primary_roles_and_retains_other_facts(monkeypatch):
    package, plan = recipe()
    package['players'][0]['facts'] = {'fine_roles': [0], 'birth_date': '1974-05-07', 'height_cm': 180}
    plan.update(schema=layer.ROLE_SCHEMA, primary_role_policy=layer.ROLE_POLICY,
        primary_role_changes=[{'player_id': 'p8052', 'recipe_fine_roles_before': [0],
                              'recipe_fine_roles_after': [9]}])
    monkeypatch.setattr(layer.packages, 'validate_package', lambda p: None)
    result = layer.bind(package, plan)
    assert result['players'][0]['facts'] == {'fine_roles': [9], 'birth_date': '1974-05-07', 'height_cm': 180}
    assert package['players'][0]['facts']['fine_roles'] == [0]


@pytest.mark.parametrize('problem', ['v1-unauthorised-roles', 'unversioned-policy', 'recipe-preimage'])
def test_role_recipe_cannot_launder_unapproved_or_stale_changes(monkeypatch, problem):
    package, plan = recipe()
    package['players'][0]['facts'] = {'fine_roles': [0]}
    plan.update(schema=layer.ROLE_SCHEMA, primary_role_policy=layer.ROLE_POLICY,
        primary_role_changes=[{'player_id': 'p8052', 'recipe_fine_roles_before': [0], 'recipe_fine_roles_after': [9]}])
    if problem == 'v1-unauthorised-roles': plan['schema'] = layer.source.SCHEMA
    if problem == 'unversioned-policy': plan['primary_role_policy'] = 'unreviewed'
    if problem == 'recipe-preimage': package['players'][0]['facts']['fine_roles'] = [14]
    monkeypatch.setattr(layer.packages, 'validate_package', lambda p: None)
    with pytest.raises(ValueError): layer.bind(package, plan)
