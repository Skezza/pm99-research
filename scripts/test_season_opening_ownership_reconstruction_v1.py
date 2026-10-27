import json
from types import SimpleNamespace

import pytest

from scripts import season_opening_ownership_reconstruction_v1 as replay
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_duplicate_layered_packages_v1 as layered
from scripts import publish_historical_role_delta_v1 as publisher


def put(path, value):
    path.write_text(json.dumps(value))


@pytest.fixture
def context(tmp_path, monkeypatch):
    r = replay.registry
    monkeypatch.setattr(r, 'ROOT', tmp_path)
    releases = []
    for name in ['parent', 'candidate', 'rebuilt']:
        folder = tmp_path / name
        (folder / 'game/DBDAT').mkdir(parents=True)
        (folder / 'game/DBDAT/JUG98030.FDI').write_bytes(b'unchanged native')
        for file in ['compiler.json', 'inventory.json', 'chain.json']:
            put(folder / file, {})
        put(folder / 'season-package.json', {'players': [], 'clubs': [], 'artifacts': []})
        releases.append(SimpleNamespace(season='2020-21', release_id=name,
            package_path=folder/'season-package.json', game_path=folder/'game',
            compiler_receipt_path=folder/'compiler.json', inventory_path=folder/'inventory.json',
            build_chain_path=folder/'chain.json', locator={}))
    base, previous, rebuilt = releases
    plan = {'schema_version': planner.SCHEMA, 'release_id': base.release_id, 'updates': []}
    path = previous.package_path.parent / delta.plan_filename(plan)
    put(path, plan)
    previous.locator['ownership_plan_path'] = str(path.relative_to(tmp_path))
    descriptor = dict(season=base.season, release_id=base.release_id,
        package_sha256=r.sha256_file(base.package_path),
        jug_sha256=r.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'), updates=[], unresolved=[])
    descriptor_path = previous.package_path.parent/'role-delta-input.json'
    put(descriptor_path, descriptor)
    receipt = dict(compilation_mode=replay.MODE, ownership_plan_sha256=r.sha256_file(path),
        source_season_package_sha256=r.canonical_document_sha256(base.package_path),
        source_compiler_receipt_sha256=r.sha256_file(base.compiler_receipt_path),
        source_build_chain_sha256=r.sha256_file(base.build_chain_path))
    put(previous.compiler_receipt_path, receipt)
    monkeypatch.setattr(r, 'load_registered_release', lambda season, identity:
                        base if identity == 'parent' else rebuilt)
    calls = []
    monkeypatch.setattr(delta, 'verify_plan', lambda *args: calls.append(('source-verify', args)))
    monkeypatch.setattr(publisher, 'updated_package', lambda package, descriptor: package)
    monkeypatch.setattr(layered, 'prepare', lambda base, plan, original, package:
                        (package, None, None, None))
    monkeypatch.setattr(replay.pipeline, 'assert_tree_matches_inventory',
                        lambda *args: calls.append(('inventory', args)))
    monkeypatch.setattr(publisher, 'publish', lambda *args, **kwargs:
                        calls.append(('publish', kwargs)))
    return SimpleNamespace(base=base, previous=previous, rebuilt=rebuilt, path=path,
        descriptor_path=descriptor_path, receipt=receipt, calls=calls)


def test_exact_latest_ownership_replays_parent_and_checks_complete_output(context):
    c = context
    result = replay.reconstruction(c.previous, 'rebuilt', minimum_free_bytes=12345)
    assert result['complete_recipe_identical'] and result['complete_game_inventory_identical']
    assert [x for x in c.calls if x[0] == 'publish'] == [('publish', dict(
        release_id='rebuilt', source_release_id='parent', ownership_plan_path=c.path,
        minimum_free_bytes=12345))]
    assert len([x for x in c.calls if x[0] == 'inventory']) == 3


@pytest.mark.parametrize('change', ['plan', 'recipe', 'descriptor', 'provenance', 'output'])
def test_changed_inputs_or_output_are_never_silently_accepted(context, change):
    c = context
    if change == 'plan':
        c.path.write_text(c.path.read_text() + ' ')
    elif change == 'recipe':
        put(c.previous.package_path, {'edited': True})
    elif change == 'descriptor':
        descriptor = json.loads(c.descriptor_path.read_text())
        descriptor['updates'] = [{'unexpected': True}]
        put(c.descriptor_path, descriptor)
    elif change == 'provenance':
        put(c.base.build_chain_path, {'changed': True})
    elif change == 'output':
        put(c.rebuilt.package_path, {'lost correction': True})
    with pytest.raises(ValueError):
        replay.reconstruction(c.previous, 'rebuilt')
    if change != 'output':
        assert not any(x[0] == 'publish' for x in c.calls)


def test_inherited_ownership_locator_does_not_hide_newer_transaction(context):
    c = context
    c.receipt['compilation_mode'] = 'some-newer-manager-or-artwork-layer'
    put(c.previous.compiler_receipt_path, c.receipt)
    assert replay.reconstruction(c.previous, 'unused') is None
    assert c.calls == []


def test_latest_ownership_precedes_inherited_source_dispatch(monkeypatch):
    from scripts import build_registered_quality_release_v1 as build
    previous = SimpleNamespace()
    monkeypatch.setattr(build.registry, 'load_preferred_release', lambda season: previous)
    monkeypatch.setattr(replay, 'reconstruction', lambda *a: {'latest_ownership': True})
    assert build.build('2020-21', release_id='test') == {'latest_ownership': True}
