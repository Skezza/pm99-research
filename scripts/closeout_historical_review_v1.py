#!/usr/bin/env python3
"""Collect current, completed worldwide audits without rebuilding or scraping.

Coverage is never approval. Historical gaps, native/recipe drift and duplicate
ownership stay visible even when an exact game revision loads successfully.
"""
import argparse
import collections
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_opening_review_v1 as opening
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph


def current_audit(document, season, package_hash):
    if document['season'] != season or document['bindings']['package_sha256'] != package_hash:
        raise ValueError('completed audit no longer describes the current recipe')


def source_collisions(rows):
    owners = collections.defaultdict(set)
    for row in rows:
        if row['status'] == 'original-first-fixture-reparsed':
            owners[row['evidence']['source_club_id']].add(row['club_id'])
    return {club for clubs in owners.values() if len(clubs) > 1 for club in clubs}


def collect(season, args):
    release = registry.load_preferred_release(season)
    package = json.loads(release.package_path.read_text()); package_hash = registry.sha256_file(release.package_path)
    base = args.review_root / season
    native_path = base / 'roster-audit.json'
    if not native_path.exists(): native_path = base / 'report.json'
    facts_path = base / 'player-facts-audit.json'
    native = json.loads(native_path.read_text()); facts = json.loads(facts_path.read_text())
    for document in (native, facts): current_audit(document, season, package_hash)
    if native['bindings']['jug_sha256'] != registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'):
        raise ValueError('completed native player audit no longer matches current game')
    if native['bindings']['eq_sha256'] != registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'):
        raise ValueError('completed native club audit no longer matches current game')
    clubs, players, _ = roster.add_legacy_english(package, season)
    duplicate_people = opening.duplicate_queue(players, {c['id']: c for c in clubs}, {})
    duplicated = collections.Counter(r['club_id'] for person in duplicate_people for r in person['candidates'])
    source_path = args.opening_root / season / 'opening-review.json'
    source = json.loads(source_path.read_text())
    current_clubs = {c['id']: c for c in clubs}
    for row in source['clubs']:
        club = current_clubs.get(row['club_id'])
        if club is None or (club['carrier_id'], club['name']) != (row['carrier_id'], row['club']):
            raise ValueError('opening source review uses superseded club labels')
    collided = source_collisions(source['clubs'])
    holders, names = _manager_graph(eq_path=release.game_path / 'DBDAT/EQ98030.FDI', ent_path=release.game_path / 'DBDAT/ENT98030.FDI')
    managers = {c['carrier_id']: (id, names.get(id), len(owned)) for id, owned in holders.items() for c in owned}
    declared = {m['id']: m for m in package['managers']}; club_index = {c['id']: c for c in clubs}
    by_club = collections.defaultdict(list)
    for player in facts['players']: by_club[player['club_id']].append(player)
    club_rows = []
    for row in native['clubs']:
        club = club_index[row['id']]; coach = declared.get(club.get('manager_id'))
        manager_id, manager_name, owners = managers.get(row['carrier_id'], (None, None, 0))
        members = by_club[row['id']]
        club_rows.append({'season': season, 'club': row['club'], 'club_id': row['id'],
            'carrier_id': row['carrier_id'], 'country': row['country_group'], 'playable': row['playable'],
            'roster_occurrences': row['recipe_roster_count'], 'native_roster_matches': row['native_roster_matches'],
            'same_club_season_identity_verified': sum(p['same_club_season_identity_match'] for p in members),
            'same_club_season_identity_unverified': sum(not p['same_club_season_identity_match'] for p in members),
            'duplicate_person_candidates': duplicated[row['id']], 'duplicated_source_club_identity': row['id'] in collided,
            'native_manager_id': manager_id, 'native_manager': manager_name, 'native_manager_owner_count': owners,
            'recipe_manager_id': coach['carrier_id'] if coach else None,
            'recipe_manager_name': coach['name'] if coach else None,
            'recipe_native_manager_link_matches': coach['carrier_id'] == manager_id if coach else None,
            'historical_verification_complete': False,
            'player_review_csv': registry.relative_workspace_path(base / 'review/players.csv')})
    qa_path = args.qa_root / season / 'qa-report.json'
    qa = json.loads(qa_path.read_text()) if qa_path.exists() else None
    qa_bound = bool(qa and qa.get('historical_revision_binding') == {
        'release_id': release.release_id, 'release_manifest_sha256': release.manifest_sha256, 'package_sha256': package_hash})
    runtime_issues = registry._validate_runtime_attestation(release)
    application = json.loads((base / 'application.json').read_text())
    result = {'season': season, 'release_id': release.release_id, 'package_sha256': package_hash,
        'clubs': len(club_rows), 'players': len(facts['players']), 'roster': native['summary'], 'player_facts': facts['summary'],
        'manager_name_corrections': application['changed_manager_names'],
        'manager_plan_verified_exclusive_records': application['source_verified_exclusive_managers'],
        'duplicate_person_candidates_ignoring_country': len(duplicate_people),
        'duplicated_source_club_slots': len(collided),
        'recipe_native_manager_link_mismatches': sum(c['recipe_native_manager_link_matches'] is False for c in club_rows),
        'exact_runtime_proved': not runtime_issues, 'runtime_issues': runtime_issues,
        'technical_qa_result': qa['result'] if qa_bound else 'not-currently-recorded',
        'technical_qa_blockers': qa['blockers'] if qa_bound else [],
        'historical_verification_complete': False,
        'bindings': [{'path': registry.relative_workspace_path(p), 'sha256': registry.sha256_file(p)}
            for p in (native_path, facts_path, source_path, base / 'application.json', base / 'review/summary.json')]}
    return result, club_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review-root', type=Path, required=True); parser.add_argument('--opening-root', type=Path, required=True)
    parser.add_argument('--qa-root', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise ValueError('completed review collection exists; choose a new output root')
    results = []; clubs = []
    for season in registry.supported_seasons():
        result, rows = collect(season, args); results.append(result); clubs.extend(rows)
        print(json.dumps({k: result[k] for k in ('season', 'exact_runtime_proved', 'duplicate_person_candidates_ignoring_country', 'recipe_native_manager_link_mismatches')}), flush=True)
    summary = {'schema_version': 'pm99-worldwide-historical-review-closeout-v1', 'seasons': results,
        'totals': {'club_seasons': len(clubs), 'playable_club_seasons': sum(c['playable'] for c in clubs),
            'non_playable_club_seasons': sum(not c['playable'] for c in clubs),
            'player_records': sum(r['players'] for r in results),
            'manager_name_corrections': sum(r['manager_name_corrections'] for r in results),
            'exact_runtime_proved_seasons': sum(r['exact_runtime_proved'] for r in results),
            'duplicate_person_candidates_ignoring_country': sum(r['duplicate_person_candidates_ignoring_country'] for r in results),
            'duplicated_source_club_slots': sum(r['duplicated_source_club_slots'] for r in results),
            'recipe_native_manager_link_mismatches': sum(r['recipe_native_manager_link_mismatches'] for r in results)},
        'historical_verification_complete': False,
        'limits': ['Native roster equality is an encoding check, not historical approval.',
            'Whole-season membership is not opening-squad ownership.',
            'Duplicate names/DOB are reconciliation candidates, not automatic deletions.',
            '2015 legacy manager links require reconciliation with its earlier native graph repair.',
            'Portrait likeness, kit design and subjective abilities are not independently approved by these roster checks.']}
    args.output.mkdir(parents=True)
    with (args.output / 'clubs.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(clubs[0])); writer.writeheader(); writer.writerows(clubs)
    pipeline.write_canonical_json(args.output / 'summary.json', summary)
    print(json.dumps(summary['totals']))


if __name__ == '__main__': main()
