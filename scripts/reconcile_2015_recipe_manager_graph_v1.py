#!/usr/bin/env python3
"""Align the legacy recipe with its already repaired native manager graph.

This is a recipe-only publication, not another database build. It verifies the
original dated repair inputs, the completed repair receipt and every native
owner/name before changing references. No game file is written or copied.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import season_package_v2 as package_v2
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.attest_registered_season_runtime_v1 import _atomic_replace_json
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph

ROOT = registry.ROOT
SCHEMA = 'pm99-2015-recipe-manager-graph-reconciliation-v1'
ARTIFACT = 'reconciled-native-manager-graph-2015'
OPERATION = ROOT / '.local/operations/2015-16'
SOURCE_PLAN = OPERATION / 'manager-facts-manager-graph-plan-v1-r2-20260913.json'
APPLICATION = OPERATION / 'manager-facts-manager-graph-application-v1-r2-20260913.json'


def align_package(package, holders, names, source_plan, *, native_aliases=None):
    """Use real ENT record identities, not old IDs paired with another name."""
    if (package['season'].get('start_year'), package['season'].get('end_year')) != (2015, 2016) or source_plan['season'] != '2015-16':
        raise ValueError('this reconciliation is specific to the legacy 2015 season')
    owners = {}
    for manager_id, clubs in holders.items():
        for club in clubs:
            if club['carrier_id'] in owners:
                raise ValueError('ambiguous native club ownership')
            owners[club['carrier_id']] = manager_id
    targets = {row['team_carrier_id']: row for row in source_plan['targets']}
    native_aliases = native_aliases or {}
    if len(targets) != len(source_plan['targets']):
        raise ValueError('duplicate dated manager targets')
    preserved = {row['team_carrier_id']: row['manager_carrier_id']
                 for row in source_plan['preserved_non_club_links']}
    for club_id, row in targets.items():
        mid = row['manager_carrier_id']
        declaration = native_aliases.get(mid)
        expected_native_name = row['manager_name']
        if declaration is not None:
            if declaration['name'] != row['manager_name']:
                raise ValueError('native alias names a different dated canonical manager')
            expected_native_name = declaration['native_names']['display_name']
        if (owners.get(club_id) != mid or names.get(mid) != expected_native_name or
                [c['carrier_id'] for c in holders.get(mid, [])] != [club_id]):
            raise ValueError('dated repair does not match native manager name/exclusive ownership')
    for club_id, mid in preserved.items():
        if owners.get(club_id) != mid or mid not in names:
            raise ValueError('preserved non-club native owner changed')
    foreign = {row['team_carrier_id'] for row in targets.values() if row['scope'] == 'foreign'}
    if {club['carrier_id'] for club in package['clubs']} != foreign | set(preserved):
        raise ValueError('foreign recipe/source graph partition differs')
    result = copy.deepcopy(package)
    managers, changes = {}, []
    for club in result['clubs']:
        carrier = club['carrier_id']
        mid = owners[carrier]
        identifier = f'manager-{mid}'
        if club['manager_id'] != identifier:
            changes.append({'club_id': club['id'], 'club_carrier_id': carrier,
                            'before': club['manager_id'], 'after': identifier,
                            'native_manager_name': names[mid]})
        club['manager_id'] = identifier
        sourced = carrier in targets
        manager = {'id': identifier, 'carrier_id': mid, 'name': targets[carrier]['manager_name'] if sourced else names[mid],
                   'policy': 'write' if sourced else 'preserve-existing-mode1',
                   'proof': {'artifact_id': ARTIFACT,
                             'grade': 'source-receipt' if sourced else 'static-contract'}}
        if mid in native_aliases:
            manager['native_names'] = dict(native_aliases[mid]['native_names'])
        if identifier in managers and managers[identifier] != manager:
            raise ValueError('conflicting declarations for a shared native manager')
        managers[identifier] = manager
    result['managers'] = sorted(managers.values(), key=lambda row: row['id'])
    return result, changes


def checked_inputs(release):
    plan = json.loads(SOURCE_PLAN.read_text())
    receipt = json.loads(APPLICATION.read_text())
    if plan.get('schema_version') != 'pm99-world-2015-manager-graph-repair-plan-v1':
        raise ValueError('unexpected original repair plan')
    if (receipt.get('schema_version') != 'pm99-world-2015-manager-graph-repair-application-v1'
            or receipt.get('season') != '2015-16' or receipt.get('readback_failure_count') != 0):
        raise ValueError('original repair was not completed successfully')
    bindings = []
    for path in (SOURCE_PLAN, APPLICATION):
        bindings.append({'path': registry.relative_workspace_path(path), 'sha256': registry.sha256_file(path)})
    for key in ('foreign_package', 'english_package', 'manager_source_allocation'):
        row = plan['inputs'][key]
        path = registry._workspace_path(row['path'], label=key)
        if registry.sha256_file(path) != row['sha256']:
            raise ValueError('original dated repair input changed: ' + key)
        bindings.append(dict(row))
    original_package = json.loads((ROOT / plan['inputs']['foreign_package']['path']).read_text())
    current = json.loads(release.package_path.read_text())
    old_clubs = {club['id']: club for club in original_package['clubs']}
    for club in current['clubs']:
        old = old_clubs.get(club['id'])
        if old is None or (old['carrier_id'], old['name']) != (club['carrier_id'], club['name']):
            raise ValueError('club identity changed since dated manager repair')
    holders, names = _manager_graph(eq_path=release.game_path / 'DBDAT/EQ98030.FDI',
                                   ent_path=release.game_path / 'DBDAT/ENT98030.FDI')
    # Whole EQ hashes include unrelated tactics. Verify the actual manager
    # graph instead; each dated target still needs its exact exclusive owner
    # and canonical name (or an explicit, recipe-bound native alias).
    align_package(current, holders, names, plan, native_aliases=recipe_native_aliases(release, current))
    return plan, bindings


def recipe_native_aliases(release, package):
    layers = [package]
    for artifact in package.get('artifacts', []):
        if not artifact['id'].startswith('english-contextual-package-'):
            continue
        relative = Path(artifact['relative_path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe English manager recipe path')
        path = release.package_path.parent / relative
        if registry.sha256_file(path) != artifact['sha256']:
            raise ValueError('English manager recipe hash changed')
        layers.append(json.loads(path.read_text()))
    aliases = {}
    for layer in layers:
        for manager in layer['managers']:
            if manager.get('native_names'):
                previous = aliases.get(manager['carrier_id'])
                if previous is not None and previous != manager:
                    raise ValueError('conflicting native manager alias declarations')
                aliases[manager['carrier_id']] = manager
    return aliases


def publish(release_id, *, register=False):
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,127}', release_id):
        raise ValueError('invalid release ID')
    release = registry.load_preferred_release('2015-16')
    if release.release_id == release_id:
        plan_path = ROOT / release.locator['manager_graph_reconciliation_path']
        plan = json.loads(plan_path.read_text())
        package = json.loads(release.package_path.read_text())
        artifact = next(a for a in package['artifacts'] if a['id'] == ARTIFACT)
        if hashlib.sha256(pipeline.canonical_json_bytes(plan)).hexdigest() != artifact['sha256']:
            raise ValueError('completed reconciliation evidence changed')
        return {'season': '2015-16', 'release_id': release_id, 'status': 'already-published',
                'validation': registry.validate_preferred_release('2015-16')}
    workspace = ROOT / '.local/recipe-manager-reconciliations-v1/2015-16' / release_id
    destination = registry.locator_path('2015-16', release_id).parent
    if workspace.exists() or destination.exists():
        raise ValueError('publication already exists; never overwrite an immutable release')
    inventory = pipeline.read_json_file(release.inventory_path)
    pipeline.assert_tree_matches_inventory(release.game_path, inventory)
    original_package = json.loads(release.package_path.read_text())
    source_plan, bindings = checked_inputs(release)
    holders, names = _manager_graph(eq_path=release.game_path / 'DBDAT/EQ98030.FDI',
                                    ent_path=release.game_path / 'DBDAT/ENT98030.FDI')
    result, changes = align_package(original_package, holders, names, source_plan)
    reconciliation = {'schema_version': SCHEMA, 'season': '2015-16',
        'source_release_id': release.release_id, 'source_package_sha256': registry.sha256_file(release.package_path),
        'source_game_inventory_fingerprint': inventory['files_fingerprint'],
        'source_bindings': bindings, 'club_reference_changes': changes,
        'dated_foreign_managers': [row for row in source_plan['targets'] if row['scope'] == 'foreign'],
        'english_manager_graph_checked_unchanged': [row for row in source_plan['targets'] if row['scope'] == 'english'],
        'preserved_non_club_links': source_plan['preserved_non_club_links'],
        'historical_verification_complete': False,
        'scope': 'recipe owner IDs and manager declarations only; all native game bytes unchanged; no new person identity claims'}
    digest = hashlib.sha256(pipeline.canonical_json_bytes(reconciliation)).hexdigest()
    result['artifacts'].append({'id': ARTIFACT, 'kind': 'season-input', 'sha256': digest,
        'media_type': 'application/json', 'relative_path': 'manager-graph-reconciliation.json'})
    result['artifacts'].sort(key=lambda row: row['id'])
    result['proofs'].extend([
        {'id': 'proof-reconciled-manager-graph-2015', 'artifact_id': ARTIFACT,
         'grade': 'source-receipt', 'covers': ['dated-repair-manager-names-and-native-owner-links']},
        {'id': 'proof-preserved-non-club-manager-links-2015', 'artifact_id': ARTIFACT,
         'grade': 'static-contract', 'covers': ['unchanged-shared-non-club-manager-links-not-dated-coach-facts']}])
    result['proofs'].sort(key=lambda row: row['id'])
    package_v2.validate_package(result)
    # Assert the narrow metadata scope, not just schema acceptance.
    for key in original_package.keys() - {'clubs', 'managers', 'artifacts', 'proofs'}:
        if result[key] != original_package[key]:
            raise ValueError('unrelated recipe fields changed')
    for before, after in zip(original_package['clubs'], result['clubs'], strict=True):
        if {k: v for k, v in before.items() if k != 'manager_id'} != {k: v for k, v in after.items() if k != 'manager_id'}:
            raise ValueError('unrelated club fields changed')
    workspace.mkdir(parents=True)
    package_path = workspace / 'season-package.json'
    package_v2.write_canonical_package(package_path, result)
    plan_path = workspace / 'manager-graph-reconciliation.json'
    pipeline.write_canonical_json(plan_path, reconciliation)
    for artifact in result['artifacts']:
        relative = artifact.get('relative_path')
        if not relative:
            continue
        rel = Path(relative)
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('unsafe inherited evidence path')
        source, target = release.package_path.parent / rel, workspace / rel
        if source.is_file() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            os.link(source, target)
    outputs = [{'path': name, 'sha256': registry.sha256_file(release.game_path / name),
                'size': (release.game_path / name).stat().st_size}
               for name in ('DBDAT/JUG98030.FDI', 'DBDAT/EQ98030.FDI', 'DBDAT/ENT98030.FDI')]
    receipt = {'schema': 'pm99-recipe-only-reconciliation-receipt-v1', 'season': '2015-16',
        'season_package_sha256': registry.canonical_document_sha256(package_path),
        'source_season_package_sha256': registry.canonical_document_sha256(release.package_path),
        'source_compiler_receipt_sha256': registry.sha256_file(release.compiler_receipt_path),
        'source_build_chain_sha256': registry.sha256_file(release.build_chain_path),
        'compilation_mode': 'recipe-only-existing-native-manager-graph', 'game_files_written': 0,
        'club_manager_references_changed': len(changes), 'manager_declarations': len(result['managers']),
        'outputs': outputs, 'difference': pipeline.inventory_difference(inventory, inventory),
        'historical_verification_complete': False}
    receipt_path = workspace / 'recipe-reconciliation-receipt.json'
    pipeline.write_canonical_json(receipt_path, receipt)
    destination.mkdir(parents=True)
    chain = {'schema_version': 'pm99-season-build-chain-v1', 'season': '2015-16',
        'package_canonical_sha256': receipt['season_package_sha256'], 'stages': [
        {'id': 'database', 'receipt_sha256': registry.sha256_file(receipt_path),
         'outputs': {row['path']: row['sha256'] for row in outputs}},
        {'id': 'inherited-identical-game', 'source_build_chain_sha256': receipt['source_build_chain_sha256'],
         'outputs': {row['path']: row['sha256'] for row in inventory['files']}}]}
    chain_path = destination / 'build-chain.json'
    pipeline.write_canonical_json(chain_path, chain)
    manifest = pipeline.read_json_file(release.release_manifest_path)
    manifest['season_document'] = pipeline.canonical_json_document_descriptor(package_path, document_id='season-package')
    paths = [('manager-graph-reconciliation', plan_path), ('recipe-reconciliation-receipt', receipt_path),
             ('previous-recipe', release.package_path), ('previous-compiler-receipt', release.compiler_receipt_path),
             ('previous-build-chain', release.build_chain_path), ('build-chain', chain_path)]
    artifacts = [pipeline.external_artifact_descriptor(artifact_id=key, path=path, role='input') for key, path in paths]
    ids = {row['id'] for row in artifacts}
    manifest['external_artifacts'] = sorted([a for a in manifest['external_artifacts'] if a['id'] not in ids] + artifacts, key=lambda a: a['id'])
    manifest['stages'].append(pipeline.make_stage_record(stage_id='recipe-manager-graph-' + release_id,
        implementation_path=Path(__file__), input_fingerprints={'previous-release': release.manifest_sha256},
        parameters={'game_files_written': 0, 'club_manager_references_changed': len(changes)}, external_artifacts=artifacts))
    manifest['stages'].sort(key=lambda row: row['id'])
    pipeline.validate_release_manifest(manifest)
    metadata = destination / 'metadata'
    metadata.mkdir()
    manifest_path = metadata / 'season-manifest.json'
    pipeline.write_canonical_json(manifest_path, manifest)
    locator = dict(release.locator)
    for key in ('qa_report_path', 'qa_report_sha256'):
        locator.pop(key, None)
    locator.update(release_id=release_id, package_path=registry.relative_workspace_path(package_path),
        package_canonical_sha256=receipt['season_package_sha256'],
        compiler_receipt_path=registry.relative_workspace_path(receipt_path),
        build_chain_path=registry.relative_workspace_path(chain_path),
        release_manifest_path=registry.relative_workspace_path(manifest_path),
        attestation_path=None, runtime_evidence_path=None, technical_status='playable-unverified',
        qa_status='not-recorded', manager_graph_reconciliation_path=registry.relative_workspace_path(plan_path))
    pipeline.write_canonical_json(destination / 'locator.json', locator)
    pipeline.assert_tree_matches_inventory(release.game_path, inventory)
    if register:
        if registry.load_preferred_release('2015-16').release_id != release.release_id:
            raise ValueError('preferred release changed during reconciliation')
        catalog = registry.load_catalog()
        catalog['2015-16'] = {'season': '2015-16', 'release_id': release_id,
                              'release_manifest_sha256': registry.sha256_file(manifest_path)}
        _atomic_replace_json(registry.CATALOG_PATH, {'schema_version': registry.CATALOG_SCHEMA,
            'seasons': [catalog[s] for s in sorted(catalog)]})
    return {'season': '2015-16', 'release_id': release_id, 'registered': register,
            'club_manager_references_changed': len(changes), 'manager_declarations': len(result['managers']),
            'game_files_written': 0, 'historical_verification_complete': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-id', required=True)
    parser.add_argument('--register', action='store_true')
    args = parser.parse_args()
    print(json.dumps(publish(args.release_id, register=args.register), indent=2))


if __name__ == '__main__':
    main()
