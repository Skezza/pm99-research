#!/usr/bin/env python3
"""Refresh native roles after a bounded delta; reuse unchanged source evidence.

This is NOT a second scrape or a new historical certification. It refuses
changed club rosters, names, DOB declarations, primary positions or source
bytes. Independent historical evidence retains its original audit hash.
"""
import argparse
import collections
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_historical_roster_audit_v1 as audit
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from app.fdi_indexed import IndexedFDIFile


def refresh(season, original_path, destination):
    old = json.loads(original_path.read_text())
    release = registry.load_preferred_release(season)
    package = json.loads(release.package_path.read_text())
    clubs, players, legacy = audit.add_legacy_english(package, season)
    by_id = {p['id']: p for p in players}
    if old['season'] != season or old['schema_version'] != audit.SCHEMA:
        raise ValueError('wrong historical audit')
    if registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI') != old['bindings']['eq_sha256']:
        raise ValueError('native club rosters changed; requires a new independent audit')
    for binding in old['bindings']['sources']:
        if registry.sha256_file(ROOT / binding['path']) != binding['sha256']:
            raise ValueError('source capture changed')
    for source in old['raw_sources']:
        if source.get('local_path') and registry.sha256_file(ROOT / source['local_path']) != source['source_sha256']:
            raise ValueError('original audited source bytes changed')
    data = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(data).entries}
    result = copy.deepcopy(old)
    native = {}
    for row in result['players']:
        player = by_id.get(row['player_id'])
        if player is None or (player['name'], player['facts'].get('birth_date'), player['carrier_id'], player['facts'].get('primary_position')) != (
                row['name'], row['birth_date'], row['carrier_id'], row['recipe_position']):
            raise ValueError('recipe player identity/primary position changed')
        carrier = row['carrier_id']
        if carrier not in native:
            native[carrier] = audit.native_player(entries[carrier].decode_payload(data), carrier)
        current = native[carrier]
        if current['name'] != row['native_name'] or current['position'] != row['native_position']:
            raise ValueError('native name/primary position changed; cannot reuse identity evidence')
        row.update(native_role_codes=current['roles'], display_role=current['display_role'],
                   display_role_conflict=audit.role_conflict(row['recipe_position'], current['roles'][0]))
    old_clubs = {c['id']: c for c in old['clubs']}
    for club in clubs:
        previous = old_clubs.get(club['id'])
        members = [r['player_id'] for r in old['players'] if r['club_id'] == club['id']]
        if previous is None or previous['carrier_id'] != club['carrier_id'] or previous['club'] != club['name'] or members != club['roster_player_ids']:
            raise ValueError('recipe club identity/ordered roster changed')
    result['bindings'].update(release_id=release.release_id, package_sha256=registry.sha256_file(release.package_path),
                              jug_sha256=registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'), legacy=legacy)
    result['native_view_refresh'] = {'source_audit_path': registry.relative_workspace_path(original_path),
        'source_audit_sha256': registry.sha256_file(original_path),
        'independence': 'Unchanged source/capture bytes rehashed; prior raw reparse retained, not recertified',
        'club_rosters_names_dates_primary_positions_unchanged': True}
    result['summary']['display_role_conflicts'] = sum(p['display_role_conflict'] for p in result['players'])
    destination.parent.mkdir(parents=True, exist_ok=True)
    pipeline.write_canonical_json(destination, result)
    return {'season': season, **result['summary']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season'); parser.add_argument('--audit-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    summaries = []
    for season in registry.supported_seasons() if args.season == 'all' else [args.season]:
        summary = refresh(season, args.audit_root / season / 'report.json', args.output / season / 'report.json')
        summaries.append(summary); print(json.dumps(summary), flush=True)
    totals = sum((collections.Counter({k: v for k, v in s.items() if k != 'season'}) for s in summaries), collections.Counter())
    pipeline.write_canonical_json(args.output / 'summary.json', {'seasons': summaries, 'totals': dict(totals)})


if __name__ == '__main__':
    main()
