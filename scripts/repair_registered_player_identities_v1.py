#!/usr/bin/env python3
"""Repair recipe-declared cloned player IDs without rebuilding season content."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'upstream/pm99-skezmod-db-editor'))
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.attest_registered_season_runtime_v1 import _atomic_replace_json
from app.indexed_jug_identity import repair_indexed_player_identities as repair
from scripts.season_visual_patch_v1 import source_inventory


def declared_repairs(package, rows):
    """Fail closed unless every mismatch is exactly a declared append donor."""
    donors = {int(p['carrier_id']): int(p['append_from_carrier_id'])
              for p in package['players'] if 'append_from_carrier_id' in p}
    for row in rows:
        if donors.get(row['record_id']) != row['old_native_id']:
            raise ValueError(f"undeclared player identity mismatch: {row}")


def publish(season, *, release_id, register=False):
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,127}', release_id):
        raise ValueError('invalid release ID')
    release = registry.load_preferred_release(season)
    source = release.game_path / 'DBDAT/JUG98030.FDI'
    old_bytes = source.read_bytes()
    repaired, rows = repair(old_bytes)
    declared_repairs(json.loads(release.package_path.read_text()), rows)
    if not rows:
        return {'season': season, 'status': 'already-correct', 'repaired_players': 0}
    destination = registry.locator_path(season, release_id).parent
    game = ROOT / '.local/season-identity-repairs-v1' / season / release_id / 'game'
    if destination.exists() or game.parent.exists():
        raise ValueError('repair release already exists; never overwrite')
    before, runtime_config = source_inventory(release)
    game.parent.mkdir(parents=True)
    shutil.copytree(release.game_path, game, copy_function=os.link)
    # Never write through a hardlink into the old release.
    temporary = game.parent / 'JUG98030.FDI.partial'
    temporary.write_bytes(repaired)
    os.replace(temporary, game / 'DBDAT/JUG98030.FDI')
    after = pipeline.build_tree_inventory(game)
    difference = pipeline.inventory_difference(before, after)
    if (difference['only_left'] or difference['only_right'] or
            [r['path'] for r in difference['changed']] != ['DBDAT/JUG98030.FDI']):
        raise ValueError('identity repair changed unrelated game content')
    if repair(repaired)[1]:
        raise ValueError('native identity validation failed after repair')
    receipt_path = game.parent / 'identity-repair.json'
    receipt = {'schema_version': 'pm99-native-player-identity-repair-v1',
        'season': season, 'previous_release_id': release.release_id,
        'previous_release_manifest_sha256': release.manifest_sha256,
        'package_canonical_sha256': release.locator['package_canonical_sha256'],
        'repaired_players': rows, 'difference': difference,
        'existing_runtime_config_difference': runtime_config,
        'allowed_write': 'two native self-ID bytes per recipe-declared clone only',
        'byte_contract': {'jug_before_sha256': hashlib.sha256(old_bytes).hexdigest(),
            'jug_after_sha256': hashlib.sha256(repaired).hexdigest(),
            'eq_unchanged_sha256': registry.sha256_file(game / 'DBDAT/EQ98030.FDI'),
            'ent_unchanged_sha256': registry.sha256_file(game / 'DBDAT/ENT98030.FDI')}}
    pipeline.write_canonical_json(receipt_path, receipt)
    chain = pipeline.read_json_file(release.build_chain_path)
    stage_id = 'declared-transform-' + str(1 + sum(
        s['id'].startswith('declared-transform-') for s in chain['stages'])).zfill(2)
    chain['stages'].append({'id': stage_id, 'receipt_sha256': registry.sha256_file(receipt_path),
        'before': {'DBDAT/JUG98030.FDI': receipt['byte_contract']['jug_before_sha256']},
        'after': {'DBDAT/JUG98030.FDI': receipt['byte_contract']['jug_after_sha256']}})
    # Preserve a user's existing display settings without pretending they are
    # a compiler output. source_inventory permits only manager.ini drift.
    if runtime_config['changed']:
        chain['stages'].append({'id': 'runtime-configuration-' + release_id,
            'outputs': {'manager.ini': registry.sha256_file(game / 'manager.ini')}})
    destination.mkdir(parents=True)
    chain_path = destination / 'build-chain.json'
    pipeline.write_canonical_json(chain_path, chain)
    manifest = pipeline.read_json_file(release.release_manifest_path)
    manifest['output'] = {'file_count': after['file_count'], 'total_bytes': after['total_bytes'],
                          'inventory_fingerprint': after['files_fingerprint']}
    artifact = pipeline.external_artifact_descriptor(artifact_id='native-player-identity-' + release_id,
                                                    path=receipt_path, role='input')
    manifest['external_artifacts'] = sorted(
        [a for a in manifest['external_artifacts'] if a['id'] != 'build-chain'] + [artifact,
        pipeline.external_artifact_descriptor(artifact_id='build-chain', path=chain_path, role='input')],
        key=lambda a: a['id'])
    manifest['stages'].append(pipeline.make_stage_record(stage_id=artifact['id'],
        implementation_path=Path(__file__), input_fingerprints={'previous-release': release.manifest_sha256},
        parameters={'repaired_players': len(rows), 'jug_sha256': receipt['byte_contract']['jug_after_sha256']},
        external_artifacts=[artifact]))
    manifest['stages'].sort(key=lambda s: s['id'])
    pipeline.validate_release_manifest(manifest)
    metadata = destination / 'metadata'
    metadata.mkdir()
    pipeline.write_canonical_json(metadata / 'season-manifest.json', manifest)
    pipeline.write_canonical_json(metadata / 'output.inventory.json', after)
    locator = dict(release.locator)
    for key in ('qa_report_path', 'qa_report_sha256'):
        locator.pop(key, None)
    locator.update({'release_id': release_id, 'game_path': registry.relative_workspace_path(game),
        'inventory_path': registry.relative_workspace_path(metadata / 'output.inventory.json'),
        'release_manifest_path': registry.relative_workspace_path(metadata / 'season-manifest.json'),
        'build_chain_path': registry.relative_workspace_path(chain_path),
        'game_inventory_fingerprint': after['files_fingerprint'], 'attestation_path': None,
        'runtime_evidence_path': None, 'technical_status': 'playable-unverified',
        'qa_status': 'not-recorded', 'native_identity_repair_path': registry.relative_workspace_path(receipt_path)})
    locator['required_file_hashes'] = {name: registry.sha256_file(game / name)
                                     for name in registry.REQUIRED_GAME_FILES}
    pipeline.write_canonical_json(destination / 'locator.json', locator)
    # Old release remains intact, including every original JUG byte.
    pipeline.assert_tree_matches_inventory(release.game_path, before)
    if register:
        catalog = registry.load_catalog()
        catalog[season] = {'season': season, 'release_id': release_id,
            'release_manifest_sha256': registry.sha256_file(metadata / 'season-manifest.json')}
        _atomic_replace_json(registry.CATALOG_PATH, {'schema_version': registry.CATALOG_SCHEMA,
                              'seasons': [catalog[s] for s in sorted(catalog)]})
    return {'season': season, 'release_id': release_id, 'registered': register,
            'repaired_players': len(rows), 'game': str(game)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season')
    parser.add_argument('--release-id', default='native-player-identity-20261003-r10')
    parser.add_argument('--register', action='store_true')
    args = parser.parse_args()
    seasons = registry.supported_seasons() if args.season == 'all' else [pipeline.normalise_season_id(args.season)]
    for season in seasons:
        print(json.dumps(publish(season, release_id=args.release_id, register=args.register)), flush=True)


if __name__ == '__main__':
    main()
