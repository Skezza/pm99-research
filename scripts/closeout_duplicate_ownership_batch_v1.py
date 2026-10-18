#!/usr/bin/env python3
"""Resume a bounded ownership batch without scraping or rebuilding old games."""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import copy
import csv
import json
import os
import shutil
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import capture_registered_season_runtime_v1 as runtime


def rebase_completed_plans(input_root, output_root, *, seasons=None):
    """Advance reviewed proposals past completed slots, without rescraping them."""
    supported = registry.supported_seasons()
    selected = supported if seasons is None else sorted(set(seasons))
    if not selected or set(selected) - set(supported):
        raise ValueError('completed plan continuation requires supported seasons')
    for season in selected:
        source_path = input_root / season / 'ownership-plan.json'
        source = json.loads(source_path.read_text())
        old = registry.load_registered_release(season, source['release_id'])
        current = registry.load_preferred_release(season)
        if (registry.sha256_file(old.package_path), registry.sha256_file(old.game_path / 'DBDAT/JUG98030.FDI')) != (
                source['package_sha256'], source['jug_sha256']):
            raise ValueError('completed proposal baseline changed')
        for name in ('EQ98030.FDI', 'ENT98030.FDI'):
            if registry.sha256_file(old.game_path / 'DBDAT' / name) != registry.sha256_file(current.game_path / 'DBDAT' / name):
                raise ValueError('club/order/manager context changed since ownership proposal')
        rows = {}
        for _, package, _ in planner.package_layers(current):
            for player in package['players']:
                if player['id'] in rows:
                    raise ValueError('completed continuation has ambiguous cross-layer player IDs')
                rows[player['id']] = player
        saved_path = current.locator.get('ownership_plan_path')
        saved = json.loads((ROOT / saved_path).read_text()) if saved_path else {'updates': []}
        saved_rows = {row['player_id']: row for row in saved['updates']}
        result = copy.deepcopy(source)
        result['updates'] = []
        reused = []
        for row in source['updates']:
            now = rows.get(row['player_id'])
            if now == row['before']:
                result['updates'].append(row)
                continue
            previous = saved_rows.get(row['player_id'])
            fields = ('before', 'replacement', 'retained_owner_player_id', 'owner_evidence', 'replacement_opening_evidence')
            if (previous is None or any(previous[key] != row[key] for key in fields) or
                    now is None or now.get('source_name') != row['replacement']['source_player']['name'] or
                    now.get('facts', {}).get('birth_date') != row['replacement']['source_player']['birth_date']):
                raise ValueError('changed proposal slot lacks its exact completed correction proof')
            reused.append({'player_id': row['player_id'], 'completed_plan_path': saved_path,
                           'completed_plan_sha256': registry.sha256_file(ROOT / saved_path)})
        result.update(release_id=current.release_id, package_sha256=registry.sha256_file(current.package_path),
                      jug_sha256=registry.sha256_file(current.game_path / 'DBDAT/JUG98030.FDI'))
        result['continued_from'] = {'plan_path': registry.relative_workspace_path(source_path),
            'plan_sha256': registry.sha256_file(source_path), 'completed_slots_not_rebuilt': reused,
            'candidate_group_count_scope': 'prior proposal cohort; current inventory requires separate identity audit'}
        result['summary']['replacement_slots'] = len(result['updates'])
        path = output_root / season / 'ownership-plan.json'
        if path.exists():
            raise ValueError('rebased evidence already exists; use another output root')
        path.parent.mkdir(parents=True, exist_ok=True)
        pipeline.write_canonical_json(path, result)
        print(json.dumps({'season': season, 'remaining_proposals': len(result['updates']),
                          'completed_slots_reused': len(reused)}), flush=True)


def reusable_quality(report, package_sha256, current_runtime):
    """A recipe hash alone cannot bind a later runner attestation."""
    return (report.get('inputs', {}).get('package_sha256') == package_sha256
        and set(report.get('checks', {})) >= {'runtime', 'kits', 'compiled_managers', 'compiled_handling'}
        and report.get('checks', {}).get('runtime') == current_runtime
        and not any(row['code'] == 'qa-execution-error' for row in report.get('blockers', [])))


def resume_quality(input_root, output_root, jobs):
    """Retain completed exact-recipe audits; retry failed checker executions only."""
    from scripts import pm99_season_qa_v1 as qa
    if output_root.exists():
        raise ValueError('quality evidence is immutable; use a new output root')
    pending = []
    retained = []
    for season in registry.supported_seasons():
        path = input_root / season / 'qa-report.json'
        report = json.loads(path.read_text()) if path.is_file() else {}
        release = registry.load_preferred_release(season)
        complete = reusable_quality(report, registry.sha256_file(release.package_path), qa.audit_runtime(season))
        if complete:
            qa._write(output_root / season / 'qa-report.json', report)
            retained.append({'season': season, 'path': registry.relative_workspace_path(path),
                             'sha256': registry.sha256_file(path)})
        else:
            pending.append(season)
    with concurrent.futures.ProcessPoolExecutor(max_workers=min(3, max(1, jobs))) as pool:
        futures = {pool.submit(qa.audit_season, season): season for season in pending}
        for future in concurrent.futures.as_completed(futures):
            season = futures[future]
            report = future.result()
            qa._write(output_root / season / 'qa-report.json', report)
            print(json.dumps({'season': season, 'result': report['result'], **report['summary']}), flush=True)
    pipeline.write_canonical_json(output_root / 'reuse-ledger.json', {
        'retained_completed_reports': retained, 'retried_checker_executions': pending,
        'checker_path': 'scripts/pm99_season_qa_v1.py',
        'checker_sha256': registry.sha256_file(ROOT / 'scripts/pm99_season_qa_v1.py')})


def closeout(plan_root, output_root, qa_root, supplemental_plan=None,
             native_readback=None, native_reproduction=None, identity_audit=None):
    """Freeze current proofs and the remaining queue; never label failed QA a pass."""
    if output_root.exists():
        raise ValueError('closeout evidence is immutable; use a new output root')
    if supplemental_plan is not None:
        supplemental = json.loads(supplemental_plan.read_text())
    else:
        supplemental = None
    seasons = registry.supported_seasons()
    plans = {}
    for season in seasons:
        path = plan_root / season / 'ownership-plan.json'
        if supplemental is not None and supplemental['season'] == season:
            path = supplemental_plan
        plans[season] = (path, json.loads(path.read_text()))
    checks = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(registry.validate_preferred_release, season, level='release'): season
                   for season in seasons}
        for future in concurrent.futures.as_completed(futures):
            check = future.result()
            checks.append(check)
            print(json.dumps({'season': futures[future], 'full_release_validation': check['valid']}), flush=True)
    if not all(check['valid'] for check in checks):
        raise ValueError('release validation failed; closeout cannot assert all games are technically verified')
    checks.sort(key=lambda row: row['season'])
    releases = []
    replacements = []
    unresolved = []
    for season in seasons:
        release = registry.load_preferred_release(season)
        path, plan = plans[season]
        report_path = qa_root / season / 'qa-report.json'
        report = json.loads(report_path.read_text())
        if report.get('inputs', {}).get('package_sha256') != registry.sha256_file(release.package_path):
            raise ValueError(f'QA is not bound to current recipe: {season}')
        if plan['updates']:
            compiled_plan = json.loads((ROOT / release.locator['ownership_plan_path']).read_text())
            actual_rows = {row['player_id']: row for row in compiled_plan['updates']}
            fields = ('before', 'replacement', 'retained_owner_player_id', 'owner_evidence', 'replacement_opening_evidence')
            if (set(actual_rows) != {row['player_id'] for row in plan['updates']} or
                    any(any(actual_rows[row['player_id']][key] != row[key] for key in fields)
                        for row in plan['updates'])):
                raise ValueError(f'current compiled ownership plan differs: {season}')
        attestation = json.loads(release.attestation_path.read_text())
        receipt = attestation['runtime_receipts'][0]
        # A historical ownership blocker remains a real failure, not technical approval.
        blockers = [row['code'] for row in report['blockers']]
        releases.append({'season': season, 'release_id': release.release_id,
            'package_path': registry.relative_workspace_path(release.package_path),
            'package_sha256': registry.sha256_file(release.package_path),
            'inventory_sha256': registry.sha256_file(release.inventory_path),
            'manifest_sha256': release.manifest_sha256,
            'runtime_evidence_path': registry.relative_workspace_path(release.runtime_evidence_path),
            'attestation_sha256': registry.sha256_file(release.attestation_path),
            'lineup_screenshot': receipt['lineup_screenshot'],
            'lineup_screenshot_sha256': receipt['lineup_screenshot_sha256'],
            'qa_path': registry.relative_workspace_path(report_path),
            'qa_sha256': registry.sha256_file(report_path), 'historical_qa_result': report['result'],
            'historical_qa_blocker_codes': blockers,
            'plan_path': registry.relative_workspace_path(path), 'plan_sha256': registry.sha256_file(path),
            'changed_slots': len(plan['updates']),
            'runtime_scope': 'fresh-changed-game' if plan['updates'] else 'unchanged-game-exact-existing-proof'})
        for row in plan['updates']:
            replacements.append({'season': season, 'club': row['club'], 'player_id': row['player_id'],
                'before': row['before'].get('source_name', row['before']['name']),
                'after': row['replacement']['source_player']['name'],
                'retained_owner_player_id': row['retained_owner_player_id'],
                'opening_date': row['replacement_opening_evidence']['date'],
                'ownership_plan_sha256': registry.sha256_file(path)})
        unresolved.extend(dict(row, season=season) for row in plan['unresolved'])
    if native_readback is None or native_reproduction is None:
        raise ValueError('closeout requires frozen native readback and reproduction proofs')
    readback = json.loads(native_readback.read_text())
    reproduction = json.loads(native_reproduction.read_text())
    changed = {row['season']: row for row in releases if row['changed_slots']}
    readback_rows = {row['season']: row for row in readback['seasons']}
    reproduction_rows = {row['season']: row for row in reproduction['seasons']}
    if (set(readback_rows) != set(changed) or set(reproduction_rows) != set(changed) or
            readback['players'] != len(replacements) or reproduction['players'] != len(replacements) or
            registry.sha256_file(ROOT / reproduction['compiler_path']) != reproduction['compiler_sha256']):
        raise ValueError('native preservation/reproduction proof coverage or compiler changed')
    for season, row in changed.items():
        native = readback_rows[season]
        rebuilt = reproduction_rows[season]
        release = registry.load_preferred_release(season)
        if (native['players'] != row['changed_slots'] or rebuilt['players'] != row['changed_slots'] or
                native['idempotent'] is not True or native['all_unrelated_clubs_tactics_managers'] != 'byte-identical' or
                native['jug_sha256'] != registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI') or
                rebuilt['exact_native_reproduction_from_source_release'] is not True or
                rebuilt['exact_portrait_directory_reproduction'] is not True):
            raise ValueError(f'native preservation/reproduction proof differs: {season}')
    identity_binding = None
    if identity_audit is not None:
        identities = json.loads(identity_audit.read_text())
        current_rows = {row['season']: row for row in releases}
        if (len(identities['seasons']) != len(seasons) or
                {row['season'] for row in identities['seasons']} != set(seasons) or
                any((row['release_id'], row['package_sha256']) !=
                    (current_rows[row['season']]['release_id'], current_rows[row['season']]['package_sha256'])
                    for row in identities['seasons'])):
            raise ValueError('full-source-name/DOB audit is not bound to current recipes')
        identity_binding = {'path': registry.relative_workspace_path(identity_audit),
            'sha256': registry.sha256_file(identity_audit),
            'remaining_candidate_groups': sum(row['duplicate_candidate_groups'] for row in identities['seasons'])}
    result = {'schema_version': 'pm99-duplicate-ownership-bounded-closeout-v1',
        'scope': 'confirmed safe repairs complete; remaining candidates unresolved, not historically certified',
        'season_count': len(seasons), 'changed_season_count': sum(bool(row['changed_slots']) for row in releases),
        'corrected_slot_count': len(replacements), 'full_release_validation_passed': len(checks),
        'unresolved_entries': len(unresolved),
        'unresolved_reasons': dict(collections.Counter(row['reason'] for row in unresolved)),
        'historical_qa_passed': sum(row['historical_qa_result'] == 'pass' for row in releases),
        'historical_qa_blockers': dict(collections.Counter(code for row in releases for code in row['historical_qa_blocker_codes'])),
        'releases': releases, 'replacements': replacements,
        'native_readback': {'path': registry.relative_workspace_path(native_readback), 'sha256': registry.sha256_file(native_readback)},
        'native_reproduction': {'path': registry.relative_workspace_path(native_reproduction), 'sha256': registry.sha256_file(native_reproduction)},
        'full_source_name_dob_audit': identity_binding,
        'preservation': 'selected player slots and stale portrait flags only; other records/assets/tactics unchanged'}
    output_root.mkdir(parents=True)
    pipeline.write_canonical_json(output_root / 'summary.json', result)
    pipeline.write_canonical_json(output_root / 'full-release-validation.json', checks)
    pipeline.write_canonical_json(output_root / 'unresolved.json', unresolved)
    with (output_root / 'replacements.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(replacements[0]) if replacements else ['season'])
        writer.writeheader()
        writer.writerows(replacements)
    print(json.dumps({key: value for key, value in result.items() if key not in {'releases', 'replacements'}}), flush=True)
    return result


def safe_plans(input_root, output_root):
    """Refine a completed proof ledger; do not rerun its collection/review."""
    people, _, _, snapshot = transfer.load_snapshot(
        ROOT / '.local/external-sources/transfermarkt-datasets/transfermarkt-datasets.duckdb',
        ROOT / '.local/season-pipeline-v2/world-2015-transfermarkt-opening-fixtures-20260831.json')
    summaries = []
    for season in registry.supported_seasons():
        source_path = input_root / season / 'ownership-plan.json'
        source = json.loads(source_path.read_text())
        if source['bindings']['snapshot'] != snapshot:
            raise ValueError('completed ownership plan uses another source snapshot')
        old = registry.load_registered_release(season, source['release_id'])
        if (registry.sha256_file(old.package_path), registry.sha256_file(old.game_path / 'DBDAT/JUG98030.FDI')) != (
                source['package_sha256'], source['jug_sha256']):
            raise ValueError('previous ownership baseline changed')
        result = copy.deepcopy(source)
        result['updates'] = []
        jug = (old.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
        for row in source['updates']:
            row = copy.deepcopy(row)
            person = transfer.unique_person(row['before'], people)
            if person is None:
                raise ValueError('previously matched duplicate identity no longer joins snapshot')
            row['duplicate_source_person'] = person
            reason = None
            if str(person['source_player_id']) in set(row['replacement_opening_evidence']['starting_xi']) | set(row['replacement_opening_evidence']['substitutes']):
                reason = 'contradictory-positive-opening-matchday-member-protected'
            elif row['before']['facts'].get('primary_position') != row['replacement']['source_player']['position']:
                reason = 'owner-proven-but-no-unused-role-compatible-opening-substitute'
            else:
                view = {'players': [{'id': row['player_id'], 'source_name': row['replacement']['source_player']['name'],
                                     'name': delta.compiler._pm99_text(row['replacement']['source_player']['name'], label='replacement')}]}
                try:
                    delta.fit_display_names(jug, view, {'updates': [row]})
                except ValueError:
                    reason = 'owner-proven-but-replacement-surname-exceeds-native-name-window'
            if reason:
                result['unresolved'].append({'reason': reason, 'player_id': row['player_id'],
                    'identity': {'source_name': row['before'].get('source_name', row['before']['name']),
                                 'birth_date': row['before']['facts']['birth_date'], 'source_person': person},
                    'candidates': [{'player_id': row['player_id'], 'carrier_id': row['carrier_id'],
                                    'club_id': row['club_id'], 'club': row['club']}],
                    'confirmed_owner_player_id': row['retained_owner_player_id'],
                    'unapplied_replacement': row['replacement']})
            else:
                result['updates'].append(row)
        result['summary'].update(replacement_slots=len(result['updates']), unresolved_entries=len(result['unresolved']),
            unresolved_reasons=dict(collections.Counter(r['reason'] for r in result['unresolved'])))
        result['refinement'] = {'input_path': registry.relative_workspace_path(source_path),
            'input_sha256': registry.sha256_file(source_path),
            'policy': 'protect-positive-matchday-members-preserve-broad-roles-and-published-surnames'}
        path = output_root / season / 'ownership-plan.json'
        if path.exists():
            if json.loads(path.read_text()) != result:
                raise ValueError('completed safe plan differs; use another output root')
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            pipeline.write_canonical_json(path, result)
        summaries.append(dict(result['summary'], season=season))
        print(json.dumps(summaries[-1]), flush=True)
    return summaries


def build_one(season, plan_root, release_id):
    plan_path = plan_root / season / 'ownership-plan.json'
    plan = json.loads(plan_path.read_text())
    if not plan['updates']:
        return {'season': season, 'status': 'unchanged-existing-game-preserved'}
    existing = registry.locator_path(season, release_id)
    if existing.exists():
        check = registry.validate_preferred_release(season, level='playable', release_id=release_id)
        if not check['valid']:
            raise ValueError('completed ownership delta no longer validates')
        completed = registry.load_registered_release(season, release_id)
        saved = json.loads((ROOT / completed.locator['ownership_plan_path']).read_text())
        projection = lambda document: [{k: row[k] for k in ('player_id', 'before', 'replacement',
            'retained_owner_player_id', 'owner_evidence', 'replacement_opening_evidence')}
            for row in document['updates']]
        if projection(saved) != projection(plan):
            raise ValueError('completed ownership delta has different requested people or source evidence')
        return {'season': season, 'status': 'reused-completed-native-delta'}
    release = registry.load_preferred_release(season)
    role = {'season': season, 'release_id': release.release_id,
        'package_sha256': registry.sha256_file(release.package_path),
        'jug_sha256': registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'), 'updates': [], 'unresolved': []}
    role_path = plan_root / season / 'role-plan.json'
    if role_path.exists():
        if json.loads(role_path.read_text()) != role:
            raise ValueError('partial-compile input changed')
    else:
        pipeline.write_canonical_json(role_path, role)
    result = publisher.publish(season, role_path, release_id=release_id, ownership_plan_path=plan_path)
    check = registry.validate_preferred_release(season, level='playable', release_id=release_id)
    if not check['valid']:
        raise ValueError('compiled ownership delta fails immutable release validation')
    return result


def freeze_implementations(implementations, hashes, destination):
    """Retain exact checked code so later iterations cannot invalidate a proof."""
    frozen = {}
    for key, source in implementations.items():
        if registry.sha256_file(source) != hashes[key]:
            raise ValueError('verification implementation changed before freezing')
        target = destination / key.removesuffix('_path') / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if registry.sha256_file(target) != hashes[key]:
                raise ValueError('frozen implementation differs; never overwrite')
        else:
            shutil.copy2(source, target)
        if registry.sha256_file(target) != hashes[key]:
            raise ValueError('frozen implementation copy failed hash verification')
        frozen[key] = target
    return frozen


def verify_native_batch(plan_root, release_id, output, *, seasons=None):
    """Reproduce a bounded delta in memory, without generating another game."""
    if output.exists():
        raise ValueError('native verification evidence is immutable')
    implementations = {'compiler_path': Path(delta.__file__),
        'cross_club_reserve_checker_path': ROOT / 'scripts/season_cross_club_reserve_repair_v1.py',
        'selected_replacement_output_checker_path': ROOT / 'scripts/cross_club_replacement_output_v1.py',
        'selected_replacement_rating_model_v3_path': ROOT / 'scripts/season_rating_calibration_v3.py',
        'primary_savio_bobb_alias_checker_path': ROOT / 'scripts/savio_bobb_2024_original_alias_v1.py',
        'within_club_reserve_checker_path': ROOT / 'scripts/season_within_club_reserve_repair_v1.py',
        'wikipedia_interior_year_identity_reader_path': ROOT / 'scripts/season_wikipedia_career_identity_v1.py',
        'ownership_source_checker_path': ROOT / 'scripts/season_common_date_ownership_v1.py',
        'ownership_planner_path': Path(planner.__file__),
        'published_identity_reader_path': Path(transfer.__file__),
        'source_reparser_path': ROOT / 'scripts/season_historical_roster_audit_v1.py',
        'original_first_fixture_reader_path': ROOT / 'scripts/season_historical_opening_review_v1.py',
        'opening_identity_supplement_path': ROOT / 'scripts/season_opening_person_supplement_v1.py',
        'used_substitute_reader_path': ROOT / 'scripts/season_opening_used_substitutes_v1.py',
        'substitution_marker_reader_path': ROOT / 'scripts/season_opening_used_substitutes_v2.py',
        'substitution_evidence_refiner_path': ROOT / 'scripts/refine_opening_substitution_events_v2.py',
        'original_public_person_reader_path': ROOT / 'scripts/season_published_person_identity_v1.py',
        'original_public_history_reader_path': ROOT / 'scripts/season_published_transfer_history_v1.py',
        'original_public_input_binder_path': ROOT / 'scripts/season_public_identity_and_history_inputs_v1.py',
        'original_published_display_alias_checker_path': ROOT / 'scripts/season_published_display_names_v1.py',
        'original_published_family_component_checker_path': ROOT / 'scripts/season_published_family_component_v1.py',
        'same_carrier_name_capacity_checker_path': ROOT / 'scripts/season_same_carrier_name_capacity_v1.py',
        'native_same_carrier_name_capacity_reader_path': ROOT / 'upstream/pm99-skezmod-db-editor/app/player_name_capacity.py',
        'english_overlay_binding_checker_path': ROOT / 'scripts/season_duplicate_english_overlay_v1.py',
        'layered_ownership_package_builder_path': ROOT / 'scripts/season_duplicate_layered_packages_v1.py',
        'sourced_reserve_role_checker_path': ROOT / 'scripts/season_sourced_reserve_role_policy_v1.py',
        'dated_reserve_owner_checker_path': ROOT / 'scripts/season_dated_reserve_owner_v1.py',
        'soccerbase_original_schedule_match_profile_reader_path': ROOT / 'scripts/season_soccerbase_original_opening_v1.py',
        'soccerbase_original_identity_bridge_reader_path': ROOT / 'scripts/replay_original_soccerbase_openings_v1.py',
        'soccerbase_duplicate_source_checker_path': ROOT / 'scripts/season_soccerbase_duplicate_source_policy_v1.py',
        'soccerbase_public_club_identity_reader_path': ROOT / 'scripts/season_english_result_date_binding_v1.py',
        'soccerbase_public_club_entity_reader_path': ROOT / 'scripts/capture_original_public_club_entities_v1.py',
        'native_xi_guard_reader_path': ROOT / 'scripts/season_contextual_tactics_v1.py',
        'recipe_schema_path': ROOT / 'scripts/season_package_v2.py',
        'editorial_rating_model_path': ROOT / 'scripts/season_editorial_ratings_v1.py',
        'rating_input_builder_path': ROOT / 'scripts/season_editorial_rating_input_builder_v1.py',
        'native_name_writer_path': ROOT / 'upstream/pm99-skezmod-db-editor/app/editor_actions.py',
        'core_compiler_path': ROOT / 'scripts/season_package_compiler_v2.py',
        'verifier_path': Path(__file__)}
    hashes = {key: registry.sha256_file(path) for key, path in implementations.items()}
    supported = registry.supported_seasons()
    selected = supported if seasons is None else sorted(set(seasons))
    if not selected or set(selected) - set(supported):
        raise ValueError('native verification selection must contain supported seasons')
    rows = []
    for season in selected:
        proposed = json.loads((plan_root / season / 'ownership-plan.json').read_text())
        if not proposed['updates']:
            continue
        release = registry.load_registered_release(season, release_id)
        saved_path = ROOT / release.locator['ownership_plan_path']
        plan = json.loads(saved_path.read_text())
        if plan != proposed:
            raise ValueError('native verification plan differs from compiled plan')
        base = registry.load_registered_release(season, plan['release_id'])
        delta.verify_plan(base, plan)
        original = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
        from scripts import season_duplicate_layered_packages_v1 as layered
        expected, expected_english, expected_view, aliases = layered.prepare(base, plan, original)
        actual = json.loads(release.package_path.read_text())
        if (expected['players'] != actual['players'] or
                any(expected[key] != actual[key] for key in ('clubs', 'managers', 'assets'))):
            raise ValueError('compiled player/club/manager/asset declarations differ')
        if expected_english is not None:
            english_layers = [pkg for label, pkg, _ in planner.package_layers(release) if label == 'english']
            if len(english_layers) != 1 or english_layers[0] != expected_english:
                raise ValueError('compiled English recipe layer differs from exact source reproduction')
        changed = {row['player_id'] for row in plan['updates']}
        countries = delta.compiler._extract_country_codes_from_textos(base.game_path / 'DBDAT/TEXTOS.PKF')
        reproduced = delta.compile_planned_players(original, expected_view, changed, countries,plan)
        installed = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
        if reproduced != installed or delta.compile_players(installed, expected_view, changed, countries) != installed:
            raise ValueError('native delta reproduction or idempotence failed')
        for name in ('EQ98030.FDI', 'ENT98030.FDI'):
            if registry.sha256_file(base.game_path / 'DBDAT' / name) != registry.sha256_file(release.game_path / 'DBDAT' / name):
                raise ValueError('unrelated club/tactic/manager bytes changed')
        carriers = {row['carrier_id'] for row in plan['updates']}
        archive, _ = delta.no_photo_archive((base.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes(), carriers)
        if archive != (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes():
            raise ValueError('native portrait directory delta differs')
        if any((release.game_path / f'DBDAT/MINIFOTO/J96{carrier:05d}.BMP').exists() for carrier in carriers):
            raise ValueError('displaced identity retains a loose portrait')
        rows.append({'season': season, 'release_id': release_id,
            'package_sha256': registry.sha256_file(release.package_path),
            'ownership_plan_path': registry.relative_workspace_path(saved_path),
            'ownership_plan_sha256': registry.sha256_file(saved_path),
            'jug_sha256': registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
            'players': len(changed), 'idempotent': True,
            'exact_native_reproduction_from_source_release': True,
            'all_unrelated_player_records': 'byte-identical',
            'all_unrelated_clubs_tactics_managers': 'byte-identical',
            'exact_portrait_directory_reproduction': True, 'display_aliases': aliases})
        print(json.dumps(rows[-1]), flush=True)
    if any(registry.sha256_file(path) != hashes[key] for key, path in implementations.items()):
        raise ValueError('verification implementation changed during the check')
    frozen = freeze_implementations(implementations, hashes,
        output.parent / ('implementation-' + release_id))
    result = {'schema_version': 'pm99-duplicate-ownership-native-verification-v2',
        'release_id': release_id, 'players': sum(row['players'] for row in rows), 'seasons': rows,
        'verification_scope': 'all-supported-seasons' if seasons is None else 'selected-season-components',
        'live_implementation_paths_at_verification': {
            key: registry.relative_workspace_path(path) for key, path in implementations.items()}}
    for key, path in implementations.items():
        result[key] = registry.relative_workspace_path(frozen[key])
        result[key.replace('_path', '_sha256')] = hashes[key]
    pipeline.write_canonical_json(output, result)
    return result


def audit_current_identities(output, previous_path=None):
    """Count full-source-name/DOB candidates, including the current English overlay."""
    if output.exists():
        raise ValueError('identity evidence is immutable')
    previous = {}
    if previous_path is not None:
        document = json.loads(previous_path.read_text())
        if document['schema_version'] != 'pm99-country-independent-player-identity-candidate-audit-v1':
            raise ValueError('previous identity evidence uses another policy')
        previous = {row['season']: row for row in document['seasons']}
    rows = []
    reused = []
    for season in registry.supported_seasons():
        release = registry.load_preferred_release(season)
        old = previous.get(season)
        if (old and (old['release_id'], old['package_sha256']) ==
                (release.release_id, registry.sha256_file(release.package_path)) and
                all(registry.sha256_file(ROOT / layer['path']) == layer['sha256'] for layer in old['layers'])):
            rows.append(old)
            reused.append(season)
            continue
        by_carrier = {}
        layer_bindings = []
        for layer, package, path in planner.package_layers(release):
            layer_bindings.append({'layer': layer, 'path': registry.relative_workspace_path(path),
                                   'sha256': registry.sha256_file(path)})
            by_carrier.update({p['carrier_id']: p for p in package['players']})
        groups = collections.defaultdict(list)
        for player in by_carrier.values():
            key = planner.roster.person_identity_key(player)
            if key is not None:
                groups[key].append({'player_id': player['id'], 'carrier_id': player['carrier_id'],
                                    'club_id': player['club_id']})
        candidates = [{'source_name_key': key[0], 'birth_date': key[1], 'players': players}
                      for key, players in sorted(groups.items()) if len(players) > 1]
        rows.append({'season': season, 'release_id': release.release_id,
            'package_sha256': registry.sha256_file(release.package_path), 'layers': layer_bindings,
            'duplicate_candidate_groups': len(candidates), 'candidates': candidates})
        print(json.dumps({'season': season, 'duplicate_candidate_groups': len(candidates)}), flush=True)
    result = {'schema_version': 'pm99-country-independent-player-identity-candidate-audit-v1',
        'policy': 'full source name and DOB, never display aliases or nationality; candidates, not all confirmed people',
        'seasons': rows}
    if previous_path is not None:
        result['reuse'] = {'path': registry.relative_workspace_path(previous_path),
                          'sha256': registry.sha256_file(previous_path), 'unchanged_seasons': reused}
    pipeline.write_canonical_json(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['refine', 'rebase', 'build', 'runtime', 'qa', 'closeout', 'verify-native', 'identity-audit'])
    parser.add_argument('--input-root', type=Path)
    parser.add_argument('--plan-root', type=Path, required=True)
    parser.add_argument('--release-id', default='opening-ownership-20261005-r23a')
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--skip-season', action='append', default=[])
    parser.add_argument('--output-root', type=Path)
    parser.add_argument('--qa-root', type=Path)
    parser.add_argument('--supplemental-plan', type=Path)
    parser.add_argument('--native-readback', type=Path)
    parser.add_argument('--native-reproduction', type=Path)
    parser.add_argument('--identity-audit', type=Path)
    args = parser.parse_args()
    if args.action == 'identity-audit':
        if args.output_root is None:
            parser.error('identity-audit requires --output-root (a JSON evidence file)')
        audit_current_identities(args.output_root, args.input_root)
        return
    if args.action == 'verify-native':
        if args.output_root is None:
            parser.error('verify-native requires --output-root (a JSON evidence file)')
        verify_native_batch(args.plan_root, args.release_id, args.output_root)
        return
    if args.action == 'rebase':
        if args.input_root is None:
            parser.error('rebase requires --input-root')
        rebase_completed_plans(args.input_root, args.plan_root)
        return
    if args.action == 'qa':
        if args.input_root is None or args.output_root is None:
            parser.error('qa requires --input-root and --output-root')
        resume_quality(args.input_root, args.output_root, args.jobs)
        return
    if args.action == 'closeout':
        if args.output_root is None or args.qa_root is None:
            parser.error('closeout requires --output-root and --qa-root')
        closeout(args.plan_root, args.output_root, args.qa_root, args.supplemental_plan,
                 args.native_readback, args.native_reproduction, args.identity_audit)
        return
    if args.action == 'refine':
        if args.input_root is None: parser.error('refine requires --input-root')
        safe_plans(args.input_root, args.plan_root)
        return
    seasons = [s for s in registry.supported_seasons() if s not in args.skip_season]
    if args.action == 'runtime':
        seasons = [s for s in seasons if registry.load_preferred_release(s).release_id == args.release_id]
        os.environ.update(PM99_RUNNER_WORKER_LANE_COUNT='3', PM99_RUNNER_HOST_LOCK_CONCURRENCY='3',
                          PM99_RUNNER_WORKER_DISPLAY_BASE='90')
        options = SimpleNamespace(expect_release_id=args.release_id, execute=True, attest=True,
            worker='tiny-m73', run_tag=None, compact_evidence=True)
        operation = lambda s: runtime.capture_one(season=s, args=options)
    else:
        operation = lambda s: build_one(s, args.plan_root, args.release_id)
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, max(1, args.jobs))) as pool:
        futures = {pool.submit(operation, season): season for season in seasons}
        for future in concurrent.futures.as_completed(futures):
            season = futures[future]
            try:
                result = future.result()
                if args.action == 'build' and registry.locator_path(season, args.release_id).exists():
                    # Catalog promotions are serial; never race JSON writes.
                    publisher.register_completed_delta(season, args.release_id)
                print(json.dumps(result), flush=True)
            except Exception as exc:
                failures.append({'season': season, 'error': str(exc)})
                print(json.dumps(failures[-1]), flush=True)
    if failures:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
