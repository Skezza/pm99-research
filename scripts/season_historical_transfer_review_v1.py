#!/usr/bin/env python3
"""Independently audit player identity/ownership using a pinned local snapshot.

Never uses current_club_id, present-day citizenship, height or position as
historical facts. Only stable full names/DOB join people; dated appearances,
matchday IDs and transfer events support historical membership. A missing
transfer is not proof a move did not occur. No recipe/game writes occur here.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_historical_roster_audit_v1 as roster
from scripts.reconcile_opening_date_identities_v1 import _normalise

SCHEMA = 'pm99-independent-historical-transfer-review-v1'


def verify_opening_sources(opening):
    """Rehash each original blob once, even if both fixture clubs reference it."""
    checked = {}
    for row in (opening or {}).get('clubs', []):
        if row['status'] != 'original-first-fixture-reparsed': continue
        for source in row['evidence']['raw_sources']:
            path = ROOT / source['path']
            if path not in checked: checked[path] = registry.sha256_file(path)
            if checked[path] != source['sha256']:
                raise ValueError('original opening source bytes changed')


def reuse_completed(season, binding, opening_path, destination):
    if not destination.exists(): return None
    previous = json.loads(destination.read_text())
    release = registry.load_preferred_release(season)
    opening_sha = registry.sha256_file(opening_path) if opening_path.exists() else None
    expected = (release.release_id, registry.sha256_file(release.package_path), binding, opening_sha)
    actual = previous['bindings']
    if (previous['schema_version'] != SCHEMA or previous['season'] != season or
            (actual['release_id'], actual['package_sha256'], actual['snapshot'], actual['opening_review_sha256']) != expected):
        raise ValueError('completed transfer review inputs changed; use a new output root')
    verify_opening_sources(json.loads(opening_path.read_text()) if opening_path.exists() else None)
    return previous['summary']


def person_index(rows):
    index = collections.defaultdict(dict)
    for row in rows:
        id, name, given, family, dob, url = row
        if dob is None: continue
        date = dob.date().isoformat() if isinstance(dob, dt.datetime) else dob.isoformat()
        names = {name, ' '.join(part for part in (given, family) if part)} - {None, ''}
        for variant in names:
            index[(_normalise(variant), date)][int(id)] = {'source_player_id': int(id), 'name': name,
                'given_name': given, 'family_name': family, 'birth_date': date, 'source_profile_url': url}
    return index


def unique_person(player, index):
    date = player['facts'].get('birth_date')
    if not isinstance(date, str): return None
    matches = {}
    for name in (player['name'], player.get('source_name')):
        if not name:
            continue
        matches.update(index.get((_normalise(name), date), {}))
        # Some published squad/profile headings include a shirt label. Keep
        # the captured heading intact; only remove this explicit decoration
        # when joining a complete name AND exact DOB to the pinned source.
        # Never expand initials, drop arbitrary digits or choose a homonym.
        labelled = re.fullmatch(r'#\d{1,2}\s+(.+)', name.strip())
        if labelled:
            matches.update(index.get((_normalise(labelled.group(1)), date), {}))
    return next(iter(matches.values())) if len(matches) == 1 else None


def transfer_interval(events, fixture_date):
    """Require a consistent bracketing entry AND departure, not entry alone."""
    if fixture_date is None: return {'status': 'no-dated-opening-snapshot'}
    dates = [e['date'] for e in events]
    end = bisect.bisect_right(dates, fixture_date)
    if end == 0: return {'status': 'no-recorded-entry-before-fixture'}
    before = events[end - 1]
    after = events[end] if end < len(events) else None
    # Same-day returns/permanent moves cannot be ordered by club ID or row order.
    if dates.count(before['date']) > 1 or (after and dates.count(after['date']) > 1):
        return {'status': 'same-day-transfer-order-unresolved', 'entry': before, 'departure': after}
    if before['date'] == fixture_date:
        return {'status': 'transfer-on-fixture-date-time-unresolved', 'entry': before, 'departure': after}
    if after is None:
        return {'status': 'entry-only-unverified-continuity', 'entry': before}
    if before['to_club_id'] != after['from_club_id']:
        return {'status': 'recorded-transfer-chain-disagrees', 'entry': before, 'departure': after}
    return {'status': 'recorded-entry-and-exit-bracket-fixture', 'source_owner_club_id': before['to_club_id'],
            'source_owner_club': before['to_club'], 'entry': before, 'departure': after,
            'limit': 'Recorded transfer continuity, not proof that the source contains every loan or move'}


def load_snapshot(database, receipt_path):
    receipt = json.loads(receipt_path.read_text())
    expected = receipt['source']['database_sha256']
    if registry.sha256_file(database) != expected:
        raise ValueError('historical snapshot differs from the already pinned source')
    import duckdb  # optional source-reading dependency, not a game dependency
    connection = duckdb.connect(str(database), read_only=True)
    connection.execute("SET memory_limit='256MB'"); connection.execute('SET threads=2')
    try:
        version = connection.execute('SELECT * FROM version').fetchall()
        if version != [(receipt['source']['database_version'],)]: raise ValueError('historical snapshot version changed')
        people = person_index(connection.execute('SELECT player_id,name,first_name,last_name,date_of_birth,url FROM players').fetchall())
        transfers = collections.defaultdict(list)
        for id, date, from_id, to_id, from_name, to_name in connection.execute(
                'SELECT player_id,transfer_date,from_club_id,to_club_id,from_club_name,to_club_name FROM transfers ORDER BY player_id,transfer_date').fetchall():
            if date and from_id is not None and to_id is not None:
                transfers[int(id)].append({'date': date.isoformat(), 'from_club_id': int(from_id),
                    'to_club_id': int(to_id), 'from_club': from_name, 'to_club': to_name})
        appearances = collections.defaultdict(set)
        for season, club, player in connection.execute(
                'SELECT DISTINCT g.season,a.player_club_id,a.player_id FROM appearances a JOIN games g ON g.game_id=a.game_id WHERE g.competition_type=\'domestic_league\'').fetchall():
            if season and club and player: appearances[(str(season), int(club))].add(int(player))
    finally:
        connection.close()
    return people, transfers, appearances, {'path': registry.relative_workspace_path(database), 'sha256': expected,
        'version': receipt['source']['database_version'], 'project_url': receipt['source']['dataset_project_url'],
        'pinned_receipt_path': registry.relative_workspace_path(receipt_path), 'pinned_receipt_sha256': registry.sha256_file(receipt_path)}


def review(season, index, transfers, appearances, binding, opening_path, output):
    release = registry.load_preferred_release(season)
    package = json.loads(release.package_path.read_text())
    clubs, players, legacy = roster.add_legacy_english(package, season)
    by_club = {c['id']: c for c in clubs}
    opening = json.loads(opening_path.read_text()) if opening_path.exists() else None
    verify_opening_sources(opening)
    verified = {c['club_id']: c['evidence'] for c in (opening or {}).get('clubs', []) if c['status'] == 'original-first-fixture-reparsed'}
    rows = []; counts = collections.Counter()
    for player in players:
        club = by_club[player['club_id']]; source = verified.get(club['id'])
        # The manager-only revision may change package hash, but a club source
        # identity cannot be reused after a name/carrier/roster alteration.
        if source:
            original = next(c for c in opening['clubs'] if c['club_id'] == club['id'])
            if (original['club'], original['carrier_id']) != (club['name'], club['carrier_id']):
                raise ValueError('dated source club identity changed')
        person = unique_person(player, index)
        row = {'player_id': player['id'], 'carrier_id': player['carrier_id'], 'name': player['name'],
               'birth_date': player['facts'].get('birth_date'), 'club_id': club['id'], 'club': club['name'],
               'source_person': person, 'source_club_id': source['source_club_id'] if source else None,
               'opening_fixture_date': source['date'] if source else club.get('opening', {}).get('fixture_date'),
               'dated_domestic_appearance_at_club': False, 'opening_matchday_full_name_hit': False,
               'automatic_change_authorised': False, 'historical_verification_complete': False}
        if person:
            id = person['source_player_id']
            row['dated_domestic_appearance_at_club'] = bool(source and id in appearances.get((season[:4], source['source_club_id']), set()))
            if source:
                row['opening_matchday_full_name_hit'] = any(_normalise(n) in {
                    _normalise(person['name']), _normalise(' '.join(p for p in (person['given_name'], person['family_name']) if p))}
                    for field in ('starting_xi', 'substitutes') for n in source[field].values())
            interval = transfer_interval(transfers.get(id, []), row['opening_fixture_date'])
            row['recorded_transfer_interval'] = interval
            if interval['status'] == 'recorded-entry-and-exit-bracket-fixture' and source:
                row['transfer_owner_comparison'] = 'match' if interval['source_owner_club_id'] == source['source_club_id'] else 'conflict'
                counts['opening-transfer-owner:' + row['transfer_owner_comparison']] += 1
            counts['transfer:' + interval['status']] += 1
        counts['identity:exact-full-name-and-DOB' if person else 'identity:unmatched-or-ambiguous'] += 1
        if row['dated_domestic_appearance_at_club']: counts['dated-domestic-club-appearance-matches'] += 1
        if row['opening_matchday_full_name_hit']: counts['positive-dated-opening-full-name-matches'] += 1
        rows.append(row)
    groups = collections.defaultdict(list)
    for row in rows:
        if row['source_person']: groups[row['source_person']['source_player_id']].append(row)
    duplicates = [{'source_player_id': id, 'source_name': candidates[0]['source_person']['name'],
                   'candidates': candidates, 'automatic_change_authorised': False,
                   'remaining': 'One snapshot owner, plus a sourced replacement for each displaced slot, is required'}
                  for id, candidates in sorted(groups.items()) if len({r['carrier_id'] for r in candidates}) > 1]
    summary = {'season': season, 'players': len(rows), 'independently_matched_duplicate_people': len(duplicates), **dict(counts)}
    document = {'schema_version': SCHEMA, 'season': season, 'historical_verification_complete': False,
        'bindings': {'release_id': release.release_id, 'package_sha256': registry.sha256_file(release.package_path),
                     'snapshot': binding, 'opening_review_path': registry.relative_workspace_path(opening_path) if opening else None,
                     'opening_review_sha256': registry.sha256_file(opening_path) if opening else None, 'legacy': legacy},
        'limits': ['No current club, nationality, height or position used as historical evidence.',
                   'A season appearance does not establish August ownership.',
                   'Incomplete transfer histories are not complete ownership certificates.',
                   'Two clubs can have different first-fixture dates; global snapshot timing is still a separate check.',
                   'Future-dated transfer rows never establish ownership before their date.'],
        'summary': summary, 'players': rows, 'duplicate_people': duplicates}
    destination = output / season / 'transfer-review.json'; destination.parent.mkdir(parents=True, exist_ok=True)
    pipeline.write_canonical_json(destination, document)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season'); parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--pinned-receipt', type=Path, required=True)
    parser.add_argument('--opening-root', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true', help='Reuse only exactly input-bound completed reports')
    args = parser.parse_args()
    people, transfers, appearances, binding = load_snapshot(args.database, args.pinned_receipt)
    summaries = []
    for season in registry.supported_seasons() if args.season == 'all' else [args.season]:
        opening_path = args.opening_root / season / 'opening-review.json'
        destination = args.output / season / 'transfer-review.json'
        summary = reuse_completed(season, binding, opening_path, destination) if args.resume else None
        if summary is None:
            if destination.exists(): raise ValueError('transfer review already exists; use --resume or a new output root')
            summary = review(season, people, transfers, appearances, binding, opening_path, args.output)
        summaries.append(summary); print(json.dumps(summary), flush=True)
    summary_path = args.output / ('summary-all.json' if args.season == 'all' else 'summary.json')
    summary = {'seasons': summaries, 'historical_verification_complete': False}
    if summary_path.exists():
        if json.loads(summary_path.read_text()) != summary: raise ValueError('completed transfer summary changed')
    else: pipeline.write_canonical_json(summary_path, summary)


if __name__ == '__main__':
    main()
