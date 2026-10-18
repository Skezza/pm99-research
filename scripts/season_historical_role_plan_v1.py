#!/usr/bin/env python3
"""Source-backed fine-role proposals; never infer a side from G/D/M/F alone."""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import season_historical_roster_audit_v1 as audit
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts.supplement_2015_ntf_with_transfermarkt import SquadParser

ROOT = registry.ROOT
FIFA = ROOT / '.local/external-sources/sofifa-fifa16/male_players_legacy.csv'
ROLE_MAP = {'GK': 0, 'RB': 1, 'RWB': 1, 'LB': 2, 'LWB': 2, 'SW': 3, 'CB': 4,
            'RM': 6, 'CF': 8, 'CM': 9, 'CAM': 9, 'LM': 10, 'RW': 11, 'ST': 12,
            'LW': 13, 'CDM': 14, 'RF': 15, 'LF': 16}
HTML_ROLES = {'goalkeeper': 0, 'rightback': 1, 'leftback': 2, 'sweeper': 3,
              'centreback': 4, 'centerback': 4, 'centraldefender': 4,
              'rightmidfielder': 6, 'rightmidfield': 6, 'centralmidfielder': 9,
              'centralmidfield': 9, 'attackingmidfielder': 9, 'attackingmidfield': 9,
              'leftmidfielder': 10, 'leftmidfield': 10, 'rightwinger': 11, 'rightwing': 11,
              'centreforward': 12, 'centerforward': 12, 'striker': 12,
              'leftwinger': 13, 'leftwing': 13, 'defensivemidfielder': 14, 'defensivemidfield': 14}


def fifa_index() -> dict:
    index = collections.defaultdict(list)
    with FIFA.open() as handle:
        for row in csv.DictReader(handle):
            edition = int(row['fifa_version'])
            row = {key: row[key] for key in ('player_id', 'long_name', 'short_name', 'dob', 'player_positions', 'fifa_update_date')}
            for name in {row['long_name'], row['short_name']}:
                index[(edition, audit.normalise(name), row['dob'])].append(row)
    return index


def fifa_roles(player: dict, season: str, index: dict) -> tuple[list[int] | None, dict | None]:
    """Exact edition + exact captured name + DOB + unique source ID required."""
    edition = int(season[:4]) + 1 - 2000
    if not isinstance(player['facts'].get('birth_date'), str):
        return None, None
    matches = {}
    for name in {player['name'], player.get('source_name', '')} - {''}:
        for row in index.get((edition, audit.normalise(name), player['facts'].get('birth_date')), []):
            matches[row['player_id']] = row
    if len(matches) != 1:
        return None, None
    row = next(iter(matches.values()))
    positions = [p.strip() for p in row['player_positions'].split(',')]
    if not positions or any(p not in ROLE_MAP for p in positions):
        return None, None
    roles = list(dict.fromkeys(ROLE_MAP[p] for p in positions))[:6]
    if audit.role_conflict(player['facts'].get('primary_position'), roles[0]):
        return None, None
    return roles, {'method': 'exact-edition-FIFA-role-mapping', 'player_id': row['player_id'],
                   'edition': edition, 'snapshot_date': row['fifa_update_date'],
                   'source_name': row['long_name'], 'birth_date': row['dob'],
                   'source_positions': positions,
                   'limit': 'FIFA role taxonomy mapped to PM99, not independent August club ownership'}


def html_roles(report: dict) -> dict:
    index = collections.defaultdict(list)
    for source in report['raw_sources']:
        if source['status'] != 'raw-source-reparsed' or not source.get('local_path', '').endswith('.html'):
            continue
        path = ROOT / source['local_path']
        payload = path.read_bytes()
        if registry.sha256_file(path) != source['source_sha256']:
            raise ValueError('raw role source changed since audit')
        rows = []
        if 'ntf' in str(path):
            from scripts.capture_2015_missing_family_squads import _SquadParser
            title = audit.BeautifulSoup(payload, 'html.parser').title.get_text(' ', strip=True)
            period = re.fullmatch(r'.+?\s+\((\d{4}(?:/\d{2})?)\)\s*\|\s*National Football Teams', title).group(1)
            raw = _SquadParser()
            raw.feed(payload.decode('utf-8'))
            for row in raw.rows:
                if len(row) >= 8 and row[5] == period and audit.normalise(row[4]) in HTML_ROLES:
                    rows.append((row[1], row[2], row[4]))
        elif 'transfermarkt' in str(path):
            raw = SquadParser()
            raw.feed(payload.decode('utf-8'))
            canonical = {audit.normalise(p['name']): p for p in audit.tm_source.parse_squad(payload)}
            for row in raw.rows:
                name = row.get('player_name', '')
                facts = canonical.get(audit.normalise(name))
                if not facts or not facts.get('birth_date'):
                    continue
                cells = row.get('cells', [])
                # Exact player cell suffix, not a substring elsewhere in the page.
                role = next((label for label in HTML_ROLES if any(
                    audit.normalise(cell).removeprefix(audit.normalise(name)) == label for cell in cells[1:3])), None)
                if role:
                    rows.append((name, facts['birth_date'], role))
        for name, dob, label in rows:
            index[(audit.normalise(name), dob)].append({'role': HTML_ROLES[audit.normalise(label)],
                'method': 'dated-squad-position', 'source_path': source['source_path'],
                'source_sha256': source['source_sha256'], 'source_name': name,
                'source_position': label, 'birth_date': dob})
    return index


def detailed_index(season: str, path: Path | None, reparse_audit_path: Path | None = None) -> tuple[dict, list]:
    index, bindings = collections.defaultdict(list), []
    if path is None:
        return index, bindings
    from scripts.capture_historical_detailed_roles_v1 import parse
    document = json.loads(path.read_text())
    if document['schema_version'] != 'pm99-historical-detailed-roles-capture-v1' or document['season'] != season:
        raise ValueError('wrong detailed-role capture season/schema')
    cache_root = registry._workspace_path(document['cache_root'], label='detailed role cache')
    reparsed_clubs = set()
    if reparse_audit_path is not None:
        checked = json.loads(reparse_audit_path.read_text())
        binding = checked['bindings']['detailed_capture']
        if checked['schema_version'] != 'pm99-historical-player-facts-audit-v1' or checked['season'] != season:
            raise ValueError('independent detailed reparse audit has wrong identity')
        if binding is not None:
            original_path = registry._workspace_path(binding['path'], label='independently reparsed capture')
            if registry.sha256_file(original_path) != binding['sha256']:
                raise ValueError('independently reparsed capture changed')
            original = json.loads(original_path.read_text())
            if (original['schema_version'], original['season'], original['cache_root']) != (
                    document['schema_version'], season, document['cache_root']):
                raise ValueError('independent detailed reparse capture has different source namespace')
            reparsed_clubs = {hashlib.sha256(pipeline.canonical_json_bytes(c)).hexdigest() for c in original['clubs']}
        bindings.append({'original_reparse_audit_path': registry.relative_workspace_path(reparse_audit_path),
                         'sha256': registry.sha256_file(reparse_audit_path),
                         'scope': 'Unchanged original-byte reparse reused; no repeated scrape or new historical approval'})
    for club in document['clubs']:
        relative = Path(club['source_path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe detailed source path')
        raw = cache_root / relative
        if registry.sha256_file(raw) != club['source_sha256']:
            raise ValueError('detailed role capture raw bytes changed')
        if hashlib.sha256(pipeline.canonical_json_bytes(club)).hexdigest() not in reparsed_clubs:
            name, _ = audit.historical_html_title(raw.read_bytes(), 'transfermarkt', season,
                                                  audit.source_group(club['country_catalog']))
            if audit.normalise(name) != audit.normalise(club['source_club_name']) or parse(raw.read_bytes()) != club['players']:
                raise ValueError('detailed role source reparse disagrees')
        for player in club['players']:
            if isinstance(player['birth_date'], str):
                index[(audit.source_group(club['country_catalog']), audit.normalise(club['club_name']),
                       audit.normalise(player['name']), player['birth_date'])].append({**player,
                           'source_path': club['source_path'], 'source_sha256': club['source_sha256'],
                           'source_url': club['source_url'], 'method': 'dated-detailed-squad-position'})
    bindings.append({'path': registry.relative_workspace_path(path), 'sha256': registry.sha256_file(path)})
    return index, bindings


def plan(season: str, report_path: Path, fifa: dict, detailed_path: Path | None = None,
         reparse_audit_path: Path | None = None, ntf_path: Path | None = None) -> dict:
    release = registry.load_preferred_release(season)
    report = json.loads(report_path.read_text())
    if (report['season'] != season or report['bindings']['package_sha256'] != registry.sha256_file(release.package_path)
            or report['bindings']['jug_sha256'] != registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI')):
        raise ValueError('role plan requires the exact current historical audit')
    package = json.loads(release.package_path.read_text())
    clubs, players, _ = audit.add_legacy_english(package, season)
    club_by_id = {c['id']: c for c in clubs}
    aliases_by_club = {c['id']: audit.club_names(audit.club_group(c), c['name'], c.get('full_name', '')) for c in clubs}
    detailed, detailed_bindings = detailed_index(season, detailed_path, reparse_audit_path)
    if ntf_path is not None:
        from scripts.capture_historical_ntf_review_v1 import verified_rows, person_names
        for row in verified_rows(season, ntf_path):
            label = audit.normalise(row['facts']['source_position'])
            if label not in HTML_ROLES:
                continue
            for name in person_names(row['facts']['name']):
                key = (row['group'], audit.normalise(row['club']), name, row['facts']['birth_date'])
                detailed[key].append({**row['facts'], 'fine_roles': [HTML_ROLES[label]],
                    'source_path': row['source_path'], 'source_sha256': row['source_sha256'],
                    'source_url': row['source_url'], 'method': 'independent-dated-NTF-detailed-position'})
        detailed_bindings.append({'path': registry.relative_workspace_path(ntf_path), 'sha256': registry.sha256_file(ntf_path)})
    verified = {r['player_id']: r for r in report['players']
                if r['membership_status'] == 'captured-squad-match' and r['match_basis'] == 'name-and-birth-date'}
    # The previous exact-source corrections are already explicit in the
    # current recipe. This source-expansion pass only needs the new capture;
    # it does not need to parse the unchanged old HTML a second time.
    html = {} if reparse_audit_path is not None else html_roles(report)
    updates, unresolved = [], []
    for player in players:
        if player.get('policy') == 'preserve-existing-mode1':
            continue
        roles = player.get('facts', {}).get('fine_roles')
        source = {'method': 'existing-explicit-recipe-roles', 'limit': 'byte conformance, not new historical verification'}
        dob = player['facts'].get('birth_date')
        club = club_by_id[player['club_id']]
        detailed_matches = [row for name in {player['name'], player.get('source_name', '')} - {''}
                            for club_name in aliases_by_club[club['id']]
                            for row in detailed.get((audit.club_group(club), club_name, audit.normalise(name), dob), [])] if isinstance(dob, str) else []
        if detailed_matches and len({tuple(r['fine_roles']) for r in detailed_matches}) == 1:
            candidate = detailed_matches[0]
            if not audit.role_conflict(player['facts'].get('primary_position'), candidate['fine_roles'][0]):
                existing = roles if isinstance(roles, list) else []
                primary = candidate['fine_roles'][0]
                roles = list(dict.fromkeys([primary, *existing]))[:6]
                source = {**candidate, 'retained_explicit_secondary_roles': [r for r in roles[1:]],
                          'secondary_role_limit': 'Retained previous explicit declarations; this page independently verifies the primary role only'}
        if not isinstance(roles, list) or not roles:
            roles, source = fifa_roles(player, season, fifa)
            if roles is None and player['id'] in verified and isinstance(player['facts'].get('birth_date'), str):
                row = verified[player['id']]
                evidence = {(e['path'], e['sha256']) for e in row['evidence'] if e['raw_status'] == 'raw-source-reparsed'}
                candidates = [r for name in {player['name'], player.get('source_name', '')} - {''}
                              for r in html.get((audit.normalise(name), player['facts'].get('birth_date')), [])
                              if (r['source_path'], r['source_sha256']) in evidence]
                if candidates and len({r['role'] for r in candidates}) == 1:
                    role = candidates[0]['role']
                    if not audit.role_conflict(player['facts'].get('primary_position'), role):
                        roles, source = [role], candidates[0]
        if roles and all(isinstance(r, int) and 0 <= r <= 17 for r in roles):
            updates.append({'player_id': player['id'], 'carrier_id': player['carrier_id'], 'name': player['name'],
                            'birth_date': player['facts'].get('birth_date'), 'fine_roles': roles, 'provenance': source})
        elif player.get('policy') != 'preserve-existing-mode1':
            unresolved.append({'player_id': player['id'], 'carrier_id': player['carrier_id'], 'name': player['name'],
                               'reason': 'no unambiguous dated detailed-role source; broad position is not a side'})
    return {'schema_version': 'pm99-historical-role-plan-v1', 'season': season,
            'release_id': release.release_id, 'package_sha256': registry.sha256_file(release.package_path),
            'jug_sha256': report['bindings']['jug_sha256'], 'audit_sha256': registry.sha256_file(report_path),
            'detailed_capture_bindings': detailed_bindings,
            'fifa_source_sha256': registry.sha256_file(FIFA), 'updates': updates, 'unresolved': unresolved,
            'summary': {'proposed_players': len(updates), 'unresolved_players': len(unresolved),
                        'methods': dict(collections.Counter(r['provenance']['method'] for r in updates))}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season'); parser.add_argument('--audit-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--detailed-root', type=Path)
    parser.add_argument('--skip-season', action='append', default=[])
    parser.add_argument('--reparse-audit-root', type=Path)
    parser.add_argument('--ntf-root', type=Path)
    args = parser.parse_args()
    fifa = fifa_index()
    for season in registry.supported_seasons() if args.season == 'all' else [args.season]:
        if season in args.skip_season:
            continue
        detailed = args.detailed_root / season / 'detailed-role-capture.json' if args.detailed_root else None
        result = plan(season, args.audit_root / season / 'report.json', fifa, detailed if detailed and detailed.exists() else None,
                      args.reparse_audit_root / season / 'player-facts-audit.json' if args.reparse_audit_root else None,
                      args.ntf_root / season / 'ntf-review-capture.json' if args.ntf_root else None)
        destination = args.output / season / 'role-plan.json'
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ValueError('role plan already exists; use a fresh output root')
        pipeline.write_canonical_json(destination, result)
        print(json.dumps({'season': season, **result['summary']}), flush=True)


if __name__ == '__main__':
    main()
