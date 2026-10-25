"""Replay the newest bounded artwork layer before inherited database layers.

Hash-bound materialised assets are reusable build inputs. No recipe edits are
discarded, no full database regeneration, and no stale art is substituted.
"""
from pathlib import Path

from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_visual_patch_v1 as art


def verify_ancestry_edge(parent, child):
    """Verify an artwork-only parent edge without replaying or publishing it.

    Artwork deliberately retains its compiler receipt. Its immediate parent
    is instead sealed by the new manifest stage and the exact chain prefix.
    Never use inherited artwork metadata to skip a later database edge.
    """
    locator = getattr(child, 'locator', {})
    if not locator.get('visual_patch_plan_path'):
        return False
    stage_id = 'portrait-' + child.release_id
    chain = pipeline.read_json_file(child.build_chain_path)
    if not chain.get('stages') or chain['stages'][-1].get('id') != stage_id:
        return False

    def retained(relative):
        path = registry.ROOT / relative
        if (path.is_symlink() or not path.is_file()
                or not path.resolve().is_relative_to(registry.ROOT.resolve())):
            raise ValueError('artwork ancestry input is not retained in the workspace')
        return path

    plan_path = retained(locator['visual_patch_plan_path'])
    application_path = retained(locator['portrait_patch_application_path'])
    application = pipeline.read_json_file(application_path)
    plan = pipeline.read_json_file(plan_path)
    stage = chain['stages'][-1]
    parent_chain = pipeline.read_json_file(parent.build_chain_path)
    without_stage = dict(chain, stages=chain['stages'][:-1])
    if (without_stage != parent_chain
            or stage.get('receipt_sha256') != registry.sha256_file(application_path)
            or application.get('plan_sha256') != registry.sha256_file(plan_path)
            or Path(application.get('plan_path', '')).resolve() != plan_path.resolve()
            or application.get('season') != child.season or child.season != parent.season
            or plan.get('inputs', {}).get('release_id') != parent.release_id
            or plan['inputs'].get('package_sha256') != registry.sha256_file(parent.package_path)
            or child.package_path.read_bytes() != parent.package_path.read_bytes()
            or registry.sha256_file(child.compiler_receipt_path) != registry.sha256_file(parent.compiler_receipt_path)):
        raise ValueError('artwork ancestry parent, chain, recipe or compiler binding differs')
    material = retained(application['materialisation_path'])
    if registry.sha256_file(material) != application.get('materialisation_sha256'):
        raise ValueError('artwork ancestry materialisation changed')
    manifest = pipeline.read_json_file(child.release_manifest_path)
    records = [s for s in manifest['stages'] if s['id'] == stage_id]
    if len(records) != 1:
        raise ValueError('artwork ancestry requires exactly one new manifest stage')
    record = records[0]
    if (record.get('input_fingerprints') != {
            'previous-release': parent.manifest_sha256,
            'patch-plan': registry.sha256_file(plan_path)}
            or record.get('external_artifacts') != [{
                'id': stage_id, 'role': 'input',
                'schema': 'pm99-external-artifact-v2',
                'sha256': registry.sha256_file(application_path),
                'size': application_path.stat().st_size}]):
        raise ValueError('artwork ancestry manifest does not seal the immediate parent')
    before = pipeline.read_json_file(parent.inventory_path)
    after = pipeline.read_json_file(child.inventory_path)
    difference = pipeline.inventory_difference(before, after)
    paths = ([r['path'] for r in difference['changed']]
             + difference['only_left'] + difference['only_right'])
    outputs = {r['path']: r['sha256'] for r in after['files'] if r['path'] in paths}
    if (not paths or any(not art.PATCH_FILE.fullmatch(path) for path in paths)
            or application.get('registered_base_inventory_fingerprint',
                               application.get('base_inventory_fingerprint')) != before['files_fingerprint']
            or application.get('output_inventory') != after
            or application.get('difference') != difference
            or application.get('unrelated_files_unchanged') is not True
            or stage.get('outputs') != outputs
            or stage.get('removed') != difference['only_left']
            or record.get('parameters') != {'outputs': outputs, 'removed': difference['only_left']}):
        raise ValueError('artwork ancestry changes unapproved files or has a stale inventory')
    for release, inventory in ((parent, before), (child, after)):
        pipeline.assert_tree_matches_inventory(release.game_path, inventory)
    return True


def reconstruction(previous, release_id):
    relative = getattr(previous, 'locator', {}).get('visual_patch_plan_path')
    if not relative:
        return None
    chain = pipeline.read_json_file(previous.build_chain_path)
    if not chain['stages'] or chain['stages'][-1]['id'] != 'portrait-' + previous.release_id:
        return None
    plan_path = registry.ROOT / relative
    plan_path.resolve().relative_to(registry.ROOT.resolve())
    application_path = registry.ROOT / previous.locator['portrait_patch_application_path']
    application = pipeline.read_json_file(application_path)
    if (registry.sha256_file(application_path) != chain['stages'][-1]['receipt_sha256']
            or registry.sha256_file(plan_path) != application['plan_sha256']):
        raise ValueError('newest artwork replay input changed')
    material_path = Path(application['materialisation_path'])
    material_path.resolve().relative_to(registry.ROOT.resolve())
    if registry.sha256_file(material_path) != application['materialisation_sha256']:
        raise ValueError('newest artwork materialisation changed')
    plan = pipeline.read_json_file(plan_path)
    baseline = registry.load_registered_release(previous.season, plan['inputs']['release_id'])
    if (registry.sha256_file(baseline.package_path) != plan['inputs']['package_sha256']
            or registry.sha256_file(previous.package_path) != registry.sha256_file(baseline.package_path)):
        raise ValueError('edited recipe cannot use exact artwork replay; no edits discarded')
    for release in [baseline, previous]:
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    destination = registry.ROOT / '.local/season-visual-replays-v1' / previous.season / release_id
    if destination.exists() or registry.locator_path(previous.season, release_id).exists():
        raise ValueError('artwork replay destination already exists')
    art.apply(plan_path, material_path.parent, destination / 'game', source_release=baseline)
    pipeline.assert_tree_matches_inventory(destination / 'game', pipeline.read_json_file(previous.inventory_path))
    proof = dict(season=previous.season, source_release_id=baseline.release_id,
        replayed_release_id=previous.release_id, complete_game_inventory_identical=True,
        complete_recipe_identical=True, recipe_sha256=registry.sha256_file(previous.package_path),
        application_sha256=registry.sha256_file(application_path),
        plan_sha256=registry.sha256_file(plan_path), materialisation_sha256=registry.sha256_file(material_path),
        game=str(destination / 'game'), registered=False,
        scope='Exact bounded artwork-input replay; not a historical approval or new database compilation')
    pipeline.write_canonical_json(destination / 'replay-proof.json', proof)
    result = art.publish(previous.season, destination / 'game', release_id, source_release=baseline)
    return dict(**result, complete_game_inventory_identical=True, complete_recipe_identical=True,
        compilation_mode='known-good-baseline-bounded-artwork-reconstruction', reused=False)
