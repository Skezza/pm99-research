#!/usr/bin/env python3
"""Compare installed native portrait pixels to a genuine named-player runner screen."""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_portrait_pipeline_v1 as portraits
from scripts import season_release_registry_v1 as registry
from scripts import season_visual_patch_v1 as art
from scripts.pm99_kit_palette_v1 import runtime_kit_palette
from scripts.verify_compact_kit_runtime_v6 import rgb565


def compare(expected, screenshot):
    if screenshot.shape != (480, 640, 3):
        raise ValueError('unsupported runner screenshot geometry')
    if expected.shape != (32, 32, 3):
        raise ValueError('unsupported profile portrait geometry')
    area = screenshot[:48, 570:640]
    search = cv2.matchTemplate(area.astype('float32'), expected.astype('float32'), cv2.TM_SQDIFF)
    _, _, (x, y), _ = cv2.minMaxLoc(search)
    x += 570
    error = np.abs(expected.astype('int16') - screenshot[y:y+32, x:x+32].astype('int16'))
    return {'passed': int(error.max()) <= 4, 'bounds': [x, y, 32, 32],
            'compared_pixels': 1024, 'exact_pixels': int((error.max(axis=2) == 0).sum()),
            'mean_channel_error': float(error.mean()), 'maximum_channel_error': int(error.max())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', required=True)
    parser.add_argument('--carrier-id', type=int, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    release = registry.load_preferred_release(args.season)
    summary = json.loads((args.evidence / 'summary.json').read_text())
    if not summary['success'] or not summary['player_profile']['expected_name_token_satisfied']:
        raise ValueError('runner did not pass the requested player-name check')
    screenshot = args.evidence / 'screens' / Path(summary['player_profile']['screenshot']).name
    bitmap = release.game_path / 'DBDAT/MINIFOTO' / f'J96{args.carrier_id:05d}.BMP'
    provenance = json.loads((args.evidence / 'input-provenance.json').read_text())
    matches = [r for r in provenance['replacements'] if int(r['carrier_id']) == args.carrier_id]
    if len(matches) != 1 or art.sha(bitmap) != matches[0]['bitmap_sha256']:
        raise ValueError('named portrait bytes no longer match the runner input')
    row = matches[0]
    players = [p for p in json.loads(release.package_path.read_text())['players']
               if int(p['carrier_id']) == args.carrier_id]
    if (len(players) != 1 or players[0]['name'] != row['name']
            or players[0]['facts']['birth_date'] != row['birth_date']):
        raise ValueError('recipe identity changed since the photo probe')
    raw = bitmap.read_bytes()
    shape = portraits.validate_minifoto_bitmap(raw)
    if (shape.width, shape.height) != (32, 32):
        raise ValueError('unsupported portrait dimensions')
    indices = np.frombuffer(raw[shape.pixel_offset:shape.pixel_offset + shape.pixel_length], dtype=np.uint8).reshape(32, 32)[::-1]
    palette, source = runtime_kit_palette(release.game_path / 'DBDAT')
    result = compare(rgb565(palette)[indices], np.asarray(Image.open(screenshot).convert('RGB')))
    result.update(season=args.season, carrier_id=args.carrier_id, name=row['name'],
                  bitmap_sha256=art.sha(bitmap), screenshot=str(screenshot), screenshot_sha256=art.sha(screenshot),
                  palette=source, palette_sha256=art.sha(Path(source['path'])),
                  scope='named-player source/recipe/BMP/display binding; not biometric recognition or certification of all player facts')
    art.save(args.output, result)
    print(json.dumps(result))
    return int(not result['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
