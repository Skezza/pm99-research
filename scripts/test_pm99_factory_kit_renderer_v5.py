"""Deterministic checks for V5 factory tonal-depth transfer."""

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
from scripts import patch_english80_reference_kits_v2 as recipe_renderer  # noqa: E402
from scripts import pm99_factory_kit_renderer_v4 as v4_renderer  # noqa: E402
from scripts import pm99_factory_kit_renderer_v5 as renderer  # noqa: E402
from scripts.pm99_kit_palette_v1 import runtime_kit_palette  # noqa: E402


DBDAT = ROOT / ".local" / "season-pipeline-v2" / "pm99-base-clean" / "DBDAT"


def _record(archive: str, carrier: int):
    records = iter_obfuscated_bmp_records(DBDAT / archive, file_name_pattern=rf"^EQ96{carrier:04d}\.BMP$")
    assert len(records) == 1
    return records[0]


def _coloured_luminances(payload: bytes, record, palette) -> list[float]:
    shape = validate_minifoto_bitmap(payload)
    start = int(shape.pixel_offset)
    pixels = payload[start : start + int(shape.width) * int(shape.height)]
    result = []
    for index in pixels:
        if not index:
            continue
        rgb = palette[index]
        if renderer.hem_renderer.boundary_renderer._is_neutral_dark_structure(rgb):
            continue
        result.append(renderer.hem_renderer.boundary_renderer._luminance(rgb))
    return result


def test_tone_transfer_expands_runtime_luminance_range_over_v4() -> None:
    palette, _ = runtime_kit_palette(DBDAT)
    style = {"pattern": "solid", "colors": [[180, 25, 35]], "shorts": [25, 35, 110]}
    target = _record("MINIESC.PKF", 1)
    template = _record("MINIESC.PKF", renderer.factory_template_carrier("MINIESC.PKF", style))
    v4 = v4_renderer.render_template_on_record(target, template, palette, style)
    v5 = renderer.render_template_on_record(target, template, palette, style)
    v4_luma = _coloured_luminances(v4, target, palette)
    v5_luma = _coloured_luminances(v5, target, palette)
    assert max(v5_luma) - min(v5_luma) >= max(v4_luma) - min(v4_luma) + 15
    assert len({round(value, 3) for value in v5_luma}) > len({round(value, 3) for value in v4_luma})


def test_tone_transfer_is_ordered_and_reaches_shadow_and_highlight() -> None:
    base = (160, 40, 30)
    profile = (80.0, 160.0, 240.0)
    shadow = renderer._transfer_tone(base, 80.0, profile)
    middle = renderer._transfer_tone(base, 160.0, profile)
    highlight = renderer._transfer_tone(base, 240.0, profile)
    assert sum(shadow) < sum(middle) < sum(highlight)
    assert shadow[0] < base[0]
    assert highlight[1] > base[1] and highlight[2] > base[2]


def test_v5_is_deterministic_and_changes_only_target_pixel_lane() -> None:
    palette, _ = runtime_kit_palette(DBDAT)
    styles = (
        {"pattern": "solid", "colors": [[30, 80, 180]], "shorts": [245, 245, 245]},
        {"pattern": "vertical_stripes", "colors": [[220, 25, 25], [240, 240, 240]], "shorts": [20, 20, 20]},
        {"pattern": "hoops", "colors": [[25, 35, 120], [150, 25, 60]], "shorts": [25, 35, 120]},
        {"pattern": "sleeves", "colors": [[150, 20, 45], [245, 245, 245]], "sleeves": [245, 245, 245], "shorts": [245, 245, 245]},
    )
    for archive in ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF"):
        target = _record(archive, 1)
        for style in styles:
            template = _record(archive, renderer.factory_template_carrier(archive, style))
            first = renderer.render_template_on_record(target, template, palette, style)
            second = renderer.render_template_on_record(target, template, palette, style)
            assert hashlib.sha256(first).digest() == hashlib.sha256(second).digest()
            shape = validate_minifoto_bitmap(first)
            original = validate_minifoto_bitmap(target.raw_bitmap)
            assert shape.bitmap_length == original.bitmap_length
            from app.bitmap_pixel_rows import bitmap_pixel_ranges
            allowed = {i for lo, hi in bitmap_pixel_ranges(target) for i in range(lo, hi)}
            assert all(a == b for i, (a, b) in enumerate(zip(first, target.raw_bitmap)) if i not in allowed)


def test_v5_retains_v4_no_shirt_colour_below_native_hem() -> None:
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
    _top, waist = renderer.hem_renderer.boundary_renderer._shirt_top_and_waist(mask)
    hems = renderer.hem_renderer._hem_by_column(mask, waist)
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
            if renderer.hem_renderer.boundary_renderer._is_neutral_dark_structure(rgb):
                continue
            assert rgb[1] >= rgb[0] and rgb[1] >= rgb[2]
