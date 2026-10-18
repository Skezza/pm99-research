import copy
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import season_barrow_opening_repair_v1 as layer


def test_wrong_season_fails_before_io():
    with pytest.raises(ValueError, match='Barrow2012'):
        layer.prepare(SimpleNamespace(season='2013-14'))


def test_exact_reviewed_slots_preserve_the_legitimate_young_rowe():
    assert layer.REPLACE[11225] == 'Danny Rowe'
    assert layer.KEEP['Danny Rowe'] == 11218
    assert not set(layer.REPLACE) & set(layer.KEEP.values())
    assert len(layer.REPLACE) + len(layer.KEEP) == 18
    assert layer.BENCH_IDS['Shaun Pearson'] == 176322  # NOT Grimsby's146786.


@pytest.mark.parametrize('field', ['orders', 'replacements', 'source_authoring_opening',
    'original_opening', 'published_person_binding', 'capacity_policy_bundle'])
def test_source_replay_rejects_modified_adjudication(monkeypatch, field):
    expected = dict(schema=layer.SCHEMA, season='2012-13')
    monkeypatch.setattr(layer, 'prepare', lambda _: copy.deepcopy(expected))
    layer.verify('baseline', expected)
    with pytest.raises(ValueError, match='does not reproduce'):
        layer.verify('baseline', dict(expected, **{field:'changed'}))


def test_recipe_preimage_is_checked_before_composition(monkeypatch):
    monkeypatch.setattr(layer.native.delta, 'updated_package', lambda *a: pytest.fail('reject first'))
    with pytest.raises(ValueError, match='preimage'):
        layer.bind({'edited':True}, {'package_canonical_sha256':'wrong'})


def test_factory_compile_cannot_silently_drop_opening_layer(monkeypatch):
    from scripts import season_package_compiler_v2 as compiler
    monkeypatch.setattr(compiler, '_load_native_package', lambda _: (
        {'artifacts':[{'id':layer.PREFIX+'2012-13'}]}, 'hash'))
    monkeypatch.setattr(compiler, '_ensure_clean_database_inputs', lambda **k: pytest.fail('reject before IO'))
    with pytest.raises(compiler.SeasonCompilerError, match='Barrow'):
        compiler.compile_package_to_tree(package_path=Path('recipe'),base_tree=Path('base'),materialisation_tree=Path('output'))


def test_normal_reconstruction_dispatch(monkeypatch, tmp_path):
    from scripts import season_profile_assignment_pruning_layer_v1 as reserve
    path = tmp_path/'plan'
    previous = SimpleNamespace(package_path=tmp_path/'recipe',locator={'sourced_profile_assignment_plan_path':str(path)})
    monkeypatch.setattr(reserve.pipeline,'read_json_file',lambda p:{'schema':layer.SCHEMA} if p==path else {})
    monkeypatch.setattr(layer,'reconstruction',lambda p,id:{'source_replayed':True})
    assert reserve.reconstruction(previous,'replay') == {'source_replayed':True}
