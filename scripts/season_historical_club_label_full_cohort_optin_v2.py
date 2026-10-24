#!/usr/bin/env python3
"""Explicit source-bound complete roster identity proof; no opening XI claim."""
from __future__ import annotations
import json
import sys
from pathlib import PurePosixPath
from pathlib import Path

ROOT = next((parent for parent in Path(__file__).resolve().parents if (parent / 'scripts').is_dir()), None)
if ROOT is None:
    raise RuntimeError('cannot locate repository scripts directory')
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_source_package_builder_v1 as builder
from scripts.season_historical_roster_audit_v1 import club_group, source_group
from scripts.reconcile_opening_date_identities_v1 import _normalise
from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.fdi_indexed import IndexedFDIFile

SCHEMA = 'pm99-source-bound-full-roster-club-identity-witness-v2'
ARTIFACT_PREFIX = 'opening-squad-preallocation-'

def _source_rows(preallocation, selector):
    wanted = json.dumps(selector, sort_keys=True, separators=(',', ':'))
    matches = [source for source in preallocation['source_clubs']
        if json.dumps(source['selector'], sort_keys=True, separators=(',', ':')) == wanted]
    if len(matches) != 1:
        raise ValueError(f'exact source selector has {len(matches)} matches in bound preallocation')
    return matches[0]

def _matches(player, row):
    facts = row.get('facts', {})
    names = {_normalise(player.get('name', '')), _normalise(player.get('source_name', ''))}
    if _normalise(facts.get('name', '')) not in names:
        return False
    dob = facts.get('birth_date')
    return not dob or player.get('facts', {}).get('birth_date') == dob

def _provider_id(selector):
    try:
        return int(PurePosixPath(selector['source_path']).stem)
    except (KeyError, TypeError, ValueError):
        raise ValueError('source selector has no literal provider ID in source_path')

def _native_owner_index(eq_bytes):
    indexed = IndexedFDIFile.from_bytes(eq_bytes)
    owners = {}
    for entry in indexed.entries:
        try:
            roster = parse_eq_external_team_roster_payload(
                eq_bytes[entry.payload_offset:entry.payload_offset + entry.payload_length], {})
        except Exception:
            roster = None
        if roster is None:
            continue
        for row in roster.rows:
            owners.setdefault(row.player_record_id, []).append(
                {'team_carrier_id': int(entry.record_id), 'flag': row.flag})
    return indexed, owners

def _bind_cohort(package, club, source, *, require_all, expected_artifact_id, owners):
    players = [p for p in package['players'] if p.get('club_id') == club['id']]
    if not players:
        raise ValueError('package carrier has no roster rows')
    bindings, used = [], set()
    native_ids = set()
    for player in players:
        matches = [r for r in source['players'] if _matches(player, r)]
        if len(matches) > 1 or (require_all and len(matches) != 1):
            raise ValueError(f"actor {player.get('person_id')} has {len(matches)} exact source-row matches")
        if not matches:
            continue
        row = matches[0]
        source_person_id = builder._source_person_id(row)
        source_selector_person_id = builder._source_person_id(row, source_selector=source['selector'])
        if player.get('person_id') != source_person_id:
            raise ValueError(f"actor {player.get('person_id')} differs from exact source identity {source_person_id}")
        if player.get('proof', {}).get('artifact_id') != expected_artifact_id:
            raise ValueError(f"actor {player.get('person_id')} is not tied to the current preallocation artifact")
        native_id = int(player['carrier_id'])
        if native_id in native_ids:
            raise ValueError('two source actors resolve to one native player carrier')
        native_ids.add(native_id)
        active = [owner for owner in owners.get(native_id, []) if owner['flag'] == 0]
        if active != [{'team_carrier_id': int(club['carrier_id']), 'flag': 0}]:
            raise ValueError(f'actor {player.get("person_id")} lacks one active native EQ owner at cited carrier')
        row_hash = row.get('source_row_sha256')
        if not row_hash or row_hash in used:
            raise ValueError('source row hash missing or reused by multiple actors')
        used.add(row_hash)
        bindings.append({'person_id': player['person_id'], 'source_row_index': row['source_row_index'],
            'source_row_sha256': row_hash, 'source_full_name': row['facts']['name'],
            'source_person_id': source_person_id,
            'source_selector_person_id': source_selector_person_id,
            'native_player_carrier_id': native_id,
            'native_active_owner_carrier_id': int(club['carrier_id']),
            'source_birth_date': row['facts'].get('birth_date'), 'package_full_name': player['name'],
            'package_source_name': player.get('source_name'), 'package_birth_date': player.get('facts', {}).get('birth_date')})
    if require_all and len(bindings) != len(players):
        raise ValueError('not every current roster actor is bound to the same source cohort')
    if require_all and native_ids != {int(str(pid).rsplit('-', 1)[-1]) for pid in club.get('roster_player_ids', [])}:
        raise ValueError('package team roster IDs differ from source-bound actor native IDs')
    if not require_all and not bindings:
        raise ValueError('prior-label selector has no positive identity anchor at cited carrier')
    bindings.sort(key=lambda r: r['person_id'])
    return bindings

def _assert_unique_source_cohort(preallocation, source, target_players, target_group):
    competitors = []
    for candidate in preallocation['source_clubs']:
        if candidate is source:
            continue
        if source_group(candidate.get('selector', {}).get('country_catalog', '')) != target_group:
            continue
        if all(sum(1 for row in candidate['players'] if _matches(player, row)) == 1
               for player in target_players):
            competitors.append(candidate['selector'])
    if competitors:
        raise ValueError('another complete source-cohort candidate also matches target roster actors')
    return []

def create_witness(*, season, source_root, carrier_id, expected_source_selector,
                   prior_label_source_selector, collision_carrier_id,
                   source_release_id=None):
    """Create a witness only when every current roster row joins exactly."""
    release = (registry.load_registered_release(season, source_release_id)
        if source_release_id is not None else registry.load_preferred_release(season))
    package = json.loads(release.package_path.read_bytes())
    artifact_id = ARTIFACT_PREFIX + season
    descriptor = next((a for a in package.get('artifacts', []) if a.get('id') == artifact_id), None)
    if not descriptor:
        raise ValueError('current package has no bound preallocation artifact')
    pre_path = Path(source_root) / season / 'opening-squad-preallocation.json'
    pre_bytes = pre_path.read_bytes()
    pre_sha = registry.sha256_file(pre_path)
    if pre_sha != descriptor.get('sha256'):
        raise ValueError('preallocation bytes do not match current package descriptor')
    pre = json.loads(pre_bytes)
    source = _source_rows(pre, expected_source_selector)
    prior_source = _source_rows(pre, prior_label_source_selector)
    if not source['players']:
        raise ValueError('source cohort is empty')
    by_carrier = {c['carrier_id']: c for c in package['clubs']}
    club, collision = by_carrier.get(carrier_id), by_carrier.get(collision_carrier_id)
    if club is None or collision is None or collision_carrier_id == carrier_id:
        raise ValueError('target and distinct old-label carrier must exist')
    if club_group(club) != club_group(collision):
        raise ValueError('old-label comparison crosses country groups')
    if source_group(expected_source_selector.get('country_catalog', '')) != club_group(club):
        raise ValueError('target source country does not match target native carrier country')
    if source_group(prior_label_source_selector.get('country_catalog', '')) != club_group(collision):
        raise ValueError('prior-label source country does not match prior native carrier country')
    target_provider_id = _provider_id(expected_source_selector)
    prior_provider_id = _provider_id(prior_label_source_selector)
    if target_provider_id == prior_provider_id:
        raise ValueError('target and prior-label source selectors share one provider club ID')
    if _normalise(club['name']) == _normalise(expected_source_selector['club_name']):
        raise ValueError('target label already matches; no correction needed')
    if _normalise(collision['name']) != _normalise(prior_label_source_selector['club_name']):
        raise ValueError('cited prior-label carrier does not display its bound source selector')
    eq_path = release.game_path / 'DBDAT/EQ98030.FDI'
    eq_bytes = eq_path.read_bytes()
    _eq_index, owners = _native_owner_index(eq_bytes)
    target_bindings = _bind_cohort(package, club, source, require_all=True,
        expected_artifact_id=artifact_id, owners=owners)
    prior_bindings = _bind_cohort(package, collision, prior_source, require_all=False,
        expected_artifact_id=artifact_id, owners=owners)
    # A second source selector that also binds the entire roster by exact
    # names/DOBs makes the source-club allocation ambiguous; refuse it.
    target_players = [p for p in package['players'] if p.get('club_id') == club['id']]
    _assert_unique_source_cohort(pre, source, target_players, club_group(club))
    return {'schema_version': SCHEMA, 'season': season, 'release_id': release.release_id,
        'package_path': registry.relative_workspace_path(release.package_path),
        'package_sha256': registry.sha256_file(release.package_path),
        'eq_path': registry.relative_workspace_path(eq_path), 'eq_sha256': registry.sha256_file(eq_path),
        'native_owner_readback': 'decoded EQ roster rows; each target actor has one active flag-zero owner at cited carrier',
        'preallocation_artifact_id': artifact_id,
        'preallocation_path': registry.relative_workspace_path(pre_path), 'preallocation_sha256': pre_sha,
        'target': {'club_id': club['id'], 'carrier_id': carrier_id, 'before': club['name'],
            'after': expected_source_selector['club_name'], 'country_group': club_group(club)},
        'distinct_old_label_carrier': {'club_id': collision['id'], 'carrier_id': collision_carrier_id,
            'label': collision['name'], 'source_selector': prior_label_source_selector},
        'source_selector': expected_source_selector,
        'target_provider_club_id': target_provider_id,
        'prior_provider_club_id': prior_provider_id,
        'source_fixture_date': source.get('opening_fixture_date'),
        'source_match_id': source.get('opening_source_match_id'),
        'source_roster_rows_total': len(source['players']),
        'target_source_rows_bound': len(target_bindings), 'current_cohort_count': len(target_bindings),
        'roster_bindings': target_bindings,
        'prior_source_roster_rows_total': len(prior_source['players']),
        'prior_source_rows_bound': len(prior_bindings),
        'prior_current_cohort_count': len(prior_bindings), 'prior_roster_bindings': prior_bindings,
        'identity_basis': 'complete_source_bound_roster_cohort',
        'opening_xi_certified': False, 'manager_admission_separate': True,
        'automatic_change_authorized': False}

def verify_witness(witness, *, source_root):
    if witness.get('schema_version') != SCHEMA:
        raise ValueError('wrong witness schema')
    fresh = create_witness(season=witness['season'], source_root=source_root,
        carrier_id=witness['target']['carrier_id'], expected_source_selector=witness['source_selector'],
        prior_label_source_selector=witness['distinct_old_label_carrier']['source_selector'],
        collision_carrier_id=witness['distinct_old_label_carrier']['carrier_id'],
        source_release_id=witness['release_id'])
    if witness != fresh:
        raise ValueError('witness is stale or modified')
    return fresh

def proposed_review_row(witness, *, manager_after, manager_carrier_id, manager_owner_count,
                        native_manager_before, manager_source_evidence):
    if not manager_after or manager_owner_count != 1:
        raise ValueError('separate uniquely-owned source-bound manager is required')
    if witness.get('opening_xi_certified') is not False:
        raise ValueError('full-cohort path cannot certify an opening XI')
    if not native_manager_before or not manager_source_evidence:
        raise ValueError('dated manager evidence and native before-name are required')
    for source in manager_source_evidence:
        if not all(source.get(key) for key in ('path', 'sha256', 'source_date', 'url')):
            raise ValueError('manager source evidence lacks dated URL/path/hash')
        path = Path(source['path'])
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file() or registry.sha256_file(path) != source['sha256']:
            raise ValueError('manager source bytes are absent or changed')
    evidence = {'date': witness.get('source_fixture_date'), 'manager': manager_after,
        'identity_basis': witness['identity_basis'], 'source_match_id': witness.get('source_match_id'),
        'full_cohort_witness': witness, 'manager_source_evidence': manager_source_evidence,
        'raw_sources': [{'path': source['path'], 'sha256': source['sha256']}
            for source in manager_source_evidence]}
    return {'status': 'source-supported-full-cohort-club-label-mismatch',
        'before': witness['target']['before'], 'after': witness['target']['after'],
        'identity_basis': witness['identity_basis'], 'full_cohort_witness': witness,
        'evidence': evidence, 'native_manager': native_manager_before,
        'native_manager_owner_count': manager_owner_count,
        'native_manager_carrier_id': manager_carrier_id,
        'historical_verification_complete': False, 'automatic_change_authorized': False,
        'manager_after': manager_after, 'native_manager_carrier_id': manager_carrier_id,
        'native_manager_owner_count': manager_owner_count}


def verify_manager_sources(row):
    """Check retained named coach/club source context; never certify an XI."""
    from bs4 import BeautifulSoup
    evidence = row.get('evidence', {})
    name = row.get('manager_after')
    club = row.get('after')
    sources = evidence.get('manager_source_evidence')
    if not name or not club or evidence.get('manager') != name or not isinstance(sources, list) or not sources:
        raise ValueError('full-cohort label change requires separate named manager evidence')
    for source in sources:
        if not all(source.get(k) for k in ('path', 'sha256', 'source_date', 'url')):
            raise ValueError('manager source lacks dated URL/path/hash')
        path = Path(source['path'])
        path = path if path.is_absolute() else ROOT / path
        if registry.sha256_file(path) != source['sha256']:
            raise ValueError('manager source bytes changed')
        page = BeautifulSoup(path.read_bytes(), 'lxml')
        for node in page(['script', 'style']):
            node.decompose()
        text = _normalise(page.get_text(' ', strip=True))
        if _normalise(name) not in text or _normalise(club) not in text:
            raise ValueError('manager source does not contain the named coach and target club')
    return True
