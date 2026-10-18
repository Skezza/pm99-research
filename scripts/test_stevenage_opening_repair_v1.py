import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import season_stevenage_opening_repair_v1 as layer


def test_wrong_year_is_rejected_before_any_source_or_game_read():
    with pytest.raises(ValueError, match='Stevenage 2002 only'):
        layer.prepare(SimpleNamespace(season='2003-04'))


def test_kept_midson_is_not_the_later_season_displaced_midson():
    assert layer.KEEP['Jack Midson'] == 10922
    assert layer.REPLACE[10926] == 'Jack Midson'
    assert len(layer.REPLACE) == 8 and len(layer.KEEP) == 10
    assert not set(layer.REPLACE) & set(layer.KEEP.values())


@pytest.mark.parametrize('field', ['orders', 'birthday_updates', 'replacements', 'supplemental_sources',
                                'retained_primary_role_updates', 'starting_xi', 'capacity_policy_bundle'])
def test_modified_plan_is_rejected_by_independent_source_replay(monkeypatch, field):
    expected = dict(schema=layer.SCHEMA, season='2002-03')
    monkeypatch.setattr(layer, 'prepare', lambda _: copy.deepcopy(expected))
    layer.verify('baseline', expected)
    with pytest.raises(ValueError, match='does not reproduce'):
        layer.verify('baseline', dict(expected, **{field: 'changed'}))


def test_unknown_schema_cannot_use_filename():
    assert layer.filename(dict(schema=layer.SCHEMA)) == layer.FILENAME
    with pytest.raises(ValueError): layer.filename(dict(schema='arbitrary-roster-swap'))


def test_recipe_edit_refused_before_fact_composer(monkeypatch):
    monkeypatch.setattr(layer.delta, 'updated_package', lambda *a: pytest.fail('must reject first'))
    with pytest.raises(ValueError, match='recipe preimage'):
        layer.bind({'unrelated': 'edit'}, {'package_canonical_sha256': 'wrong'})


def test_native_eq_change_refused_before_compiler(tmp_path, monkeypatch):
    game = tmp_path / 'game/DBDAT'; game.mkdir(parents=True)
    (game/'JUG98030.FDI').write_bytes(b'baseline')
    monkeypatch.setattr(layer.registry, 'load_registered_release', lambda *a: SimpleNamespace(game_path=game.parent))
    monkeypatch.setattr(layer.delta, 'compile_players', lambda *a: pytest.fail('no compiler before guard'))
    with pytest.raises(ValueError, match='native baseline'):
        layer.compile_native(b'baseline', b'edited club', {}, {}, dict(season='2002-03', release_id='base',
            jug_sha256=layer.digest(b'baseline'), eq_sha256=layer.digest(b'original club')))


def test_changed_supplemental_hash_refused(tmp_path, monkeypatch):
    root = tmp_path / 'stevenage'; root.mkdir(); (root/'person.html').write_bytes(b'changed')
    monkeypatch.setattr(layer, 'ROOT', root)
    monkeypatch.setattr(layer.pipeline, 'read_json_file', lambda p: {'cache_files': [
        dict(cache_path='stevenage/person.html', sha256='wrong', url='https://example.org')]
        if p.name.startswith('stevenage-2002') else []})
    with pytest.raises(ValueError, match='historical source changed'): layer.supplemental('person.html')


def test_missing_supplemental_receipt_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(layer, 'ROOT', tmp_path/'stevenage')
    monkeypatch.setattr(layer.pipeline, 'read_json_file', lambda _: {'cache_files': []})
    with pytest.raises(ValueError, match='one original'): layer.supplemental('person.html')


def test_original_secondary_dates_reparsed_from_actual_cached_pages():
    if not layer.ROOT.exists(): pytest.skip('local original historical pages not installed')
    dates, proofs = layer.secondary_dates()
    assert dates == {'Phil Wilson': '1982-10-17', 'Stuart Fraser': '1980-01-09', 'Jamie Campbell': '1972-10-21'}
    assert len(proofs) == 3 and all(p['sha256'] and p['receipt_sha256'] for p in proofs)


def test_factory_rejects_before_any_native_io(monkeypatch):
    from scripts import season_package_compiler_v2 as compiler
    monkeypatch.setattr(compiler, '_load_native_package', lambda _: (
        {'artifacts': [{'id': layer.PREFIX+'2002-03'}]}, 'hash'))
    monkeypatch.setattr(compiler, '_ensure_clean_database_inputs', lambda **k: pytest.fail('reject before native IO'))
    with pytest.raises(compiler.SeasonCompilerError, match='Stevenage'):
        compiler.compile_package_to_tree(package_path=Path('recipe'), base_tree=Path('base'), materialisation_tree=Path('output'))


def test_normal_reconstruction_dispatches_new_schema(monkeypatch, tmp_path):
    from scripts import season_profile_assignment_pruning_layer_v1 as reserve
    path = tmp_path/'plan'
    previous = SimpleNamespace(package_path=tmp_path/'recipe', locator={'sourced_profile_assignment_plan_path': str(path)})
    monkeypatch.setattr(reserve.pipeline, 'read_json_file', lambda p: {'schema': layer.SCHEMA} if p == path else {})
    monkeypatch.setattr(layer, 'reconstruction', lambda p, id: {'Stevenage_replayed': True})
    assert reserve.reconstruction(previous, 'replay') == {'Stevenage_replayed': True}
