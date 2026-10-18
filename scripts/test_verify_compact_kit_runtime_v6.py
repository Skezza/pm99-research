from pathlib import Path

import numpy as np
from PIL import Image
from scripts import verify_compact_kit_runtime_v6 as verify
from scripts import cascade_compact_kit_v6 as cascade


def test_rgb565_expansion_matches_observed_runner_channels():
    assert verify.rgb565([(128, 128, 100)]).tolist() == [[131, 129, 98]]


def test_genuine_corrected_pilot_matches_actual_pixels():
    root = Path(__file__).resolve().parents[1]
    result = verify.verify('2004-05', root / '.local/runlogs/pm99_runner/nano_v6_stoke_pilot_2004_05_20261004_a',
        root / '.local/kit-visual-forensics-v1/nano-v6-pilot-20261004/DBDAT')
    assert result['passed'], result
    assert result['candidate_dbdat'] is True


def test_wrong_palette_is_rejected_by_pixel_check(tmp_path):
    record = cascade.renderer._record_index(cascade.BASE / cascade.ARCHIVE)[2]
    palette, _ = cascade.renderer._palette(cascade.BASE)
    # Like the real palette chart: opaque blocks put slot 111 away from the
    # engine-blended transparent boundary, so the negative control is strict.
    from dataclasses import replace
    bitmap = verify.hem_renderer.boundary_renderer.recipe_renderer
    record = replace(record, raw_bitmap=bitmap.top_down_indices_to_raw(record, [[111] * 24 for _ in range(32)]))
    indices = np.asarray(verify.hem_renderer.boundary_renderer.recipe_renderer.record_to_top_down_indices(record))
    screen = np.zeros((480, 640, 3), dtype=np.uint8)
    screen[120:151, 481:505] = verify.rgb565(palette)[indices[:31]]
    path = tmp_path / 'screen.png'
    Image.fromarray(screen).save(path)
    assert verify.compare(record, palette, path)['passed']
    wrong = list(palette)
    wrong[111] = (10, 15, 0)
    assert not verify.compare(record, wrong, path)['passed']
