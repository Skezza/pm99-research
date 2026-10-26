#!/usr/bin/env python3
"""Plan only dated, independently reparsed, exclusively owned manager names."""
import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_SCHEMA = 'pm99-independent-snapshot-opening-review-v1'
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_package_compiler_v2 as compiler
from scripts import season_historical_opening_review_v1 as opening
from scripts.capture_ntf_historical_carrier_squads_v1 import CALENDAR_YEAR_COUNTRIES
from scripts.transfermarkt_calendar_year_policy_v1 import AUDIT_CALENDAR_COUNTRIES
from scripts.season_historical_roster_audit_v1 import club_group

CALENDAR_SOURCE_COUNTRIES = CALENDAR_YEAR_COUNTRIES | set(AUDIT_CALENDAR_COUNTRIES)


def plan(season, audit_path):
    release = registry.load_preferred_release(season)
    report = json.loads(audit_path.read_text())
    package = json.loads(release.package_path.read_text())
    binding = report['bindings']
    if report['schema_version'] not in (opening.SCHEMA, SNAPSHOT_SCHEMA) or report['season'] != season:
        raise ValueError('wrong independent opening review')
    if (binding['release_id'], binding['package_sha256'], binding['eq_sha256'], binding['ent_sha256']) != (
            release.release_id, registry.sha256_file(release.package_path),
            registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'),
            registry.sha256_file(release.game_path / 'DBDAT/ENT98030.FDI')):
        raise ValueError('manager review no longer describes current recipe/native owners')
    clubs = {c['id']: c for c in package['clubs']}
    managers = {m['id']: m for m in package['managers']}
    source_owners = collections.defaultdict(list)
    for row in report['clubs']:
        if row['status'] == 'original-first-fixture-reparsed':
            source_owners[row['evidence']['source_club_id']].append(row)
    allowed = set()
    for rows in source_owners.values():
        # An English league carrier can be distinguished from an erroneous
        # second non-league slot; two foreign slots cannot be guessed apart.
        playable = [r for r in rows if r['playable']]
        if len(rows) == 1: allowed.add(rows[0]['club_id'])
        elif len(playable) == 1: allowed.add(playable[0]['club_id'])
    updates, unresolved, seen, checked_sources = [], [], set(), {}
    for row in report['clubs']:
        if row['status'] != 'original-first-fixture-reparsed' or not row['evidence'].get('manager'):
            unresolved.append({'club_id': row['club_id'], 'club': row['club'], 'reason': row['status']})
            continue
        club = clubs.get(row['club_id']); manager = managers.get(club.get('manager_id')) if club else None
        if row['club_id'] not in allowed:
            unresolved.append({'club_id': row['club_id'], 'club': row['club'], 'reason': 'historical club represented by multiple native carriers'})
            continue
        if (club and club_group(club) in CALENDAR_SOURCE_COUNTRIES
                and row['evidence']['date'][:4] != season[:4]):
            unresolved.append({'club_id': row['club_id'], 'club': row['club'], 'reason': 'calendar-country first fixture falls outside season start year'})
            continue
        if (manager is None or manager['carrier_id'] != row['native_manager_carrier_id'] or
                row['native_manager_owner_count'] != 1 or manager['carrier_id'] in seen):
            unresolved.append({'club_id': row['club_id'], 'club': row['club'], 'reason': 'legacy, shared or mismatched native manager owner'})
            continue
        for source in row['evidence']['raw_sources']:
            path = ROOT / source['path']
            if path not in checked_sources: checked_sources[path] = registry.sha256_file(path)
            if checked_sources[path] != source['sha256']:
                raise ValueError('original dated manager source bytes changed')
        target = row['evidence']['manager']
        try:
            native_name = compiler._pm99_text(target, label='sourced manager name')
        except ValueError:
            unresolved.append({'club_id': row['club_id'], 'club': row['club'], 'reason': 'manager name cannot be represented safely'})
            continue
        seen.add(manager['carrier_id'])
        updates.append({'club_id': club['id'], 'club_carrier_id': club['carrier_id'], 'club': club['name'],
            'manager_id': manager['id'], 'carrier_id': manager['carrier_id'], 'before': manager['name'],
            'before_policy': manager.get('policy'), 'native_before': row['native_manager'], 'after': target,
            'native_after': native_name, 'first_fixture_date': row['evidence']['date'],
            'evidence': row['evidence'], 'native_manager_owner_count': 1})
    names = collections.Counter(opening._normalise(r['after']) for r in updates)
    ambiguous = [r for r in updates if names[opening._normalise(r['after'])] > 1]
    unresolved += [{'club_id': r['club_id'], 'club': r['club'], 'reason': 'same historical manager at multiple first-fixture clubs; dated ownership needs reconciliation'} for r in ambiguous]
    updates = [r for r in updates if names[opening._normalise(r['after'])] == 1]
    return {'schema_version': 'pm99-historical-manager-plan-v1', 'season': season,
            'release_id': release.release_id, 'package_sha256': binding['package_sha256'],
            'eq_sha256': binding['eq_sha256'], 'ent_sha256': binding['ent_sha256'],
            'audit_path': registry.relative_workspace_path(audit_path), 'audit_sha256': registry.sha256_file(audit_path),
            'updates': updates, 'unresolved': unresolved,
            'summary': {'source_verified_exclusive_managers': len(updates),
                        'native_name_corrections': sum(r['native_before'] != r['native_after'] for r in updates),
                        'remaining_clubs': len(unresolved)}, 'historical_verification_complete': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season'); parser.add_argument('--audit-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    for season in registry.supported_seasons() if args.season == 'all' else [args.season]:
        result = plan(season, args.audit_root / season / 'opening-review.json')
        path = args.output / season / 'manager-plan.json'; path.parent.mkdir(parents=True, exist_ok=True)
        pipeline.write_canonical_json(path, result)
        print(json.dumps({'season': season, **result['summary']}), flush=True)


if __name__ == '__main__':
    main()
