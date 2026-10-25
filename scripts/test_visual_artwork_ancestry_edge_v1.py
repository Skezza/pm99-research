import copy
from types import SimpleNamespace

import pytest

from scripts import season_pipeline_v2 as pipeline
from scripts import season_visual_patch_reconstruction_v1 as subject


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(subject.registry, 'ROOT', tmp_path)
    save = pipeline.write_canonical_json
    sha = subject.registry.sha256_file
    releases = []
    for name in ('base', 'art'):
        root = tmp_path / name
        game = root / 'game'
        (game / 'DBDAT').mkdir(parents=True)
        (game / 'DBDAT/JUG98030.FDI').write_bytes(b'unchanged database')
        (game / 'DBDAT/NANOESC.PKF').write_bytes(name.encode())
        package = root / 'package.json'
        package.write_bytes(b'{}')
        compiler = root / 'compiler.json'
        compiler.write_bytes(b'{}')
        inventory = root / 'inventory.json'
        save(inventory, pipeline.build_tree_inventory(game))
        releases.append(SimpleNamespace(season='2002-03', release_id=name,
            package_path=package, compiler_receipt_path=compiler, game_path=game,
            inventory_path=inventory, build_chain_path=root / 'chain.json',
            release_manifest_path=root / 'manifest.json', manifest_sha256=name + '-manifest'))
    parent, child = releases
    save(parent.build_chain_path, {'stages': []})
    plan = tmp_path / 'plan.json'
    save(plan, {'inputs': {'release_id': parent.release_id, 'package_sha256': sha(parent.package_path)}})
    material = tmp_path / 'material.json'
    material.write_bytes(b'{}')
    before = pipeline.read_json_file(parent.inventory_path)
    after = pipeline.read_json_file(child.inventory_path)
    difference = pipeline.inventory_difference(before, after)
    outputs = {'DBDAT/NANOESC.PKF': sha(child.game_path / 'DBDAT/NANOESC.PKF')}
    application = tmp_path / 'application.json'
    save(application, {'season': child.season, 'plan_path': str(plan), 'plan_sha256': sha(plan),
        'materialisation_path': str(material), 'materialisation_sha256': sha(material),
        'registered_base_inventory_fingerprint': before['files_fingerprint'],
        'output_inventory': after, 'difference': difference, 'unrelated_files_unchanged': True})
    stage_id = 'portrait-' + child.release_id
    save(child.build_chain_path, {'stages': [{'id': stage_id,
        'receipt_sha256': sha(application), 'outputs': outputs, 'removed': []}]})
    descriptor = {'id': stage_id, 'role': 'input', 'schema': 'pm99-external-artifact-v2',
        'sha256': sha(application), 'size': application.stat().st_size}
    save(child.release_manifest_path, {'stages': [{'id': stage_id,
        'input_fingerprints': {'previous-release': parent.manifest_sha256, 'patch-plan': sha(plan)},
        'external_artifacts': [descriptor], 'parameters': {'outputs': outputs, 'removed': []}}]})
    child.locator = {'visual_patch_plan_path': str(plan.relative_to(tmp_path)),
        'portrait_patch_application_path': str(application.relative_to(tmp_path))}
    return parent, child, application, plan


def test_retained_compiler_artwork_edge_has_separate_exact_parent_authority(tmp_path, monkeypatch):
    parent, child, _, _ = fixture(tmp_path, monkeypatch)
    assert subject.verify_ancestry_edge(parent, child) is True


@pytest.mark.parametrize('problem', ['wrong_parent', 'chain_prefix', 'recipe', 'compiler',
    'application', 'plan', 'materialisation', 'duplicate_descriptor', 'hidden_native_write'])
def test_artwork_ancestry_cannot_skip_or_rewrite_database_edges(tmp_path, monkeypatch, problem):
    parent, child, application, plan = fixture(tmp_path, monkeypatch)
    if problem == 'wrong_parent':
        parent.manifest_sha256 = 'sibling-manifest'
    elif problem == 'chain_prefix':
        parent.build_chain_path.write_bytes(pipeline.canonical_json_bytes({'stages': [{'id': 'omitted'}]}))
    elif problem == 'recipe':
        child.package_path.write_bytes(b'{"changed":true}')
    elif problem == 'compiler':
        child.compiler_receipt_path.write_bytes(b'{"changed":true}')
    elif problem == 'application':
        application.write_bytes(b'{}')
    elif problem == 'plan':
        plan.write_bytes(b'{}')
    elif problem == 'materialisation':
        (tmp_path / 'material.json').write_bytes(b'changed')
    elif problem == 'duplicate_descriptor':
        manifest = pipeline.read_json_file(child.release_manifest_path)
        descriptors = manifest['stages'][0]['external_artifacts']
        descriptors.append(copy.deepcopy(descriptors[0]))
        child.release_manifest_path.write_bytes(pipeline.canonical_json_bytes(manifest))
    else:
        (child.game_path / 'DBDAT/JUG98030.FDI').write_bytes(b'changed database')
    with pytest.raises(ValueError):
        subject.verify_ancestry_edge(parent, child)


def test_inherited_artwork_receipt_is_not_authority_for_a_new_database_child(tmp_path, monkeypatch):
    parent, child, _, _ = fixture(tmp_path, monkeypatch)
    child.release_id = 'later-database-release'
    assert subject.verify_ancestry_edge(parent, child) is False
