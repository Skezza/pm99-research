#!/usr/bin/env python3
"""Measure the genuine TEAM RATING icon against its installed indexed bitmap.

The runner's 16-bit display expands RGB565 channels. Index zero is transparent,
the blitter blends the two-pixel silhouette edge, and the UI clips the bottom
sprite row. Exact colour measurements use the unblended garment interiors.
This proves displayed colours/geometry, not historical source accuracy.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'upstream/pm99-skezmod-db-editor'))
from scripts import season_kit_render_bindings_v1 as renderer
from scripts import season_release_registry_v1 as registry
from scripts import season_visual_patch_v1 as visual
from scripts.capture_registered_season_runtime_v1 import _selector
from scripts.pm99_factory_kit_renderer_v6 import hem_renderer


def rgb565(palette):
    values = np.asarray(palette, dtype=np.uint16)
    return np.stack(((values[:, 0] >> 3) * 255 // 31,
                     (values[:, 1] >> 2) * 255 // 63,
                     (values[:, 2] >> 3) * 255 // 31), axis=1).astype(np.int16)


def compare(record, palette, screenshot):
    full = np.asarray(hem_renderer.boundary_renderer.recipe_renderer.record_to_top_down_indices(record))
    if full.shape != (32, 24):
        raise ValueError('unsupported TEAM RATING bitmap dimensions')
    opaque = full != 0
    mask = opaque.copy()
    padded = np.pad(opaque, 2)
    for dy in range(5):
        for dx in range(5):
            mask &= padded[dy:dy + 32, dx:dx + 24]
    indices, mask = full[:31], mask[:31]
    if mask.sum() < 100:
        raise ValueError('too few unblended garment pixels for colour verification')
    expected = rgb565(palette)[indices]
    observed = np.asarray(Image.open(screenshot).convert('RGB'), dtype=np.int16)
    if observed.shape[:2] != (480, 640):
        raise ValueError('unsupported runner screenshot dimensions')
    best = None
    for y in range(112, 125):
        for x in range(473, 487):
            errors = np.abs(observed[y:y + 31, x:x + 24] - expected)[mask]
            candidate = (float(errors.mean()), x, y, int(errors.max()))
            if best is None or candidate < best:
                best = candidate
    mean, x, y, maximum = best
    return {'passed': maximum <= 4, 'position': [x, y], 'compared_interior_pixels': int(mask.sum()),
            'visible_opaque_pixels': int((indices != 0).sum()),
            'mean_channel_error': mean, 'maximum_channel_error': maximum,
            'excluded': ['transparent index 0', 'two-pixel engine-blended silhouette boundary',
                         'bottom row clipped by game UI'],
            'comparison': 'decoded native BMP versus actual runner RGB565 pixels'}


def verify(season, evidence, dbdat=None):
    release = registry.load_preferred_release(season)
    selector = _selector(season)
    clubs = json.loads(release.package_path.read_text())['clubs']
    if season == '2015-16':
        clubs += json.loads((ROOT / 'seasons/2015-16/english-layer/season-package.legacy.json').read_text())['clubs']
    matches = [c for c in clubs if c['name'] == selector['team_name']]
    if len(matches) != 1:
        raise ValueError('recipe needs exactly one club matching the runner selector')
    carrier = int(matches[0]['carrier_id'])
    dbdat = dbdat or release.game_path / 'DBDAT'
    # A disposable DBDAT override has no root DAT.PKF; the runner keeps the
    # original game-root resource, which is the release's verified palette.
    palette, palette_source = renderer._palette(release.game_path / 'DBDAT')
    record = renderer._record_index(dbdat / 'NANOESC.PKF')[int(carrier)]
    screenshots = list((evidence / 'screens').glob('*line_up_inspect*.png'))
    if len(screenshots) != 1:
        raise ValueError('expected one real Line-Up inspect screenshot')
    summary = json.loads((evidence / 'summary.json').read_text())
    if not summary.get('success') or summary.get('phase_reached') != 'return_from_line_up':
        raise ValueError('runner route did not complete')
    result = compare(record, palette, screenshots[0])
    result.update(season=season, carrier_id=carrier, screenshot=str(screenshots[0]),
                  screenshot_sha256=visual.sha(screenshots[0]), palette=palette_source,
                  bitmap_sha256=renderer.sha256_bytes(record.raw_bitmap),
                  archive_sha256=visual.sha(dbdat / 'NANOESC.PKF'),
                  release_id=release.release_id, candidate_dbdat=dbdat != release.game_path / 'DBDAT')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season')
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--dbdat', type=Path, help='explicit unregistered diagnostic candidate')
    args = parser.parse_args()
    result = verify(args.season, args.evidence, args.dbdat)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 2)
