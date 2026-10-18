#!/usr/bin/env python3
"""Recover historical club labels from the recipe's own hash-bound source rows.

Never select a new carrier, move a player, scrape or infer by a majority vote.
An authored cohort must unanimously resolve one original source-club selector,
contain its complete sourced opening XI, and pass original fixture rechecking.
This report does not rename installed games or approve an entire squad.
"""
import argparse
import collections
import concurrent.futures
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_source_package_builder_v1 as builder
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_opening_review_v1 as opening
from scripts.capture_ntf_historical_carrier_squads_v1 import CALENDAR_YEAR_COUNTRIES
from scripts.reconcile_opening_date_identities_v1 import _normalise
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph

SCHEMA = 'pm99-independent-historical-club-label-review-v1'


def selector_key(selector):
    return tuple(selector.get(k) for k in ('country_catalog', 'competition_catalog', 'club_name', 'source_path', 'source_sha256'))


def indexed_claims(preallocation):
    index = collections.defaultdict(list); sources = {}
    for source in preallocation['source_clubs']:
        key = selector_key(source['selector']); sources[key] = source
        for row in source['players']:
            for id in {builder._source_person_id(row), builder._source_person_id(row, source_selector=source['selector'])}:
                index[id].append((key, row))
    return index, sources


def unanimous_claim(club, players, artifact_id, index, sources):
    common = None; authored = []
    group = roster.club_group(club)
    for player in players:
        if player.get('proof', {}).get('artifact_id') != artifact_id: continue
        matches = []
        for key, row in index.get(player.get('person_id'), []):
            facts = row['facts']
            if roster.source_group(key[0]) != group: continue
            if _normalise(facts['name']) not in {_normalise(player['name']), _normalise(player.get('source_name'))}: continue
            if facts.get('birth_date') and player['facts'].get('birth_date') != facts['birth_date']: continue
            matches.append(key)
        if not matches: return None, 'authored player no longer binds one original source row'
        keys = set(matches); common = keys if common is None else common & keys
        authored.append(player)
    if not common or len(common) != 1: return None, 'authored cohort has absent or mixed original source clubs'
    key = next(iter(common)); source = sources[key]
    if source.get('opening_xi_complete') is not True: return None, 'original source lacks a complete opening XI'
    actual = {p.get('person_id') for p in authored}
    xi = [row for row in source['players'] if isinstance(row.get('opening_xi_order'), int)]
    if len(xi) != 11 or any(not ({builder._source_person_id(row), builder._source_person_id(row, source_selector=source['selector'])} & actual) for row in xi):
        return None, 'current club does not retain all eleven original authored starters'
    return source, None


def review(season, source_root, opening_root, reused_root, output, *, source_release_id=None, carrier_ids=None):
    release = (registry.load_registered_release(season, source_release_id)
        if source_release_id is not None else registry.load_preferred_release(season))
    package = json.loads(release.package_path.read_text())
    selected = set(carrier_ids) if carrier_ids is not None else None
    if selected is not None and (not selected or selected - {c['carrier_id'] for c in package['clubs']}):
        raise ValueError('label review requires nonempty existing selected carriers')
    artifact_id = 'opening-squad-preallocation-' + season
    descriptor = next((a for a in package['artifacts'] if a['id'] == artifact_id), None)
    preallocation_path = source_root / season / 'opening-squad-preallocation.json'
    if descriptor is None or not preallocation_path.exists():
        result = {'schema_version': SCHEMA, 'season': season, 'summary': {'supported_label_mismatches': 0, 'source_unavailable': True},
            'historical_verification_complete': False, 'clubs': [], 'bindings': {'release_id': release.release_id,
                'package_sha256': registry.sha256_file(release.package_path)}}
    else:
        if registry.sha256_file(preallocation_path) != descriptor['sha256']:
            raise ValueError('club source-row recovery does not bind the current recipe artifact')
        preallocation = json.loads(preallocation_path.read_text())
        capture_path = opening_root / season / 'opening-lineups.json'
        if registry.sha256_file(capture_path) != preallocation['sources']['opening_lineup_sha256']:
            raise ValueError('original fixture capture differs from authored preallocation')
        capture = json.loads(capture_path.read_text()); index, sources = indexed_claims(preallocation)
        # The capture's selector omits the CSV path/hash. Compare those via
        # the separately bound preallocation, and compare fixture selectors
        # by the exact declared country, competition and historical name.
        captured = collections.defaultdict(list)
        for row in capture['clubs']:
            captured[selector_key(row['source_selector'])[:3]].append(row)
        reused_path = reused_root / season / 'opening-review.json'
        previous = json.loads(reused_path.read_text()) if reused_path.exists() else None
        verified = {}
        if previous and previous['bindings'].get('opening_capture_sha256') == registry.sha256_file(capture_path):
            for row in previous['clubs']:
                if row['status'] == 'original-first-fixture-reparsed':
                    proof = row['evidence']; verified[(str(proof['source_club_id']), proof['date'])] = proof
        by_club = collections.defaultdict(list)
        for p in package['players']: by_club[p['club_id']].append(p)
        holders, names = _manager_graph(eq_path=release.game_path / 'DBDAT/EQ98030.FDI', ent_path=release.game_path / 'DBDAT/ENT98030.FDI')
        native_managers = {c['carrier_id']: (id, names.get(id), len(owned)) for id, owned in holders.items() for c in owned}
        rows = []; checked = {}; counts = collections.Counter()
        for club in package['clubs']:
            if selected is not None and club['carrier_id'] not in selected: continue
            if club['id'].startswith(('english-club-', 'legacy-english-club-')): continue
            source, reason = unanimous_claim(club, by_club[club['id']], artifact_id, index, sources)
            row = {'club_id': club['id'], 'carrier_id': club['carrier_id'], 'before': club['name'],
                'status': 'source-authoring-club-unresolved', 'reason': reason, 'historical_verification_complete': False,
                'automatic_change_authorised': False}
            if source:
                target = source['selector']['club_name']; row['source_selector'] = source['selector']; row['after'] = target
                if builder._normalise_club_name(target) == builder._normalise_club_name(club['name']):
                    row['status'] = 'authored-club-label-already-matches'
                else:
                    candidates = captured.get(selector_key(source['selector'])[:3], [])
                    try:
                        if len(candidates) != 1: raise ValueError('no unique exact original fixture selector')
                        candidate = candidates[0]; native_id, native_name, owners = native_managers.get(club['carrier_id'], (None, None, 0))
                        proof = verified.get((str(candidate['source_selector'].get('transfermarkt_club_id')), candidate['first_league_fixture_date']))
                        if proof:
                            for raw in proof['raw_sources']:
                                path = ROOT / raw['path']
                                if path not in checked: checked[path] = registry.sha256_file(path)
                                if checked[path] != raw['sha256']: raise ValueError('reused original fixture bytes changed')
                        else: proof = opening.verify_opening(candidate, capture, opening_root / season / 'cache')
                        if (proof['date'], str(candidate['source_match_id'])) != (source['opening_fixture_date'], str(source['opening_source_match_id'])):
                            raise ValueError('authored XI and original first fixture differ')
                        xi_ids = {str(p['opening_source_player_id']) for p in source['players'] if isinstance(p.get('opening_xi_order'), int)}
                        if xi_ids != set(proof['starting_xi']): raise ValueError('authored starters differ from independently parsed original XI')
                        if roster.club_group(club) in CALENDAR_YEAR_COUNTRIES and proof['date'][:4] != season[:4]:
                            raise ValueError('calendar-country source is outside season start year')
                        row.update(status='source-supported-club-label-mismatch', evidence=proof,
                            native_manager_carrier_id=native_id, native_manager=native_name, native_manager_owner_count=owners,
                            manager_after=proof['manager'], raw_original_bytes_rechecked=True)
                    except (OSError, KeyError, ValueError) as exc:
                        row.update(status='club-label-first-fixture-evidence-gap', reason=str(exc))
            counts[row['status']] += 1; rows.append(row)
        result = {'schema_version': SCHEMA, 'season': season, 'historical_verification_complete': False,
            'bindings': {'release_id': release.release_id, 'package_sha256': registry.sha256_file(release.package_path),
                'eq_sha256': registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'),
                'ent_sha256': registry.sha256_file(release.game_path / 'DBDAT/ENT98030.FDI'),
                'source_row_path': registry.relative_workspace_path(preallocation_path), 'source_row_sha256': descriptor['sha256'],
                'original_capture_path': registry.relative_workspace_path(capture_path), 'original_capture_sha256': registry.sha256_file(capture_path)},
            'summary': {'clubs': len(rows), 'supported_label_mismatches': counts['source-supported-club-label-mismatch'], **dict(counts)},
            'limits': ['Restores authored source identity; does not choose a new carrier or move a player.',
                'No majority voting, current-profile club assignment or name similarity inference.',
                'Dependent manager, kit and duplicate club identities still need correction checks.'], 'clubs': rows}
    destination = output / season / 'club-label-review.json'; destination.parent.mkdir(parents=True, exist_ok=True)
    pipeline.write_canonical_json(destination, result)
    return {'season': season, **result['summary']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season'); parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--opening-root', type=Path, required=True); parser.add_argument('--reuse-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--jobs', type=int, choices=(1, 2), default=1)
    args = parser.parse_args(); summaries = []
    seasons = registry.supported_seasons() if args.season == 'all' else [args.season]
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(review, s, args.source_root, args.opening_root, args.reuse_root, args.output) for s in seasons]
        for future in concurrent.futures.as_completed(futures):
            result = future.result(); summaries.append(result); print(json.dumps(result), flush=True)
    pipeline.write_canonical_json(args.output / 'summary.json', {'seasons': sorted(summaries, key=lambda x: x['season']), 'historical_verification_complete': False})


if __name__ == '__main__': main()
