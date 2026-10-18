#!/usr/bin/env python3
"""Build an unregistered 256-index NANOESC calibration chart for the runner."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'upstream/pm99-skezmod-db-editor'))
from scripts import season_release_registry_v1 as registry
from scripts import patch_english80_reference_kits_v2 as bitmap
from app.minifoto_bitmap_archive import iter_obfuscated_bmp_records


def make(season, carrier, output, offset=0):
    release = registry.load_preferred_release(season)
    if output.exists():
        raise ValueError('requires a fresh diagnostic directory')
    output.resolve().relative_to(ROOT / '.local')
    dbdat = output / 'DBDAT'
    dbdat.mkdir(parents=True)
    for path in (release.game_path / 'DBDAT').iterdir():
        if path.is_file() and path.name != 'NANOESC.PKF':
            (dbdat / path.name).hardlink_to(path)
    source = release.game_path / 'DBDAT/NANOESC.PKF'
    data = source.read_bytes()
    record = next(r for r in iter_obfuscated_bmp_records(source)
                  if r.file_name == f'EQ96{carrier:04d}.BMP')
    if (record.width, record.height) != (24, 32):
        raise ValueError('unsupported small-icon dimensions')
    rows = [[(y * 8 + x // 3 + offset) % 256 for x in range(24)] for y in range(32)]
    payload = bitmap.top_down_indices_to_raw(record, rows)
    changed = bytearray(data)
    changed[record.bitmap_offset:record.bitmap_offset + record.bitmap_length] = payload
    (dbdat / 'NANOESC.PKF').write_bytes(changed)
    receipt = {'diagnostic_only': True, 'season': season, 'carrier_id': carrier,
        'original_archive_sha256': registry.sha256_file(source),
        'chart_archive_sha256': registry.sha256_file(dbdat / 'NANOESC.PKF'),
        'chart_layout': '8 columns x 32 rows; each index is three horizontal pixels',
        'index_offset': offset,
        'game_exe': str(release.game_path / 'MANAGPRE.EXE')}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season')
    parser.add_argument('--carrier', required=True, type=int)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--offset', type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(make(args.season, args.carrier, args.output, args.offset)))
