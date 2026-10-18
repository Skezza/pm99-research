"""Reproduce a complete sourced club transaction, never discard recipe edits."""
import json
import os
from pathlib import Path

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_package_v2 as packages
from scripts import prepare_paired_whole_club_native_v1 as native
from scripts import prepare_paired_club_assets_v1 as assets
from scripts import season_kit_render_bindings_v1 as render
from scripts import verify_paired_whole_club_native_v1 as readback
from scripts import verify_paired_club_identity_v1 as identity
from scripts import publish_paired_whole_club_delta_v1 as publisher

MODE = 'known-good-baseline-complete-coupled-roster-manager-ground-and-kit-delta'


def bound_receipt(previous):
    receipt_path = getattr(previous, 'compiler_receipt_path', None)
    if receipt_path is None:
        return None
    compiler = pipeline.read_json_file(receipt_path)
    if compiler.get('compilation_mode') != MODE:
        return None
    locator = previous.locator
    path = registry.ROOT / locator['paired_whole_club_candidate_receipt_path']
    if registry.sha256_file(path) != locator['paired_whole_club_candidate_receipt_sha256']:
        raise ValueError('complete-club reconstruction receipt changed')
    if registry.canonical_document_sha256(previous.package_path) != compiler['season_package_sha256']:
        raise ValueError('edited complete-club recipe cannot use exact reconstruction; no edits discarded')
    pipeline.assert_tree_matches_inventory(previous.game_path, pipeline.read_json_file(previous.inventory_path))
    receipt = pipeline.read_json_file(path)
    if (receipt['season'] != previous.season or registry.sha256_file(path) != compiler['candidate_receipt_sha256']
            or not receipt.get('paired_asset_stage')):
        raise ValueError('complete-club reconstruction source receipt is incomplete')
    for name, digest in receipt['native_hashes'].items():
        if registry.sha256_file(previous.game_path / 'DBDAT' / name) != digest:
            raise ValueError('complete-club reconstruction native source changed')
    return path, receipt


def replay_assets(candidate, receipt, original_folder, output):
    """Re-render all three sizes from bound styles; link original HTML unchanged."""
    output.mkdir()
    cache = output / 'source-cache'
    cache.mkdir()
    specs, rows = {}, []
    for ground in receipt['paired_asset_stage']['grounds']:
        carrier = ground['carrier_id']
        filename = f'ground-original-{carrier}.html'
        raw = original_folder / filename
        if registry.sha256_file(raw) != ground['sha256']:
            raise ValueError('original complete-club ground evidence changed')
        os.link(raw, cache / filename)
        pipeline.write_canonical_json(cache / (filename + '.source.json'),
            dict(url=ground['url'], sha256=ground['sha256']))
        specs[carrier] = (ground['club'], ground['ground'], filename,
            ground['url'], ground['dated_match_anchors'])
        if ground.get('exact_season_table_row'):
            specs[carrier] += (ground['exact_season_table_row'],)
        document = pipeline.read_json_file(original_folder / f'kit-source-{carrier}.json')
        row = document['catalogue_row']
        if row['carrier_id'] != carrier or row['club_name'] != ground['club']:
            raise ValueError('original complete-club kit belongs to another carrier')
        for evidence in row['source'].get('evidence', []):
            if registry.sha256_file(registry.ROOT / evidence['path']) != evidence['sha256']:
                raise ValueError('original complete-club kit evidence changed')
        rows.append(row)
    year = int(receipt['season'][:4])
    catalogue = dict(schema_version='pm99-season-kit-catalogue-v1',
        season=dict(start_year=year, end_year=year + 1, label=f'{year}/{str(year + 1)[-2:]}'), rows=rows)
    pipeline.write_canonical_json(output / 'kit-catalogue.json', catalogue)
    bindings, rendered = render.render_catalogue(catalogue, dbdat=candidate / 'game/DBDAT',
        output_dir=output / 'renders', pattern_cache_dir=output / 'pattern-cache', allow_network=False)
    if rendered['coverage']['bound_club_count'] != len(rows):
        raise ValueError('complete-club reconstruction kit render has gaps')
    pipeline.write_canonical_json(output / 'render-bindings.json', bindings)
    pipeline.write_canonical_json(output / 'render-receipt.json', rendered)
    return specs


def reconstruction(previous, release_id):
    source = bound_receipt(previous)
    if source is None:
        return None
    path, receipt = source
    pair_path = registry.ROOT / receipt['source_pair']['path']
    if registry.sha256_file(pair_path) != receipt['source_pair']['sha256']:
        raise ValueError('complete-club reconstruction original group changed')
    root = registry.ROOT / '.local/paired-whole-club-replays-v1' / previous.season / release_id
    if root.exists() or registry.locator_path(previous.season, release_id).parent.exists():
        raise ValueError('complete-club reconstruction release already exists')
    managers = {}
    for row in receipt['managers']:
        original = registry.ROOT / row['path']
        if registry.sha256_file(original) != row['sha256']:
            raise ValueError('complete-club reconstruction manager evidence changed')
        managers[row['carrier_id']] = original
    overrides = {relative: registry.ROOT / value['path']
        for relative, value in receipt['inherited_recipe_bindings'].items()}
    native.prepare(pair_path, managers, root / 'native', input_overrides=overrides)
    specs = replay_assets(root / 'native', receipt, path.parent, root / 'assets')
    completed = root / 'complete'
    assets.prepare(root / 'native', root / 'assets', completed, ground_specs=specs)
    pipeline.assert_tree_matches_inventory(completed / 'game', pipeline.read_json_file(previous.inventory_path))
    if packages.canonical_json_bytes(pipeline.read_json_file(completed / 'season-package.json')) != (
            packages.canonical_json_bytes(pipeline.read_json_file(previous.package_path))):
        raise ValueError('complete-club reconstruction recipe differs; no edits discarded')
    native_proof = root / 'native-proof.json'
    identity_proof = root / 'identity-proof.json'
    readback.verify(completed, native_proof)
    pair = pipeline.read_json_file(pair_path)
    proposal = pipeline.read_json_file(registry.ROOT / pair['proposals'][0]['path'])
    binding = proposal['bindings']['published_person_supplement']
    person_input = registry.ROOT / binding['path']
    if registry.sha256_file(person_input) != binding['sha256']:
        raise ValueError('complete-club reconstruction person reader input changed')
    identity.verify(completed, person_input, identity_proof)
    publisher.publish(completed, native_proof, identity_proof, release_id,
        source_release_id=receipt['source_release_id'])
    return dict(season=previous.season, release_id=release_id,
        source_release_id=receipt['source_release_id'], reused=False,
        complete_game_inventory_identical=True, complete_recipe_identical=True,
        compilation_mode='source-bound-complete-club-reconstruction-not-factory-compile')
