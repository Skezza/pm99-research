#!/usr/bin/env python3
"""Publish manager-name-only copies of the known-good season games.

No rebuild of squads, tactics, ratings, portraits or kits. Failed historical
QA remains failed. A fresh runtime attestation is needed for the new inventory.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'upstream/pm99-skezmod-db-editor')]
from app.ent_manager_profiles import parse_indexed_ent_manager_profile
from app.fdi_indexed import IndexedFDIFile
from app.xor import xor_decode
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_package_v2 as packages
from scripts.season_visual_patch_v1 import source_inventory
from scripts.season_playtest_variant_v1 import _copy_game_tree
from scripts.publish_contextual_tactics_delta_v1 import verify_recipe_artifact
from scripts.publish_historical_role_delta_v1 import register_completed_delta
from scripts.verify_manager_display_runtime_v1 import verify
from scripts.attest_registered_season_runtime_v1 import _atomic_replace_json

RELEASE = 'historical-manager-display-20261005-r22a'


def gates(root):
    proof = json.loads((root / 'championships-field-proof-v1.json').read_text())
    actual = verify(Path(proof['candidate']), Path(proof['run']), Path(proof['frame']),
                    visual_review=root / 'field-probe-image-review-v1.json')
    if actual != proof:
        raise ValueError('manager field proof changed')
    run = ROOT / '.local/runlogs/pm99_runner/manager_display_corrected_2016_17_20261005_a'
    summary = json.loads((run / 'summary.json').read_text())
    command = json.loads((run / 'control_launch.json').read_text())['child_command']
    candidate = root / '2016-17/candidate-v1'
    receipt = json.loads((candidate / 'candidate-receipt.json').read_text())
    if (not summary.get('success') or summary.get('crash_detected') or summary.get('wine_debugger_detected') or
            Path(command[command.index('--dbdat-dir') + 1]) != candidate / 'DBDAT' or
            registry.sha256_file(candidate / 'DBDAT/ENT98030.FDI') != receipt['after_ent_sha256']):
        raise ValueError('normal manager display pilot is not a successful exact-input run')
    return {'schema': 'pm99-manager-display-runtime-gates-v1', 'field': proof,
            'normal_pilot': str(run), 'normal_pilot_summary_sha256': registry.sha256_file(run / 'summary.json'),
            'scope': 'sampled field/render/startup proof, not gameplay of every season'}


def audit(candidate, source):
    receipt = json.loads((candidate / 'candidate-receipt.json').read_text())
    if (receipt['field_probe'] or receipt['source_release_id'] != source.release_id or
            receipt['source_package_sha256'] != registry.canonical_document_sha256(source.package_path)):
        raise ValueError('candidate is not a normal delta of the current source')
    for file, key in [('EQ98030.FDI', 'source_eq_sha256'), ('JUG98030.FDI', 'source_jug_sha256'),
                      ('ENT98030.FDI', 'source_ent_sha256')]:
        if registry.sha256_file(source.game_path / 'DBDAT' / file) != receipt[key]:
            raise ValueError('source native input changed')
    old = json.loads(source.package_path.read_text())
    package = json.loads((candidate / 'season-package.json').read_text())
    packages.validate_package(package)
    clean = copy.deepcopy(package)
    for manager in clean['managers']:
        manager.pop('native_names', None)
    for artifact in clean['artifacts']:
        if artifact['id'].startswith('english-contextual-package-'):
            artifact.update(next(a for a in old['artifacts'] if a['id'] == artifact['id']))
    if clean != old:
        raise ValueError('manager candidate changed unrelated recipe data')
    english_artifacts = [a for a in package['artifacts'] if a['id'].startswith('english-contextual-package-')]
    if english_artifacts:
        descriptor = english_artifacts[0]
        english_path = candidate / descriptor['relative_path']
        verify_recipe_artifact(english_path, descriptor['sha256'])
        english = json.loads(english_path.read_text())
        previous_descriptor = next(a for a in old['artifacts'] if a['id'] == descriptor['id'])
        previous_path = source.package_path.parent / previous_descriptor['relative_path']
        verify_recipe_artifact(previous_path, previous_descriptor['sha256'])
        previous_english = json.loads(previous_path.read_text())
        clean_english = copy.deepcopy(english)
        legacy = {row['manager_id']: row for row in receipt.get('legacy_english_bindings', [])}
        previous_managers = {m['id']: m for m in previous_english['managers']}
        for manager in clean_english['managers']:
            manager.pop('native_names', None)
            if manager['id'] in legacy:
                binding = legacy[manager['id']]
                if (manager['carrier_id'], manager['name'], binding['before_carrier_id']) != (
                        binding['after_carrier_id'], binding['name'], previous_managers[manager['id']]['carrier_id']):
                    raise ValueError('legacy manager carrier binding changed identity')
                manager['carrier_id'] = binding['before_carrier_id']
                if 'policy' not in previous_managers[manager['id']]:
                    manager.pop('policy', None)
        if clean_english != previous_english:
            raise ValueError('English candidate changed unrelated recipe data')
    before = (source.game_path / 'DBDAT/ENT98030.FDI').read_bytes()
    after = (candidate / 'DBDAT/ENT98030.FDI').read_bytes()
    if registry.sha256_file(candidate / 'DBDAT/ENT98030.FDI') != receipt['after_ent_sha256']:
        raise ValueError('candidate ENT changed')
    records = lambda data: {e.record_id: data[e.payload_offset:e.payload_offset + e.payload_length]
                            for e in IndexedFDIFile.from_bytes(data).entries}
    left, right = records(before), records(after)
    if set(left) != set(right):
        raise ValueError('manager directory IDs changed')
    changes = {row['carrier_id']: row for row in receipt['changes']}
    if len(changes) != len(receipt['changes']):
        raise ValueError('duplicate manager updates')
    for carrier, raw in left.items():
        other = right[carrier]
        if carrier not in changes:
            if raw != other:
                raise ValueError('unrelated ENT profile changed')
            continue
        original = parse_indexed_ent_manager_profile(raw, record_id=carrier)
        updated = parse_indexed_ent_manager_profile(other, record_id=carrier)
        expected = changes[carrier]['native_names']
        if (updated.surname, updated.display_name) != (expected['surname'], expected['display_name']):
            raise ValueError('native short/full name read-back failed')
        if 'SHORTQA' in updated.surname or 'FULLQA' in updated.display_name:
            raise ValueError('field probe label leaked into a release')
        if (original.format != updated.format or xor_decode(raw)[2:7] != xor_decode(other)[2:7] or
                (original.format == 'full_profile' and
                 raw[original.profile_text_offset or len(raw):] != other[updated.profile_text_offset or len(other):])):
            raise ValueError('profile type, ID or biography bytes changed')
    for layer in [package] + ([english] if english_artifacts else []):
        for manager in layer['managers']:
            if not manager.get('native_names'):
                continue
            profile = parse_indexed_ent_manager_profile(right[manager['carrier_id']], record_id=manager['carrier_id'])
            alias = manager['native_names']
            if (profile.surname, profile.display_name) != (alias['surname'], alias['display_name']):
                raise ValueError('recipe layer does not match both native manager name fields')
    if receipt.get('legacy_english_bindings'):
        from scripts.reconcile_2015_recipe_manager_graph_v1 import checked_inputs
        graph = json.loads((ROOT / '.local/operations/2015-16/manager-facts-manager-graph-application-v1-r2-20260913.json').read_text())
        if (receipt['season'] != '2015-16' or graph['readback_failure_count'] != 0 or
                graph['byte_contract']['ent_after_sha256'] != receipt['source_ent_sha256']):
            raise ValueError('legacy bindings do not extend the proven native manager graph')
        checked_inputs(source)  # Check every exclusive manager edge/name, not unrelated tactics bytes.
    return package, receipt


def refresh_unpublished_workspace(season, release_id, workspace, destination, before, source, root):
    """Reuse our unregistered copy after checking and archiving its metadata.

    This is an explicit recovery operation, never an edit to a preferred or
    attested game. It avoids a second 26-game copy to correct recipe bindings.
    """
    if registry.load_preferred_release(season).release_id == release_id:
        raise ValueError('cannot refresh a registered game')
    locator_path = destination / 'locator.json'
    if locator_path.exists():
        locator = json.loads(locator_path.read_text())
        if locator.get('attestation_path') or locator.get('runtime_evidence_path'):
            raise ValueError('cannot refresh an attested game')
        if (ROOT / locator['game_path']).resolve() != (workspace / 'game').resolve():
            raise ValueError('unpublished locator points to another game')
    old_candidate = root / season / 'candidate-v1/candidate-receipt.json'
    old = json.loads(old_candidate.read_text())
    if old['source_release_id'] != source.release_id or old['source_package_sha256'] != registry.canonical_document_sha256(source.package_path):
        raise ValueError('unpublished game does not extend this baseline')
    actual = pipeline.build_tree_inventory(workspace / 'game')
    difference = pipeline.inventory_difference(before, actual)
    if (difference['only_left'] or difference['only_right'] or
            [row['path'] for row in difference['changed']] != ['DBDAT/ENT98030.FDI'] or
            registry.sha256_file(workspace / 'game/DBDAT/ENT98030.FDI') != old['after_ent_sha256']):
        raise ValueError('unpublished game changed beyond the exact earlier ENT candidate')
    recovery = root / 'unpublished-recipe-binding-recovery' / season
    if recovery.exists():
        ledger = json.loads((recovery / 'ledger.json').read_text())
        if (ledger['season'], ledger['release_id'], ledger['preferred_source'], ledger['before_inventory_fingerprint']) != (
                season, release_id, source.release_id, actual['files_fingerprint']):
            raise ValueError('existing unpublished recovery snapshot does not match this input')
        return {'metadata_recovery': str(recovery), 'independent_game_copy_reused': True, 'resumed_recovery': True}
    recovery.mkdir(parents=True)
    shutil.copytree(workspace, recovery / 'workspace-metadata', ignore=shutil.ignore_patterns('game'))
    if destination.exists():
        shutil.copytree(destination, recovery / 'registry-metadata')
    pipeline.write_canonical_json(recovery / 'ledger.json', {
        'schema': 'pm99-unpublished-manager-binding-recovery-v1', 'season': season,
        'release_id': release_id, 'preferred_source': source.release_id,
        'before_inventory_fingerprint': actual['files_fingerprint'],
        'reason': 'fix layered recipe aliases and legacy English manager bindings',
        'game_copy_reused': True, 'source_game_edited': False, 'deleted_files': [],
    })
    return {'metadata_recovery': str(recovery), 'independent_game_copy_reused': True}


def publish(season, root, runtime_gates, *, release_id=RELEASE, register=False,
            candidate_root=None, refresh_unpublished=False):
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,127}', release_id):
        raise ValueError('unsafe release ID')
    source = registry.load_preferred_release(season)
    if source.release_id == release_id:
        return {'season': season, 'already_registered': True}
    candidate = (candidate_root or root) / season / 'candidate-v1'
    package, plan = audit(candidate, source)
    workspace = root / season / release_id
    destination = registry.locator_path(season, release_id).parent
    if destination.exists() and not refresh_unpublished:
        if register:
            return register_completed_delta(season, release_id)
        raise ValueError('release already exists; inspect it, never overwrite')
    if workspace.exists() and not refresh_unpublished:
        raise ValueError('partial output exists; inspect it, never overwrite')
    before, drift = source_inventory(source)
    copies = {}
    for artifact in package['artifacts']:
        if not artifact.get('relative_path'):
            continue
        rel = Path(artifact['relative_path'])
        if not rel.parts or rel.is_absolute() or '..' in rel.parts or rel.parts[0] == 'game' or str(rel) in (
                'season-package.json', 'manager-display-compiler.json', 'manager-display-runtime-gates.json'):
            raise ValueError('unsafe recipe input path')
        options = (candidate / rel, source.package_path.parent / rel, ROOT / rel)
        path = next((p for p in options if p.is_file()), options[0])
        verify_recipe_artifact(path, artifact['sha256'])
        copies[rel] = path
    reuse = workspace.exists()
    required_copy_bytes = 0 if reuse else before['total_bytes']
    if shutil.disk_usage(root).free < required_copy_bytes + sum(p.stat().st_size for p in copies.values()) + 8 * 1024**3:
        raise ValueError('retain 8 GiB free after the independent game copy')
    recovery = refresh_unpublished_workspace(season, release_id, workspace, destination, before, source, root) if reuse else None
    write = _atomic_replace_json if recovery else pipeline.write_canonical_json
    workspace.mkdir(exist_ok=reuse)
    game = workspace / 'game'
    if not reuse:
        _copy_game_tree(source.game_path, game)
    temporary = workspace / 'ENT98030.FDI.partial'
    shutil.copy2(candidate / 'DBDAT/ENT98030.FDI', temporary)
    os.replace(temporary, game / 'DBDAT/ENT98030.FDI')
    for rel, path in copies.items():
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    package_path = workspace / 'season-package.json'
    packages.write_canonical_package(package_path, package)
    write(workspace / 'manager-display-plan.json', plan)
    write(workspace / 'manager-display-runtime-gates.json', runtime_gates)
    after = pipeline.build_tree_inventory(game)
    difference = pipeline.inventory_difference(before, after)
    if difference['only_left'] or difference['only_right'] or [r['path'] for r in difference['changed']] != ['DBDAT/ENT98030.FDI']:
        raise ValueError('manager display delta changed unrelated game files')
    outputs = [{'path': p, 'sha256': registry.sha256_file(game / p), 'size': (game / p).stat().st_size}
               for p in ('DBDAT/JUG98030.FDI', 'DBDAT/EQ98030.FDI', 'DBDAT/ENT98030.FDI')]
    receipt = {'schema': 'pm99-manager-display-delta-v1', 'season': season,
        'season_package_sha256': registry.canonical_document_sha256(package_path),
        'source_season_package_sha256': registry.canonical_document_sha256(source.package_path),
        'source_compiler_receipt_sha256': registry.sha256_file(source.compiler_receipt_path),
        'source_build_chain_sha256': registry.sha256_file(source.build_chain_path),
        'compilation_mode': 'known-good-baseline-manager-short-name-only-delta', 'outputs': outputs,
        'source_game_inventory_fingerprint': before['files_fingerprint'],
        'difference': difference, 'existing_runtime_config_difference': drift,
        'managers_written': plan['changed_managers'], 'unresolved_aliases': plan['unresolved_count'],
        'canonical_names_changed': 0, 'player_facts_written': 0, 'ratings_written': 0, 'artwork_written': 0,
        'independent_playable_game_copy': True, 'historical_verification_complete': False,
        'unpublished_recipe_binding_recovery': recovery,
        'allowed_write': 'proven ENT name segments and name-block lengths; IDs, type and biography exact'}
    receipt_path = workspace / 'manager-display-compiler.json'
    write(receipt_path, receipt)
    destination.mkdir(parents=True, exist_ok=bool(recovery))
    chain = {'schema_version': 'pm99-season-build-chain-v1', 'season': season,
        'package_canonical_sha256': receipt['season_package_sha256'], 'stages': [
            {'id': 'database', 'receipt_sha256': registry.sha256_file(receipt_path),
             'outputs': {r['path']: r['sha256'] for r in outputs}},
            {'id': 'inherited-known-good-assets', 'source_build_chain_sha256': receipt['source_build_chain_sha256'],
             'outputs': {r['path']: r['sha256'] for r in after['files'] if r['path'] not in [v['path'] for v in outputs]}}]}
    chain_path = destination / 'build-chain.json'
    write(chain_path, chain)
    manifest = pipeline.read_json_file(source.release_manifest_path)
    manifest['season_document'] = pipeline.canonical_json_document_descriptor(package_path, document_id='season-package')
    manifest['output'] = {'file_count': after['file_count'], 'total_bytes': after['total_bytes'],
                          'inventory_fingerprint': after['files_fingerprint']}
    artifacts = [pipeline.external_artifact_descriptor(artifact_id=aid, path=path, role='input') for aid, path in [
        ('manager-display-plan', workspace / 'manager-display-plan.json'), ('manager-display-compiler', receipt_path),
        ('manager-display-runtime-gates', workspace / 'manager-display-runtime-gates.json'),
        ('previous-build-chain', source.build_chain_path), ('previous-compiler-receipt', source.compiler_receipt_path),
        ('previous-recipe', source.package_path), ('build-chain', chain_path)]]
    replaced = {a['id'] for a in artifacts}
    manifest['external_artifacts'] = sorted([a for a in manifest['external_artifacts'] if a['id'] not in replaced] + artifacts,
                                            key=lambda a: a['id'])
    manifest['stages'].append(pipeline.make_stage_record(stage_id='manager-display-' + release_id,
        implementation_path=Path(__file__), input_fingerprints={'previous-release': source.manifest_sha256},
        parameters={'managers_written': plan['changed_managers'], 'scope': 'native display aliases, not historical identity changes'},
        external_artifacts=artifacts))
    manifest['stages'].sort(key=lambda s: s['id'])
    pipeline.validate_release_manifest(manifest)
    metadata = destination / 'metadata'
    metadata.mkdir(exist_ok=bool(recovery))
    manifest_path, inventory_path = metadata / 'season-manifest.json', metadata / 'output.inventory.json'
    write(manifest_path, manifest)
    write(inventory_path, after)
    locator = copy.deepcopy(source.locator)
    for field in ('qa_report_path', 'qa_report_sha256'):
        locator.pop(field, None)
    locator.update({'release_id': release_id, 'game_path': registry.relative_workspace_path(game),
        'package_path': registry.relative_workspace_path(package_path), 'package_canonical_sha256': receipt['season_package_sha256'],
        'compiler_receipt_path': registry.relative_workspace_path(receipt_path),
        'inventory_path': registry.relative_workspace_path(inventory_path),
        'release_manifest_path': registry.relative_workspace_path(manifest_path), 'build_chain_path': registry.relative_workspace_path(chain_path),
        'game_inventory_fingerprint': after['files_fingerprint'], 'attestation_path': None,
        'runtime_evidence_path': None, 'technical_status': 'playable-unverified', 'qa_status': 'not-recorded'})
    locator['required_file_hashes'] = {file: registry.sha256_file(game / file) for file in registry.REQUIRED_GAME_FILES}
    write(destination / 'locator.json', locator)
    pipeline.assert_tree_matches_inventory(source.game_path, before)
    result = {'season': season, 'release_id': release_id, 'managers_written': plan['changed_managers'], 'registered': False}
    if register:
        result.update(register_completed_delta(season, release_id), registered=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season')
    parser.add_argument('--root', type=Path, default=ROOT / '.local/manager-display-v1')
    parser.add_argument('--release-id', default=RELEASE)
    parser.add_argument('--register', action='store_true')
    parser.add_argument('--candidate-root', type=Path)
    parser.add_argument('--refresh-unpublished', action='store_true', help='archive metadata and reuse only our exact unregistered copies')
    args = parser.parse_args()
    root = args.root.resolve()
    runtime_gates = gates(root)
    for season in registry.supported_seasons() if args.season == 'all' else [args.season]:
        print(json.dumps(publish(season, root, runtime_gates, release_id=args.release_id, register=args.register,
                                candidate_root=args.candidate_root.resolve() if args.candidate_root else None,
                                refresh_unpublished=args.refresh_unpublished)), flush=True)
