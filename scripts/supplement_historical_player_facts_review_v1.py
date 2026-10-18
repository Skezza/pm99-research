#!/usr/bin/env python3
"""Add independent NTF evidence to an unchanged factual audit, without rescraping.

Every existing name, DOB, carrier, club and compared field must still match
the current declarations. Role/artwork-only revisions can therefore reuse
completed evidence. No game or recipe is changed here.
"""
import argparse
import collections
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_historical_player_facts_audit_v1 as facts
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import capture_historical_ntf_review_v1 as ntf


def refreshed_checks(player, previous, extra, nationality_amendment=None):
    if (player['name'], player['carrier_id'], player['facts'].get('birth_date'), player['club_id']) != (
            previous['name'], previous['carrier_id'], previous['birth_date'], previous['club_id']):
        raise ValueError('previous facts audit identity/club changed')
    checks = {}
    for field in facts.FIELDS:
        original = previous['fields'][field]
        declared = player['facts'].get(field)
        if declared != original['recipe_value']:
            if (field != 'nationality' or nationality_amendment is None or
                    (nationality_amendment['player_id'], nationality_amendment['carrier_id'], nationality_amendment['name'],
                     nationality_amendment['birth_date'], nationality_amendment['before'], nationality_amendment['after']) != (
                    player['id'], player['carrier_id'], player['name'], player['facts'].get('birth_date'), original['recipe_value'], declared)):
                raise ValueError('previous audited player fact changed without exact bound amendment')
        candidates = [{'facts': {'nationalities': original['source_values']}}] if field == 'nationality' else [
            {'facts': {field: value}} for value in original['source_values']]
        # A shirt number at another club is not a shirt-number source here.
        candidates += [r for r in extra if field != 'shirt_number' or r['club_id'] == player['club_id']]
        checks[field] = facts.field_check(field, declared, candidates)
    return checks


def supplement(season, original_path, capture_path, destination, allow_known_nationality_delta=False):
    old = json.loads(original_path.read_text())
    if (old['schema_version'], old['season']) != ('pm99-historical-player-facts-audit-v1', season):
        raise ValueError('wrong original facts audit')
    release = registry.load_preferred_release(season)
    package = json.loads(release.package_path.read_text())
    amendments = {}
    amendment_binding = None
    if allow_known_nationality_delta:
        descriptor = next((a for a in package['artifacts'] if a['id'] == 'historical-nationality-plan-' + season), None)
        if descriptor is None or descriptor['relative_path'] != 'nationality-plan.json':
            raise ValueError('current recipe has no known nationality delta')
        amendment_path = release.package_path.parent / descriptor['relative_path']
        amendment = json.loads(amendment_path.read_text())
        if (hashlib.sha256(pipeline.canonical_json_bytes(amendment)).hexdigest() != descriptor['sha256'] or
                amendment['season'] != season or amendment['package_sha256'] != old['bindings']['package_sha256']):
            raise ValueError('known nationality delta does not bind previous factual audit')
        receipt = json.loads(release.compiler_receipt_path.read_text())
        if receipt['nationality_plan_sha256'] != registry.sha256_file(amendment_path):
            raise ValueError('native nationality receipt does not bind amendment bytes')
        amendments = {r['player_id']: r for r in amendment['updates']}
        amendment_binding = {'path': registry.relative_workspace_path(amendment_path), 'sha256': registry.sha256_file(amendment_path)}
    clubs, players, legacy = roster.add_legacy_english(package, season)
    by_id = {p['id']: p for p in players}
    if len(by_id) != len(old['players']) or set(by_id) != {p['player_id'] for p in old['players']}:
        raise ValueError('factual audit roster changed')
    rows = ntf.verified_rows(season, capture_path) if capture_path and capture_path.exists() else []
    by_identity = collections.defaultdict(list)
    for row in rows:
        for name in ntf.person_names(row['facts']['name']):
            by_identity[(name, row['facts']['birth_date'])].append(row)
    result = copy.deepcopy(old)
    counts = collections.Counter()
    for previous in result['players']:
        player = by_id[previous['player_id']]
        names = {roster.normalise(n) for n in (player['name'], player.get('source_name')) if n}
        dob = player['facts'].get('birth_date')
        matches = [r for name in names for r in by_identity.get((name, dob), [])] if isinstance(dob, str) else []
        # Two name representations of the same source row are one piece of evidence.
        matches = list({(r['source_path'], r['facts']['name'], r['facts']['birth_date']): r for r in matches}.values())
        previous['fields'] = refreshed_checks(player, previous, matches, amendments.get(player['id']))
        previous['same_club_season_identity_match'] |= any(r['club_id'] == player['club_id'] for r in matches)
        previous['evidence'] += [{k: v for k, v in r.items() if k not in ('facts', 'group')} |
            {'source_name': r['facts']['name'], 'source_position': r['facts']['source_position'],
             'birth_date': r['facts']['birth_date']} for r in matches]
        for field, check in previous['fields'].items():
            counts[field + ':' + check['status']] += 1
        counts['identity-with-dated-name-and-DOB-source' if previous['evidence'] else 'identity-without-independent-DOB-match'] += 1
        counts['same-club-season-squad-identity-match' if previous['same_club_season_identity_match'] else 'same-club-season-squad-identity-unverified'] += 1
    audited = {p['player_id']: p for p in result['players']}
    for club in result['clubs']:
        declaration = next(c for c in clubs if c['id'] == club['club_id'])
        club['same_club_season_identity_matches'] = sum(audited[id]['same_club_season_identity_match']
            for id in declaration['roster_player_ids'] if id in audited)
    result['bindings'].update(release_id=release.release_id, package_sha256=registry.sha256_file(release.package_path), legacy=legacy)
    result['bindings']['previous_factual_audit'] = {'path': registry.relative_workspace_path(original_path),
        'sha256': registry.sha256_file(original_path), 'scope': 'Unchanged previously compared facts; no repeat scrape'}
    result['bindings']['ntf_review_capture'] = {'path': registry.relative_workspace_path(capture_path),
        'sha256': registry.sha256_file(capture_path)} if capture_path and capture_path.exists() else None
    result['bindings']['known_nationality_delta'] = amendment_binding
    result['summary'] = {'clubs': len(clubs), 'players': len(players), **dict(counts)}
    destination.parent.mkdir(parents=True, exist_ok=True)
    pipeline.write_canonical_json(destination, result)
    return {'season': season, **result['summary']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season'); parser.add_argument('--facts-root', type=Path, required=True)
    parser.add_argument('--legacy-2015-facts-root', type=Path)
    parser.add_argument('--ntf-root', type=Path); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-known-nationality-delta', action='store_true')
    args = parser.parse_args()
    summaries = []
    for season in registry.supported_seasons() if args.season == 'all' else [args.season]:
        original = (args.legacy_2015_facts_root if season == '2015-16' and args.legacy_2015_facts_root else args.facts_root) / season / 'player-facts-audit.json'
        capture = args.ntf_root / season / 'ntf-review-capture.json' if args.ntf_root else None
        summary = supplement(season, original, capture, args.output / season / 'player-facts-audit.json', args.allow_known_nationality_delta)
        summaries.append(summary); print(json.dumps(summary), flush=True)
    totals = sum((collections.Counter({k: v for k, v in s.items() if k != 'season'}) for s in summaries), collections.Counter())
    pipeline.write_canonical_json(args.output / 'summary.json', {'seasons': summaries, 'totals': dict(totals), 'historical_verification_complete': False})


if __name__ == '__main__':
    main()
