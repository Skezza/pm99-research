#!/usr/bin/env python3
"""Publish a runtime-proven tactics-only change without regenerating a season."""
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
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_package_v2 as package_v2
from scripts import season_pipeline_v2 as pipeline
from scripts import season_contextual_tactics_v1 as tactics
from scripts.season_visual_patch_v1 import source_inventory
from scripts.publish_historical_role_delta_v1 import register_completed_delta
from scripts.season_playtest_variant_v1 import _copy_game_tree


def verify_recipe_artifact(path: Path, expected_sha256: str):
    """Older JSON layers bind semantic compact JSON, not their pretty file."""
    raw_sha = registry.sha256_file(path)
    if raw_sha == expected_sha256:
        return {'hash_contract': 'raw-file', 'raw_sha256': raw_sha}
    if path.suffix.lower() == '.json':
        semantic_sha = hashlib.sha256(pipeline.canonical_json_bytes(json.loads(path.read_text()))).hexdigest()
        if semantic_sha == expected_sha256:
            return {'hash_contract': 'canonical-semantic-json', 'raw_sha256': raw_sha,
                    'canonical_sha256': semantic_sha}
    raise ValueError('recipe-local input missing or its hash changed: ' + str(path))


def verify_completion(candidate: Path, save_run: Path, reload_run: Path, match_run: Path):
    """Require a genuinely changed native save and a negative-control reload."""
    from app.eq_initial_tactics import GRID_BYTES, read_initial_tactics
    from scripts.verify_contextual_tactics_runtime_v1 import verify
    original = json.loads((candidate / 'candidate-receipt.json').read_text())
    eq = tactics.payloads((candidate / 'DBDAT/EQ98030.FDI').read_bytes())[307]
    offset = read_initial_tactics(eq).grid_offset
    grid = eq[offset:offset + GRID_BYTES]
    source_game = Path(original['source_game_path'])
    source_eq = tactics.payloads((source_game / 'DBDAT/EQ98030.FDI').read_bytes())[307]
    source_offset = read_initial_tactics(source_eq).grid_offset
    if source_eq[source_offset:source_offset + GRID_BYTES] == grid:
        raise ValueError('reload baseline already contains the candidate tactics')
    saves = [p for p in (save_run / 'tactics_library').glob('TACTIC.*')
             if p.read_bytes().startswith(b'\xff') and p.read_bytes().endswith(grid)
             and (source_game / 'TACTICS' / p.name).is_file()
             and p.read_bytes() != (source_game / 'TACTICS' / p.name).read_bytes()]
    if len(saves) != 1:
        raise ValueError('game did not produce one independently changed native tactics save')
    saved = saves[0]
    def launch(folder):
        return json.loads((folder / 'control_launch.json').read_text())['child_command']
    def argument(command, name):
        if name not in command:
            raise ValueError('missing runtime validation argument: ' + name)
        return command[command.index(name) + 1]
    save_command, reload_command, match_command = map(launch, (save_run, reload_run, match_run))
    if Path(argument(save_command, '--dbdat-dir')).resolve() != (candidate / 'DBDAT').resolve():
        raise ValueError('native save did not come from this candidate')
    if (Path(argument(reload_command, '--dbdat-dir')).resolve() != (source_game / 'DBDAT').resolve()
            or Path(argument(reload_command, '--tactics-override-file')).resolve() != saved.resolve()
            or '--tactics-load-row' not in reload_command):
        raise ValueError('reload was not an independent old-baseline negative control')
    reload_proof = verify(candidate, reload_run)
    summary = json.loads((match_run / 'summary.json').read_text())
    if (Path(argument(match_command, '--dbdat-dir')).resolve() != (candidate / 'DBDAT').resolve()
            or not summary.get('success') or not summary.get('dashboard_reached')
            or summary.get('crash_detected') or summary.get('wine_debugger_detected')
            or summary.get('match_count', 0) < 1 or not summary.get('skip_initial_tactics_strategy')):
        raise ValueError('candidate did not complete a match with its opening tactics preserved')
    return {'save_reload_proven': True, 'match_smoke_proven': True,
            'saved_file': registry.relative_workspace_path(saved),
            'saved_file_sha256': registry.sha256_file(saved),
            'reload_proof': reload_proof,
            'match_summary_sha256': registry.sha256_file(match_run / 'summary.json'),
            'save_run': registry.relative_workspace_path(save_run),
            'reload_run': registry.relative_workspace_path(reload_run),
            'match_run': registry.relative_workspace_path(match_run)}


def publish(candidate: Path, run: Path, *, release_id: str, register: bool = False,
            save_run: Path | None = None, reload_run: Path | None = None, match_run: Path | None = None):
    from scripts.verify_contextual_tactics_runtime_v1 import verify
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,127}', release_id):
        raise ValueError('invalid release ID')
    proof = verify(candidate, run)
    if any(p is not None for p in (save_run, reload_run, match_run)) and not all(
            p is not None for p in (save_run, reload_run, match_run)):
        raise ValueError('provide all three save, reload and match runs')
    if register and save_run is None:
        raise ValueError('registration requires independent save/reload and match proof')
    completion = verify_completion(candidate, save_run, reload_run, match_run) if save_run else None
    original = json.loads((candidate / 'candidate-receipt.json').read_text())
    release = registry.load_preferred_release(original['season'])
    if (release.release_id, registry.canonical_document_sha256(release.package_path),
            registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'),
            registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI')) != (
            original['source_release_id'], original['source_package_sha256'],
            original['source_eq_sha256'], original['source_jug_sha256']):
        raise ValueError('tactics candidate no longer extends the current release')
    layer = json.loads((candidate / 'contextual-tactics.json').read_text())
    if len(layer['clubs']) != 1 or layer['clubs'][0]['carrier_id'] != 307:
        raise ValueError('Stoke pilot publisher cannot publish a multi-club rollout; require formation coverage gates')
    before_eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    after_eq = tactics.apply_layer(before_eq, jug, layer)
    if (after_eq != (candidate / 'DBDAT/EQ98030.FDI').read_bytes() or
            hashlib.sha256(after_eq).hexdigest() != original['output_eq_sha256'] or
            tactics.apply_layer(after_eq, jug, layer) != after_eq):
        raise ValueError('candidate tactics bytes changed or are not deterministic')
    launch = json.loads((run / 'control_launch.json').read_text())['child_command']
    if Path(launch[launch.index('--dbdat-dir') + 1]).resolve() != (candidate / 'DBDAT').resolve():
        raise ValueError('runtime evidence belongs to a different candidate')
    destination = registry.locator_path(release.season, release_id).parent
    workspace = candidate.parent / release_id
    if workspace.exists() or destination.exists():
        raise ValueError('tactics release exists; never overwrite')
    before, runtime_drift = source_inventory(release)
    if shutil.disk_usage(candidate.parent).free < before['total_bytes'] + 512 * 1024 * 1024:
        raise ValueError('insufficient space for an independent playable tactics release')
    package = json.loads((candidate / 'season-package.json').read_text())
    package['artifacts'].append({'id': 'english-contextual-package-2015-16', 'kind': 'season-input',
        'sha256': registry.sha256_file(candidate / 'english-season-package.json'),
        'media_type': 'application/json', 'relative_path': 'english-season-package.json'})
    package['artifacts'].sort(key=lambda a: a['id'])
    package_v2.validate_package(package)
    inherited_artifact_bindings = []
    input_copies = []
    for artifact in package['artifacts']:
        relative = artifact.get('relative_path')
        if not relative:
            continue
        rel = Path(relative)
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('unsafe inherited tactics recipe artifact path')
        options = (candidate / rel, release.package_path.parent / rel, ROOT / rel)
        source = next((p for p in options if p.is_file()), options[0])
        target = workspace / rel
        if not source.is_file():
            raise ValueError('recipe-local input missing or its hash changed')
        binding = verify_recipe_artifact(source, artifact['sha256'])
        inherited_artifact_bindings.append({'id': artifact['id'], **binding})
        input_copies.append((source, target))
    # All recipe inputs and runtime gates are verified before creating output.
    workspace.mkdir()
    game = workspace / 'game'
    # This tree is launched directly by pm99-season. It must not share mutable
    # TACTICS, settings or save-file inodes with the preceding release. Reflinks
    # are safe; the helper falls back to independent ordinary copies.
    _copy_game_tree(release.game_path, game)
    temporary = workspace / 'EQ98030.FDI.partial'
    temporary.write_bytes(after_eq)
    os.replace(temporary, game / 'DBDAT/EQ98030.FDI')
    for source, target in input_copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    package_path = workspace / 'season-package.json'
    package_path.write_bytes(package_v2.canonical_json_bytes(package))
    proof_path = workspace / 'tactics-visual-runtime-proof.json'
    pipeline.write_canonical_json(proof_path, proof)
    if completion:
        pipeline.write_canonical_json(workspace / 'tactics-completion-proof.json', completion)
    after = pipeline.build_tree_inventory(game)
    difference = pipeline.inventory_difference(before, after)
    if (difference['only_left'] or difference['only_right'] or
            [r['path'] for r in difference['changed']] != ['DBDAT/EQ98030.FDI']):
        raise ValueError('tactics delta changed unrelated game files')
    outputs = [{'path': p, 'sha256': registry.sha256_file(game / p), 'size': (game / p).stat().st_size}
               for p in ('DBDAT/JUG98030.FDI', 'DBDAT/EQ98030.FDI', 'DBDAT/ENT98030.FDI')]
    receipt = {'schema': 'pm99-native-contextual-tactics-delta-v1', 'season': release.season,
        'season_package_sha256': registry.canonical_document_sha256(package_path),
        'source_season_package_sha256': registry.canonical_document_sha256(release.package_path),
        'source_compiler_receipt_sha256': registry.sha256_file(release.compiler_receipt_path),
        'source_build_chain_sha256': registry.sha256_file(release.build_chain_path),
        'source_game_inventory_fingerprint': before['files_fingerprint'],
        'compilation_mode': 'known-good-baseline-tactics-only-delta', 'clubs_written': len(layer['clubs']),
        'players_written': 0, 'managers_written': 0, 'outputs': outputs,
        'difference': difference, 'existing_runtime_config_difference': runtime_drift,
        'changed_carriers': original['changed_carriers'], 'changed_bytes': original['changed_bytes'],
        'byte_idempotent': True, 'runtime_states_proven': True, 'phase_averages_proven': True,
        'independent_playable_game_copy': True,
        'inherited_artifact_bindings': inherited_artifact_bindings,
        'save_reload_proven': bool(completion), 'match_smoke_proven': bool(completion),
        'runtime_proof_path': registry.relative_workspace_path(run / 'tactics-runtime-proof.json'),
        'allowed_write': 'named XI 1760-byte coordinate grid and explicitly evidenced two-byte control restoration; all other records exact'}
    receipt_path = workspace / 'tactics-delta-compiler.json'
    pipeline.write_canonical_json(receipt_path, receipt)
    destination.mkdir(parents=True)
    chain = {'schema_version': 'pm99-season-build-chain-v1', 'season': release.season,
        'package_canonical_sha256': receipt['season_package_sha256'], 'stages': [
            {'id': 'database', 'receipt_sha256': registry.sha256_file(receipt_path),
             'outputs': {r['path']: r['sha256'] for r in outputs}},
            {'id': 'inherited-known-good-assets', 'source_build_chain_sha256': receipt['source_build_chain_sha256'],
             'outputs': {r['path']: r['sha256'] for r in after['files'] if not r['path'].endswith(('JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI'))}}]}
    chain_path = destination / 'build-chain.json'
    pipeline.write_canonical_json(chain_path, chain)
    manifest = pipeline.read_json_file(release.release_manifest_path)
    manifest['season_document'] = pipeline.canonical_json_document_descriptor(package_path, document_id='season-package')
    manifest['output'] = {'file_count': after['file_count'], 'total_bytes': after['total_bytes'],
                          'inventory_fingerprint': after['files_fingerprint']}
    artifacts = [pipeline.external_artifact_descriptor(artifact_id=aid, path=path, role='input') for aid, path in [
        ('contextual-tactics-layer', workspace / 'contextual-tactics.json'),
        ('contextual-tactics-proof', proof_path), ('contextual-tactics-delta-compiler', receipt_path),
        ('previous-build-chain', release.build_chain_path), ('previous-compiler-receipt', release.compiler_receipt_path),
        ('previous-recipe', release.package_path), ('build-chain', chain_path)]]
    if completion:
        artifacts.extend(pipeline.external_artifact_descriptor(artifact_id=aid, path=path, role='input')
            for aid, path in [('contextual-tactics-completion', workspace / 'tactics-completion-proof.json'),
                ('contextual-tactics-native-save', ROOT / completion['saved_file']),
                ('contextual-tactics-reload-state', reload_run / 'tactics-runtime-proof.json'),
                ('contextual-tactics-match-summary', match_run / 'summary.json')])
    replaced = {a['id'] for a in artifacts}
    manifest['external_artifacts'] = sorted([a for a in manifest['external_artifacts'] if a['id'] not in replaced] + artifacts, key=lambda a: a['id'])
    manifest['stages'].append(pipeline.make_stage_record(stage_id='contextual-tactics-' + release_id,
        implementation_path=Path(__file__), input_fingerprints={'previous-release': release.manifest_sha256},
        parameters={'changed_clubs': len(layer['clubs']), 'byte_idempotent': True, 'scope': 'Stoke 2015 only'},
        external_artifacts=artifacts))
    manifest['stages'].sort(key=lambda s: s['id'])
    pipeline.validate_release_manifest(manifest)
    metadata = destination / 'metadata'
    metadata.mkdir()
    manifest_path = metadata / 'season-manifest.json'
    inventory_path = metadata / 'output.inventory.json'
    pipeline.write_canonical_json(manifest_path, manifest)
    pipeline.write_canonical_json(inventory_path, after)
    locator = copy.deepcopy(release.locator)
    for field in ('qa_report_path', 'qa_report_sha256'):
        locator.pop(field, None)
    locator.update({'release_id': release_id, 'game_path': registry.relative_workspace_path(game),
        'package_path': registry.relative_workspace_path(package_path),
        'package_canonical_sha256': receipt['season_package_sha256'],
        'compiler_receipt_path': registry.relative_workspace_path(receipt_path),
        'inventory_path': registry.relative_workspace_path(inventory_path),
        'release_manifest_path': registry.relative_workspace_path(manifest_path),
        'build_chain_path': registry.relative_workspace_path(chain_path),
        'game_inventory_fingerprint': after['files_fingerprint'], 'attestation_path': None,
        'runtime_evidence_path': None, 'technical_status': 'playable-unverified', 'qa_status': 'not-recorded'})
    locator['required_file_hashes'] = {name: registry.sha256_file(game / name) for name in registry.REQUIRED_GAME_FILES}
    pipeline.write_canonical_json(destination / 'locator.json', locator)
    pipeline.assert_tree_matches_inventory(release.game_path, before)
    result = {'season': release.season, 'release_id': release_id, 'registered': False,
              'changed_clubs': len(layer['clubs']), 'changed_game_files': ['DBDAT/EQ98030.FDI'], 'game': str(game)}
    if register:
        result.update(register_completed_delta(release.season, release_id), registered=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('run', type=Path)
    parser.add_argument('--release-id', required=True)
    parser.add_argument('--register', action='store_true')
    parser.add_argument('--save-run', type=Path)
    parser.add_argument('--reload-run', type=Path)
    parser.add_argument('--match-run', type=Path)
    args = parser.parse_args()
    print(json.dumps(publish(args.candidate.resolve(), args.run.resolve(),
        release_id=args.release_id, register=args.register,
        save_run=args.save_run, reload_run=args.reload_run, match_run=args.match_run), indent=2))


if __name__ == '__main__':
    main()
