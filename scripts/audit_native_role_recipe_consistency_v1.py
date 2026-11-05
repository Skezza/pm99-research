#!/usr/bin/env python3
"""Read-only census of preferred recipe roles against indexed native roles.

This flags mechanical inconsistencies for review. It does not establish a
historical error or authorize role edits. Detailed mismatch/preserve cases are
written only beneath the caller-selected private output directory.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'upstream/pm99-skezmod-db-editor')]

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles
from scripts import season_exact_fifa_role_delta_v1 as role_policy
from scripts import season_historical_roster_audit_v1 as roster_audit
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_release_registry_v1 as registry


SCHEMA = 'pm99-preferred-native-role-recipe-consistency-audit-v1'
POSITIONS = {'G', 'D', 'M', 'F'}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def binding_snapshot(releases: list[registry.PreferredRelease]) -> dict[str, Any]:
    catalog_hash = registry.sha256_file(registry.CATALOG_PATH)
    rows = []
    for release in releases:
        locator = registry.locator_path(release.season, release.release_id)
        files = {
            'locator': locator,
            'package': release.package_path,
            'jug': release.game_path / 'DBDAT/JUG98030.FDI',
            'eq': release.game_path / 'DBDAT/EQ98030.FDI',
        }
        rows.append({
            'season': release.season,
            'release_id': release.release_id,
            'paths': {key: registry.relative_workspace_path(path) for key, path in files.items()},
            'sha256': {key: registry.sha256_file(path) for key, path in files.items()},
        })
    return {'catalog_path': registry.relative_workspace_path(registry.CATALOG_PATH),
            'catalog_sha256': catalog_hash, 'releases': rows}


def position_fallbacks(actor: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in actor.get('fact_fallbacks', [])
            if isinstance(item, dict) and item.get('field') == 'primary_position']


def fine_role_fallbacks(actor: dict[str, Any]) -> list[dict[str, Any]]:
    facts = actor.get('facts') or {}
    value = facts.get('fine_roles')
    result = [item for item in actor.get('fact_fallbacks', [])
              if isinstance(item, dict) and item.get('field') == 'fine_roles']
    if isinstance(value, dict) and value.get('policy') == 'preserve-existing-mode1':
        result.append({'field': 'fine_roles', 'method': 'inline-policy', 'value': value})
    return result


def order_status(actor: dict[str, Any], club: dict[str, Any], order: dict[str, tuple[str, int]]) -> dict[str, Any]:
    found = order.get(actor['id'])
    if found is None:
        return {'status': 'not-listed-in-opening', 'position': None}
    return {'status': found[0], 'position': found[1]}


def season_audit(release: registry.PreferredRelease) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    package = read_json(release.package_path)
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    entries = {entry.record_id: entry for entry in IndexedFDIFile.from_bytes(jug).entries}
    owners = ownership.native_owners(eq)
    clubs = {club['id']: club for club in package.get('clubs', [])}
    opening_order: dict[str, tuple[str, int]] = {}
    for club in package.get('clubs', []):
        opening = club.get('opening') or {}
        for index, player_id in enumerate(opening.get('starting_xi_player_ids') or [], 1):
            opening_order[player_id] = ('XI', index)
        for index, player_id in enumerate(opening.get('substitute_player_ids') or [], 1):
            opening_order[player_id] = ('SUB', index)

    counts: collections.Counter[str] = collections.Counter()
    proof_counts: collections.Counter[str] = collections.Counter()
    cases: list[dict[str, Any]] = []
    whole_preserve_actors: list[dict[str, Any]] = []
    explicit_mismatches: list[dict[str, Any]] = []
    for actor in package.get('players', []):
        facts = actor.get('facts') or {}
        source_position = facts.get('primary_position')
        whole_preserve = actor.get('policy') == 'preserve-existing-mode1'
        primary_fallback = position_fallbacks(actor)
        fine_fallback = fine_role_fallbacks(actor)
        fine_roles = facts.get('fine_roles')
        explicit_roles = (isinstance(fine_roles, list) and not fine_fallback)
        proof = actor.get('proof') if isinstance(actor.get('proof'), dict) else {}
        proof_id = str(proof.get('artifact_id') or 'unlabelled')
        if whole_preserve:
            counts['top_level_whole_record_preserve'] += 1
            counts['whole_preserve_fine_roles_fallback' if fine_fallback else 'whole_preserve_fine_roles_explicit_or_other'] += 1
            proof_counts[proof_id] += 1
        if not isinstance(source_position, str) or source_position not in POSITIONS:
            if whole_preserve:
                counts['whole_record_preserve_without_concrete_primary_position'] += 1
                carrier = actor.get('carrier_id')
                entry = entries.get(carrier)
                native_facts = native_roles = None
                if entry is not None:
                    payload = entry.decode_payload(jug)
                    _, native_roles = read_indexed_native_roles(payload, carrier)
                    native_facts = roster_audit.native_player(payload, carrier)
                club = clubs.get(actor.get('club_id'), {})
                expected_owner = club.get('carrier_id')
                owner_set = sorted(owners.get(carrier, set()))
                active_owner = expected_owner in owner_set
                counts['whole_preserve_active_expected_eq_owner' if active_owner else 'whole_preserve_missing_or_different_eq_owner'] += 1
                whole_preserve_actors.append({
                    'carrier_id': carrier,
                    'player_id': actor.get('id'),
                    'recipe_name': actor.get('source_name') or actor.get('name'),
                    'club_id': actor.get('club_id'),
                    'club_carrier_id': expected_owner,
                    'source_proof_artifact_id': proof_id,
                    'source_proof_grade': proof.get('grade'),
                    'top_level_whole_record_preserve': True,
                    'recipe_primary_position': source_position,
                    'recipe_fine_role_class': 'policy-fallback' if fine_fallback else ('explicit-list' if explicit_roles else 'other'),
                    'recipe_fine_roles': fine_roles,
                    'native_primary_position': native_facts.get('position') if native_facts else None,
                    'native_six_fine_codes': native_roles,
                    'active_eq_owner': active_owner,
                    'eq_owner_carrier_ids': owner_set,
                    'opening_order': order_status(actor, club, opening_order),
                    'recipe_roster_order': next((index for index, player_id in enumerate(club.get('roster_player_ids', []), 1)
                                                 if player_id == actor.get('id')), None),
                })
            continue

        counts['positioned_recipe_actors'] += 1
        counts['source_position_fallback' if primary_fallback else 'concrete_recipe_primary_position'] += 1
        counts['fine_roles_fallback' if fine_fallback else 'fine_roles_explicit'] += 1
        counts['non_whole_record_preserve_actor' if not whole_preserve and not primary_fallback else 'preserve_or_fallback_actor'] += 1
        if not whole_preserve:
            proof_counts[proof_id] += 1

        carrier = actor.get('carrier_id')
        entry = entries.get(carrier)
        if entry is None:
            counts['missing_native_jug_record'] += 1
            continue
        payload = entry.decode_payload(jug)
        native_end, native_roles = read_indexed_native_roles(payload, carrier)
        native_facts = roster_audit.native_player(payload, carrier)
        first_role = next((value for value in native_roles if value != 98), None)
        first_compatible = first_role is not None and role_policy.compatible(source_position, first_role)
        active_roles = [value for value in native_roles if value != 98]
        six_role_projection = [
            role_policy.compatible(source_position, value)
            for value in active_roles
        ]
        full_projection_compatible = bool(six_role_projection) and all(six_role_projection)
        explicit_projection_matches = None
        if explicit_roles:
            expected_roles = fine_roles + [98] * (6 - len(fine_roles))
            explicit_projection_matches = expected_roles == native_roles
            counts['explicit_native_projection_matches' if explicit_projection_matches
                   else 'explicit_native_projection_differs'] += 1
        native_primary = native_facts.get('position')
        broad_matches = native_primary == source_position
        club = clubs.get(actor.get('club_id'), {})
        expected_owner = club.get('carrier_id')
        owner_set = sorted(owners.get(carrier, set()))
        active_owner = expected_owner in owner_set
        order = order_status(actor, club, opening_order)
        roster_index = next((index for index, player_id in enumerate(club.get('roster_player_ids', []), 1)
                             if player_id == actor.get('id')), None)

        counts['active_expected_eq_owner' if active_owner else 'missing_or_different_eq_owner'] += 1
        counts['native_primary_matches_recipe' if broad_matches else 'native_primary_differs_or_unknown'] += 1
        counts['first_role_compatible' if first_compatible else 'first_role_incompatible_or_missing'] += 1
        counts['all_active_six_roles_compatible' if full_projection_compatible else 'six_role_projection_has_conflict_or_empty'] += 1
        counts[f"{('fallback' if fine_fallback else 'explicit')}_{'first_role_mismatch' if not first_compatible else 'first_role_match'}"] += 1

        row = {
            'carrier_id': carrier,
            'player_id': actor.get('id'),
            'recipe_name': actor.get('source_name') or actor.get('name'),
            'club_id': actor.get('club_id'),
            'club_carrier_id': expected_owner,
            'recipe_primary_position': source_position,
            'recipe_primary_position_is_fallback': bool(primary_fallback),
            'top_level_whole_record_preserve': whole_preserve,
            'fine_role_class': 'policy-fallback' if fine_fallback else ('explicit-list' if explicit_roles else 'other'),
            'recipe_fine_roles': fine_roles,
            'source_proof_artifact_id': proof_id,
            'source_proof_grade': proof.get('grade'),
            'native_first_fine_code': first_role,
            'native_six_fine_codes': native_roles,
            'native_six_role_compatible_with_recipe_primary': six_role_projection,
            'first_role_compatible': first_compatible,
            'all_active_six_roles_compatible': full_projection_compatible,
            'any_native_role_compatible': any(six_role_projection),
            'explicit_native_projection_matches': explicit_projection_matches,
            'native_primary_position': native_primary,
            'native_primary_matches_recipe': broad_matches,
            'active_eq_owner': active_owner,
            'eq_owner_carrier_ids': owner_set,
            'opening_order': order,
            'recipe_roster_order': roster_index,
        }
        if whole_preserve or not first_compatible or not broad_matches or not full_projection_compatible or not active_owner or explicit_projection_matches is False:
            cases.append(row)
        if whole_preserve:
            whole_preserve_actors.append(row)
        if explicit_roles and not first_compatible:
            explicit_mismatches.append(row)

    cases.sort(key=lambda row: (row['carrier_id'], row['player_id'] or ''))
    whole_preserve_actors.sort(key=lambda row: (row['carrier_id'], row['player_id'] or ''))
    explicit_mismatches.sort(key=lambda row: row['carrier_id'])
    summary = {
        'season': release.season,
        'release_id': release.release_id,
        'counts': dict(sorted(counts.items())),
        'source_proof_artifact_counts': dict(sorted(proof_counts.items())),
        'case_count': len(cases),
        'whole_record_preserve_actor_count': len(whole_preserve_actors),
        'explicit_first_role_mismatch_count': len(explicit_mismatches),
        'representative_explicit_mismatches': explicit_mismatches[:1],
        'interpretation': 'Mechanical consistency flags only; these do not independently prove historical identity or authorize a role edit.',
    }
    return summary, cases, whole_preserve_actors


def run(output: Path) -> dict[str, Any]:
    output = output.resolve()
    if output.exists():
        raise ValueError(f'output path already exists: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    releases = [registry.load_preferred_release(season) for season in registry.supported_seasons()]
    if len(releases) != 26:
        raise ValueError(f'expected 26 preferred releases, found {len(releases)}')
    before = binding_snapshot(releases)
    output.mkdir()
    summaries, representatives = [], []
    cases_dir = output / 'cases'
    cases_dir.mkdir()
    for release in releases:
        summary, cases, whole_preserve_actors = season_audit(release)
        case_path = cases_dir / f'{release.season}.json'
        case_path.write_text(json.dumps({'schema': SCHEMA + '-season-cases', **summary,
                                         'whole_record_preserve_actors': whole_preserve_actors,
                                         'cases': cases}, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
        summaries.append(summary)
        for row in summary['representative_explicit_mismatches']:
            representatives.append({'season': release.season, **row})
    # One representative explicit mismatch per season, ordered by season then carrier.
    representatives.sort(key=lambda row: (row['season'], row['carrier_id']))
    representatives = representatives[:10]
    after = binding_snapshot(releases)
    if before != after:
        raise RuntimeError('preferred catalog/release inputs changed during read-only audit')
    report = {
        'schema': SCHEMA,
        'preferred_release_count': len(releases),
        'snapshot_before': before,
        'snapshot_after': after,
        'season_summaries': summaries,
        'representative_explicit_mismatches_first_by_season_and_carrier': representatives,
        'interpretation': 'A mismatch is a mechanical consistency flag, not a confirmed historical bug.',
    }
    (output / 'summary.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True,
                        help='new private output directory for summary and per-season case JSON files')
    args = parser.parse_args()
    report = run(args.output)
    print(json.dumps({'preferred_release_count': report['preferred_release_count'],
                      'season_case_counts': {row['season']: row['case_count'] for row in report['season_summaries']},
                      'explicit_representatives': len(report['representative_explicit_mismatches_first_by_season_and_carrier']),
                      'output': str(args.output.resolve())}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
