"""Promote a complete checked delta chain with one catalog replacement.

Intermediate releases remain private. This verifies immutable ancestry and
actual file inventories; historical/runtime approval belongs to the caller.
"""
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.attest_registered_season_runtime_v1 import _atomic_replace_json


def check_chain(season, release_ids):
    if not release_ids or len(set(release_ids)) != len(release_ids):
        raise ValueError('nonempty unique ordered delta chain required')
    initial = registry.load_preferred_release(season)
    parent = initial
    for release_id in release_ids:
        if release_id == parent.release_id:
            raise ValueError('chain must advance the current release')
        child = registry.load_registered_release(season, release_id)
        receipt = pipeline.read_json_file(child.compiler_receipt_path)
        expected = (registry.canonical_document_sha256(parent.package_path),
            registry.sha256_file(parent.compiler_receipt_path),
            registry.sha256_file(parent.build_chain_path))
        actual = tuple(receipt.get(k) for k in ('source_season_package_sha256',
            'source_compiler_receipt_sha256', 'source_build_chain_sha256'))
        if actual != expected:
            raise ValueError('delta chain does not extend the exact immutable parent')
        pipeline.assert_tree_matches_inventory(child.game_path,
            pipeline.read_json_file(child.inventory_path))
        if registry.canonical_document_sha256(child.package_path) != child.locator['package_canonical_sha256']:
            raise ValueError('delta chain recipe changed')
        for name, sha in child.locator['required_file_hashes'].items():
            if registry.sha256_file(child.game_path / name) != sha:
                raise ValueError('delta chain required native file changed')
        if registry.sha256_file(child.release_manifest_path) != child.manifest_sha256:
            raise ValueError('delta chain manifest changed')
        pipeline.validate_release_manifest(pipeline.read_json_file(child.release_manifest_path))
        parent = child
    return initial, parent


def register_chain(season, release_ids):
    initial, final = check_chain(season, release_ids)
    catalog = registry.load_catalog()
    current = registry.load_preferred_release(season)
    if (current.release_id, current.manifest_sha256) != (initial.release_id, initial.manifest_sha256):
        raise ValueError('preferred baseline moved during chain verification')
    catalog[season] = dict(season=season, release_id=final.release_id,
        release_manifest_sha256=final.manifest_sha256)
    _atomic_replace_json(registry.CATALOG_PATH, dict(schema_version=registry.CATALOG_SCHEMA,
        seasons=[catalog[s] for s in sorted(catalog)]))
    return dict(season=season, previous_release=initial.release_id, release_id=final.release_id,
        checked_chain=list(release_ids), catalog_writes=1, intermediate_releases_promoted=False,
        historical_verification_complete=False)
