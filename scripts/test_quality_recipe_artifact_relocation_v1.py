"""Exact-copy and legacy hash-convention regression tests for cold builds."""
import hashlib
from pathlib import Path

import pytest

from scripts import build_registered_quality_release_v1 as build
from scripts import season_pipeline_v2 as pipeline


def setup(tmp_path, *, identity='sourced-italian-opening-xi-2006-07-223', legacy=False):
    source, target = tmp_path / 'source', tmp_path / 'target'
    source.mkdir(); target.mkdir()
    raw = pipeline.canonical_json_bytes({'source': 'immutable', 'orders': [1, 2]})
    file = source / 'layer.json'
    file.write_bytes(raw + b'\n')
    sha = hashlib.sha256(raw if legacy else raw + b'\n').hexdigest()
    artifact = {'id': identity, 'relative_path': 'layer.json', 'sha256': sha}
    return source, target, {'artifacts': [artifact]}


def test_exact_new_plan_is_carried_and_idempotently_reused(tmp_path):
    source, target, package = setup(tmp_path)
    build._carry_recipe_local_artifacts(package, source / 'recipe.json', target / 'recipe.json')
    assert (source / 'layer.json').read_bytes() == (target / 'layer.json').read_bytes()
    build._carry_recipe_local_artifacts(package, source / 'recipe.json', target / 'recipe.json')


@pytest.mark.parametrize('identity', ['historical-role-plan-2006-07',
    'historical-nationality-plan-2006-07', 'historical-manager-plan-2006-07',
    'historical-club-label-plan-2006-07'])
def test_declared_legacy_json_content_hash_preserved_without_rewriting(tmp_path, identity):
    source, target, package = setup(tmp_path, identity=identity, legacy=True)
    build._carry_recipe_local_artifacts(package, source / 'recipe.json', target / 'recipe.json')
    assert (source / 'layer.json').read_bytes() == (target / 'layer.json').read_bytes()


@pytest.mark.parametrize('problem', ['source', 'destination', 'unsafe', 'new-plan-legacy-hash', 'noncanonical-legacy'])
def test_mutated_or_unsafe_inputs_refused(tmp_path, problem):
    source, target, package = setup(tmp_path)
    if problem == 'source':
        (source / 'layer.json').write_bytes(b'{"changed":true}\n')
    elif problem == 'destination':
        (target / 'layer.json').write_bytes(b'{"changed":true}\n')
    elif problem == 'unsafe':
        package['artifacts'][0]['relative_path'] = '../layer.json'
    elif problem == 'new-plan-legacy-hash':
        package['artifacts'][0]['sha256'] = hashlib.sha256((source / 'layer.json').read_bytes()[:-1]).hexdigest()
    elif problem == 'noncanonical-legacy':
        package['artifacts'][0]['id'] = 'historical-role-plan-2006-07'
        package['artifacts'][0]['sha256'] = hashlib.sha256((source / 'layer.json').read_bytes()[:-1]).hexdigest()
        (source / 'layer.json').write_bytes(b'{ "orders": [1,2], "source": "immutable" }\n')
    with pytest.raises(build.QualityBuildError):
        build._carry_recipe_local_artifacts(package, source / 'recipe.json', target / 'recipe.json')
