import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import season_contextual_tactics_v1 as tactics
from scripts import season_package_compiler_v2 as compiler
from scripts import season_package_v2 as package_v2
from scripts import season_pipeline_v2 as pipeline
from scripts.test_season_package_compiler_v2 import _write_fixture_base, _copy_base
from app.eq_initial_tactics import read_initial_tactics


def context():
    result = {'format': tactics.FORMAT, 'template_id': 'synthetic-context', 'slots': [
        {'player_id': f'player-{i:02d}', 'native_player_id': i, 'native_name': f'Target {chr(64 + i)}',
         'role': tactics.ROLES[i - 1],
         'states': [[70 + z, 80 + i, 100 + i, 200 + z] for z in range(20)]}
        for i in range(1, 12)]}
    result['slots'][0]['states'][0][3] = 0
    return result


def test_context_order_geometry_and_summary_fail_closed():
    valid = context()
    tactics.validate_context(valid, [f'player-{i:02d}' for i in range(1, 12)])
    assert tactics.summary_positions(valid)[0] == [79, 81, 101, 199]
    bad = copy.deepcopy(valid)
    bad['slots'][0], bad['slots'][1] = bad['slots'][1], bad['slots'][0]
    with pytest.raises(ValueError):
        tactics.validate_context(bad, [f'player-{i:02d}' for i in range(1, 12)])
    for field, value in [('format', 'unproven')]:
        bad = copy.deepcopy(valid); bad[field] = value
        with pytest.raises(ValueError):
            tactics.validate_context(bad)


def test_inline_recipe_context_roundtrip_survives_unrelated_edit(tmp_path):
    base, recipe = _write_fixture_base(tmp_path)
    package = json.loads(recipe.read_text())
    opening = package['clubs'][0]['opening']
    opening['tactics_context'] = context()
    opening['tactics_positions'] = tactics.summary_positions(context())
    package_v2.write_canonical_package(recipe, package)
    original = package_v2.read_canonical_package(recipe)
    assert original['clubs'][0]['opening']['tactics_context'] == context()
    first = _copy_base(base, tmp_path / 'first')
    receipt = compiler.compile_package_to_tree(package_path=recipe, base_tree=base, materialisation_tree=first)
    assert receipt['contextual_tactics_carriers'] == [307]
    original['managers'][0]['name'] = 'Different Manager'
    package_v2.write_canonical_package(recipe, original)
    second = _copy_base(base, tmp_path / 'second')
    compiler.compile_package_to_tree(package_path=recipe, base_tree=base, materialisation_tree=second)
    for tree in (first, second):
        raw = (tree / 'DBDAT/EQ98030.FDI').read_bytes()
        read = read_initial_tactics(tactics.payloads(raw)[307])
        assert read.states == tuple(tuple(tuple(s) for s in slot['states']) for slot in context()['slots'])


def test_recipe_rejects_conflicting_static_summary(tmp_path):
    base, recipe = _write_fixture_base(tmp_path)
    package = json.loads(recipe.read_text())
    package['clubs'][0]['opening']['tactics_context'] = context()
    with pytest.raises(package_v2.PackageValidationError, match='summary conflicts'):
        package_v2.validate_package(package)


def test_hash_bound_layer_reapplied_after_static_compiler_and_identity_mismatch_is_atomic(tmp_path):
    base, recipe = _write_fixture_base(tmp_path)
    package = json.loads(recipe.read_text())
    layer = {'schema_version': tactics.SCHEMA, 'season': '2015-16',
             'clubs': [{'carrier_id': 307, 'context': context(), 'restore_control_prefix': [90, 50],
                        'control_prefix_before': list(read_initial_tactics(tactics.payloads(
                            (base / 'DBDAT/EQ98030.FDI').read_bytes())[307]).controls[:2])}]}
    layer_path = tmp_path / 'context.json'
    layer_path.write_bytes(pipeline.canonical_json_bytes(layer))
    package['artifacts'].append({'id': 'contextual-tactics-2015-16', 'kind': 'season-input',
        'sha256': hashlib.sha256(layer_path.read_bytes()).hexdigest(), 'relative_path': 'context.json'})
    package['artifacts'].sort(key=lambda a: a['id'])
    package_v2.write_canonical_package(recipe, package)
    output = _copy_base(base, tmp_path / 'output')
    compiler.compile_package_to_tree(package_path=recipe, base_tree=base, materialisation_tree=output)
    raw = (output / 'DBDAT/EQ98030.FDI').read_bytes()
    jug = (output / 'DBDAT/JUG98030.FDI').read_bytes()
    assert tactics.apply_layer(raw, jug, layer) == raw
    read = read_initial_tactics(tactics.payloads(raw)[307])
    assert read.states[-1][-1] == (89, 91, 111, 219)
    assert read.controls[:2] == b'\x5a\x32'
    changed_controls = bytearray(raw)
    from app.fdi_indexed import IndexedFDIFile
    entry = next(e for e in IndexedFDIFile.from_bytes(raw).entries if e.record_id == 307)
    changed_controls[entry.payload_offset + read.grid_offset + tactics.GRID_BYTES] = 42
    with pytest.raises(ValueError, match='unrelated control'):
        tactics.apply_layer(bytes(changed_controls), jug, layer)
    layer['clubs'][0]['context']['slots'][0]['native_name'] = 'Wrong Player'
    layer_path.write_bytes(pipeline.canonical_json_bytes(layer))
    next(a for a in package['artifacts'] if a['id'].startswith('contextual-tactics-'))['sha256'] = hashlib.sha256(layer_path.read_bytes()).hexdigest()
    package_v2.write_canonical_package(recipe, package)
    rejected = _copy_base(base, tmp_path / 'rejected')
    before = pipeline.build_tree_inventory(rejected)
    with pytest.raises(ValueError, match='identity'):
        compiler.compile_package_to_tree(package_path=recipe, base_tree=base, materialisation_tree=rejected)
    assert pipeline.build_tree_inventory(rejected) == before


def test_artifact_hash_or_season_change_is_rejected(tmp_path):
    recipe = tmp_path / 'package.json'
    layer = {'schema_version': tactics.SCHEMA, 'season': '2015-16', 'clubs': [{'carrier_id': 307, 'context': context()}]}
    pipeline.write_canonical_json(tmp_path / 'context.json', layer)
    package = {'season': {'start_year': 2015, 'end_year': 2016}, 'artifacts': [
        {'id': 'contextual-tactics-2015-16', 'relative_path': 'context.json', 'sha256': 'a' * 64}]}
    with pytest.raises(ValueError, match='hash'):
        tactics.package_layers(package, recipe)
    package['artifacts'][0]['sha256'] = hashlib.sha256((tmp_path / 'context.json').read_bytes()).hexdigest()
    package['season']['start_year'] = 2014
    with pytest.raises(ValueError, match='another season'):
        tactics.package_layers(package, recipe)
