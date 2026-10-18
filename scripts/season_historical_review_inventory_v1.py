#!/usr/bin/env python3
"""Export every club/player review result; never turn coverage into approval."""
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


def unresolved(row):
    issues = []
    if not row['same_club_season_identity_match']:
        issues.append('club-season-identity-unverified')
    if not row.get('august_ownership_verified'):
        issues.append('opening-squad-ownership-unverified')
    for field, check in row['fields'].items():
        if check['status'] != 'match':
            issues.append(field + ':' + check['status'])
    return issues


def export(season, roster_path, facts_path, destination):
    release = registry.load_preferred_release(season)
    roster = json.loads(roster_path.read_text())
    facts = json.loads(facts_path.read_text())
    package_hash = registry.sha256_file(release.package_path)
    for document in (roster, facts):
        if document['season'] != season or document['bindings']['package_sha256'] != package_hash:
            raise ValueError('review inventory requires audits of current declarations')
    if roster['bindings']['jug_sha256'] != registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'):
        raise ValueError('review inventory native roster audit is stale')
    destination.mkdir(parents=True, exist_ok=True)
    if (destination / 'players.csv').exists() or (destination / 'clubs.csv').exists():
        raise ValueError('review export already exists')
    native = collections.defaultdict(list)
    for row in roster['players']:
        native[row['player_id']].append(row)
    by_club = collections.defaultdict(list)
    fields = ['season', 'club', 'club_id', 'player', 'player_id', 'carrier_id', 'birth_date',
              'same_club_season_identity_match', 'august_ownership_verified', 'display_roles',
              'native_name_mismatch', 'display_role_conflict', 'unresolved', 'evidence_urls']
    fields += [field + suffix for field in ('nationality', 'height_cm', 'weight_kg', 'shirt_number')
               for suffix in ('_recipe', '_sources', '_status')]
    counts = collections.Counter()
    with (destination / 'players.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        for player in facts['players']:
            originals = native.get(player['player_id'], [])
            if not originals:
                raise ValueError('player absent from independent native roster audit')
            missing = unresolved(player)
            wrong_name = any(not p['native_name_matches'] for p in originals)
            wrong_role = any(p['display_role_conflict'] for p in originals)
            if wrong_name: missing.append('native-name-mismatch')
            if wrong_role: missing.append('display-role-contradiction')
            for issue in missing: counts[issue] += 1
            by_club[player['club_id']].append((player, wrong_name, wrong_role, missing))
            row = {'season': season, 'club': player['club'], 'club_id': player['club_id'],
                   'player': player['name'], 'player_id': player['player_id'], 'carrier_id': player['carrier_id'],
                   'birth_date': json.dumps(player['birth_date']) if isinstance(player['birth_date'], dict) else player['birth_date'],
                   'same_club_season_identity_match': player['same_club_season_identity_match'],
                   'august_ownership_verified': player['august_ownership_verified'],
                   'display_roles': '|'.join(sorted({p['display_role'] for p in originals})),
                   'native_name_mismatch': wrong_name, 'display_role_conflict': wrong_role,
                   'unresolved': '|'.join(missing),
                   'evidence_urls': '|'.join(sorted({r['source_url'] for r in player['evidence'] if r.get('source_url')}))}
            for field, check in player['fields'].items():
                row.update({field + '_recipe': json.dumps(check['recipe_value']),
                            field + '_sources': '|'.join(map(str, check['source_values'])),
                            field + '_status': check['status']})
            writer.writerow(row)
    club_rows = []
    for club in roster['clubs']:
        members = by_club[club['id']]
        club_rows.append({'season': season, 'club': club['club'], 'club_id': club['id'],
            'carrier_id': club['carrier_id'], 'country': club['country_group'], 'playable': club['playable'],
            'roster_occurrences': club['recipe_roster_count'],
            'native_roster_matches': club['native_roster_matches'],
            'same_club_season_identity_matches': sum(p['same_club_season_identity_match'] for p, _, _, _ in members),
            'native_name_mismatches': sum(w for _, w, _, _ in members),
            'display_role_contradictions': sum(w for _, _, w, _ in members),
            'players_with_unresolved_checks': sum(bool(gaps) for _, _, _, gaps in members),
            'historical_verification_complete': False})
    with (destination / 'clubs.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(club_rows[0])); writer.writeheader(); writer.writerows(club_rows)
    summary = {'season': season, 'release_id': release.release_id, 'clubs': len(club_rows),
        'playable_clubs': sum(c['playable'] for c in club_rows),
        'non_playable_clubs': sum(not c['playable'] for c in club_rows), 'players': len(facts['players']),
        'remaining': dict(counts), 'historical_verification_complete': False,
        'limits': ['Every declaration enumerated is not every historical player verified.',
                   'Whole-season sources do not prove August ownership.',
                   'Current files do not certify managers, kit design, portrait identity or subjective abilities.'],
        'bindings': {'package_sha256': package_hash, 'roster_audit_path': registry.relative_workspace_path(roster_path),
                     'roster_audit_sha256': registry.sha256_file(roster_path),
                     'facts_audit_path': registry.relative_workspace_path(facts_path),
                     'facts_audit_sha256': registry.sha256_file(facts_path)}}
    pipeline.write_canonical_json(destination / 'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season'); parser.add_argument('--roster-root', type=Path, required=True)
    parser.add_argument('--facts-root', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); results = []
    for season in registry.supported_seasons() if args.season == 'all' else [args.season]:
        result = export(season, args.roster_root / season / 'report.json',
                        args.facts_root / season / 'player-facts-audit.json', args.output / season)
        results.append(result)
        print(json.dumps({k: result[k] for k in ('season', 'clubs', 'players', 'historical_verification_complete')}), flush=True)
    pipeline.write_canonical_json(args.output / 'summary.json', {'seasons': results, 'historical_verification_complete': False})


if __name__ == '__main__':
    main()
