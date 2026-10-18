#!/usr/bin/env python3
"""Correct only unambiguous exact-identity, source-backed nationalities.

No club-country default, no choice between dual flags and no portrait-based
identity. Unsupported native countries and whole-record fallbacks stay queued.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_package_compiler_v2 as compiler
from scripts.build_2015_english92_release import _country_code, UNKNOWN_NATIONALITY, UNREPRESENTABLE_NATIONALITY
from scripts.season_historical_player_facts_audit_v1 import country


def plan(season, audit_path):
    release = registry.load_preferred_release(season)
    report = json.loads(audit_path.read_text())
    if report['schema_version'] != 'pm99-historical-player-facts-audit-v1':
        raise ValueError('wrong nationality audit schema')
    if (report['season'], report['bindings']['package_sha256']) != (season, registry.sha256_file(release.package_path)):
        raise ValueError('nationality audit does not describe current recipe')
    package = json.loads(release.package_path.read_text())
    by_id = {p['id']: p for p in package['players']}
    codes = compiler._extract_country_codes_from_textos(release.game_path / 'DBDAT/TEXTOS.PKF')
    updates, unresolved = [], []
    for row in report['players']:
        check = row['fields']['nationality']
        if check['status'] not in ('conflict', 'recipe-missing-or-preserved'):
            continue
        player = by_id.get(row['player_id'])
        values = sorted({country(v) for v in check['source_values']} - {None})
        if player is None or player.get('policy') == 'preserve-existing-mode1' or len(values) != 1:
            unresolved.append({'player_id': row['player_id'], 'reason': 'legacy/whole-record fallback or ambiguous country'})
            continue
        code = values[0]
        if country(check['recipe_value']) == code:
            continue  # An alias such as LAT/LVA is not a nationality correction.
        if code in UNKNOWN_NATIONALITY or code in UNREPRESENTABLE_NATIONALITY:
            unresolved.append({'player_id': row['player_id'], 'nationality': code, 'reason': 'not representable in native country table'})
            continue
        try:
            native = _country_code(code, codes)
        except ValueError:
            unresolved.append({'player_id': row['player_id'], 'nationality': code, 'reason': 'country translation unresolved'})
            continue
        if native == codes['XXX']:
            unresolved.append({'player_id': row['player_id'], 'nationality': code, 'reason': 'country translation unresolved'})
            continue
        if (player['name'], player['carrier_id'], player['facts']['birth_date'], player['facts']['nationality']) != (
                row['name'], row['carrier_id'], row['birth_date'], check['recipe_value']):
            raise ValueError('nationality identity/fact binding changed')
        updates.append({'player_id': player['id'], 'carrier_id': player['carrier_id'], 'name': player['name'],
                        'birth_date': player['facts']['birth_date'], 'before': player['facts']['nationality'],
                        'after': code, 'native_country_code': native,
                        'original_fallbacks': [f for f in player.get('fact_fallbacks', []) if f['field'] == 'nationality'],
                        'provenance': {'method': 'unambiguous-dated-source-name-and-DOB-nationality',
                            'evidence': row['evidence'], 'audit_field': check,
                            'limit': 'Provider historical squad flags are not a separate international-allegiance chronology'}})
    return {'schema_version': 'pm99-historical-nationality-plan-v1', 'season': season,
            'release_id': release.release_id, 'package_sha256': registry.sha256_file(release.package_path),
            'jug_sha256': registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
            'audit_path': registry.relative_workspace_path(audit_path), 'audit_sha256': registry.sha256_file(audit_path),
            'updates': updates, 'unresolved': unresolved,
            'summary': {'supported_corrections': len(updates), 'unresolved_candidates': len(unresolved)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season'); parser.add_argument('--audit-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    for season in registry.supported_seasons() if args.season == 'all' else [args.season]:
        result = plan(season, args.audit_root / season / 'player-facts-audit.json')
        path = args.output / season / 'nationality-plan.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        pipeline.write_canonical_json(path, result)
        print(json.dumps({'season': season, **result['summary']}), flush=True)


if __name__ == '__main__':
    main()
