#!/usr/bin/env python3
"""Independently check every declared player, retaining missing evidence.

Reuses a hash-bound raw-reparse roster audit, rather than scraping it again.
Same-edition FIFA facts and complete dated HTML squad rows supplement it.
Whole-season membership and identity evidence never certify August ownership.
No recipe or game is written by this command.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_role_plan_v1 as roles
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts.prepare_2015_world_fifa16_drafts import FIFA_NATIONALITY_TO_PM99
from scripts.capture_historical_detailed_roles_v1 import parse, parse_complete_squad

FIELDS = ('nationality', 'height_cm', 'weight_kg', 'shirt_number')
COUNTRIES = {roster.normalise(k): v for k, v in FIFA_NATIONALITY_TO_PM99.items()}
COUNTRIES.update({roster.normalise(k): v for k, v in {
    'Ireland': 'IRL', 'South Korea': 'KOR', 'North Korea': 'PRK',
    'Curaçao': 'CUW', 'Guinea-Bissau': 'GNB', 'Czechia': 'CZE',
    'Democratic Republic of the Congo': 'COD', 'DR Congo': 'COD',
    'Republic of the Congo': 'CGO', 'North Macedonia': 'MKD',
    'Bosnia-Herzegovina': 'BOS', 'United States of America': 'USA',
    'Holland': 'NED', 'Algiers': 'ALG', 'Zaire': 'COD',
}.items()})
CODE_ALIASES = {'ICE': 'ISL', 'BIH': 'BOS', 'DEU': 'GER', 'NLD': 'NED',
                'DZA': 'ALG', 'PRT': 'POR', 'ZAF': 'RSA', 'LAT': 'LVA'}


def country(value):
    if not isinstance(value, str) or not value.strip():
        return None
    return CODE_ALIASES.get(value, value) if len(value) == 3 and value.isupper() else COUNTRIES.get(roster.normalise(value))


def field_check(field, recipe, candidates):
    """Only exact-DOB identities reach this function; ambiguity stays visible."""
    values = set()
    ambiguous = False
    for candidate in candidates:
        facts = candidate['facts']
        if field == 'nationality':
            labels = facts.get('nationalities') or [facts.get('nationality')]
            mapped = {country(label) for label in labels} - {None}
            ambiguous |= len(mapped) > 1
            values.update(mapped)
        elif isinstance(facts.get(field), int) and not isinstance(facts[field], bool):
            values.add(facts[field])
    comparable_recipe = country(recipe) if field == 'nationality' else recipe
    if not values:
        status = 'no-independent-field-source'
    elif not isinstance(comparable_recipe, (str, int)) or comparable_recipe in ('UNK', 'XXX'):
        status = 'recipe-missing-or-preserved'
    elif comparable_recipe in values:
        status = 'match' if len(values) == 1 else 'compatible-but-source-ambiguous'
    else:
        status = 'conflict' if len(values) == 1 and not ambiguous else 'conflict-source-ambiguous'
    return {'status': status, 'recipe_value': recipe, 'source_values': sorted(values),
            'automatic_change_authorised': False}


def fifa_facts_index():
    index = collections.defaultdict(list)
    with roles.FIFA.open() as handle:
        earliest = {}
        for row in csv.DictReader(handle):
            key = (int(row['fifa_version']), row['player_id'])
            if key not in earliest or row['fifa_update_date'] < earliest[key]['fifa_update_date']:
                earliest[key] = {k: row[k] for k in (
                    'fifa_version', 'player_id', 'long_name', 'short_name', 'dob',
                    'height_cm', 'weight_kg', 'nationality_name', 'fifa_update_date')}
    for row in earliest.values():
        facts = {'birth_date': row['dob'], 'nationality': country(row['nationality_name']),
                 'height_cm': int(row['height_cm']) if row['height_cm'].isdigit() else None,
                 'weight_kg': int(row['weight_kg']) if row['weight_kg'].isdigit() else None}
        candidate = {'facts': facts, 'provider': 'exact-edition-FIFA',
                     'source_player_id': row['player_id'], 'snapshot_date': row['fifa_update_date'],
                     'source_name': row['long_name'], 'club': None}
        for name in {row['long_name'], row['short_name']}:
            index[(int(row['fifa_version']), roster.normalise(name), row['dob'])].append(candidate)
    return index


def baseline_sources(season, report):
    """Reuse an unchanged, original-byte-verified capture, not recipe facts."""
    for binding in report['bindings']['sources']:
        if registry.sha256_file(ROOT / binding['path']) != binding['sha256']:
            raise ValueError('historical capture changed after its independent audit')
    accepted = set()
    statuses = collections.defaultdict(set)
    for source in report['raw_sources']:
        key = source['source_path'], source['source_sha256']
        statuses[key].add(source['status'])
        if source['status'] == 'raw-source-reparsed':
            if registry.sha256_file(ROOT / source['local_path']) != source['source_sha256']:
                raise ValueError('original source changed after independent reparse')
            accepted.add(key)
    sources, _ = roster.load_sources(season)
    rows = []
    for source in sources:
        key = source['source_path'], source['source_sha256']
        if key not in accepted or statuses[key] != {'raw-source-reparsed'}:
            continue
        for facts in source['players']:
            rows.append({'facts': facts, 'club': source['club_name'],
                         'group': roster.source_group(source['country_catalog']),
                         'provider': 'original-dated-squad-reparse',
                         'source_path': source['source_path'], 'source_sha256': source['source_sha256']})
    return rows


def detailed_sources(season, path):
    if path is None or not path.exists():
        return [], None
    document = json.loads(path.read_text())
    if document['season'] != season or document['schema_version'] != 'pm99-historical-detailed-roles-capture-v1':
        raise ValueError('wrong detailed capture season/schema')
    root = registry._workspace_path(document['cache_root'], label='detailed source cache')
    rows = []
    for club in document['clubs']:
        relative = Path(club['source_path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe detailed source path')
        source = root / relative
        if registry.sha256_file(source) != club['source_sha256']:
            raise ValueError('detailed source changed')
        raw = source.read_bytes()
        title, _ = roster.historical_html_title(raw, 'transfermarkt', season, roster.source_group(club['country_catalog']))
        complete = parse_complete_squad(raw)
        if roster.normalise(title) != roster.normalise(club['source_club_name']) or [p for p in complete if p['fine_roles']] != club['players']:
            raise ValueError('detailed capture disagrees with original dated source')
        for player in complete:
            rows.append({'facts': player, 'club': club['club_name'],
                         'group': roster.source_group(club['country_catalog']),
                         'provider': 'original-dated-detailed-squad-reparse',
                         'source_url': club['source_url'], 'source_path': club['source_path'],
                         'source_sha256': club['source_sha256']})
    return rows, {'path': registry.relative_workspace_path(path), 'sha256': registry.sha256_file(path)}


def audit_season(season, baseline_path, detailed_path, fifa, output):
    release = registry.load_preferred_release(season)
    package = json.loads(release.package_path.read_text())
    clubs, players, legacy = roster.add_legacy_english(package, season)
    baseline = json.loads(baseline_path.read_text())
    if baseline['season'] != season or baseline['schema_version'] != roster.SCHEMA:
        raise ValueError('wrong baseline roster audit')
    old = {p['player_id']: p for p in baseline['players']}
    rows = baseline_sources(season, baseline)
    detailed, binding = detailed_sources(season, detailed_path)
    rows += detailed
    by_identity = collections.defaultdict(list)
    for row in rows:
        facts = row['facts']
        if isinstance(facts.get('birth_date'), str):
            by_identity[(roster.normalise(facts['name']), facts['birth_date'])].append(row)
    by_club = {c['id']: c for c in clubs}
    audited, counts = [], collections.Counter()
    for player in players:
        previous = old.get(player['id'])
        facts = player['facts']
        # A role-only revision can reuse this identity audit; arbitrary factual
        # changes cannot inherit it merely because the carrier ID stayed put.
        if previous is None or (previous['name'], previous['birth_date'], previous['carrier_id']) != (
                player['name'], facts.get('birth_date'), player['carrier_id']):
            raise ValueError('player identity changed since roster baseline; audit it first')
        names = {roster.normalise(n) for n in (player['name'], player.get('source_name')) if n}
        dob = facts.get('birth_date')
        matched = [r for name in names for r in by_identity.get((name, dob), [])] if isinstance(dob, str) else []
        fifa_matches = {r['source_player_id']: r for name in names
                        for r in fifa.get((int(season[:4]) + 1 - 2000, name, dob), [])} if isinstance(dob, str) else {}
        if len(fifa_matches) == 1:
            matched += list(fifa_matches.values())
        club = by_club[player['club_id']]
        aliases = roster.club_names(roster.club_group(club), club['name'], club.get('full_name', ''))
        at_club = [r for r in matched if r.get('group') == roster.club_group(club) and roster.normalise(r.get('club')) in aliases]
        checks = {field: field_check(field, facts.get(field), at_club if field == 'shirt_number' else matched) for field in FIELDS}
        for field, check in checks.items():
            counts[field + ':' + check['status']] += 1
        counts['identity-with-dated-name-and-DOB-source' if matched else 'identity-without-independent-DOB-match'] += 1
        counts['same-club-season-squad-identity-match' if at_club else 'same-club-season-squad-identity-unverified'] += 1
        audited.append({'player_id': player['id'], 'carrier_id': player['carrier_id'],
                        'name': player['name'], 'birth_date': dob, 'club_id': club['id'], 'club': club['name'],
                        'whole_record_fallback': player.get('policy') == 'preserve-existing-mode1',
                        'baseline_membership_status': previous['membership_status'],
                        'same_club_season_identity_match': bool(at_club),
                        'august_ownership_verified': False, 'fields': checks,
                        'evidence': [{k: v for k, v in row.items() if k not in ('facts', 'group')} for row in matched]})
    club_rows = []
    audited_by_id = {p['player_id']: p for p in audited}
    for club in clubs:
        members = [audited_by_id[id] for id in club['roster_player_ids'] if id in audited_by_id]
        club_rows.append({'club_id': club['id'], 'club': club['name'], 'carrier_id': club['carrier_id'],
                          'playable': club['division'] != 'preserve-existing-mode1-membership',
                          'roster_size': len(club['roster_player_ids']),
                          'same_club_season_identity_matches': sum(p['same_club_season_identity_match'] for p in members),
                          'august_ownership_verified': False})
    result = {'schema_version': 'pm99-historical-player-facts-audit-v1', 'season': season,
              'historical_verification_complete': False,
              'scope': 'Every declared playable and non-playable team/player; missing facts remain explicit',
              'temporal_limit': 'Whole-season membership; NOT August ownership. Shirt numbers are not auto-corrected.',
              'bindings': {'release_id': release.release_id, 'package_sha256': registry.sha256_file(release.package_path),
                           'roster_audit_path': registry.relative_workspace_path(baseline_path),
                           'roster_audit_sha256': registry.sha256_file(baseline_path), 'legacy': legacy,
                           'detailed_capture': binding, 'exact_editions_FIFA_sha256': registry.sha256_file(roles.FIFA)},
              'summary': {'clubs': len(clubs), 'players': len(audited), **dict(counts)},
              'clubs': club_rows, 'players': audited}
    output.mkdir(parents=True, exist_ok=True)
    destination = output / 'player-facts-audit.json'
    if destination.exists():
        raise ValueError('fact audit already exists; use a fresh output root')
    pipeline.write_canonical_json(destination, result)
    return {'season': season, **result['summary']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season'); parser.add_argument('--roster-audit-root', type=Path, required=True)
    parser.add_argument('--detailed-root', type=Path)
    parser.add_argument('--fallback-detailed-root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    fifa = fifa_facts_index()
    summaries = []
    for season in registry.supported_seasons() if args.season == 'all' else [args.season]:
        detail = args.detailed_root / season / 'detailed-role-capture.json' if args.detailed_root else None
        if (detail is None or not detail.exists()) and args.fallback_detailed_root:
            detail = args.fallback_detailed_root / season / 'detailed-role-capture.json'
        summary = audit_season(season, args.roster_audit_root / season / 'report.json', detail, fifa, args.output / season)
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
    totals = sum((collections.Counter({k: v for k, v in s.items() if k != 'season'}) for s in summaries), collections.Counter())
    pipeline.write_canonical_json(args.output / 'summary.json', {'seasons': summaries, 'totals': dict(totals), 'historical_verification_complete': False})


if __name__ == '__main__':
    main()
