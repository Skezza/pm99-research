"""Assemble checked private native/kit ingredients without changing a release."""
import copy
import os
import shutil
from pathlib import Path

from scripts import prepare_ofk_2004_source_allocation_v1 as source
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_kit_render_bindings_v1 as render
from scripts.publish_contextual_tactics_delta_v1 import verify_recipe_artifact
from scripts.season_art_transaction_v1 import atomic_bytes


def assemble(output, *, native=None, proof_path=None, proposal_path=None, kits_dir=None, season='2004-05'):
    if output.exists(): raise ValueError('private assembled game is immutable')
    native = native or source.AUDIT / 'ofk-2004-private-native-v1'
    kits = kits_dir or source.AUDIT / 'ofk-2004-private-kits-v1'
    proof_path = proof_path or source.AUDIT / 'ofk-2004-independent-native-readback-v1.json'
    proposal_path = proposal_path or source.AUDIT / 'ofk-2004-fixed18-private-allocation-v1.json'
    readback = pipeline.read_json_file(proof_path)
    receipt = pipeline.read_json_file(native / 'native-proof.json')
    coupled = readback.get('schema_version') == 'pm99-private-coupled-foreign-independent-native-v1'
    receipt_key = 'candidate_receipt_sha256' if coupled else 'source_candidate_receipt_sha256'
    if readback[receipt_key] != registry.sha256_file(native / 'native-proof.json'):
        raise ValueError('private native independent proof is stale')
    if (coupled and (not readback['all19_native_identities_and_skills_read_back']
            or not readback['all_unselected_native_records_identical']
            or readback['introduced_candidate_groups'] or readback['replacement_cross_club_candidates'])
            or not coupled and readback['cross_club_same_name_DOB_candidates']):
        raise ValueError('new private foreign squad still collides with other recipe people')
    kit_proof = pipeline.read_json_file(kits / 'private-kit-proof.json')
    if kit_proof['source_baseline_release_id'] != receipt['baseline_release_id']:
        raise ValueError('private kits and source roster have different baselines')
    if receipt.get('season', '2004-05') != season: raise ValueError('private native season differs')
    baseline = registry.load_registered_release(season, receipt['baseline_release_id'])
    names = dict(receipt['native_hashes'])
    names.update({r['archive']: r['after_sha256'] for r in kit_proof['changes']})
    ingredients = {n: (native if n in receipt['native_hashes'] else kits) / 'DBDAT' / n for n in names}
    for n, path in ingredients.items():
        if registry.sha256_file(path) != names[n]: raise ValueError('private ingredient changed')
    package = copy.deepcopy(pipeline.read_json_file(native / 'season-package.json'))
    compositions = {path.name:path for path in native.glob('ownership-plan-*.json')}
    opening_name = 'ofk-original-opening-2015.html' if coupled else 'ofk-original-opening.html'
    opening_path = source.ROOT / ('ofk-first-fixture-2015-2598829.html' if coupled else 'ofk-first-fixture-2004-3142214.html')
    source_overrides = {opening_name:opening_path, **compositions}
    inherited = {}
    for artifact in package['artifacts']:
        relative = artifact.get('relative_path')
        if not relative: continue
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts or not path.parts:
            raise ValueError('unsafe private recipe-local artifact')
        original = source_overrides.get(relative, baseline.package_path.parent / path)
        inherited[relative] = (original, verify_recipe_artifact(original, artifact['sha256']))
    binding = pipeline.read_json_file(kits / 'render-bindings.json')
    artifacts = binding['clubs'][0]['artifacts']
    kit = next(k for k in package['assets']['kits'] if k['club_id'] == 'club-706')
    proof_id = 'ofk-reviewed-period-kit-' + season[:4]
    kit.update(policy='write', artifact_ids=[a['id'] for a in artifacts],
        proof=dict(artifact_id=proof_id, grade='reviewed-editorial'))
    package['artifacts'] += copy.deepcopy(artifacts) + [dict(id=proof_id, kind='season-input',
        relative_path='ofk-period-kit-source.json', sha256=registry.sha256_file(kits / 'kit-catalogue.json'))]
    package['artifacts'].sort(key=lambda a: a['id'])
    from scripts import season_package_v2 as packages
    packages.validate_package(package)
    if shutil.disk_usage(baseline.game_path).free < 8 * 1024**3 + sum(p.stat().st_size for p in ingredients.values()):
        raise ValueError('private materialisation crosses8GiB local reserve')
    output.mkdir(parents=True)
    shutil.copytree(baseline.game_path, output / 'game', copy_function=os.link)
    for n, path in ingredients.items(): atomic_bytes(output / 'game/DBDAT' / n, path.read_bytes())
    for row in readback['players']:
        path = output / 'game/DBDAT/MINIFOTO' / f"J96{row['carrier_id']:05d}.BMP"
        if path.exists(): path.unlink()  # Only this private clone's hardlink; baseline survives.
    new_inputs = {
        opening_name: opening_path,
        'ofk-period-kit-source.json': kits / 'kit-catalogue.json',
        **compositions,
        **{a['relative_path']: kits / 'renders' / a['relative_path'] for a in artifacts},
    }
    for artifact in package['artifacts']:
        relative = artifact.get('relative_path')
        if not relative: continue
        if relative in new_inputs: path = new_inputs[relative]
        else: path = inherited[relative][0]
        verify_recipe_artifact(path, artifact['sha256'])
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        os.link(path, target)
    pipeline.write_canonical_json(output / 'season-package.json', package)
    inventory = pipeline.build_tree_inventory(output / 'game')
    if any(registry.sha256_file(path) != names[n] for n, path in ingredients.items()):
        raise ValueError('private ingredients changed during materialisation')
    baseline_inventory = pipeline.build_tree_inventory(baseline.game_path)
    old = {r['path']: r for r in baseline_inventory['files']}
    new = {r['path']: r for r in inventory['files']}
    allowed = {'DBDAT/' + n for n in names} | {
        f"DBDAT/MINIFOTO/J96{r['carrier_id']:05d}.BMP" for r in readback['players']}
    if any(old.get(n) != new.get(n) for n in old.keys() | new.keys() if n not in allowed):
        raise ValueError('private materialisation changed an unrelated game file')
    pipeline.write_canonical_json(output / 'inventory.json', inventory)
    proposal = pipeline.read_json_file(proposal_path)
    dated = proposal['dated_manager_ground'] if coupled else dict(manager='Branko Babic',ground='Omladinski stadion')
    receipt = dict(schema_version='pm99-private-original-foreign-game-v1', season=season,
        baseline_release_id=baseline.release_id, inventory_fingerprint=inventory['files_fingerprint'],
        corrected_slots=len(readback['players']), manager=dated['manager'], native_club='OFK Beograd',
        dated_ground=dated['ground'], period_kit_sizes=3,
        source_proposal_sha256=registry.sha256_file(proposal_path),
        game_hashes={n: registry.sha256_file(output / 'game' / n) for n in
            ['MANAGPRE.EXE'] + ['DBDAT/' + n for n in names]},
        native_hashes=names,
        recipe_sha256=registry.sha256_file(output / 'season-package.json'),
        exact_historical_formation_claimed=False,
        foreign_opaque_tactics='Unmodified native mode1 block; not historically certified.',
        registered=False, publication_authorised=False, runtime_verified=False,
        duplicate_case_closed=False, remaining=['typed reconstruction', 'fresh runtime/player/kit proof', 'normal promotion'])
    pipeline.write_canonical_json(output / 'candidate-receipt.json', receipt)
    return receipt


if __name__ == '__main__': assemble(source.AUDIT / 'ofk-2004-private-game-v1')
