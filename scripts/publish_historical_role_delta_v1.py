#!/usr/bin/env python3
"""Compile bounded role/country/club/coach deltas onto an immutable release.

The old compiler receipt and full build chain remain historical inputs. A new
receipt explicitly describes partial compilation; it is not relabelled as a
clean/full database build. Hardlinks share unchanged assets; each changed FDI
or executable is atomically replaced, never written through a source hardlink.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'upstream/pm99-skezmod-patcher'))
from player_birth_year_guard import patch_native_birth_year_guard
from scripts import season_release_registry_v1 as registry
from scripts import season_package_v2 as package_v2
from scripts import season_disk_budget_v1 as disk_budget
from scripts import season_pipeline_v2 as pipeline
from scripts.season_visual_patch_v1 import source_inventory
from scripts.attest_registered_season_runtime_v1 import _atomic_replace_json
from scripts.season_historical_roster_audit_v1 import add_legacy_english
from app.indexed_jug_roles import rewrite_indexed_native_roles
from app.indexed_jug_nationality import rewrite_indexed_native_nationalities
from app.fdi_indexed import IndexedFDIFile
from scripts.build_2015_english92_release import _patch_ent_name, _rebuild_indexed
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph

DATABASES = ('DBDAT/JUG98030.FDI', 'DBDAT/EQ98030.FDI', 'DBDAT/ENT98030.FDI')


def _write_amavisca_source_artifact(workspace, assignment_plan):
    """Write the exact recipe artifact encoding, including its final newline."""
    from scripts import season_amavisca_retirement_xi_r194_v4 as amavisca_tx
    source_artifact = assignment_plan['source_plan_artifact']
    if (assignment_plan.get('schema') != amavisca_tx.SCHEMA
            or source_artifact['filename'] != amavisca_tx.SOURCE_PLAN_FILENAME
            or source_artifact['artifact_id'] != amavisca_tx.artifact_id(assignment_plan)
            or hashlib.sha256(package_v2.canonical_json_bytes(source_artifact['document'])).hexdigest() != source_artifact['sha256']):
        raise ValueError('Amavisca SOURCE artifact binding differs')
    target = workspace / source_artifact['filename']
    if target.exists():
        raise ValueError('existing Amavisca SOURCE artifact must not be overwritten')
    pipeline.write_canonical_json(target, source_artifact['document'])
    if registry.sha256_file(target) != source_artifact['sha256']:
        raise ValueError('Amavisca written SOURCE artifact hash differs')
    return target


def _verify_completed_delta_ancestry(season, current, release_id, release_ids):
    """Check every explicit edge against its compiler or sealed artwork parent.

    No intermediate default changes and no automatic parent guessing. The
    caller still supplies source/native/runtime approval; this checks that its
    fully composed candidate descends from the actual current immutable base.
    """
    if (not isinstance(release_ids, (list, tuple)) or len(release_ids) < 2
            or any(not isinstance(r, str) for r in release_ids)
            or len(set(release_ids)) != len(release_ids)
            or release_ids[0] != current.release_id or release_ids[-1] != release_id):
        raise ValueError('completed delta ancestry must be an explicit unique current-to-final chain')
    parent = current
    for child_id in release_ids[1:]:
        child = registry.load_registered_release(season, child_id)
        receipt = pipeline.read_json_file(child.compiler_receipt_path)
        if (receipt['source_season_package_sha256'], receipt['source_compiler_receipt_sha256'],
                receipt['source_build_chain_sha256']) != (
                registry.canonical_document_sha256(parent.package_path), registry.sha256_file(parent.compiler_receipt_path),
                registry.sha256_file(parent.build_chain_path)):
            from scripts.season_visual_patch_reconstruction_v1 import verify_ancestry_edge
            if not verify_ancestry_edge(parent, child):
                raise ValueError('completed delta ancestry has an unverified or skipped immutable parent edge')
        parent = child


def register_completed_delta(season, release_id, *, verified_ancestor_chain=None):
    """Promote an already compiled exact-baseline delta without rebuilding it."""
    current = registry.load_preferred_release(season)
    locator_path = registry.locator_path(season, release_id)
    locator = json.loads(locator_path.read_text())
    receipt = json.loads((ROOT / locator['compiler_receipt_path']).read_text())
    if current.release_id == release_id:
        return {'season': season, 'release_id': release_id, 'already_registered': True}
    if verified_ancestor_chain is not None:
        _verify_completed_delta_ancestry(season, current, release_id, verified_ancestor_chain)
    elif (receipt['source_season_package_sha256'], receipt['source_compiler_receipt_sha256'], receipt['source_build_chain_sha256']) != (
            registry.canonical_document_sha256(current.package_path), registry.sha256_file(current.compiler_receipt_path),
            registry.sha256_file(current.build_chain_path)):
        raise ValueError('completed delta does not extend the current immutable baseline')
    game = ROOT / locator['game_path']
    pipeline.assert_tree_matches_inventory(game, pipeline.read_json_file(ROOT / locator['inventory_path']))
    if registry.canonical_document_sha256(ROOT / locator['package_path']) != locator['package_canonical_sha256']:
        raise ValueError('completed delta recipe hash changed')
    for name, expected in locator['required_file_hashes'].items():
        if registry.sha256_file(game / name) != expected:
            raise ValueError('completed delta native file hash changed')
    manifest_path = ROOT / locator['release_manifest_path']
    pipeline.validate_release_manifest(pipeline.read_json_file(manifest_path))
    catalog = registry.load_catalog()
    catalog[season] = {'season': season, 'release_id': release_id, 'release_manifest_sha256': registry.sha256_file(manifest_path)}
    _atomic_replace_json(registry.CATALOG_PATH, {'schema_version': registry.CATALOG_SCHEMA,
        'seasons': [catalog[s] for s in sorted(catalog)]})
    return {'season': season, 'release_id': release_id, 'registered_without_rebuild': True,
            'historical_verification_complete': False}


def club_plan_artifact(package, season, club_plan):
    """Keep older label evidence; only subsequent layers use hashed names."""
    base = 'historical-club-label-plan-' + season
    sha = hashlib.sha256(pipeline.canonical_json_bytes(club_plan)).hexdigest()
    repeated = any(a['id'] == base for a in package['artifacts'])
    suffix = '-' + sha[:16] if repeated else ''
    return (base + suffix, 'club-update-' + sha + '.json' if repeated else 'club-plan.json',
        'proof-historical-club-labels-' + season + suffix)


def _validate_manager_display_projection(manager_plan):
    if manager_plan.get('native_name_projection') != 'explicit-published-family-name-v1':
        return
    import unicodedata
    from scripts.season_manager_display_repair_v1 import short_name

    def normalized(value):
        return ''.join(c for c in unicodedata.normalize('NFKD', value).casefold()
                       if c.isalnum())

    for row in manager_plan['updates']:
        full, native = row['after'], row['native_after']
        family, _ = short_name(full)
        suffixes = {normalized(' '.join(full.split()[i:]))
                    for i in range(1, len(full.split()))}
        if not normalized(native) or (
                family is None and normalized(native) not in suffixes) or (
                family is not None and normalized(native) != normalized(family)) or (
                len(full.split()) > 1 and normalized(native) == normalized(full)):
            raise ValueError('manager family-name projection does not match the published surname')


def updated_package(package, plan, nationality_plan=None, manager_plan=None, club_plan=None):
    result = copy.deepcopy(package)
    by_id = {p['id']: p for p in result['players']}
    for row in plan['updates']:
        player = by_id.get(row['player_id'])
        if player is None:
            # Legacy English declarations are separately hash-bound in the plan.
            if not row['player_id'].startswith('legacy-english-player-'):
                raise ValueError('unknown recipe player in role plan')
            continue
        if (player['carrier_id'], player['name'], player['facts'].get('birth_date')) != (
                row['carrier_id'], row['name'], row['birth_date']):
            raise ValueError('role plan identity no longer matches recipe')
        if player.get('policy') == 'preserve-existing-mode1':
            raise ValueError('cannot silently rewrite a whole-record fallback')
        player['facts']['fine_roles'] = list(row['fine_roles'])
    if nationality_plan is not None:
        for row in nationality_plan['updates']:
            player = by_id.get(row['player_id'])
            if player is None or (player['carrier_id'], player['name'], player['facts'].get('birth_date'), player['facts'].get('nationality')) != (
                    row['carrier_id'], row['name'], row['birth_date'], row['before']):
                raise ValueError('nationality plan identity/fact no longer matches recipe')
            if player.get('policy') == 'preserve-existing-mode1':
                raise ValueError('cannot silently rewrite a whole-record nationality fallback')
            player['facts']['nationality'] = row['after']
            if 'fact_fallbacks' in player:
                player['fact_fallbacks'] = [f for f in player['fact_fallbacks'] if f['field'] != 'nationality']
        identity = 'historical-nationality-plan-' + plan['season']
        result['artifacts'] = sorted([a for a in result['artifacts'] if a['id'] != identity] + [{
            'id': identity, 'kind': 'season-input', 'sha256': hashlib.sha256(pipeline.canonical_json_bytes(nationality_plan)).hexdigest(),
            'media_type': 'application/json', 'relative_path': 'nationality-plan.json'}], key=lambda a: a['id'])
        proof_id = 'proof-historical-nationalities-' + plan['season']
        result['proofs'] = sorted([p for p in result['proofs'] if p['id'] != proof_id] + [{
            'id': proof_id, 'grade': 'source-receipt', 'artifact_id': identity,
            'covers': ['source-backed-nationality-corrections']}], key=lambda p: p['id'])
    if manager_plan is not None:
        _validate_manager_display_projection(manager_plan)
        managers = {m['id']: m for m in result['managers']}
        clubs = {c['id']: c for c in result['clubs']}
        manager_sha = hashlib.sha256(pipeline.canonical_json_bytes(manager_plan)).hexdigest()
        artifact_id = 'historical-manager-plan-' + plan['season'] + '-' + manager_sha[:16]
        for row in manager_plan['updates']:
            manager = managers.get(row['manager_id']); club = clubs.get(row['club_id'])
            if (manager is None or club is None or club['manager_id'] != row['manager_id'] or
                    (club['carrier_id'], manager['carrier_id'], manager['name'], manager.get('policy')) !=
                    (row['club_carrier_id'], row['carrier_id'], row['before'], row['before_policy'])):
                raise ValueError('manager plan identity/ownership no longer matches recipe')
            manager.update(name=row['after'], policy='write',
                person_id='manager-historical-' + hashlib.sha256(row['after'].encode()).hexdigest()[:24],
                proof={'artifact_id': artifact_id, 'grade': 'source-receipt'})
            # Name edits must not retain an alias derived from the old person.
            # The bound plan names the exact native display replacement too.
            if ('native_names' in manager or manager_plan.get('source_method')=='dated-closed-manager-tenure-v1'
                    or manager_plan.get('native_name_projection')=='explicit-published-family-name-v1'):
                manager['native_names'] = {'surname': row['native_after'],
                                           'display_name': row['native_after']}
        result['artifacts'] = sorted([a for a in result['artifacts'] if a['id'] != artifact_id] + [{
            'id': artifact_id, 'kind': 'season-input',
            'sha256': manager_sha,
            'media_type': 'application/json', 'relative_path': 'manager-update-' + manager_sha + '.json'}], key=lambda a: a['id'])
        proof_id = 'proof-historical-managers-' + plan['season'] + '-' + manager_sha[:16]
        result['proofs'] = sorted([p for p in result['proofs'] if p['id'] != proof_id] + [{
            'id': proof_id, 'grade': 'source-receipt', 'artifact_id': artifact_id,
            'covers': (['visually-transcribed-contemporary-first-fixture-manager-name', 'original-source-and-native-owner-bound']
                if manager_plan.get('source_method')=='dated-original-newspaper-first-fixture-manager-v1'
                else ['raw-reparsed-dated-closed-manager-tenure']
                if manager_plan.get('source_method')=='dated-closed-manager-tenure-v1'
                else ['dated-named-manager-source-and-exclusive-native-owner']
                if manager_plan.get('source_method')=='dated-source-cohort-manager-evidence-v1'
                else ['raw-reparsed-first-fixture-manager-names'])}], key=lambda p: p['id'])
    if club_plan is not None:
        clubs = {c['id']: c for c in result['clubs']}
        identity, club_filename, proof_id = club_plan_artifact(package, plan['season'], club_plan)
        for row in club_plan['updates']:
            club = clubs.get(row['club_id'])
            if club is None or (club['carrier_id'], club['name'], club.get('full_name')) != (
                    row['carrier_id'], row['before'], row['before_full']):
                raise ValueError('club label plan no longer matches recipe')
            club.update(name=row['after'], full_name=row['after'], identity_id=row['identity_after'],
                proof={'artifact_id': identity, 'grade': 'source-receipt'})
        result['artifacts'] = sorted([a for a in result['artifacts'] if a['id'] != identity] + [{
            'id': identity, 'kind': 'season-input',
            'sha256': hashlib.sha256(pipeline.canonical_json_bytes(club_plan)).hexdigest(),
            'media_type': 'application/json', 'relative_path': club_filename}], key=lambda a: a['id'])
        result['proofs'] = sorted(result['proofs'] + [{
            'id': proof_id, 'grade': 'source-receipt',
            'artifact_id': identity, 'covers': ['unanimous-authored-source-club-labels']}], key=lambda p: p['id'])
    # Detailed provenance is per player in this immutable, hash-bound artifact.
    if plan['updates']:
        identity = 'historical-role-plan-' + plan['season']
        descriptor = {'id': identity, 'kind': 'season-input',
                      'sha256': hashlib.sha256(pipeline.canonical_json_bytes(plan)).hexdigest(),
                      'media_type': 'application/json', 'relative_path': 'role-plan.json'}
        result['artifacts'] = sorted([a for a in result['artifacts'] if a['id'] != identity] + [descriptor], key=lambda a: a['id'])
        proof_id = 'proof-historical-roles-' + plan['season']
        result['proofs'] = sorted([p for p in result['proofs'] if p['id'] != proof_id] + [
            {'id': proof_id, 'grade': 'source-receipt', 'artifact_id': identity, 'covers': ['source-backed-detailed-role-mapping']}], key=lambda p: p['id'])
    if plan.get('policy') == 'original-TFF-first-XI-broad-position-conservative-compatible-role-v1' and plan['updates']:
        proof = next(p for p in result['proofs'] if p['id']=='proof-historical-roles-'+plan['season'])
        proof['grade']='reviewed-editorial'
        proof['covers']=['source-backed-broad-position-conservative-central-role']
    package_v2.validate_package(result)
    return result


def _verify_prepared_donor_workspace(workspace, release, before, patched, package, plan, assignment, *, assignment_module=None):
    """Resume metadata only after independently proving the entire staged game."""
    if workspace.is_symlink() or workspace.resolve()!=workspace.absolute():
        raise ValueError('unsafe prepared donor workspace')
    game=workspace/'game'
    after=pipeline.build_tree_inventory(game)
    difference=pipeline.inventory_difference(before,after)
    if (difference['only_left'] or difference['only_right']
            or sorted(row['path'] for row in difference['changed'])!=['DBDAT/JUG98030.FDI']
            or (game/'DBDAT/JUG98030.FDI').read_bytes()!=patched):
        raise ValueError('prepared donor game is not the exact already-computed source delta')
    if assignment_module is None:
        from scripts import season_donor_keeper_role_delta_v1 as assignment_module
    expected={'season-package.json':package_v2.canonical_json_bytes(package),
        'role-delta-input.json':pipeline.canonical_json_bytes(plan)+b'\n',
        assignment_module.filename(assignment):pipeline.canonical_json_bytes(assignment)+b'\n'}
    for name,raw in expected.items():
        path=workspace/name
        if path.is_symlink() or not path.is_file() or path.read_bytes()!=raw or path.stat().st_nlink!=1:
            raise ValueError('prepared donor recipe/input is missing, shared or changed: '+name)
    if (workspace/'role-delta-compiler.json').exists():
        raise ValueError('prepared donor metadata already progressed; inspect rather than overwrite')
    for path in workspace.rglob('*'):
        if path.is_relative_to(game) or not path.is_file() or path.relative_to(workspace).as_posix() in expected:
            continue
        original=release.package_path.parent/path.relative_to(workspace)
        if path.is_symlink() or not original.is_file() or registry.sha256_file(path)!=registry.sha256_file(original):
            raise ValueError('unrecognised or changed prepared donor metadata')
    return after


def publish(season, plan_path, *, release_id, register=False, modern_birth_dates=False, nationality_plan_path=None, manager_plan_path=None, club_plan_path=None, ownership_plan_path=None, visibility_plan_path=None, mode1_keeper_plan_path=None, birth_year_plan_path=None, mode1_opening_plan_path=None, italian_opening_plan_path=None, source_release_id=None, trabzon_opening_plan_path=None, name_only_plan_path=None, profile_assignment_plan_path=None, resume_unregistered_assignment=False, minimum_free_bytes=disk_budget.DEFAULT_RESERVE):
    disk_budget.validate_reserve(minimum_free_bytes)
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,127}', release_id):
        raise ValueError('invalid release ID')
    release = (registry.load_registered_release(season, source_release_id)
               if source_release_id is not None else registry.load_preferred_release(season))
    plan = json.loads(plan_path.read_text())
    explicit_keeper_role_replay = (
        plan.get('policy') == 'original-target-squad-full-name-DOB-literal-G-to-PM99-role-zero-v1'
        and bool(plan.get('updates')) and not plan.get('unresolved')
        and not any((register, modern_birth_dates, nationality_plan_path, manager_plan_path,
            club_plan_path, ownership_plan_path, visibility_plan_path, mode1_keeper_plan_path,
            birth_year_plan_path, mode1_opening_plan_path, italian_opening_plan_path,
            trabzon_opening_plan_path, name_only_plan_path, profile_assignment_plan_path,
            resume_unregistered_assignment)))
    if (source_release_id is not None
            and plan.get('policy') == 'original-target-squad-full-name-DOB-literal-G-to-PM99-role-zero-v1'
            and not explicit_keeper_role_replay):
        raise ValueError('explicit keeper SOURCE requires a nonempty resolved role-only plan without mixed options')
    explicit_manager_replay = (manager_plan_path is not None and not any((
        register, modern_birth_dates, nationality_plan_path, club_plan_path,
        ownership_plan_path, visibility_plan_path, mode1_keeper_plan_path,
        birth_year_plan_path, mode1_opening_plan_path, italian_opening_plan_path, trabzon_opening_plan_path)))
    explicit_label_replay = (club_plan_path is not None and manager_plan_path is not None
        and not any((register, modern_birth_dates, nationality_plan_path, ownership_plan_path,
            visibility_plan_path, mode1_keeper_plan_path, birth_year_plan_path,
            mode1_opening_plan_path, italian_opening_plan_path, trabzon_opening_plan_path,
            name_only_plan_path, profile_assignment_plan_path)))
    explicit_birth_replay = (birth_year_plan_path is not None and not any((
        register, modern_birth_dates, nationality_plan_path, manager_plan_path,
        club_plan_path, ownership_plan_path, visibility_plan_path, mode1_keeper_plan_path,
        mode1_opening_plan_path, italian_opening_plan_path, trabzon_opening_plan_path,
        name_only_plan_path, profile_assignment_plan_path)))
    explicit_ownership_replay = (ownership_plan_path is not None and not any((
        register,modern_birth_dates,nationality_plan_path,manager_plan_path,club_plan_path,
        visibility_plan_path,mode1_keeper_plan_path,birth_year_plan_path,mode1_opening_plan_path,
        italian_opening_plan_path,trabzon_opening_plan_path,name_only_plan_path,profile_assignment_plan_path)))
    if trabzon_opening_plan_path is not None and any((modern_birth_dates, nationality_plan_path, manager_plan_path,
            club_plan_path, ownership_plan_path, visibility_plan_path, mode1_keeper_plan_path,
            birth_year_plan_path, mode1_opening_plan_path, italian_opening_plan_path)):
        raise ValueError('Trabzon full-XI delta cannot mix unrelated repairs')
    if name_only_plan_path is not None and any((modern_birth_dates, nationality_plan_path, manager_plan_path,
            club_plan_path, ownership_plan_path, visibility_plan_path, mode1_keeper_plan_path,
            birth_year_plan_path, mode1_opening_plan_path, italian_opening_plan_path, trabzon_opening_plan_path)):
        raise ValueError('name-only delta cannot mix unrelated repairs')
    if profile_assignment_plan_path is not None and any((modern_birth_dates, nationality_plan_path, manager_plan_path,
            club_plan_path, ownership_plan_path, visibility_plan_path, mode1_keeper_plan_path,
            birth_year_plan_path, mode1_opening_plan_path, italian_opening_plan_path, trabzon_opening_plan_path, name_only_plan_path)):
        raise ValueError('reserve assignment pruning cannot mix unrelated repairs')
    if source_release_id is not None and (register or (italian_opening_plan_path is None and trabzon_opening_plan_path is None and name_only_plan_path is None and profile_assignment_plan_path is None and not explicit_manager_replay and not explicit_label_replay and not explicit_birth_replay and not explicit_ownership_replay and not explicit_keeper_role_replay)):
        raise ValueError('explicit source reconstruction is unregistered Italian or manager-only replay')
    if profile_assignment_plan_path is not None and plan.get('updates'):
        raise ValueError('reserve assignment pruning requires an inert player descriptor')
    if explicit_ownership_replay and plan.get('updates'):
        raise ValueError('explicit ownership SOURCE replay requires an inert player descriptor')
    if name_only_plan_path is not None and plan.get('updates'):
        raise ValueError('name-only delta requires an inert player descriptor')
    if trabzon_opening_plan_path is not None and plan.get('updates'):
        raise ValueError('Trabzon full-XI delta requires an inert player descriptor')
    if source_release_id is not None and (explicit_manager_replay or explicit_label_replay) and plan.get('updates'):
        raise ValueError('explicit manager replay requires an inert player descriptor')
    source_jug = release.game_path / DATABASES[0]
    if (plan['season'], plan['release_id'], plan['package_sha256'], plan['jug_sha256']) != (
            season, release.release_id, registry.sha256_file(release.package_path), registry.sha256_file(source_jug)):
        raise ValueError('role plan is stale; never apply to a different release')
    package = json.loads(release.package_path.read_text())
    if plan.get('policy') == 'original-target-squad-full-name-DOB-literal-G-to-PM99-role-zero-v1':
        from scripts import season_sourced_goalkeeper_roles_v1 as sourced_goalkeepers
        sourced_goalkeepers.verify(release, plan)
    if plan.get('policy') == 'original-TFF-first-XI-broad-position-conservative-compatible-role-v1':
        from scripts import season_tff_sourced_opening_xi_v1 as opening_xi
        opening_xi.verify_broad_roles(release,plan)
    _, declared, _ = add_legacy_english(package, season)
    by_id = {p['id']: p for p in declared}
    updates = {}
    for row in plan['updates']:
        player = by_id.get(row['player_id'])
        if player is None or (player['carrier_id'], player['name'], player['facts'].get('birth_date')) != (
                row['carrier_id'], row['name'], row['birth_date']):
            raise ValueError('role plan contains an unbound player')
        if row['carrier_id'] in updates:
            raise ValueError('duplicate native role carrier')
        updates[row['carrier_id']] = row['fine_roles']
    original = source_jug.read_bytes()
    patched, changes = rewrite_indexed_native_roles(original, updates)
    nationality_plan, nationality_changes, nationality_updates = None, [], {}
    if nationality_plan_path is not None:
        nationality_plan = json.loads(nationality_plan_path.read_text())
        if (nationality_plan['season'], nationality_plan['release_id'], nationality_plan['package_sha256'], nationality_plan['jug_sha256']) != (
                season, release.release_id, registry.sha256_file(release.package_path), registry.sha256_file(source_jug)):
            raise ValueError('nationality plan is stale')
        from scripts.season_package_compiler_v2 import _extract_country_codes_from_textos
        from scripts.build_2015_english92_release import _country_code
        countries = _extract_country_codes_from_textos(release.game_path / 'DBDAT/TEXTOS.PKF')
        for row in nationality_plan['updates']:
            if row['carrier_id'] in nationality_updates:
                raise ValueError('duplicate nationality carrier')
            code = _country_code(row['after'], countries)
            if code != row['native_country_code'] or code == countries['XXX']:
                raise ValueError('nationality translation is not proven')
            nationality_updates[row['carrier_id']] = code
        patched, nationality_changes = rewrite_indexed_native_nationalities(patched, nationality_updates)
    original_exe = (release.game_path / 'MANAGPRE.EXE').read_bytes()
    patched_exe, birth_receipt = patch_native_birth_year_guard(original_exe) if modern_birth_dates else (original_exe, None)
    original_ent = (release.game_path / DATABASES[2]).read_bytes()
    original_eq = (release.game_path / DATABASES[1]).read_bytes()
    patched_eq, club_plan, club_changes = original_eq, None, []
    if club_plan_path is not None:
        from scripts import season_original_carrier_label_restoration_v1 as original_labels
        from scripts import season_original_carrier_label_restoration_v2 as exact_page_labels
        from scripts import season_period_squad_carrier_label_v2 as annual_labels
        from scripts import season_period_cohort_coach_v3 as cohort_coaches
        from scripts import season_period_cohort_coach_v4 as extended_cohort_coaches
        candidate_club_plan = json.loads(club_plan_path.read_text())
        if candidate_club_plan.get('schema_version') in (original_labels.SCHEMA, exact_page_labels.SCHEMA, annual_labels.SCHEMA, cohort_coaches.SCHEMA, extended_cohort_coaches.SCHEMA):
            label_policy = {original_labels.SCHEMA:original_labels,annual_labels.SCHEMA:annual_labels,
                exact_page_labels.SCHEMA:exact_page_labels,
                cohort_coaches.SCHEMA:cohort_coaches, extended_cohort_coaches.SCHEMA:extended_cohort_coaches}[candidate_club_plan['schema_version']]
            label_policy.verify(release, candidate_club_plan)
            if label_policy in (cohort_coaches, extended_cohort_coaches):
                if manager_plan_path is None:raise ValueError('coupled cohort/coach correction requires manager plan')
                label_policy.verify_manager_pair(candidate_club_plan,json.loads(manager_plan_path.read_text()))
            from scripts.season_historical_club_label_plan_v1 import rewrite_club_labels
            club_plan = candidate_club_plan
            patched_eq, club_changes = rewrite_club_labels(original_eq, club_plan['updates'])
        else:
            from scripts.season_historical_club_label_plan_v1 import SCHEMA, rewrite_club_labels
            club_plan = json.loads(club_plan_path.read_text())
            if club_plan['schema_version'] != SCHEMA or (
                    club_plan['season'], club_plan['release_id'], club_plan['package_sha256'],
                    club_plan['eq_sha256'], club_plan['ent_sha256']) != (
                    season, release.release_id, registry.sha256_file(release.package_path),
                    hashlib.sha256(original_eq).hexdigest(), hashlib.sha256(original_ent).hexdigest()):
                raise ValueError('club label plan is stale')
            audit_path = ROOT / club_plan['audit_path']
            if registry.sha256_file(audit_path) != club_plan['audit_sha256']:
                raise ValueError('club label source audit changed')
            audit = json.loads(audit_path.read_text())
            source_bindings = club_plan['source_bindings']
            if audit['bindings'] != source_bindings:
                raise ValueError('club source bindings changed')
            for field in ('source_row', 'original_capture'):
                if registry.sha256_file(ROOT / source_bindings[field + '_path']) != source_bindings[field + '_sha256']:
                    raise ValueError('club original source bytes changed')
            supported = {r['club_id']: r for r in audit['clubs'] if r['status'] in (
                'source-supported-club-label-mismatch', 'source-supported-full-cohort-club-label-mismatch')}
            from scripts import season_historical_club_label_full_cohort_optin_v2 as full_cohort_optin
            paired = json.loads(manager_plan_path.read_text())['updates'] if manager_plan_path else []
            for row in club_plan['updates']:
                proof = supported.get(row['club_id'])
                if proof is None or any(row[k] != proof[k] for k in ('carrier_id', 'before', 'after', 'evidence', 'source_selector')):
                    raise ValueError('club label is not supported by the bound source-row audit')
                if proof['status'] == 'source-supported-full-cohort-club-label-mismatch':
                    full_cohort_optin.verify_manager_sources(proof)
                    witness = proof.get('full_cohort_witness')
                    if not isinstance(witness, dict) or row.get('full_cohort_witness') != witness:
                        raise ValueError('typed full-cohort witness is absent or differs from plan')
                    source_root = (ROOT / witness['preallocation_path']).parent.parent
                    fresh = full_cohort_optin.verify_witness(witness, source_root=source_root)
                    if (fresh['release_id'], fresh['package_sha256'], fresh['eq_sha256']) != (
                            release.release_id, registry.sha256_file(release.package_path),
                            registry.sha256_file(release.game_path / DATABASES[1])):
                        raise ValueError('typed full-cohort witness no longer binds publisher parent')
                if not any(r['club_id'] == row['club_id'] and r['after'] == row['evidence']['manager'] for r in paired):
                    raise ValueError('club rename lacks its paired sourced manager')
            patched_eq, club_changes = rewrite_club_labels(original_eq, club_plan['updates'])
    patched_ent, manager_plan, manager_changes = original_ent, None, []
    if manager_plan_path is not None:
        manager_plan = json.loads(manager_plan_path.read_text())
        _validate_manager_display_projection(manager_plan)
        if (manager_plan['season'], manager_plan['release_id'], manager_plan['package_sha256'], manager_plan['eq_sha256'], manager_plan['ent_sha256']) != (
                season, release.release_id, registry.sha256_file(release.package_path),
                registry.sha256_file(release.game_path / DATABASES[1]), hashlib.sha256(original_ent).hexdigest()):
            raise ValueError('manager plan is stale')
        holders, names = _manager_graph(eq_path=release.game_path / DATABASES[1], ent_path=release.game_path / DATABASES[2])
        indexed = IndexedFDIFile.from_bytes(original_ent); entries = {e.record_id: e for e in indexed.entries}; replacements = {}; checked_sources = {}
        for row in manager_plan['updates']:
            id = row['carrier_id']
            if id in replacements or [c['carrier_id'] for c in holders.get(id, [])] != [row['club_carrier_id']] or names.get(id) != row['native_before']:
                raise ValueError('manager native ownership/name is unbound or shared')
            for source in row['evidence']['raw_sources']:
                path = ROOT / source['path']
                if path not in checked_sources: checked_sources[path] = registry.sha256_file(path)
                if checked_sources[path] != source['sha256']:
                    raise ValueError('manager original evidence bytes changed')
            original_payload = entries[id].decode_payload(original_ent)
            replacements[id] = _patch_ent_name(original_payload, id, row['native_after'])
            if replacements[id] != original_payload:
                manager_changes.append({'carrier_id': id, 'club_carrier_id': row['club_carrier_id'],
                                        'before': row['native_before'], 'after': row['native_after']})
        patched_ent = _rebuild_indexed(original_ent, indexed, replacements)
        # Rebuilding directory offsets is allowed; every untouched decoded
        # record and the non-name tail of each renamed record remain intact.
        new_indexed = IndexedFDIFile.from_bytes(patched_ent)
        for entry in new_indexed.entries:
            expected = replacements.get(entry.record_id, entries[entry.record_id].decode_payload(original_ent))
            if entry.decode_payload(patched_ent) != expected:
                raise ValueError('manager name delta altered unrelated ENT record bytes')
    ownership_plan, ownership_changes, portrait_archive, portrait_offsets, ownership_aliases = None, [], None, {}, []
    if ownership_plan_path is not None:
        from scripts import season_duplicate_ownership_delta_v1 as ownership
        ownership_plan = json.loads(ownership_plan_path.read_text())
        ownership.verify_plan(release, ownership_plan)
        if any((plan['updates'], nationality_changes, club_changes, manager_changes)):
            raise ValueError('ownership replacements cannot be mixed with unrelated repairs')
    keeper_plan, keeper_changes = None, []
    if mode1_keeper_plan_path is not None:
        from scripts import season_mode1_sourced_keeper_slot_v1 as keeper_slot
        if any((plan['updates'], nationality_plan, manager_plan, club_plan, ownership_plan, visibility_plan_path)) or patched_exe != original_exe:
            raise ValueError('sourced keeper slot repair cannot mix unrelated changes')
        keeper_plan = json.loads(mode1_keeper_plan_path.read_text())
        keeper_slot.verify_bound(release, keeper_plan)
        patched = keeper_slot.apply(original, original_eq, keeper_plan)
        keeper_changes = keeper_plan['players']
    birth_year_plan, birth_year_changes = None, []
    if birth_year_plan_path is not None:
        from scripts import season_sourced_birth_years_v1 as birth_years
        if any((plan['updates'], nationality_plan, manager_plan, club_plan, ownership_plan, visibility_plan_path, keeper_plan)) or patched_exe != original_exe:
            raise ValueError('sourced birth-year repair cannot mix unrelated changes')
        birth_year_plan = json.loads(birth_year_plan_path.read_text())
        from scripts import season_biographic_birth_years_v1 as biographic_years
        if birth_year_plan.get('policy') == biographic_years.POLICY:
            birth_years = biographic_years
        from scripts import season_cross_period_birth_years_v1 as cross_period_years
        if birth_year_plan.get('policy') == cross_period_years.POLICY:
            birth_years = cross_period_years
        from scripts import season_original_person_birth_years_v1 as original_person_years
        if birth_year_plan.get('policy') == original_person_years.POLICY:
            birth_years = original_person_years
        birth_year_filename = (birth_years.filename(birth_year_plan)
            if hasattr(birth_years, 'filename') else birth_years.FILENAME)
        birth_years.verify(release, birth_year_plan)
        patched, birth_year_changes = birth_years.apply(original, birth_year_plan)
    opening_plan = None
    if mode1_opening_plan_path is not None:
        from scripts import season_tff_sourced_opening_xi_v1 as opening_xi
        if any((plan['updates'], nationality_plan, manager_plan, club_plan, ownership_plan, visibility_plan_path, keeper_plan, birth_year_plan)) or patched_exe != original_exe:
            raise ValueError('full original-XI repair cannot mix unrelated deltas')
        opening_plan = json.loads(mode1_opening_plan_path.read_text())
        opening_xi.verify(release, opening_plan)
    italian_plan = None
    if italian_opening_plan_path is not None:
        from scripts import season_italian_opening_layer_v1 as italian_opening
        if any((plan['updates'], nationality_plan, manager_plan, club_plan, ownership_plan, visibility_plan_path, keeper_plan, birth_year_plan, opening_plan)) or patched_exe != original_exe:
            raise ValueError('Italian original-XI repair cannot mix unrelated deltas')
        italian_plan = json.loads(italian_opening_plan_path.read_text())
        italian_opening.verify(release, italian_plan)
    trabzon_plan = None
    if trabzon_opening_plan_path is not None:
        from scripts import season_trabzon_opening_layer_v1 as trabzon_opening
        trabzon_plan = json.loads(trabzon_opening_plan_path.read_text())
        trabzon_opening.verify(release, trabzon_plan)
    name_plan = None
    if name_only_plan_path is not None:
        from scripts import season_maccabi_name_layer_v1 as names
        name_plan = json.loads(name_only_plan_path.read_text())
        from scripts import season_number_label_names_v2 as numeric_labels
        if name_plan.get('schema') == numeric_labels.SCHEMA:
            names = numeric_labels
        names.verify(release, name_plan)
    assignment_plan = None
    if profile_assignment_plan_path is not None:
        from scripts import season_profile_assignment_pruning_layer_v1 as assignments
        assignment_plan = json.loads(profile_assignment_plan_path.read_text())
        from scripts import season_source_bound_duplicate_opening_v1 as duplicate_opening
        if assignment_plan.get('schema') == duplicate_opening.SCHEMA:
            assignments = duplicate_opening
        from scripts import season_source_bound_namesake_dates_v1 as namesake_dates
        if assignment_plan.get('schema') == namesake_dates.SCHEMA:
            assignments = namesake_dates
        from scripts import season_original_secondary_facts_v1 as secondary_facts
        if assignment_plan.get('schema') == secondary_facts.SCHEMA:
            assignments = secondary_facts
        from scripts import season_original_country_policy_v2 as country_policy
        if assignment_plan.get('schema') == country_policy.SCHEMA:
            assignments = country_policy
        from scripts import season_source_verified_player_changes_v1 as source_changes
        if assignment_plan.get('schema') == source_changes.SCHEMA:
            assignments = source_changes
        from scripts import season_amavisca_retirement_xi_r194_v4 as amavisca_tx
        if assignment_plan.get('schema') == amavisca_tx.SCHEMA:
            assignments = amavisca_tx
        from scripts import season_verified_owned_roster_transaction_v1 as owned_roster
        if assignment_plan.get('schema') == owned_roster.SCHEMA:
            assignments = owned_roster
        from scripts import season_resolved_period_country_v3 as resolved_country
        if assignment_plan.get('schema') == resolved_country.SCHEMA:
            assignments = resolved_country
        from scripts import season_stevenage_opening_repair_v1 as stevenage
        if assignment_plan.get('schema') == stevenage.SCHEMA:
            assignments = stevenage
        from scripts import season_boreham_opening_repair_v1 as boreham
        if assignment_plan.get('schema') == boreham.SCHEMA:
            assignments = boreham
        from scripts import season_barrow_opening_repair_v1 as barrow
        if assignment_plan.get('schema') == barrow.SCHEMA:
            assignments = barrow
        from scripts import season_city_2024_opening_exchange_v1 as city_exchange
        if assignment_plan.get('schema') == city_exchange.SCHEMA:
            assignments = city_exchange
        from scripts import season_opening_identity_exchange_v1 as opening_exchange
        if assignment_plan.get('schema') == opening_exchange.SCHEMA:
            assignments = opening_exchange
        from scripts import season_riera_postownership_country_role_v1 as riera_country_role
        if assignment_plan.get('schema') == riera_country_role.SCHEMA:
            assignments = riera_country_role
        from scripts import season_madrid_mode1_activation_v1 as madrid_activation
        if assignment_plan.get('schema') == madrid_activation.SCHEMA:
            assignments = madrid_activation
        from scripts import season_inter_gimmelli_serena_exchange_v1 as gimmelli_serena
        if assignment_plan.get('schema') == gimmelli_serena.SCHEMA:
            assignments = gimmelli_serena
        from scripts import season_rawle_forbes_standard_v1 as rawle_forbes
        if assignment_plan.get('schema_version') == rawle_forbes.SCHEMA:
            assignments = rawle_forbes
        from scripts import season_evers_mcclune_opening_v1 as evers_mcclune
        if assignment_plan.get('schema') == evers_mcclune.SCHEMA:
            assignments = evers_mcclune
        from scripts import season_ballymena_shevlin_reserve_v1 as shevlin_reserve
        if assignment_plan.get('schema') == shevlin_reserve.SCHEMA:
            assignments = shevlin_reserve
        from scripts import season_english_woolley_mcloughlin_v1 as english_reserves
        if assignment_plan.get('schema_version') == english_reserves.SCHEMA:
            assignments = english_reserves
        from scripts import season_anelka_traore_lens_chain_v1 as anelka_chain
        if assignment_plan.get('schema') == anelka_chain.SCHEMA:
            assignments = anelka_chain
        from scripts import season_coady_centerback_cascade_v1 as coady_cascade
        if assignment_plan.get('schema') == coady_cascade.SCHEMA:
            assignments = coady_cascade
        from scripts import season_coady_centerback_exchange_v1 as coady_role
        if assignment_plan.get('schema') == coady_role.SCHEMA:
            assignments = coady_role
        from scripts import season_batth_wolves_opening_transfer_v1 as batth_wolves
        if assignment_plan.get('schema') == batth_wolves.SCHEMA:
            assignments = batth_wolves
        from scripts import season_altrincham_macc_joint_exchange_v1 as alty_joint
        if assignment_plan.get('schema') == alty_joint.SCHEMA:
            assignments = alty_joint
        from scripts import season_shuker_city_reserve_move_v1 as shuker_move
        if assignment_plan.get("schema") == shuker_move.SCHEMA:
            assignments = shuker_move
        from scripts import season_blackburn_ostenstad_etuhu_atomic_v1 as blackburn_city
        if assignment_plan.get('schema') == blackburn_city.SCHEMA:
            assignments = blackburn_city
        from scripts import season_altrincham_2001_role_overlay_v3 as alty_2001_roles
        if assignment_plan.get('schema') == alty_2001_roles.SCHEMA:
            assignments = alty_2001_roles
        from scripts import season_altrincham_2001_whole_club_v2 as alty_2001
        if assignment_plan.get('schema') == alty_2001.SCHEMA:
            assignments = alty_2001
        from scripts import season_woking_2003_owned_opening_v1 as woking_owned
        if assignment_plan.get('schema') == woking_owned.SCHEMA:
            assignments = woking_owned
        from scripts import season_arsenal_2021_owned_opening_v1 as arsenal_owned
        if assignment_plan.get('schema') == arsenal_owned.SCHEMA:
            assignments = arsenal_owned
        from scripts import season_morecambe_2000_owned_opening_v1 as morecambe_owned
        if assignment_plan.get('schema') == morecambe_owned.SCHEMA:
            assignments = morecambe_owned
        from scripts import season_takano_period_country_v1 as takano_country
        if assignment_plan.get('schema') == takano_country.SCHEMA:
            assignments = takano_country
        from scripts import season_preetz_period_profile_v1 as preetz_profile
        if assignment_plan.get('schema') == preetz_profile.SCHEMA:
            assignments = preetz_profile
        from scripts import season_haladas2000_opening_keeper_v1 as haladas_keeper
        if assignment_plan.get('schema') == haladas_keeper.SCHEMA:
            assignments = haladas_keeper
        from scripts import season_kiraly_period_profile_v1 as kiraly_profile
        if assignment_plan.get('schema') == kiraly_profile.SCHEMA:
            assignments = kiraly_profile
        from scripts import season_source_bound_shirt_numbers_v1 as shirt_numbers
        if assignment_plan.get('schema') == shirt_numbers.SCHEMA:
            assignments = shirt_numbers
        from scripts import season_stoke_commons_number_v1 as commons_number
        if assignment_plan.get('schema') == commons_number.SCHEMA:
            assignments = commons_number
        from scripts import season_original_alias_countries_v1 as alias_countries
        if assignment_plan.get('schema') == alias_countries.SCHEMA:
            assignments = alias_countries
        from scripts import season_source_bound_birthday_disagreements_v1 as birthday_disagreements
        if assignment_plan.get('schema') == birthday_disagreements.SCHEMA:
            assignments = birthday_disagreements
        from scripts import season_quality_only_delta_v1 as quality_only
        if assignment_plan.get('schema') == quality_only.SCHEMA:
            assignments = quality_only
        from scripts import season_exact_fifa_role_delta_v1 as exact_roles
        if assignment_plan.get('schema') == exact_roles.SCHEMA:
            assignments = exact_roles
        from scripts import season_exact_fifa_role_delta_v2 as conservative_roles
        if assignment_plan.get('schema') == conservative_roles.SCHEMA:
            assignments = conservative_roles
        from scripts import season_source_bound_maccabi_role_r129_v1 as maccabi_roles
        if assignment_plan.get('schema') == maccabi_roles.SCHEMA:
            assignments = maccabi_roles
        from scripts import season_annual_position_role_candidate_v1 as annual_roles
        if assignment_plan.get('schema') == annual_roles.SCHEMA:
            assignments = annual_roles
        from scripts import season_barrow_winger_fine_role_v1 as barrow_winger_roles
        if assignment_plan.get('schema') == barrow_winger_roles.SCHEMA:
            assignments = barrow_winger_roles
        from scripts import season_horne_26979_facts_v1 as horne_facts
        if assignment_plan.get('schema') == horne_facts.SCHEMA:
            assignments = horne_facts
        from scripts import season_vokes_crouch_opening_exchange_v2 as vokes_crouch
        if assignment_plan.get('schema') == vokes_crouch.SCHEMA:
            assignments = vokes_crouch
        from scripts import season_2015_english_fifa_roles_v1 as english_roles
        if assignment_plan.get('schema') == english_roles.SCHEMA:
            assignments = english_roles
        from scripts import season_donor_keeper_role_delta_v1 as donor_roles
        if assignment_plan.get('schema') == donor_roles.SCHEMA:
            assignments = donor_roles
        from scripts import season_exact_primary_position_delta_v1 as primary_positions
        if assignment_plan.get('schema') == primary_positions.SCHEMA:
            assignments = primary_positions
        from scripts import season_exact_primary_position_delta_v2 as alias_primary_positions
        if assignment_plan.get('schema') == alias_primary_positions.SCHEMA:
            assignments = alias_primary_positions
        from scripts import season_opening_cohort_delta_v1 as opening_cohort
        if assignment_plan.get('schema') == opening_cohort.PROFILE_SCHEMA:
            assignments = opening_cohort
        from scripts import season_source_bound_fixture_membership_v1 as fixture_membership
        if assignment_plan.get('schema') == fixture_membership.PROFILE_SCHEMA:
            assignments = fixture_membership
        assignments.verify(release, assignment_plan)
    if not changes and not nationality_changes and not club_changes and not (nationality_plan and nationality_plan['updates']) and not (manager_plan and manager_plan['updates']) and patched_exe == original_exe and not (ownership_plan and ownership_plan['updates']) and visibility_plan_path is None and keeper_plan is None and not birth_year_changes and opening_plan is None and italian_plan is None and trabzon_plan is None and name_plan is None and assignment_plan is None:
        return {'season': season, 'status': 'no-native-role-changes', 'registered': False}
    visibility_only = visibility_plan_path is not None and not any((plan['updates'], nationality_plan, manager_plan, club_plan, ownership_plan))
    result = copy.deepcopy(package) if visibility_only else updated_package(package, plan, nationality_plan, manager_plan, club_plan)
    if assignment_plan is not None:
        result = assignments.bind(package, assignment_plan)
        patched, patched_eq = assignments.apply(original, original_eq, assignment_plan)
        if assignments.apply(patched, patched_eq, assignment_plan) != (patched, patched_eq):
            raise ValueError('reserve assignment pruning is not idempotent')
        if assignment_plan.get('schema') == owned_roster.SCHEMA:
            from scripts import season_duplicate_ownership_delta_v1 as portrait_delta
            original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
            portrait_archive, portrait_offsets = portrait_delta.no_photo_archive(original_archive,
                {r['carrier_id'] for r in assignment_plan['updates']})
        if assignment_plan.get('schema') in (stevenage.SCHEMA, boreham.SCHEMA, barrow.SCHEMA):
            from scripts import season_duplicate_ownership_delta_v1 as portrait_delta
            original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
            portrait_archive, portrait_offsets = portrait_delta.no_photo_archive(original_archive,
                {r['carrier_id'] for r in assignment_plan['replacements']})
        elif assignment_plan.get('schema') == opening_exchange.SCHEMA:
            from scripts import season_duplicate_ownership_delta_v1 as portrait_delta
            original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
            portrait_archive, portrait_offsets = portrait_delta.no_photo_archive(original_archive,
                opening_exchange.selected_carriers(assignment_plan))
        elif assignment_plan.get('schema') == city_exchange.SCHEMA:
            from scripts import season_duplicate_ownership_delta_v1 as portrait_delta
            original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
            portrait_archive, portrait_offsets = portrait_delta.no_photo_archive(original_archive,
                {r[k] for r in assignment_plan['exchanges'] for k in ('city_carrier','destination_carrier')})
        elif assignment_plan.get('schema') == arsenal_owned.SCHEMA:
            from scripts import season_duplicate_ownership_delta_v1 as portrait_delta
            original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
            portrait_archive, portrait_offsets = portrait_delta.no_photo_archive(original_archive,
                arsenal_owned.selected_carriers(assignment_plan))
        elif assignment_plan.get('schema') == morecambe_owned.SCHEMA:
            from scripts import season_duplicate_ownership_delta_v1 as portrait_delta
            original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
            portrait_archive, portrait_offsets = portrait_delta.no_photo_archive(original_archive,
                morecambe_owned.selected_carriers(assignment_plan))
        elif assignment_plan.get('schema') == haladas_keeper.SCHEMA:
            from scripts import season_duplicate_ownership_delta_v1 as portrait_delta
            original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
            portrait_archive, portrait_offsets = portrait_delta.no_photo_archive(original_archive,
                haladas_keeper.selected_carriers(assignment_plan))
        elif assignment_plan.get('schema_version') == rawle_forbes.SCHEMA:
            original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
            portrait_archive = rawle_forbes.apply_minifoto(original_archive, assignment_plan)
            portrait_offsets = {carrier: [] for carrier in rawle_forbes.selected_carriers(assignment_plan)}
        elif assignment_plan.get('schema_version') == english_reserves.SCHEMA:
            original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
            portrait_archive = english_reserves.apply_minifoto(original_archive, assignment_plan)
            portrait_offsets = {carrier: [] for carrier in english_reserves.selected_carriers(assignment_plan)}
        elif assignment_plan.get('schema') == anelka_chain.SCHEMA:
            original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
            portrait_archive, portrait_offsets = anelka_chain.apply_photo_archive(original_archive, assignment_plan)
        elif assignment_plan.get('schema') == evers_mcclune.SCHEMA:
            from scripts import season_duplicate_ownership_delta_v1 as portrait_delta
            original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
            portrait_archive, portrait_offsets = portrait_delta.no_photo_archive(original_archive, evers_mcclune.selected_carriers(assignment_plan))
        elif assignment_plan.get('schema') == shevlin_reserve.SCHEMA:
            original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
            portrait_archive = shevlin_reserve.apply_minifoto(original_archive, assignment_plan)
            if shevlin_reserve.apply_minifoto(portrait_archive, assignment_plan) != portrait_archive:
                raise ValueError('Ballymena selected no-photo archive is not idempotent')
            portrait_offsets = shevlin_reserve.photo_offsets(assignment_plan)
        elif assignment_plan.get('schema') == gimmelli_serena.SCHEMA:
            from scripts import season_duplicate_ownership_delta_v1 as portrait_delta
            original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
            portrait_archive, portrait_offsets = portrait_delta.no_photo_archive(
                original_archive, gimmelli_serena.selected_carriers(assignment_plan))
        elif assignment_plan.get('schema') == blackburn_city.SCHEMA:
            original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
            portrait_archive = blackburn_city.apply_minifoto(original_archive, assignment_plan)
            portrait_offsets = {carrier: [] for carrier in blackburn_city.selected_carriers(assignment_plan)}
        elif assignment_plan.get('schema') == alty_2001_roles.SCHEMA:
            patched_ent = alty_2001_roles.apply_ent(original_ent, assignment_plan)
            if alty_2001_roles.apply_ent(patched_ent, assignment_plan) != patched_ent:
                raise ValueError('Altrincham sourced role composition manager is not idempotent')
            original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
            portrait_archive = alty_2001_roles.apply_minifoto(original_archive, assignment_plan)
            portrait_offsets = alty_2001_roles.photo_offsets(assignment_plan)
        elif assignment_plan.get('schema') == alty_2001.SCHEMA:
            patched_ent = alty_2001.apply_ent(original_ent, assignment_plan)
            if alty_2001.apply_ent(patched_ent, assignment_plan) != patched_ent:
                raise ValueError('Altrincham 2001 manager is not idempotent')
            original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
            portrait_archive = alty_2001.apply_minifoto(original_archive, assignment_plan)
            if alty_2001.apply_minifoto(portrait_archive, assignment_plan) != portrait_archive:
                raise ValueError('Altrincham 2001 photo archive is not idempotent')
            portrait_offsets = alty_2001.photo_offsets(assignment_plan)
        elif assignment_plan.get('schema') == alty_joint.SCHEMA:
            patched_ent = alty_joint.apply_ent(original_ent, assignment_plan)
            if alty_joint.apply_ent(patched_ent, assignment_plan) != patched_ent:
                raise ValueError('Altrincham sourced manager is not idempotent')
            original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
            if alty_joint.apply_minifoto(original_archive, assignment_plan) != original_archive:
                raise ValueError('Altrincham composition unexpectedly changes the photo archive')
        elif assignment_plan.get('schema') == woking_owned.SCHEMA:
            patched_ent = woking_owned.apply_ent(original_ent, assignment_plan)
            if woking_owned.apply_ent(patched_ent, assignment_plan) != patched_ent:
                raise ValueError('Woking sourced manager is not idempotent')
            from scripts import season_duplicate_ownership_delta_v1 as portrait_delta
            original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
            portrait_archive, portrait_offsets = portrait_delta.no_photo_archive(original_archive,
                woking_owned.selected_carriers(assignment_plan))
        elif assignment_plan.get('schema') == opening_cohort.PROFILE_SCHEMA:
            original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
            portrait_archive, portrait_offsets = assignments.apply_profile_minifoto(
                original_archive, assignment_plan)
        predicted = (len(patched) if patched != original else 0) + len(patched_eq) + len(package_v2.canonical_json_bytes(result)) + len(pipeline.canonical_json_bytes(assignment_plan)) + 32 * 1024**2
        if assignment_plan.get('schema') in (woking_owned.SCHEMA, alty_joint.SCHEMA, alty_2001.SCHEMA, alty_2001_roles.SCHEMA):
            predicted += len(patched_ent)
        if portrait_archive is not None and portrait_archive != original_archive:
            predicted += len(portrait_archive)
        disk_budget.require_space(release.game_path, predicted,
            minimum_free_bytes=minimum_free_bytes, context="season publication")
    if name_plan is not None:
        result = names.bind(package, name_plan)
        patched = names.apply(original, name_plan)
        if names.apply(patched, name_plan) != patched:
            raise ValueError('name-only native delta is not idempotent')
        predicted = len(patched) + len(package_v2.canonical_json_bytes(result)) + len(pipeline.canonical_json_bytes(name_plan)) + 32 * 1024**2
        disk_budget.require_space(release.game_path, predicted,
            minimum_free_bytes=minimum_free_bytes, context="season publication")
    if trabzon_plan is not None:
        result = trabzon_opening.bind(package, trabzon_plan)
        patched, patched_eq = trabzon_opening.apply(original, original_eq, trabzon_plan)
        if trabzon_opening.apply(patched, patched_eq, trabzon_plan) != (patched, patched_eq):
            raise ValueError('Trabzon full-XI delta is not idempotent')
        predicted = len(patched) + len(patched_eq) + len(package_v2.canonical_json_bytes(result)) + 32 * 1024**2
        disk_budget.require_space(release.game_path, predicted,
            minimum_free_bytes=minimum_free_bytes, context="season publication")
    if italian_plan is not None:
        result = italian_opening.bind(package, italian_plan)
        patched_eq = italian_opening.prune(original_eq, italian_plan)
        patched = italian_opening.order(original, patched_eq, italian_plan, exact_before=True)
        if italian_opening.prune(patched_eq, italian_plan) != patched_eq or italian_opening.order(patched, patched_eq, italian_plan) != patched:
            raise ValueError('Italian original-XI delta is not idempotent')
        predicted = len(patched) + len(patched_eq) + len(package_v2.canonical_json_bytes(result)) + len(pipeline.canonical_json_bytes(italian_plan)) + 32*1024**2
        disk_budget.require_space(release.game_path, predicted,
            minimum_free_bytes=minimum_free_bytes, context="season publication")
    if keeper_plan is not None:
        result = keeper_slot.bind(package, keeper_plan)
        if keeper_slot.apply(patched, original_eq, keeper_plan) != patched:
            raise ValueError('sourced keeper slot delta is not idempotent')
    if birth_year_plan is not None:
        result = birth_years.bind(package, birth_year_plan)
        if birth_years.apply(patched, birth_year_plan) != (patched, []):
            raise ValueError('sourced birth-year delta is not idempotent')
        predicted = len(patched) + len(package_v2.canonical_json_bytes(result)) + len(pipeline.canonical_json_bytes(birth_year_plan)) + 32*1024**2
        disk_budget.require_space(release.game_path, predicted,
            minimum_free_bytes=minimum_free_bytes, context="season publication")
    if opening_plan is not None:
        from scripts import season_duplicate_ownership_delta_v1 as portrait_delta
        from scripts.season_package_compiler_v2 import _extract_country_codes_from_textos
        result = opening_xi.updated_package(package, opening_plan)
        countries = _extract_country_codes_from_textos(release.game_path / 'DBDAT/TEXTOS.PKF')
        patched = opening_xi.apply(original, original_eq, result, countries, opening_plan)
        if opening_xi.apply(patched, original_eq, result, countries, opening_plan) != patched:
            raise ValueError('full original-XI delta is not idempotent')
        original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
        stale = {r['carrier_id'] for r in opening_plan['replacements'] if r['kind'] == 'wrong-person-facts'}
        portrait_archive, portrait_offsets = portrait_delta.no_photo_archive(original_archive, stale)
        predicted = len(patched) + len(pipeline.canonical_json_bytes(result)) + len(pipeline.canonical_json_bytes(opening_plan)) + (len(portrait_archive) if portrait_archive != original_archive else 0) + 32 * 1024 ** 2
        disk_budget.require_space(release.game_path, predicted,
            minimum_free_bytes=minimum_free_bytes, context="season publication")
    updated_english = None
    if assignment_plan is not None and assignment_plan.get('schema') == fixture_membership.PROFILE_SCHEMA:
        updated_english = fixture_membership.updated_english(assignment_plan)
    if assignment_plan is not None and assignment_plan.get('schema') == english_roles.SCHEMA:
        updated_english = english_roles.updated_english(assignment_plan)
    if assignment_plan is not None and assignment_plan.get('kind') == 'season-rating-calibration-2015-english-v3':
        from scripts import season_2015_english_rating_calibration_v3 as english_ratings
        updated_english = english_ratings.updated_english(assignment_plan)
    if ownership_plan is not None:
        from scripts import season_duplicate_layered_packages_v1 as layered_ownership
        result, updated_english, ownership_view, ownership_aliases = layered_ownership.prepare(
            release, ownership_plan, original, result)
        changed_ids = {row['player_id'] for row in ownership_plan['updates']}
        patched = ownership.compile_planned_players(original, ownership_view, changed_ids,
            ownership.compiler._extract_country_codes_from_textos(release.game_path / 'DBDAT/TEXTOS.PKF'),ownership_plan)
        ownership_changes = [{'carrier_id': row['carrier_id'], 'club_id': row['club_id'],
            'before': row['before']['source_name'] if row['before'].get('source_name') else row['before']['name'],
            'after': row['replacement']['source_player']['name']} for row in ownership_plan['updates']]
        carriers = {row['carrier_id'] for row in ownership_plan['updates']}
        original_archive = (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
        portrait_archive, portrait_offsets = ownership.no_photo_archive(original_archive, carriers)
        predicted = len(patched) + (len(portrait_archive) if portrait_archive != original_archive else 0) + 32 * 1024 * 1024
        disk_budget.require_space(release.game_path, predicted,
            minimum_free_bytes=minimum_free_bytes, context="season publication")
    visibility_plan, visibility_changes = None, []
    if visibility_plan_path is not None:
        from scripts import season_roster_visibility_v1 as visibility
        visibility_plan = json.loads(visibility_plan_path.read_text())
        visibility.verify_bound(release, visibility_plan)
        patched_eq, visibility_changes = visibility.apply(patched_eq, visibility_plan, exact_before=True)
        result = visibility.bind(result, visibility_plan)
        disk_budget.require_space(release.game_path, len(patched_eq) + len(package_v2.canonical_json_bytes(result)) + 32*1024**2,
            minimum_free_bytes=minimum_free_bytes, context="season publication")
    destination = registry.locator_path(season, release_id).parent
    workspace = ROOT / '.local/historical-role-deltas-v1' / season / release_id
    prepared=workspace.exists() and resume_unregistered_assignment
    if destination.exists() or (workspace.exists() and not prepared):
        raise ValueError('role delta already exists; never overwrite')
    before, runtime_drift = source_inventory(release)
    game = workspace / 'game'
    if prepared:
        from scripts import season_donor_keeper_role_delta_v1 as donor
        from scripts import season_ballymena_shevlin_reserve_v1 as shevlin_resume
        if (assignment_plan is None or assignment_plan.get('schema') not in (donor.SCHEMA, shevlin_resume.SCHEMA, opening_cohort.PROFILE_SCHEMA)
                or any((plan['updates'],nationality_plan,manager_plan,club_plan,ownership_plan,
                    visibility_plan_path,keeper_plan,birth_year_plan,opening_plan,italian_plan,trabzon_plan,name_plan))
                or patched_eq!=original_eq or patched_ent!=original_ent or patched_exe!=original_exe):
            raise ValueError('prepared-workspace resume is limited to this exact donor role/country assignment')
        _verify_prepared_donor_workspace(workspace,release,before,patched,result,plan,assignment_plan, assignment_module=assignments)
    else:
        workspace.mkdir(parents=True)
        shutil.copytree(release.game_path, game, copy_function=os.link)
        for name, payload in [(DATABASES[0], patched), (DATABASES[1], patched_eq), (DATABASES[2], patched_ent), ('MANAGPRE.EXE', patched_exe)]:
            if payload == (release.game_path / name).read_bytes():
                continue
            temporary = workspace / (Path(name).name + '.partial')
            temporary.write_bytes(payload)
            os.replace(temporary, game / name)
    removed_photos = []
    archive_changed = portrait_archive is not None and portrait_archive != original_archive
    if archive_changed:
        temporary = workspace / 'MINIFOTO.PKF.partial'
        temporary.write_bytes(portrait_archive)
        os.replace(temporary, game / 'DBDAT/MINIFOTO.PKF')
    for carrier in portrait_offsets:
        relative = f'DBDAT/MINIFOTO/J96{carrier:05d}.BMP'
        if (game / relative).exists():
            # Unlink this new game's directory entry only; source hardlink
            # content and the preceding playable game are untouched.
            (game / relative).unlink()
            removed_photos.append(relative)
    after = pipeline.build_tree_inventory(game)
    difference = pipeline.inventory_difference(before, after)
    if (sorted(difference['only_left']) != sorted(removed_photos) or difference['only_right'] or
            sorted(r['path'] for r in difference['changed']) != sorted(
                ([DATABASES[0]] if patched != original else []) + ([DATABASES[1]] if patched_eq != original_eq else []) + ([DATABASES[2]] if patched_ent != original_ent else []) + (['MANAGPRE.EXE'] if patched_exe != original_exe else []) + (['DBDAT/MINIFOTO.PKF'] if archive_changed else []))):
        raise ValueError('role delta changed unrelated game content')
    if rewrite_indexed_native_roles(patched, updates) != (patched, []):
        raise ValueError('role delta is not idempotent')
    if rewrite_indexed_native_nationalities(patched, nationality_updates) != (patched, []):
        raise ValueError('nationality delta is not idempotent')
    package_path = workspace / 'season-package.json'
    if not prepared:
        package_path.write_bytes(package_v2.canonical_json_bytes(result))
    if updated_english is not None:
        from scripts import season_duplicate_english_overlay_v1 as overlay
        if assignment_plan is not None and assignment_plan.get('schema') == fixture_membership.PROFILE_SCHEMA:
            matches = [a for a in result['artifacts'] if str(a.get('relative_path', '')).endswith('english-season-package.json')]
            if len(matches) != 1:
                raise ValueError('membership correction needs one exact English overlay artifact')
            artifact = matches[0]
        else:
            artifact = next(a for a in result['artifacts'] if a['id'] == overlay.ARTIFACT)
        relative = Path(artifact['relative_path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe repaired English recipe artifact path')
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(package_v2.canonical_json_bytes(updated_english))
        if registry.sha256_file(target) != artifact['sha256']:
            raise ValueError('repaired English recipe artifact hash differs')
    # A visibility/ownership/no-op delta is not a new historical role source.
    # Keep the inherited role-plan filename and proof bound to its original.
    saved_plan = workspace / ('role-plan.json' if plan['updates'] else 'role-delta-input.json')
    if not prepared:
        pipeline.write_canonical_json(saved_plan, plan)
    if visibility_plan is not None:
        pipeline.write_canonical_json(workspace / 'roster-visibility.json', visibility_plan)
    if keeper_plan is not None:
        pipeline.write_canonical_json(workspace / keeper_slot.FILENAME, keeper_plan)
    if birth_year_plan is not None:
        pipeline.write_canonical_json(workspace / birth_year_filename, birth_year_plan)
    if opening_plan is not None:
        pipeline.write_canonical_json(workspace / opening_xi.FILENAME, opening_plan)
    if italian_plan is not None:
        pipeline.write_canonical_json(workspace / italian_opening.FILENAME, italian_plan)
    if trabzon_plan is not None:
        pipeline.write_canonical_json(workspace / trabzon_opening.FILENAME, trabzon_plan)
    if name_plan is not None:
        pipeline.write_canonical_json(workspace / names.FILENAME, name_plan)
    if assignment_plan is not None and not prepared:
        pipeline.write_canonical_json(workspace / assignments.filename(assignment_plan), assignment_plan)
        if assignment_plan.get('schema') == amavisca_tx.SCHEMA:
            _write_amavisca_source_artifact(workspace, assignment_plan)
        if assignment_plan.get('schema') == alty_joint.SCHEMA:
            artifact = alty_joint.source_artifact(assignment_plan)
            pipeline.write_canonical_json(workspace / artifact['filename'], artifact['document'])
            if registry.sha256_file(workspace / artifact['filename']) != artifact['sha256']:
                raise ValueError('Altrincham source artifact write/hash differs')
        if assignment_plan.get('schema') == blackburn_city.SCHEMA:
            artifact = blackburn_city.source_artifact(assignment_plan)
            target = workspace / artifact['filename']
            if target.exists():
                raise ValueError('existing Blackburn/City source artifact must not be overwritten')
            pipeline.write_canonical_json(target, artifact['document'])
            if registry.sha256_file(target) != artifact['sha256']:
                raise ValueError('Blackburn/City source artifact write/hash differs')
        if assignment_plan.get('schema') == alty_2001_roles.SCHEMA:
            artifact = alty_2001_roles.source_artifact(assignment_plan)
            target = workspace / artifact['filename']
            if target.exists():
                raise ValueError('existing Altrincham role source artifact must not be overwritten')
            pipeline.write_canonical_json(target, artifact['document'])
            if registry.sha256_file(target) != artifact['sha256']:
                raise ValueError('Altrincham role source artifact write/hash differs')
        if assignment_plan.get('schema') == alty_2001.SCHEMA:
            artifact = alty_2001.source_artifact(assignment_plan)
            target = workspace / artifact['filename']
            if target.exists():
                raise ValueError('existing Altrincham 2001 inner source artifact must not be overwritten')
            pipeline.write_canonical_json(target, artifact['document'])
            if registry.sha256_file(target) != artifact['sha256']:
                raise ValueError('Altrincham 2001 source artifact write/hash differs')
    saved_ownership_plan = None
    if ownership_plan is not None:
        saved_ownership_plan = workspace / ownership.plan_filename(ownership_plan)
        pipeline.write_canonical_json(saved_ownership_plan, ownership_plan)
    saved_nationality_plan = None
    if nationality_plan is not None:
        saved_nationality_plan = workspace / 'nationality-plan.json'
        pipeline.write_canonical_json(saved_nationality_plan, nationality_plan)
    saved_club_plan = None
    if club_plan is not None:
        saved_club_plan = workspace / club_plan_artifact(package, season, club_plan)[1]
        pipeline.write_canonical_json(saved_club_plan, club_plan)
    saved_manager_plan = None
    if manager_plan is not None:
        manager_sha = hashlib.sha256(pipeline.canonical_json_bytes(manager_plan)).hexdigest()
        saved_manager_plan = workspace / ('manager-update-' + manager_sha + '.json')
        pipeline.write_canonical_json(saved_manager_plan, manager_plan)
        holders_after, names_after = _manager_graph(eq_path=game / DATABASES[1], ent_path=game / DATABASES[2])
        for row in manager_plan['updates']:
            if (names_after.get(row['carrier_id']) != row['native_after'] or
                    [c['carrier_id'] for c in holders_after.get(row['carrier_id'], [])] != [row['club_carrier_id']]):
                raise ValueError('manager name delta failed native name/owner readback')
    # Preserve recipe-local evidence when an unrelated field is patched. A
    # new workspace must not silently lose the preceding nationality/role plan.
    for artifact in result['artifacts']:
        relative = artifact.get('relative_path')
        if not relative: continue
        rel = Path(relative)
        if rel.is_absolute() or '..' in rel.parts: raise ValueError('unsafe inherited recipe artifact path')
        inherited = release.package_path.parent / rel
        target = workspace / rel
        if inherited.is_file() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            os.link(inherited, target)
    outputs = [{'path': name, 'sha256': registry.sha256_file(game / name), 'size': (game / name).stat().st_size}
               for name in DATABASES]
    receipt = {'schema': 'pm99-native-role-delta-compiler-v1', 'season': season,
        'season_package_sha256': registry.canonical_document_sha256(package_path),
        'source_season_package_sha256': registry.canonical_document_sha256(release.package_path),
        'compilation_mode': 'known-good-baseline-opening-ownership-player-delta' if ownership_plan else ('known-good-baseline-club-and-manager-name-delta' if club_plan else ('known-good-baseline-manager-name-delta' if manager_plan else ('known-good-baseline-role-and-nationality-delta' if nationality_plan else 'known-good-baseline-role-only-delta'))),
        'source_game_inventory_fingerprint': before['files_fingerprint'],
        'source_compiler_receipt_sha256': registry.sha256_file(release.compiler_receipt_path),
        'source_build_chain_sha256': registry.sha256_file(release.build_chain_path),
        'plan_sha256': registry.sha256_file(saved_plan),
        'nationality_plan_sha256': registry.sha256_file(saved_nationality_plan) if saved_nationality_plan else None,
        'manager_plan_sha256': registry.sha256_file(saved_manager_plan) if saved_manager_plan else None,
        'club_plan_sha256': registry.sha256_file(saved_club_plan) if saved_club_plan else None,
        'players_written': len({r['carrier_id'] for r in changes + nationality_changes + ownership_changes}),
        'ownership_changes': ownership_changes,
        'ownership_plan_sha256': registry.sha256_file(saved_ownership_plan) if saved_ownership_plan else None,
        'ownership_display_aliases': ownership_aliases,
        'ownership_editorial_policy': {'rating_model': ('source-bound-selected-replacement-output-with-versioned-model'
                if any(r.get('source_bound_replacement_output') for r in ownership_plan['updates'])
                else 'deterministic-editorial-v1'),
            'model_sha256': ownership.ratings.MODEL_SHA256,
            'strength_policy': 'versioned-country-strength-v1',
            'fine_roles': ('explicit-source-bound-replacement-role-review-where-declared'
                if any(r.get('source_bound_replacement_output') for r in ownership_plan['updates'])
                else 'conservative-central-role-from-sourced-broad-position-not-independent-detailed-role-proof')} if ownership_plan else None,
        'ownership_portrait_fallback': {'directory_offsets': portrait_offsets, 'removed_loose_paths': removed_photos},
        'nationality_changes': nationality_changes,
        'clubs_written': len(club_changes), 'club_changes': club_changes, 'managers_written': len(manager_changes), 'manager_changes': manager_changes, 'changes': changes, 'outputs': outputs,
        'difference': difference, 'existing_runtime_config_difference': runtime_drift,
        'allowed_write': ('Declared displaced-person JUG records only, through the native compiler; matching stale portrait directory flags/loose override removed; all clubs, managers, tactics and unrelated players/assets byte-identical' if ownership_plan else 'six role bytes and optional one nationality byte per declared native player; optional two-byte player birth-year bound; optional exclusively owned ENT manager-name fields and EQ short/full club labels/directory offsets; every other record byte unchanged'),
        'native_birth_year_guard': birth_receipt,
        'historical_verification_complete': False,
        'remaining_detailed_role_source_gaps': len(plan['unresolved'])}
    receipt_path = workspace / 'role-delta-compiler.json'
    if visibility_plan is not None:
        receipt.update(compilation_mode='known-good-baseline-authored-roster-visibility-delta',
            visibility_changes=visibility_changes,
            visibility_plan_sha256=registry.sha256_file(workspace/'roster-visibility.json'),
            allowed_write='Explicit copied seed exclusion bytes only; player identities, skills, other roster rows, tactics and assets unchanged')
    if keeper_plan is not None:
        receipt.update(compilation_mode='known-good-baseline-original-first-fixture-mode1-keeper-slot-delta',
            keeper_slot_changes=keeper_changes, players_written=len(keeper_changes),
            keeper_slot_plan_sha256=registry.sha256_file(workspace / keeper_slot.FILENAME),
            allowed_write='Two exclusively owned reciprocal startup bytes only; full XI not certified; facts, names, ratings, shared players and all other files unchanged')
    if birth_year_plan is not None:
        receipt.update(compilation_mode='known-good-baseline-original-sourced-modern-birth-year-delta',
            birth_year_changes=birth_year_changes, players_written=len(birth_year_changes),
            birth_year_plan_sha256=registry.sha256_file(workspace / birth_year_filename),
            allowed_write='Two native birth-year bytes per exclusively owned source-proven English player only; day/month and every other byte/fact/rating/file unchanged')
    if opening_plan is not None:
        receipt.update(compilation_mode='known-good-baseline-original-TFF-full-mode1-XI-delta',
            original_opening_xi=opening_plan['starting_xi'],
            opening_order_changes=opening_plan['orders'], opening_identity_changes=opening_plan['replacements'],
            players_written=len(opening_plan['orders']),
            original_opening_plan_sha256=registry.sha256_file(workspace / opening_xi.FILENAME),
            allowed_write='Target exclusively owned compact club startup bytes, two explicit source-backed name/person records and stale wrong-person portrait only; all EQ/tactics, managers, EXE, kits and other players exact')
    if italian_plan is not None:
        receipt.update(compilation_mode='known-good-baseline-original-Italian-roster-pruning-full-XI-delta',
            original_opening_xi=italian_plan['starting_xi'],
            opening_order_changes=italian_plan['orders'],
            opening_primary_role_changes=italian_plan.get('primary_role_changes', []),
            removed_target_roster_links=italian_plan['removed_player_ids'],
            players_written=len({row['carrier_id'] for row in italian_plan['orders'] if row['before'] != row['after']}
                | {row['carrier_id'] for row in italian_plan.get('primary_role_changes', [])}),
            original_italian_opening_plan_sha256=registry.sha256_file(workspace / italian_opening.FILENAME),
            allowed_write='Only target EQ count/deleted reviewed five-byte roster rows, retained exclusively owned JUG startup bytes, and explicitly versioned source-XI primary fine-role bytes; adjacent five role bytes, shared/orphan player records, other club payloads, opaque tactics, other facts, skills, managers, EXE, kits and portraits exact')
    if trabzon_plan is not None:
        receipt.update(compilation_mode='known-good-baseline-original-Trabzon-roster-pruning-full-XI-delta',
            original_opening_xi=[p['carrier_id'] for p in trabzon_plan['starting_xi']],
            opening_primary_role_changes=trabzon_plan.get('primary_role_changes', []),
            opening_order_changes=trabzon_plan['orders'], removed_target_roster_links=[32505],
            original_trabzon_opening_plan_sha256=registry.sha256_file(workspace / trabzon_opening.FILENAME),
            players_written=sum(r['startup_order'] != r['after'] for r in trabzon_plan['orders']),
            allowed_write='Only Trabzon1002 EQ count/exact reviewed32505 roster link, exclusive retained JUG startup bytes and explicit source-present primary-role bytes; secondary-role bytes, all other facts, skills, tactics, assets and other records exact')
    if name_plan is not None:
        receipt.update(compilation_mode='known-good-baseline-source-bound-player-name-only-delta',
            original_name_only_plan_sha256=registry.sha256_file(workspace / names.FILENAME),
            players_written=len(name_plan['updates']),
            allowed_write='Only two original-source display-name strings and their exactly reversible zero padding; current native suffix/roles/facts/skills/unknown bytes, other records, roster, managers, EXE and all assets unchanged')
        if name_plan.get('schema') == numeric_labels.SCHEMA:
            receipt.update(compilation_mode='known-good-baseline-original-numeric-label-name-year-delta',
                corrected_birth_years=sum(row['repair_birth_year'] for row in name_plan['updates']),
                allowed_write=name_plan['scope'])
    if assignment_plan is not None and assignment_plan.get('schema') in (stevenage.SCHEMA, boreham.SCHEMA, barrow.SCHEMA):
        receipt.update(compilation_mode={
            stevenage.SCHEMA:'known-good-baseline-source-bound-Stevenage-opening-in-place',
            boreham.SCHEMA:'known-good-baseline-source-bound-Boreham-opening-in-place',
            barrow.SCHEMA:'known-good-baseline-source-bound-Barrow-opening-in-place'}[assignment_plan['schema']],
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], original_opening_xi=assignment_plan['starting_xi'],
            opening_order_changes=assignment_plan['orders'],
            opening_identity_changes=assignment_plan['replacements'],
            opening_secondary_date_changes=assignment_plan['birthday_updates'],
            fixed_duplicate_case_ids=(['2c01311314826e92f838732f4049bdbb8a1f3f3dab539de196dd43de8bfed553']
                if assignment_plan['schema'] == stevenage.SCHEMA else assignment_plan['fixed_duplicate_case_ids']),
            players_written=len(assignment_plan['orders']), allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') in (owned_roster.SCHEMA, source_changes.SCHEMA, quality_only.SCHEMA, exact_roles.SCHEMA, conservative_roles.SCHEMA, english_roles.SCHEMA, donor_roles.SCHEMA, primary_positions.SCHEMA, alias_primary_positions.SCHEMA, country_policy.SCHEMA, resolved_country.SCHEMA, shirt_numbers.SCHEMA, commons_number.SCHEMA, alias_countries.SCHEMA, birthday_disagreements.SCHEMA, maccabi_roles.SCHEMA, annual_roles.SCHEMA, barrow_winger_roles.SCHEMA, horne_facts.SCHEMA):
        receipt.update(compilation_mode=assignments.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[],fixed_duplicate_case_ids=[],
            players_written=len(assignment_plan['updates']),allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == vokes_crouch.SCHEMA:
        receipt.update(compilation_mode=vokes_crouch.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            players_written=2, allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == madrid_activation.SCHEMA:
        receipt.update(compilation_mode=madrid_activation.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            players_written=1, allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == riera_country_role.SCHEMA:
        receipt.update(compilation_mode=riera_country_role.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            players_written=1, allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == amavisca_tx.SCHEMA:
        receipt.update(compilation_mode=amavisca_tx.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[dict(club_carrier_id=8, player_carrier_id=19)],
            fixed_duplicate_case_ids=[], players_written=len(assignment_plan['order_replacements']),
            allowed_write=assignment_plan['native_scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == opening_exchange.SCHEMA:
        receipt.update(compilation_mode=opening_exchange.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            players_written=len(assignment_plan['decisions']), allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema_version') == rawle_forbes.SCHEMA:
        receipt.update(compilation_mode=rawle_forbes.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            players_written=1,
            allowed_write='Only source-backed carrier33254 Rawle-to-Forbes identity/facts/editorial ratings and proof/no-photo projection; Boston11027, all roster links and every other actor preserved.',
            source_summary=assignment_plan['summary'])
    elif assignment_plan is not None and assignment_plan.get('schema') == evers_mcclune.SCHEMA:
        receipt.update(compilation_mode=evers_mcclune.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[dict(club_carrier_id=385,player_carrier_id=33121)],
            fixed_duplicate_case_ids=[], players_written=2, allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == shevlin_reserve.SCHEMA:
        receipt.update(compilation_mode=shevlin_reserve.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            players_written=1, allowed_write=shevlin_reserve.SCOPE)
    elif assignment_plan is not None and assignment_plan.get('schema') == gimmelli_serena.SCHEMA:
        receipt.update(compilation_mode=gimmelli_serena.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[gimmelli_serena.CASE_ID],
            players_written=2, allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema_version') == english_reserves.SCHEMA:
        receipt.update(compilation_mode=english_reserves.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            players_written=2, allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == anelka_chain.SCHEMA:
        receipt.update(compilation_mode=anelka_chain.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            players_written=2, allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == coady_cascade.SCHEMA:
        receipt.update(compilation_mode=coady_cascade.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            players_written=1, allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == coady_role.SCHEMA:
        receipt.update(compilation_mode=coady_role.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            players_written=1, allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == batth_wolves.SCHEMA:
        receipt.update(compilation_mode=batth_wolves.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[dict(club_carrier_id=351,player_carrier_id=10749)],
            fixed_duplicate_case_ids=[], players_written=len(assignment_plan['order_changes']),
            allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == alty_joint.SCHEMA:
        receipt.update(compilation_mode=alty_joint.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            players_written=19, allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get("schema") == shuker_move.SCHEMA:
        receipt.update(compilation_mode=shuker_move.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[dict(club_carrier_id=382,player_carrier_id=32945)],
            fixed_duplicate_case_ids=[], players_written=len(assignment_plan["startup_order_changes"]),
            allowed_write=assignment_plan["scope"])
    elif assignment_plan is not None and assignment_plan.get('schema') == blackburn_city.SCHEMA:
        receipt.update(compilation_mode=blackburn_city.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            players_written=2, allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == alty_2001_roles.SCHEMA:
        receipt.update(compilation_mode=alty_2001_roles.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            players_written=18, allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == alty_2001.SCHEMA:
        receipt.update(compilation_mode=alty_2001.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            players_written=18, allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == woking_owned.SCHEMA:
        receipt.update(compilation_mode=woking_owned.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            opening_identity_changes=assignment_plan['proposal']['allocation'],
            paired_Oxford_replacement=assignment_plan['Oxford_replacement'],
            sourced_Woking_manager=assignment_plan['coach'],
            players_written=17, allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == city_exchange.SCHEMA:
        receipt.update(compilation_mode=city_exchange.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            opening_identity_changes=assignment_plan['exchanges'],
            players_written=6, allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == arsenal_owned.SCHEMA:
        receipt.update(compilation_mode=arsenal_owned.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            opening_identity_changes=assignment_plan['assignment']['replacements'],
            players_written=29,allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == morecambe_owned.SCHEMA:
        receipt.update(compilation_mode=morecambe_owned.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            opening_identity_changes=[11002], retained_person_skills=17,
            players_written=18,allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == takano_country.SCHEMA:
        receipt.update(compilation_mode=takano_country.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],players_written=1,
            allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == preetz_profile.SCHEMA:
        receipt.update(compilation_mode=preetz_profile.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[],fixed_duplicate_case_ids=[],players_written=1,
            allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == haladas_keeper.SCHEMA:
        receipt.update(compilation_mode=haladas_keeper.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[],fixed_duplicate_case_ids=[assignment_plan['source_decision']['frozen_case_id']],
            players_written=1,allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == kiraly_profile.SCHEMA:
        receipt.update(compilation_mode=kiraly_profile.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[],fixed_duplicate_case_ids=[],players_written=1,
            allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == secondary_facts.SCHEMA:
        receipt.update(compilation_mode=secondary_facts.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            players_written=len(assignment_plan['updates']), allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == namesake_dates.SCHEMA:
        receipt.update(compilation_mode='known-good-baseline-source-bound-exact-namesake-birthdays',
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[assignment_plan['fixed_case']['id']],
            players_written=len(assignment_plan['updates']), allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None and assignment_plan.get('schema') == opening_cohort.PROFILE_SCHEMA:
        identity_changes = opening_cohort.publication_identity_changes(assignment_plan)
        receipt.update(compilation_mode=opening_cohort.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            opening_identity_changes=identity_changes,
            players_written=len(identity_changes),
            allowed_write='Only source-bound selected opening-cohort actors, reviewed facts/ratings, fixed target roster memberships, compatible complete mode-1 orders, and selected native-no-photo deactivations; all other actors, clubs, managers, game files, and assets byte-identical.')
    elif assignment_plan is not None and assignment_plan.get('schema') == fixture_membership.PROFILE_SCHEMA:
        receipt.update(compilation_mode=fixture_membership.MODE,
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=[], fixed_duplicate_case_ids=[],
            players_written=0, allowed_write=assignment_plan['scope'])
    elif assignment_plan is not None:
        starter_opening = assignment_plan.get('schema') == duplicate_opening.SCHEMA
        assignment_reviews = [assignment_plan['review']] if starter_opening else assignment_plan['reviews']
        receipt.update(compilation_mode=('known-good-baseline-source-bound-duplicate-starter-opening' if starter_opening
                                        else 'known-good-baseline-source-bound-reserve-assignment-pruning'),
            original_profile_assignment_plan_sha256=registry.sha256_file(workspace / assignments.filename(assignment_plan)),
            removed_target_roster_links=(duplicate_opening.removed_carriers(assignment_plan['review'])
                                        if starter_opening else [r['removed_player']['carrier_id'] for r in assignment_reviews]),
            fixed_duplicate_case_ids=[r['case_id'] for r in assignment_reviews],
            players_written=(len({r['carrier_id'] for r in assignment_plan['orders'] if r['startup_order'] != r['after']} |
                                 {r['carrier_id'] for r in assignment_plan['primary_role_changes']}) if starter_opening else 0),
            allowed_write=('One positively source-proved duplicate starter EQ link/count and required indexed offsets; complete sourced XI startup bytes and source-profile-compatible primary roles. A promoted duplicate secondary role is cleared; other secondary roles, birthdays, broad positions, skills, other records/managers/tactics/EXE/assets unchanged.' if starter_opening else
                           'Only source-proved duplicate reserve EQ links/counts and required indexed offsets; every JUG byte, startup order, manager, tactic, EXE and asset unchanged'))
        if starter_opening and assignment_plan['review'].get('shared_removed_membership'):
            receipt['allowed_write'] = ('Source-priority duplicate target EQ link plus independently sourced wrong shared target membership; complete sourced XI startup/primary-role bytes and promoted duplicate secondary clear. Shared global players and other native clubs unchanged. Recipe preserves shared players/assets and structurally rebinds only the retired target owner; surviving unqualified fallback membership is not historical approval.')
    pipeline.write_canonical_json(receipt_path, receipt)
    destination.mkdir(parents=True)
    # Database outputs reflect this partial compile. All other outputs are
    # inherited verbatim; the former complete chain is retained as evidence.
    chain = {'schema_version': 'pm99-season-build-chain-v1', 'season': season,
        'package_canonical_sha256': receipt['season_package_sha256'], 'stages': [
            {'id': 'database', 'receipt_sha256': registry.sha256_file(receipt_path),
             'outputs': {r['path']: r['sha256'] for r in outputs}},
            {'id': 'bounded-portrait-fallback-and-unchanged-assets' if ownership_plan else 'inherited-known-good-assets', 'source_build_chain_sha256': receipt['source_build_chain_sha256'],
             'outputs': {r['path']: r['sha256'] for r in after['files'] if r['path'] not in (*DATABASES, 'MANAGPRE.EXE')}},
            {'id': 'player-birth-year-guard' if birth_receipt else 'inherited-calendar-executable',
             'outputs': {'MANAGPRE.EXE': registry.sha256_file(game / 'MANAGPRE.EXE')}}]}
    chain_path = destination / 'build-chain.json'
    pipeline.write_canonical_json(chain_path, chain)
    manifest = pipeline.read_json_file(release.release_manifest_path)
    manifest['season_document'] = pipeline.canonical_json_document_descriptor(package_path, document_id='season-package')
    manifest['output'] = {'file_count': after['file_count'], 'total_bytes': after['total_bytes'],
                          'inventory_fingerprint': after['files_fingerprint']}
    artifacts = [pipeline.external_artifact_descriptor(artifact_id=id, path=path, role='input') for id, path in [
        ('historical-role-plan', saved_plan), ('historical-role-delta-compiler', receipt_path),
        ('previous-build-chain', release.build_chain_path), ('previous-compiler-receipt', release.compiler_receipt_path),
        ('previous-recipe', release.package_path), ('build-chain', chain_path)]]
    if saved_nationality_plan is not None:
        artifacts.append(pipeline.external_artifact_descriptor(artifact_id='historical-nationality-plan', path=saved_nationality_plan, role='input'))
    if saved_manager_plan is not None:
        artifacts.append(pipeline.external_artifact_descriptor(artifact_id='historical-manager-plan', path=saved_manager_plan, role='input'))
    if saved_club_plan is not None:
        artifacts.append(pipeline.external_artifact_descriptor(artifact_id='historical-club-label-plan', path=saved_club_plan, role='input'))
    if birth_year_plan is not None:
        artifacts.append(pipeline.external_artifact_descriptor(artifact_id='original-sourced-birth-year-plan', path=workspace / birth_year_filename, role='input'))
    if opening_plan is not None:
        artifacts.append(pipeline.external_artifact_descriptor(artifact_id='original-tff-opening-xi-plan', path=workspace / opening_xi.FILENAME, role='input'))
    if italian_plan is not None:
        artifacts.append(pipeline.external_artifact_descriptor(artifact_id='original-italian-opening-xi-plan', path=workspace / italian_opening.FILENAME, role='input'))
    if trabzon_plan is not None:
        artifacts.append(pipeline.external_artifact_descriptor(artifact_id='original-trabzon-opening-xi-plan', path=workspace / trabzon_opening.FILENAME, role='input'))
    if name_plan is not None:
        artifacts.append(pipeline.external_artifact_descriptor(artifact_id='original-player-name-only-plan', path=workspace / names.FILENAME, role='input'))
    if assignment_plan is not None:
        artifacts.append(pipeline.external_artifact_descriptor(artifact_id='original-profile-assignment-pruning-plan', path=workspace / assignments.filename(assignment_plan), role='input'))
        if assignment_plan.get('schema') == amavisca_tx.SCHEMA:
            artifacts.append(pipeline.external_artifact_descriptor(artifact_id=amavisca_tx.artifact_id(assignment_plan), path=workspace / amavisca_tx.SOURCE_PLAN_FILENAME, role='input'))
        if assignment_plan.get('schema') == alty_joint.SCHEMA:
            artifacts.append(pipeline.external_artifact_descriptor(artifact_id='altrincham-macc-inner-source-plan', path=workspace / alty_joint.SOURCE_PLAN_FILENAME, role='input'))
        if assignment_plan.get('schema') == blackburn_city.SCHEMA:
            artifacts.append(pipeline.external_artifact_descriptor(artifact_id=blackburn_city.artifact_id(assignment_plan), path=workspace / blackburn_city.SOURCE_PLAN_FILENAME, role='input'))
        if assignment_plan.get('schema') == alty_2001_roles.SCHEMA:
            artifacts.append(pipeline.external_artifact_descriptor(artifact_id='altrincham-2001-role-source-v3', path=workspace / alty_2001_roles.INNER_FILENAME, role='input'))
        if assignment_plan.get('schema') == alty_2001.SCHEMA:
            artifacts.append(pipeline.external_artifact_descriptor(artifact_id='altrincham-2001-inner-source-plan-v2', path=workspace / alty_2001.SOURCE_PLAN_FILENAME, role='input'))
    if saved_ownership_plan is not None:
        artifacts.append(pipeline.external_artifact_descriptor(artifact_id='duplicate-ownership-plan', path=saved_ownership_plan, role='input'))
    if keeper_plan is not None:
        artifacts.append(pipeline.external_artifact_descriptor(artifact_id='mode1-sourced-keeper-slot-plan', path=workspace / keeper_slot.FILENAME, role='input'))
    replaced = {a['id'] for a in artifacts}
    manifest['external_artifacts'] = sorted([a for a in manifest['external_artifacts'] if a['id'] not in replaced] + artifacts, key=lambda a: a['id'])
    manifest['stages'].append(pipeline.make_stage_record(stage_id='historical-role-delta-' + release_id, implementation_path=Path(__file__),
        input_fingerprints={'previous-release': release.manifest_sha256},
        parameters={'changed_role_players': len(changes), 'changed_nationality_players': len(nationality_changes),
                    'changed_manager_names': len(manager_changes),
                    'changed_club_names': len(club_changes),
                    'changed_ownership_slots': len(ownership_changes),
                    'historical_verification_complete': False}, external_artifacts=artifacts))
    manifest['stages'].sort(key=lambda s: s['id'])
    pipeline.validate_release_manifest(manifest)
    metadata = destination / 'metadata'
    metadata.mkdir()
    manifest_path, inventory_path = metadata / 'season-manifest.json', metadata / 'output.inventory.json'
    pipeline.write_canonical_json(manifest_path, manifest)
    pipeline.write_canonical_json(inventory_path, after)
    locator = dict(release.locator)
    for key in ('qa_report_path', 'qa_report_sha256'):
        locator.pop(key, None)
    locator.update({'release_id': release_id, 'game_path': registry.relative_workspace_path(game),
        'package_path': registry.relative_workspace_path(package_path),
        'package_canonical_sha256': receipt['season_package_sha256'],
        'compiler_receipt_path': registry.relative_workspace_path(receipt_path),
        'inventory_path': registry.relative_workspace_path(inventory_path),
        'release_manifest_path': registry.relative_workspace_path(manifest_path),
        'build_chain_path': registry.relative_workspace_path(chain_path),
        'game_inventory_fingerprint': after['files_fingerprint'], 'attestation_path': None,
        'runtime_evidence_path': None, 'technical_status': 'playable-unverified', 'qa_status': 'not-recorded',
        'historical_role_plan_path': registry.relative_workspace_path(saved_plan),
        'historical_role_delta_path': registry.relative_workspace_path(receipt_path)})
    locator['required_file_hashes'] = {name: registry.sha256_file(game / name) for name in registry.REQUIRED_GAME_FILES}
    if keeper_plan is not None:
        locator['mode1_keeper_slot_plan_path'] = registry.relative_workspace_path(workspace / keeper_slot.FILENAME)
    if birth_year_plan is not None:
        locator['sourced_birth_year_plan_path'] = registry.relative_workspace_path(workspace / birth_year_filename)
    if opening_plan is not None:
        locator['sourced_mode1_opening_plan_path'] = registry.relative_workspace_path(workspace / opening_xi.FILENAME)
    if italian_plan is not None:
        locator['sourced_italian_opening_plan_path'] = registry.relative_workspace_path(workspace / italian_opening.FILENAME)
        if 'mode1_keeper_slot_plan_path' in locator:
            locator['retained_mode1_keeper_slot_plan_path'] = locator.pop('mode1_keeper_slot_plan_path')
    if trabzon_plan is not None:
        locator['sourced_trabzon_opening_plan_path'] = registry.relative_workspace_path(workspace / trabzon_opening.FILENAME)
    if name_plan is not None:
        locator['sourced_player_name_only_plan_path'] = registry.relative_workspace_path(workspace / names.FILENAME)
    if assignment_plan is not None:
        locator['sourced_profile_assignment_plan_path'] = registry.relative_workspace_path(workspace / assignments.filename(assignment_plan))
    # Refresh visual requirements from actual portrait operations, not a list
    # of season-specific schema names which can omit the next identity writer.
    if ownership_plan is not None or opening_plan is not None or portrait_archive is not None:
        if ownership_plan is not None:
            locator['ownership_plan_path'] = registry.relative_workspace_path(saved_ownership_plan)
            locator['ownership_delta_path'] = registry.relative_workspace_path(receipt_path)
        visual = dict(locator.get('required_visual_file_hashes', {}))
        for relative in removed_photos:
            visual.pop(relative, None)
        if archive_changed:
            visual['DBDAT/MINIFOTO.PKF'] = registry.sha256_file(game / 'DBDAT/MINIFOTO.PKF')
        locator['required_visual_file_hashes'] = visual
        locator['required_visual_absent_paths'] = sorted(set(locator.get('required_visual_absent_paths', [])) |
            {f'DBDAT/MINIFOTO/J96{carrier:05d}.BMP' for carrier in portrait_offsets})
    pipeline.write_canonical_json(destination / 'locator.json', locator)
    pipeline.assert_tree_matches_inventory(release.game_path, before)
    if register:
        catalog = registry.load_catalog()
        catalog[season] = {'season': season, 'release_id': release_id, 'release_manifest_sha256': registry.sha256_file(manifest_path)}
        _atomic_replace_json(registry.CATALOG_PATH, {'schema_version': registry.CATALOG_SCHEMA,
            'seasons': [catalog[s] for s in sorted(catalog)]})
    return {'season': season, 'release_id': release_id, 'registered': register,
            'changed_birth_years': len(birth_year_changes),
            'changed_players': receipt['players_written'], 'changed_nationalities': len(nationality_changes),
            'changed_managers': len(manager_changes),
            'changed_clubs': len(club_changes),
            'changed_ownership_slots': len(ownership_changes),
            'game': str(game), 'historical_verification_complete': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season'); parser.add_argument('--plan-root', type=Path, required=True)
    parser.add_argument('--release-id', required=True); parser.add_argument('--register', action='store_true')
    parser.add_argument('--modern-birth-dates', action='store_true')
    parser.add_argument('--skip-season', action='append', default=[])
    parser.add_argument('--nationality-plan-root', type=Path)
    parser.add_argument('--manager-plan-root', type=Path)
    parser.add_argument('--club-plan-root', type=Path)
    parser.add_argument('--ownership-plan-root', type=Path)
    args = parser.parse_args()
    for season in registry.supported_seasons() if args.season == 'all' else [args.season]:
        if season in args.skip_season:
            continue
        print(json.dumps(publish(season, args.plan_root / season / 'role-plan.json',
                                 release_id=args.release_id, register=args.register,
                                 modern_birth_dates=args.modern_birth_dates,
                                 nationality_plan_path=args.nationality_plan_root / season / 'nationality-plan.json' if args.nationality_plan_root else None,
                                 manager_plan_path=args.manager_plan_root / season / 'manager-plan.json' if args.manager_plan_root else None,
                                 club_plan_path=args.club_plan_root / season / 'club-plan.json' if args.club_plan_root else None,
                                 ownership_plan_path=args.ownership_plan_root / season / 'ownership-plan.json' if args.ownership_plan_root else None)), flush=True)


if __name__ == '__main__':
    main()
