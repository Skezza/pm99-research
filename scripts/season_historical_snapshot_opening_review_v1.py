#!/usr/bin/env python3
"""Independently query dated opening matches from an already pinned snapshot.

This supplements missing raw HTML evidence, not existing successful reviews.
No present-day club, citizenship or position profile field is a historical
fact. First-match observations are not complete August squads. No game writes.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_opening_review_v1 as opening
from scripts.season_historical_manager_plan_v1 import SNAPSHOT_SCHEMA
from scripts.reconcile_opening_date_identities_v1 import _club_key, _normalise
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph
from scripts.audit_world_2015_source_coverage import strict_club_key

COUNTRIES = {'Belgium': 'belgium', 'Denmark': 'denmark', 'England': 'eng',
    'France': 'france', 'Germany': 'ger', 'Greece': 'greece', 'Italy': 'italy',
    'Netherlands': 'netherl', 'Portugal': 'portugal', 'Russia': 'russia',
    'Scotland': 'scots', 'Spain': 'spain', 'Türkiye': 'turkey', 'Ukraine': 'ukraine'}

QUERY = """
WITH sides AS (
    SELECT game_id,date,competition_id,home_club_id AS club_id,
           home_club_name AS club_name,home_club_manager_name AS manager,
           home_club_formation AS formation,url
    FROM games WHERE season=? AND competition_type='domestic_league'
    UNION ALL
    SELECT game_id,date,competition_id,away_club_id AS club_id,
           away_club_name AS club_name,away_club_manager_name AS manager,
           away_club_formation AS formation,url
    FROM games WHERE season=? AND competition_type='domestic_league'
), ordered AS (
    SELECT *,row_number() OVER (PARTITION BY club_id ORDER BY date,game_id) AS n
    FROM sides
)
SELECT o.game_id,o.date,o.club_id,o.club_name,o.manager,o.formation,o.url,
       o.competition_id,c.country_name
FROM ordered o JOIN competitions c USING(competition_id) WHERE n=1
ORDER BY o.club_id
"""


def index_rows(rows):
    result = collections.defaultdict(list)
    for game, date, club, name, manager, formation, url, competition, country in rows:
        if country not in COUNTRIES: continue
        result[(roster.source_group(COUNTRIES[country]), _club_key(strict_club_key(name)))].append({
            'source_game_id': str(game), 'date': date.date().isoformat() if hasattr(date, 'date') else date.isoformat(),
            'source_club_id': int(club), 'source_club_name': name,
            'manager': manager, 'formation': formation, 'source_url': url,
            'source_competition_id': competition, 'source_country': country})
    return result


def only_candidate(club, index):
    # Exact normalized historical name and country; no nearest/fuzzy match.
    candidates = index.get((roster.club_group(club), _club_key(strict_club_key(club.get('full_name') or club['name']))), [])
    return candidates[0] if len(candidates) == 1 else None


def query_snapshot(database, pinned_receipt, season):
    pin = json.loads(pinned_receipt.read_text())['source']
    digest = registry.sha256_file(database)
    if digest != pin['database_sha256']: raise ValueError('qualified snapshot source bytes changed')
    import duckdb
    connection = duckdb.connect(str(database), read_only=True)
    connection.execute("SET memory_limit='256MB'"); connection.execute('SET threads=2')
    try:
        if connection.execute('SELECT * FROM version').fetchall() != [(pin['database_version'],)]:
            raise ValueError('qualified snapshot version changed')
        index = index_rows(connection.execute(QUERY, [int(season[:4]), int(season[:4])]).fetchall())
        lineups = collections.defaultdict(lambda: collections.defaultdict(dict))
        rows = connection.execute("""SELECT l.game_id,l.club_id,l.player_id,l.player_name,l.type
            FROM game_lineups l JOIN games g ON g.game_id=l.game_id
            WHERE g.season=? AND g.competition_type='domestic_league'""", [int(season[:4])]).fetchall()
        for game, club, player, name, kind in rows:
            if kind in ('starting_lineup', 'substitutes') and player is not None and name:
                lineups[(str(game), int(club))][kind][str(player)] = name
    finally:
        connection.close()
    if registry.sha256_file(database) != digest: raise ValueError('snapshot changed during query')
    raw_sources = [{'path': registry.relative_workspace_path(database), 'sha256': digest,
        'url': pin['dataset_project_url'], 'version': pin['database_version']},
        {'path': registry.relative_workspace_path(pinned_receipt),
         'sha256': registry.sha256_file(pinned_receipt), 'url': pin['dataset_project_url']}]
    return index, lineups, raw_sources


def audit(season, database, pinned_receipt, destination):
    if destination.exists(): raise ValueError('completed source review exists; choose a new destination')
    release = registry.load_preferred_release(season)
    package_hash = registry.sha256_file(release.package_path)
    package = json.loads(release.package_path.read_text())
    clubs, players, legacy = roster.add_legacy_english(package, season)
    index, lineups, sources = query_snapshot(database, pinned_receipt, season)
    holders, names = _manager_graph(eq_path=release.game_path / 'DBDAT/EQ98030.FDI', ent_path=release.game_path / 'DBDAT/ENT98030.FDI')
    native = {c['carrier_id']: (id, names.get(id), len(owned)) for id, owned in holders.items() for c in owned}
    rows = []; verified = {}; counts = collections.Counter()
    for club in clubs:
        id, name, owners = native.get(club['carrier_id'], (None, None, 0))
        row = {'club_id': club['id'], 'carrier_id': club['carrier_id'], 'club': club['name'],
            'playable': club['id'].startswith(('english-club-', 'legacy-english-club-')),
            'native_manager': name, 'native_manager_carrier_id': id, 'native_manager_owner_count': owners,
            'status': 'opening-source-unavailable', 'manager_status': 'not-independently-verified',
            'full_opening_roster_verified': False}
        source = only_candidate(club, index)
        if source:
            match = lineups.get((source['source_game_id'], source['source_club_id']), {})
            evidence = {**source, 'raw_sources': sources, 'source_kind': 'independently-queried-pinned-dated-snapshot',
                'starting_xi': dict(match.get('starting_lineup', {})), 'substitutes': dict(match.get('substitutes', {})),
                'first_fixture_scope': 'earliest domestic fixture present in this pinned snapshot; source completeness remains a limit',
                'starting_xi_complete': len(match.get('starting_lineup', {})) == 11}
            row.update(status='original-first-fixture-reparsed', evidence=evidence)
            row['manager_status'] = ('match' if _normalise(source['manager']) == _normalise(name) else 'mismatch') if source['manager'] else 'source-manager-unpublished'
            verified[club['id']] = evidence
        counts[row['status']] += 1; counts['manager:' + row['manager_status']] += 1
        rows.append(row)
    if registry.sha256_file(release.package_path) != package_hash: raise ValueError('recipe changed during source review')
    summary = {'season': season, 'clubs': len(rows), **dict(counts)}
    document = {'schema_version': SNAPSHOT_SCHEMA, 'season': season,
        'historical_verification_complete': False, 'summary': summary,
        'bindings': {'release_id': release.release_id, 'package_sha256': package_hash,
            'eq_sha256': registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'),
            'ent_sha256': registry.sha256_file(release.game_path / 'DBDAT/ENT98030.FDI'), 'legacy': legacy},
        'limits': ['Dated match lists are not complete August squads.',
            'Snapshot earliest fixture is not a guarantee of complete competition coverage.',
            'No current player profile facts used to assert historical club membership.',
            'No new native-club mapping is guessed from an approximate name.'],
        'clubs': rows, 'duplicate_players': opening.duplicate_queue(players, {c['id']: c for c in clubs}, verified)}
    destination.parent.mkdir(parents=True, exist_ok=True); pipeline.write_canonical_json(destination, document)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season'); parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--pinned-receipt', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.season, args.database, args.pinned_receipt, args.output / args.season / 'opening-review.json')))


if __name__ == '__main__': main()
