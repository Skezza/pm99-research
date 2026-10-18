import copy
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import season_boreham_opening_repair_v1 as layer


def test_wrong_year_rejected_before_io():
    with pytest.raises(ValueError, match='Boreham2017'):
        layer.prepare(SimpleNamespace(season='2016-17'))


def test_retained_real_club_restores_young_ryan_without_touching_other_club():
    assert layer.CLUB == 3304
    assert layer.REPLACE[10859] == 'Michael Folivi'
    assert 'Ryan Johnson' not in layer.KEEP
    assert not set(layer.REPLACE) & set(layer.KEEP.values())
    assert len(layer.REPLACE) + len(layer.KEEP) == 18
    assert layer.KEEP['Fred Burbidge'] == 10860
    assert layer.KEEP['Bradley Ash'] == 10856


def test_retained_spelling_bridges_are_explicit_not_fuzzy():
    assert layer.PREIMAGE_ALIASES == {'Dan Woodards':'Danny Woodards', 'Shaun Jeffers':'Sean Jeffers'}


@pytest.mark.parametrize('field', ['orders', 'replacements', 'supplemental_sources',
    'retained_primary_role_updates', 'starting_xi', 'capacity_policy_bundle',
    'provider_link_adjudication'])
def test_source_replay_rejects_changed_plan(monkeypatch, field):
    expected = dict(schema=layer.SCHEMA, season='2017-18')
    monkeypatch.setattr(layer, 'prepare', lambda _: copy.deepcopy(expected))
    layer.verify('baseline', expected)
    with pytest.raises(ValueError, match='does not reproduce'):
        layer.verify('baseline', dict(expected, **{field: 'changed'}))


def test_unknown_schema_rejected():
    with pytest.raises(ValueError): layer.filename({'schema': 'arbitrary-swap'})


def test_recipe_edit_rejected_before_composer(monkeypatch):
    monkeypatch.setattr(layer.delta, 'updated_package', lambda *a: pytest.fail('must reject first'))
    with pytest.raises(ValueError, match='preimage'):
        layer.bind({'edited': True}, {'package_canonical_sha256': 'wrong'})


def test_eq_edit_rejected_before_compiler(tmp_path, monkeypatch):
    db = tmp_path / 'game/DBDAT'; db.mkdir(parents=True)
    (db/'JUG98030.FDI').write_bytes(b'baseline')
    monkeypatch.setattr(layer.registry, 'load_registered_release', lambda *a: SimpleNamespace(game_path=db.parent))
    monkeypatch.setattr(layer.delta, 'compile_players', lambda *a: pytest.fail('reject first'))
    with pytest.raises(ValueError, match='baseline changed'):
        layer.apply(b'baseline', b'edited', dict(season='2017-18', release_id='base',
            jug_sha256=layer.core.digest(b'baseline'), eq_sha256=layer.core.digest(b'original')))


def test_factory_cannot_drop_source_layer(monkeypatch):
    from scripts import season_package_compiler_v2 as compiler
    monkeypatch.setattr(compiler, '_load_native_package', lambda _: (
        {'artifacts': [{'id':layer.PREFIX+'2017-18'}]}, 'hash'))
    monkeypatch.setattr(compiler, '_ensure_clean_database_inputs', lambda **k: pytest.fail('reject before IO'))
    with pytest.raises(compiler.SeasonCompilerError, match='Boreham'):
        compiler.compile_package_to_tree(package_path=Path('recipe'), base_tree=Path('base'), materialisation_tree=Path('output'))


def test_normal_reconstruction_dispatch(monkeypatch,tmp_path):
    from scripts import season_profile_assignment_pruning_layer_v1 as reserve
    path=tmp_path/'plan';previous=SimpleNamespace(package_path=tmp_path/'recipe',locator={'sourced_profile_assignment_plan_path':str(path)})
    monkeypatch.setattr(reserve.pipeline,'read_json_file',lambda p:{'schema':layer.SCHEMA} if p==path else {})
    monkeypatch.setattr(layer,'reconstruction',lambda p,id:{'source_replayed':True})
    assert reserve.reconstruction(previous,'replay')=={'source_replayed':True}
