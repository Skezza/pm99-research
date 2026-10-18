#!/usr/bin/env python3
"""Count actual portraits by native playable/non-playable ownership.

This is availability/bitmap-shape evidence, not approval of face identity or
shooting date. The bounded output retains counts and examples, not another
300,000-row export or a copy of game assets.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'upstream/pm99-skezmod-db-editor'))
from app.minifoto_bitmap_archive import iter_minifoto_records, validate_minifoto_bitmap
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_package_compiler_v2 as compiler
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.audit_registered_visual_assets_v1 import invalid_photo_entries


def ownership_group(clubs, modes, declarations):
    if any(modes.get(club) == 0 for club in clubs):
        return 'playable'
    groups = {roster.club_group(declarations[club]) for club in clubs if club in declarations}
    if len(groups) != 1 or None in groups:
        return 'non-playable-unclassified'
    return 'non-playable-english' if groups == {'england'} else 'non-playable-overseas'


def run(output):
    if output.exists():
        raise ValueError('portrait coverage evidence is immutable; use a fresh path')
    archive_cache = {}
    seasons = []
    for season in registry.supported_seasons():
        release = registry.load_preferred_release(season)
        players, clubs, layers = {}, {}, []
        for layer, package, path in planner.package_layers(release):
            players.update({p['carrier_id']: p for p in package['players']})
            clubs.update({c['carrier_id']: c for c in package['clubs']})
            layers.append({'layer': layer, 'path': registry.relative_workspace_path(path),
                           'sha256': registry.sha256_file(path)})
        dbdat = release.game_path / 'DBDAT'
        eq_path = dbdat / 'EQ98030.FDI'
        owners, _, modes = compiler._source_roster_owners(eq_path.read_bytes())
        archive_path = dbdat / 'MINIFOTO.PKF'
        digest = registry.sha256_file(archive_path)
        if digest not in archive_cache:
            decoded = {r.player_record_id for r in iter_minifoto_records(archive_path)}
            archive_cache[digest] = (decoded, invalid_photo_entries(archive_path, decoded))
        decoded, invalid = archive_cache[digest]
        counts = collections.defaultdict(collections.Counter)
        examples = collections.defaultdict(list)
        for carrier, native_clubs in sorted(owners.items()):
            group = ownership_group(native_clubs, modes, clubs)
            loose = dbdat / f'MINIFOTO/J96{carrier:05d}.BMP'
            status = 'missing'
            if loose.is_file():
                try:
                    validate_minifoto_bitmap(loose.read_bytes())
                    status = 'loose-bitmap-present-identity-unverified'
                except ValueError:
                    status = 'invalid-loose-bitmap'
            elif carrier in decoded:
                status = 'archived-bitmap-present-identity-unverified'
            elif carrier in invalid:
                status = 'invalid-active-archived-bitmap'
            counts[group][status] += 1
            if status == 'missing' and len(examples[group]) < 10:
                player = players.get(carrier, {})
                examples[group].append({'carrier_id': carrier,
                    'name': player.get('source_name') or player.get('name'),
                    'birth_date': player.get('facts', {}).get('birth_date'),
                    'clubs': [clubs.get(c, {}).get('name') for c in native_clubs]})
        row = {'season': season, 'release_id': release.release_id, 'layers': layers,
            'eq_sha256': registry.sha256_file(eq_path), 'minifoto_sha256': digest,
            'distinct_rostered_carriers': len(owners),
            'groups': {key: dict(value) for key, value in sorted(counts.items())},
            'missing_examples': dict(examples)}
        seasons.append(row)
        print(json.dumps({key: row[key] for key in ('season', 'groups')}), flush=True)
    totals = collections.defaultdict(collections.Counter)
    for row in seasons:
        for group, counts in row['groups'].items():
            totals[group].update(counts)
    result = {'schema_version': 'pm99-current-native-portrait-coverage-v1',
        'scope': 'All native rostered carriers; physical availability and valid bitmap structure, NOT face identity/date approval',
        'implementation_sha256': registry.sha256_file(Path(__file__)),
        'totals': {key: dict(value) for key, value in sorted(totals.items())}, 'seasons': seasons}
    pipeline.write_canonical_json(output, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)
