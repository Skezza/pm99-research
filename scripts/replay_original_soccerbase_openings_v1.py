#!/usr/bin/env python3
"""Reuse existing immutable Soccerbase originals; no network or native writes.

Full original biographies bridge separate provider IDs only through a unique
full-name/DOB identity. Source schedules, fragments and profiles are rehashed
against their original URL receipts. Current positions and clubs are ignored.
This review does not silently promote a schedule date to a match-page date.
"""
import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_soccerbase_original_opening_v1 as original
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_pipeline_v2 as pipeline
from scripts import season_public_identity_and_history_inputs_v1 as public
from scripts import season_published_person_identity_v1 as identities

POLICY = 'replayed-original-Soccerbase-full-name-DOB-provider-bridge-source-only-v1'


def read_original(cache, kind, id, proofs):
    path = cache / kind / (str(id)+'.html')
    receipt = path.with_name(path.name+'.source.json')
    raw = path.read_bytes()
    metadata = json.loads(receipt.read_text())
    digest = hashlib.sha256(raw).hexdigest()
    if set(metadata) != {'url', 'sha256'} or metadata['sha256'] != digest:
        raise ValueError('original Soccerbase URL/SHA receipt differs')
    proof = {'path': registry.relative_workspace_path(path), 'sha256': digest,
             'source_receipt_path': registry.relative_workspace_path(receipt),
             'source_receipt_sha256': registry.sha256_file(receipt), 'url': metadata['url']}
    proofs.append(proof)
    return raw, metadata['url']


def bridge(person, people):
    probe = {'name': person['name'], 'facts': {'birth_date': person['birth_date']}}
    result = transfer.unique_person(probe, people)
    if result is not None and type(result['source_player_id']) is not int:
        # A Soccerbase-native identity is not a Transfermarkt bridge. Keep
        # provider namespaces separate even when a later repair index knows
        # this person from their original Soccerbase biography.
        result = None
    return {'soccerbase_person': person, 'transfermarkt_person': result,
            'identity_basis': 'unique-original-full-name-and-exact-DOB' if result else None,
            'ownership_established_by_identity_bridge': False}


def replay_club(season, capture, people, allow_declared_unknown_details=False, *,
                allow_missing_birth_date=False):
    team_path = capture.get('source_path', '')
    import re
    identity = re.fullmatch(r'soccerbase/team/(\d+)/august', team_path)
    if identity is None:
        raise ValueError('capture does not identify one namespaced original Soccerbase team')
    team = int(identity.group(1))
    cache = ROOT / '.local' / ('season-'+season) / 'soccerbase-august-cache-v1'
    proofs = []
    raw, url = read_original(cache, 'team', team, proofs)
    fixture = original.first_fixture(raw, team, season, capture['competition_name'], capture['club_name'], url)
    raw, url = read_original(cache, 'match', fixture['game_id'], proofs)
    sheet = original.match(raw, fixture, team, url, allow_declared_unknown_details)
    bridged = {'starting_xi': [], 'published_bench': []}; gaps = []
    for field in bridged:
        for player in sheet[field]:
            try:
                raw, url = read_original(cache, 'player', player['provider_player_id'], proofs)
                person = original.profile(raw, player, url, allow_missing_birth_date=allow_missing_birth_date)
                result = bridge(person, people)
                result['dated_match_position'] = player['position']
                result['published_match_name'] = player['published_match_name']
                bridged[field].append(result)
                if result['transfermarkt_person'] is None:
                    gaps.append({'source_player_id': player['source_player_id'],
                                 'reason': 'no-unique-independent-full-name-DOB-provider-bridge'})
            except (ValueError, OSError) as exc:
                gaps.append({'source_player_id': player['source_player_id'], 'reason': str(exc)})
    return {'club': capture['club_name'], 'status': 'original-first-fixture-reparsed',
        'source_capture': {k: capture[k] for k in ('source_path', 'source_sha256', 'country_catalog',
                                                 'competition_catalog', 'competition_name')},
        'fixture': fixture, 'original_match': sheet, 'identity_bridges': bridged,
        'identity_gaps': gaps, 'raw_sources': proofs,
        'approved_for_native_ownership_repair': False}


def review(season, people):
    source = ROOT / '.local' / ('season-'+season) / 'soccerbase-august-english-nonleague-v1.json'
    if not source.is_file():
        return {'season': season, 'clubs': [], 'source_gap': 'original-Soccerbase-capture-not-present'}
    captured = json.loads(source.read_text())
    if captured.get('season', {}).get('label') != season[:4]+'/'+season[-2:]:
        raise ValueError('original Soccerbase capture belongs to another season')
    release = registry.load_preferred_release(season)
    clubs = [c for _, package, _ in planner.package_layers(release) for c in package['clubs']]
    rows = []
    for capture in captured['clubs']:
        names = roster.club_names('england', capture['club_name'])
        matching = [c for c in clubs if roster.club_group(c)=='england'
                    and names & roster.club_names('england', c['name'], c.get('full_name', ''))]
        if not matching:
            continue
        try:
            row = replay_club(season, capture, people)
        except (ValueError, OSError) as exc:
            row = {'club': capture['club_name'], 'status': 'original-source-gap', 'reason': str(exc)}
        row['represented_native_clubs'] = [{'club_id':c['id'], 'carrier_id':c['carrier_id'],
            'club':c['name']} for c in matching]
        rows.append(row)
    return {'season': season, 'capture_input': {'path':registry.relative_workspace_path(source),
        'sha256': registry.sha256_file(source)}, 'release_id':release.release_id, 'clubs':rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--snapshot-receipt', type=Path, required=True)
    parser.add_argument('--published-people', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seasons', nargs='+', default=[f'{y}-{str(y+1)[-2:]}' for y in range(2000,2026)])
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('source review is immutable; choose a new output')
    people, _, _, pin = transfer.load_snapshot(args.snapshot, args.snapshot_receipt)
    binding = public.binding(args.published_people, identities.POLICY)
    people, _, _ = public.merge_bound(people, {}, {'published_person_supplement':binding})
    seasons = []; counts = collections.Counter()
    for season in args.seasons:
        result = review(season, people); seasons.append(result)
        for row in result['clubs']:
            counts[row['status']] += 1
            if row['status']=='original-first-fixture-reparsed':
                counts['published-XI-people'] += len(row['original_match']['starting_xi'])
                counts['independently-identified-XI-people'] += len(row['identity_bridges']['starting_xi'])
                for values in row['identity_bridges'].values():
                    counts['unique-provider-identity-bridges'] += sum(v['transfermarkt_person'] is not None for v in values)
                counts['identity-gaps'] += len(row['identity_gaps'])
        print(json.dumps({'season':season,'reviewed_native_club_sources':len(result['clubs']),
                          'cumulative':dict(counts)}),flush=True)
    document = {'policy':POLICY, 'snapshot_binding':pin, 'published_person_binding':binding,
        'seasons':seasons, 'summary':dict(counts), 'native_games_modified':0,
        'approved_for_native_ownership_repair':False}
    pipeline.write_canonical_json(args.output, document)


if __name__=='__main__':
    main()
