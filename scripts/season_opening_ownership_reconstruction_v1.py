"""Replay a latest, exact, source-bound ownership transaction without a seed rebuild."""
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry

MODE = 'known-good-baseline-opening-ownership-player-delta'


def reconstruction(previous, release_id, *, minimum_free_bytes=8 * 1024**3):
    receipt_path = getattr(previous, 'compiler_receipt_path', None)
    if receipt_path is None:
        return None
    receipt = pipeline.read_json_file(receipt_path)
    if receipt.get('compilation_mode') != MODE:
        return None
    from scripts import publish_historical_role_delta_v1 as publisher
    from scripts import season_duplicate_ownership_delta_v1 as delta
    from scripts import season_duplicate_ownership_plan_v1 as planner
    from scripts import season_duplicate_layered_packages_v1 as layered

    folder = previous.package_path.parent
    locator_path = previous.locator.get('ownership_plan_path')
    if not locator_path:
        raise ValueError('ownership SOURCE requires its own bound plan')
    path = registry.ROOT / locator_path
    plan = pipeline.read_json_file(path)
    if plan.get('schema_version') != planner.SCHEMA:
        raise ValueError('unsupported generic ownership SOURCE schema')
    if (path.resolve() != (folder / delta.plan_filename(plan)).resolve()
            or registry.sha256_file(path) != receipt.get('ownership_plan_sha256')):
        raise ValueError('ownership SOURCE plan binding changed')
    descriptor_path = folder / 'role-delta-input.json'
    descriptor = pipeline.read_json_file(descriptor_path)
    base = registry.load_registered_release(previous.season, plan['release_id'])
    expected_descriptor = dict(season=previous.season, release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),
        jug_sha256=registry.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI'),
        updates=[], unresolved=[])
    if descriptor != expected_descriptor:
        raise ValueError('ownership SOURCE descriptor is not the exact inert parent binding')
    expected = {
        'source_season_package_sha256': registry.canonical_document_sha256(base.package_path),
        'source_compiler_receipt_sha256': registry.sha256_file(base.compiler_receipt_path),
        'source_build_chain_sha256': registry.sha256_file(base.build_chain_path),
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ValueError('ownership SOURCE parent provenance changed')
    delta.verify_plan(base, plan)
    original = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    source_main = publisher.updated_package(pipeline.read_json_file(base.package_path), descriptor)
    expected_main, _, _, _ = layered.prepare(base, plan, original, source_main)
    package = pipeline.read_json_file(previous.package_path)
    if expected_main != package:
        raise ValueError('edited ownership recipe cannot use exact SOURCE replay')
    for release in (base, previous):
        pipeline.assert_tree_matches_inventory(release.game_path,
            pipeline.read_json_file(release.inventory_path))
    publisher.publish(previous.season, descriptor_path, release_id=release_id,
        source_release_id=base.release_id, ownership_plan_path=path,
        minimum_free_bytes=minimum_free_bytes)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,
        pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes() != previous.package_path.read_bytes():
        raise ValueError('ownership SOURCE complete recipe bytes differ')
    return dict(season=previous.season, release_id=release_id,
        previous_release_id=previous.release_id, source_release_id=base.release_id,
        complete_recipe_identical=True, complete_game_inventory_identical=True,
        compilation_mode='source-bound-opening-ownership-reconstruction-not-factory-compile')
