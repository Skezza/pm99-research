#!/usr/bin/env python3
"""Publish the audited English tactics rollout as bounded known-good deltas.

Requires every formation family to have a genuine sampled runtime proof and
both classes of startup repair to have runtime evidence. Never describes those
samples as gameplay validation of every club. Facts, ratings and assets stay
byte-exact; independent playable copies do not share mutable source inodes.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'upstream/pm99-skezmod-db-editor')]
from scripts import season_contextual_tactics_v1 as tactics
from scripts import season_opening_order_repair_v1 as repair
from scripts import season_tactics_formation_runtime_v1 as runtime
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_package_v2 as packages
from scripts.season_visual_patch_v1 import source_inventory
from scripts.season_playtest_variant_v1 import _copy_game_tree
from scripts.publish_contextual_tactics_delta_v1 import verify_recipe_artifact
from scripts.publish_historical_role_delta_v1 import register_completed_delta
from scripts.verify_contextual_tactics_runtime_v1 import verify

DEFAULT_RELEASE = 'historical-contextual-tactics-20261005-r21a'


def completion_gates(root):
    coverage = runtime.verify_coverage(root, root)
    checks = []
    for season, carrier, tag in [
        ('2001-02', 375, 'tactics_deployment_repaired_stoke_2001_02_20261005_c'),
        ('2015-16', 324, 'tactics_order_repaired_stevenage_2015_16_20261005_b'),
    ]:
        candidate = root / season / 'english-rollout-candidate-v3'
        run = ROOT / '.local/runlogs/pm99_runner' / tag
        proof = verify(candidate, run, carrier)
        launch = json.loads((run / 'control_launch.json').read_text())['child_command']
        dbdat = Path(launch[launch.index('--dbdat-dir') + 1])
        exe = Path(launch[launch.index('--exe-file') + 1])
        expected_exe = Path(json.loads((candidate / 'candidate-receipt.json').read_text())['exe_path'])
        if (any(registry.sha256_file(dbdat / file) != registry.sha256_file(candidate / 'DBDAT' / file)
                for file in ('EQ98030.FDI', 'JUG98030.FDI')) or
                registry.sha256_file(exe) != registry.sha256_file(expected_exe)):
            raise ValueError('startup repair proof used another database/executable')
        checks.append({'season': season, 'carrier_id': carrier, 'run': str(run),
                       'proof': proof, 'scope': 'one genuinely loaded team for this repair class'})
    original = registry.load_registered_release('2015-16', 'historical-contextual-tactics-20261005-r20a')
    completion_path = original.package_path.parent / 'tactics-completion-proof.json'
    completion = json.loads(completion_path.read_text())
    match_path = ROOT / completion['match_run'] / 'summary.json'
    match = json.loads(match_path.read_text())
    if (not completion['save_reload_proven'] or not completion['match_smoke_proven'] or
            registry.sha256_file(ROOT / completion['saved_file']) != completion['saved_file_sha256'] or
            registry.sha256_file(match_path) != completion['match_summary_sha256'] or
            not match.get('success') or match.get('match_count', 0) < 1 or
            not match.get('skip_initial_tactics_strategy') or match.get('crash_detected')):
        raise ValueError('inherited pilot native save/reload/match proof changed or failed')
    from app.eq_initial_tactics import read_initial_tactics
    final_eq = tactics.payloads((root / '2015-16/english-rollout-candidate-v3/DBDAT/EQ98030.FDI').read_bytes())[307]
    baseline_eq = tactics.payloads((original.game_path / 'DBDAT/EQ98030.FDI').read_bytes())[307]
    if read_initial_tactics(final_eq) != read_initial_tactics(baseline_eq):
        raise ValueError('rollout changed the completed native save/reload pilot grid')
    fresh_run = ROOT / '.local/runlogs/pm99_runner/tactics_rollout_match_2015_16_20261005_t'
    fresh_path = fresh_run / 'summary.json'
    fresh = json.loads(fresh_path.read_text())
    launch = json.loads((fresh_run / 'control_launch.json').read_text())['child_command']
    inputs = Path(launch[launch.index('--dbdat-dir') + 1])
    played_exe = Path(launch[launch.index('--exe-file') + 1])
    candidate = root / '2015-16/english-rollout-candidate-v3'
    if (not fresh.get('success') or not fresh.get('dashboard_reached') or fresh.get('match_count', 0) < 1 or
            not fresh.get('skip_initial_tactics_strategy') or fresh.get('crash_detected') or fresh.get('wine_debugger_detected') or
            any(registry.sha256_file(inputs / file) != registry.sha256_file(candidate / 'DBDAT' / file)
                for file in ('EQ98030.FDI', 'JUG98030.FDI')) or
            registry.sha256_file(played_exe) != registry.sha256_file(original.game_path / 'MANAGPRE.EXE')):
        raise ValueError('final rollout did not complete a match with shipped tactics preserved')
    return {'schema_version': 'pm99-contextual-tactics-rollout-runtime-gates-v1',
            'formation_coverage': coverage, 'opening_order_samples': checks,
            'native_save_reload_match_pilot': {'path': str(completion_path),
                'sha256': registry.sha256_file(completion_path), 'unchanged_stoke_grid': True,
                'scope': 'inherited unchanged Stoke pilot only, not save/reload or matches for every shape'},
            'fresh_rollout_match': {'run': str(fresh_run), 'summary_sha256': registry.sha256_file(fresh_path),
                'scope': 'one completed Stoke match with all 92 English contextual club grids loaded'},
            'every_club_runtime_tested': False, 'foreign_mode1': 'preserved, not authored'}


def publish(season, root, gates, *, release_id, register=False):
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,127}', release_id):
        raise ValueError('invalid release ID')
    current = registry.load_preferred_release(season)
    if current.release_id == release_id:
        pipeline.assert_tree_matches_inventory(current.game_path, pipeline.read_json_file(current.inventory_path))
        return {'season': season, 'release_id': release_id, 'already_registered': True, 'registered': True}
    candidate = root / season / 'english-rollout-candidate-v3'
    audit = repair.audit_candidate(candidate)
    formations = json.loads((candidate / 'contextual-tactics.json').read_text())['clubs']
    if (gates.get('schema_version') != 'pm99-contextual-tactics-rollout-runtime-gates-v1' or
            gates.get('formation_coverage', {}).get('success') is not True or
            {c['formation'] for c in formations} - set(gates['formation_coverage']['samples']) or
            len(gates.get('opening_order_samples', [])) != 2):
        raise ValueError('rollout requires formation and both opening-order runtime gates')
    prior = json.loads((candidate / 'candidate-receipt.json').read_text())
    if (current.release_id, registry.canonical_document_sha256(current.package_path),
            registry.sha256_file(current.game_path / 'DBDAT/EQ98030.FDI'),
            registry.sha256_file(current.game_path / 'DBDAT/JUG98030.FDI')) != (
            prior['source_release_id'], prior['source_package_sha256'], prior['source_eq_sha256'], prior['source_jug_sha256']):
        raise ValueError('rollout does not extend the current known-good release')
    before, drift = source_inventory(current)
    if shutil.disk_usage(root).free < before['total_bytes'] + 8 * 1024**3:
        raise ValueError('retain at least 8 GiB free after the independent game copy')
    workspace = root / season / release_id
    destination = registry.locator_path(season, release_id).parent
    if workspace.exists() or destination.exists():
        raise ValueError('release output exists; inspect/resume it, never overwrite')
    package = json.loads((candidate / 'season-package.json').read_text())
    packages.validate_package(package)
    copies, bindings = {}, []
    for artifact in package['artifacts']:
        if not artifact.get('relative_path'):
            continue
        rel = Path(artifact['relative_path'])
        if (not rel.parts or rel.is_absolute() or '..' in rel.parts or rel.parts[0] == 'game' or
                str(rel) in ('season-package.json', 'runtime-formation-gates.json', 'tactics-rollout-compiler.json')):
            raise ValueError('unsafe rollout recipe-local input')
        options = (candidate / rel, current.package_path.parent / rel, ROOT / rel)
        source = next((p for p in options if p.is_file()), options[0])
        binding = verify_recipe_artifact(source, artifact['sha256'])
        if rel in copies and copies[rel] != source:
            raise ValueError('conflicting rollout recipe-local input')
        copies[rel] = source
        bindings.append({'id': artifact['id'], **binding})
    for file in ('contextual-tactics.json', 'opening-order.json', 'english-season-package.json'):
        copies[Path(file)] = candidate / file
    expected_input_bytes = sum(path.stat().st_size for path in set(copies.values()))
    if shutil.disk_usage(root).free < before['total_bytes'] + expected_input_bytes + 8 * 1024**3:
        raise ValueError('insufficient space for the independent game and retained recipe inputs')
    workspace.mkdir()
    game = workspace / 'game'
    _copy_game_tree(current.game_path, game)
    for file in ('EQ98030.FDI', 'JUG98030.FDI'):
        temporary = workspace / (file + '.partial')
        shutil.copy2(candidate / 'DBDAT' / file, temporary)
        os.replace(temporary, game / 'DBDAT' / file)
    for rel, source in copies.items():
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    if any(registry.sha256_file(game / 'DBDAT' / file) != registry.sha256_file(candidate / 'DBDAT' / file)
           for file in ('EQ98030.FDI', 'JUG98030.FDI')):
        raise ValueError('published database differs from frozen candidate bytes')
    package_path = workspace / 'season-package.json'
    package_path.write_bytes(packages.canonical_json_bytes(package))
    gate_path = workspace / 'runtime-formation-gates.json'
    pipeline.write_canonical_json(gate_path, gates)
    after = pipeline.build_tree_inventory(game)
    difference = pipeline.inventory_difference(before, after)
    changed = [r['path'] for r in difference['changed']]
    if difference['only_left'] or difference['only_right'] or set(changed) - {'DBDAT/EQ98030.FDI', 'DBDAT/JUG98030.FDI'}:
        raise ValueError('rollout changed unrelated game files')
    outputs = [{'path': p, 'sha256': registry.sha256_file(game / p), 'size': (game / p).stat().st_size}
               for p in ('DBDAT/JUG98030.FDI', 'DBDAT/EQ98030.FDI', 'DBDAT/ENT98030.FDI')]
    receipt = {'schema': 'pm99-contextual-tactics-rollout-delta-v1', 'season': season,
        'season_package_sha256': registry.canonical_document_sha256(package_path),
        'source_season_package_sha256': registry.canonical_document_sha256(current.package_path),
        'source_compiler_receipt_sha256': registry.sha256_file(current.compiler_receipt_path),
        'source_build_chain_sha256': registry.sha256_file(current.build_chain_path),
        'source_game_inventory_fingerprint': before['files_fingerprint'],
        'compilation_mode': 'known-good-baseline-English-contextual-tactics-and-startup-order-delta',
        'clubs_written': audit['contextual_clubs'], 'startup_bytes_changed': audit['startup_bytes_changed'],
        'player_facts_written': 0, 'ratings_written': 0, 'managers_written': 0, 'artwork_written': 0,
        'outputs': outputs, 'difference': difference, 'existing_runtime_config_difference': drift,
        'byte_idempotent': True, 'independent_playable_game_copy': True,
        'inherited_artifact_bindings': bindings, 'offline_audit': audit,
        'runtime_scope': gates['formation_coverage']['scope'],
        'foreign_mode1': 'byte-for-byte preserved; named-slot contract not proved',
        'allowed_write': 'English selected EQ coordinate grids; explicitly named one-byte JUG startup order only'}
    receipt_path = workspace / 'tactics-rollout-compiler.json'
    pipeline.write_canonical_json(receipt_path, receipt)
    destination.mkdir(parents=True)
    chain = {'schema_version': 'pm99-season-build-chain-v1', 'season': season,
        'package_canonical_sha256': receipt['season_package_sha256'], 'stages': [
            {'id': 'database', 'receipt_sha256': registry.sha256_file(receipt_path),
             'outputs': {r['path']: r['sha256'] for r in outputs}},
            {'id': 'inherited-known-good-assets', 'source_build_chain_sha256': receipt['source_build_chain_sha256'],
             'outputs': {r['path']: r['sha256'] for r in after['files'] if not r['path'].endswith(('JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI'))}}]}
    chain_path = destination / 'build-chain.json'
    pipeline.write_canonical_json(chain_path, chain)
    manifest = pipeline.read_json_file(current.release_manifest_path)
    manifest['season_document'] = pipeline.canonical_json_document_descriptor(package_path, document_id='season-package')
    manifest['output'] = {'file_count': after['file_count'], 'total_bytes': after['total_bytes'],
                          'inventory_fingerprint': after['files_fingerprint']}
    artifacts = [pipeline.external_artifact_descriptor(artifact_id=identity, path=path, role='input')
        for identity, path in [('contextual-tactics-layer', workspace / 'contextual-tactics.json'),
            ('opening-order-layer', workspace / 'opening-order.json'), ('contextual-tactics-runtime-gates', gate_path),
            ('contextual-tactics-rollout-compiler', receipt_path), ('previous-build-chain', current.build_chain_path),
            ('previous-compiler-receipt', current.compiler_receipt_path), ('previous-recipe', current.package_path),
            ('build-chain', chain_path)]]
    replaced = {a['id'] for a in artifacts}
    manifest['external_artifacts'] = sorted([a for a in manifest['external_artifacts'] if a['id'] not in replaced] + artifacts,
                                            key=lambda a: a['id'])
    manifest['stages'].append(pipeline.make_stage_record(stage_id='contextual-tactics-rollout-' + release_id,
        implementation_path=Path(__file__), input_fingerprints={'previous-release': current.manifest_sha256},
        parameters={'contextual_clubs': 92, 'scope': 'English mode0; sampled runtime formation coverage',
                    'startup_bytes_changed': audit['startup_bytes_changed']}, external_artifacts=artifacts))
    manifest['stages'].sort(key=lambda s: s['id'])
    pipeline.validate_release_manifest(manifest)
    metadata = destination / 'metadata'
    metadata.mkdir()
    manifest_path, inventory_path = metadata / 'season-manifest.json', metadata / 'output.inventory.json'
    pipeline.write_canonical_json(manifest_path, manifest)
    pipeline.write_canonical_json(inventory_path, after)
    locator = copy.deepcopy(current.locator)
    for field in ('qa_report_path', 'qa_report_sha256'):
        locator.pop(field, None)
    locator.update({'release_id': release_id, 'game_path': registry.relative_workspace_path(game),
        'package_path': registry.relative_workspace_path(package_path), 'package_canonical_sha256': receipt['season_package_sha256'],
        'compiler_receipt_path': registry.relative_workspace_path(receipt_path),
        'inventory_path': registry.relative_workspace_path(inventory_path),
        'release_manifest_path': registry.relative_workspace_path(manifest_path),
        'build_chain_path': registry.relative_workspace_path(chain_path),
        'game_inventory_fingerprint': after['files_fingerprint'], 'attestation_path': None,
        'runtime_evidence_path': None, 'technical_status': 'playable-unverified', 'qa_status': 'not-recorded'})
    locator['required_file_hashes'] = {file: registry.sha256_file(game / file) for file in registry.REQUIRED_GAME_FILES}
    pipeline.write_canonical_json(destination / 'locator.json', locator)
    pipeline.assert_tree_matches_inventory(current.game_path, before)
    result = {'season': season, 'release_id': release_id, 'registered': False, 'contextual_clubs': 92,
              'startup_bytes_changed': audit['startup_bytes_changed'], 'changed_game_files': changed,
              'game_path': str(game), 'every_club_runtime_tested': False}
    if register:
        result.update(register_completed_delta(season, release_id), registered=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season')
    parser.add_argument('--root', type=Path, default=ROOT / '.local/contextual-tactics-v1')
    parser.add_argument('--release-id', default=DEFAULT_RELEASE)
    parser.add_argument('--register', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    gates = completion_gates(root)
    for season in registry.supported_seasons() if args.season == 'all' else [args.season]:
        result = publish(season, root, gates, release_id=args.release_id, register=args.register)
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
