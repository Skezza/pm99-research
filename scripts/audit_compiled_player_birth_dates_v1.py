#!/usr/bin/env python3
"""Read back literal recipe birthdays from actual native player records.

Read-only: no source scraping, date inference, age rebasing or database writes.
Preserved dates are counted as gaps, never called independently verified facts.
"""
import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.fdi_indexed import IndexedFDIFile
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry


def inspect(package, raw):
    entries = {entry.record_id: entry for entry in IndexedFDIFile.from_bytes(raw).entries}
    checked, preserved, failures = 0, 0, []
    for player in package['players']:
        birthday = player['facts'].get('birth_date')
        if player.get('policy') == 'preserve-existing-mode1' or not isinstance(birthday, str):
            preserved += 1
            continue
        row = {'player_id': player['id'], 'carrier_id': player['carrier_id'],
               'name': player['name'], 'recipe_birth_date': birthday}
        checked += 1
        try:
            date.fromisoformat(birthday)
            entry = entries[player['carrier_id']]
            payload = entry.decode_payload(raw)
            native = roster.native_player(payload, player['carrier_id'])
            if roster.normalise(native['name']) != roster.normalise(player['name']):
                failures.append(dict(row, reason='native-person-name-disagrees', native_name=native['name']))
                continue
            end = native['name_end']
            day, month = payload[end+12] ^ 0x61, payload[end+13] ^ 0x61
            year = int.from_bytes(bytes(value ^ 0x61 for value in payload[end+14:end+16]), 'little')
            row['native_birth_components'] = {'year': year, 'month': month, 'day': day}
            observed = date(year, month, day).isoformat()
            if observed != birthday:
                failures.append(dict(row, reason='literal-recipe-native-birthday-mismatch', native_birth_date=observed))
        except (KeyError, ValueError) as exc:
            failures.append(dict(row, reason='native-or-recipe-birthday-unreadable', detail=str(exc)))
    return {'literal_players_checked': checked, 'preserved_date_gaps': preserved,
            'failure_count': len(failures), 'failures': failures,
            'scope': 'literal recipe/native conformance only; not independent source identity or runtime age clearance'}


def audit(season, release_id=None):
    release = registry.load_registered_release(season, release_id) if release_id else registry.load_preferred_release(season)
    package = json.loads(release.package_path.read_text())
    jug = release.game_path / 'DBDAT/JUG98030.FDI'
    result = inspect(package, jug.read_bytes())
    return {'season': season, 'release_id': release.release_id,
            'package_sha256': registry.sha256_file(release.package_path),
            'JUG_sha256': registry.sha256_file(jug), **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', default='all')
    parser.add_argument('--release-id')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('birth-date audit evidence is immutable')
    seasons = registry.supported_seasons() if args.season == 'all' else [pipeline.normalise_season_id(args.season)]
    rows = [audit(season, args.release_id) for season in seasons]
    result = {'schema_version': 'pm99-compiled-literal-player-birth-date-readback-v1',
              'seasons': rows, 'failure_count': sum(row['failure_count'] for row in rows),
              'scope': 'read-only conformance audit; findings are not automatic repair authorizations'}
    pipeline.write_canonical_json(args.output, result)
    print(json.dumps({'seasons': len(rows), 'failure_count': result['failure_count']}))


if __name__ == '__main__':
    main()
