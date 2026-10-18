"""Deterministic checks for V4's native right-hem contour."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import iter_obfuscated_bmp_records, validate_minifoto_bitmap  # noqa: E402
from scripts import pm99_factory_kit_renderer_v4 as renderer  # noqa: E402
from scripts.pm99_kit_palette_v1 import runtime_kit_palette  # noqa: E402
from scripts import patch_english80_reference_kits_v2 as recipe_renderer  # noqa: E402


DBDAT = ROOT / ".local" / "season-pipeline-v2" / "pm99-base-clean" / "DBDAT"


def _record(archive: str, carrier: int):
    records = iter_obfuscated_bmp_records(DBDAT / archive, file_name_pattern=rf"^EQ96{carrier:04d}\.BMP$")
    assert len(records) == 1
    return records[0]


def test_native_right_hem_is_smooth_and_bounded() -> None:
    for archive in ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF"):
        record = _record(archive, 1252)
        rows = recipe_renderer.record_to_top_down_indices(record)
        mask = [[index != 0 for index in row] for row in rows]
        _top, waist = renderer.boundary_renderer._shirt_top_and_waist(mask)
        hems = renderer._hem_by_column(mask, waist)
        assert len(hems) == int(record.width)
        assert all(waist - 2 <= hem <= waist for hem in hems)
        assert all(abs(right - left) <= 1 for left, right in zip(hems, hems[1:]))
        bounds = renderer.boundary_renderer._row_bounds(mask, waist)
        assert bounds is not None
        _left, right = bounds
        assert hems[right] < waist


def test_right_hem_render_is_deterministic_and_pixel_lane_only() -> None:
    palette, _ = runtime_kit_palette(DBDAT)
    style = {
        "pattern": "hoops",
        "colors": [[21, 28, 78], [145, 21, 64]],
        "shorts": [21, 28, 78],
    }
    for archive in ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF"):
        target = _record(archive, 1)
        template = _record(archive, renderer.factory_template_carrier(archive, style))
        first = renderer.render_template_on_record(target, template, palette, style)
        second = renderer.render_template_on_record(target, template, palette, style)
        assert hashlib.sha256(first).digest() == hashlib.sha256(second).digest()
        assert validate_minifoto_bitmap(first).bitmap_length == validate_minifoto_bitmap(target.raw_bitmap).bitmap_length
        from app.bitmap_pixel_rows import bitmap_pixel_ranges
        allowed = {i for lo, hi in bitmap_pixel_ranges(target) for i in range(lo, hi)}
        assert all(a == b for i, (a, b) in enumerate(zip(first, target.raw_bitmap)) if i not in allowed)


def test_per_column_hem_prevents_shirt_colour_leaking_into_shorts() -> None:
    palette, _ = runtime_kit_palette(DBDAT)
    record = _record("MINIESC.PKF", 2)
    style = {
        "pattern": "vertical_stripes",
        "colors": [[238, 24, 24], [238, 238, 238]],
        "shorts": [16, 176, 56],
    }
    payload = renderer.render_record(record, palette, style)
    rows = recipe_renderer.record_to_top_down_indices(record)
    mask = [[index != 0 for index in row] for row in rows]
    _top, waist = renderer.boundary_renderer._shirt_top_and_waist(mask)
    hems = renderer._hem_by_column(mask, waist)
    width, offset = int(record.width), int(record.pixel_offset)
    pixels = payload[offset : offset + width * int(record.height)]
    for y in range(int(record.height)):
        for x in range(width):
            if y <= hems[x] + 1:
                continue
            index = pixels[(int(record.height) - 1 - y) * width + x]
            if not index:
                continue
            rgb = palette[index]
            if renderer.boundary_renderer._is_neutral_dark_structure(rgb):
                continue
            assert rgb[1] >= rgb[0] and rgb[1] >= rgb[2]
