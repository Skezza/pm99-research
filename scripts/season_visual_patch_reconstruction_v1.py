"""Replay the newest bounded artwork layer before inherited database layers.

Hash-bound materialised assets are reusable build inputs. No recipe edits are
discarded, no full database regeneration, and no stale art is substituted.
"""
from pathlib import Path

from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_visual_patch_v1 as art


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
