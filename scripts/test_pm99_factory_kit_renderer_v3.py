"""Deterministic checks for V3 native-boundary kit rendering."""

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
from scripts import pm99_factory_kit_renderer_v3 as renderer  # noqa: E402
from scripts.pm99_kit_palette_v1 import runtime_kit_palette  # noqa: E402
from scripts import patch_english80_reference_kits_v2 as recipe_renderer  # noqa: E402


DBDAT = ROOT / ".local" / "season-pipeline-v2" / "pm99-base-clean" / "DBDAT"


def _record(archive: str, carrier: int):
    records = iter_obfuscated_bmp_records(DBDAT / archive, file_name_pattern=rf"^EQ96{carrier:04d}\.BMP$")
    assert len(records) == 1
    return records[0]


def test_native_pattern_templates_are_explicit() -> None:
    for archive in ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF"):
        assert renderer.factory_template_carrier(archive, {"pattern": "vertical_stripes"}) == 2
        assert renderer.factory_template_carrier(archive, {"pattern": "hoops"}) == 1252
        assert renderer.factory_template_carrier(archive, {"pattern": "sleeves"}) == 309


def test_waist_valley_and_native_regions_are_observable() -> None:
    palette, _ = runtime_kit_palette(DBDAT)
    for archive, carrier in (("MINIESC.PKF", 2), ("NANOESC.PKF", 2), ("RIDIESC.PKF", 2)):
        record = _record(archive, carrier)
        rows = recipe_renderer.record_to_top_down_indices(record)
        mask = [[index != 0 for index in row] for row in rows]
        shirt_top, waist = renderer._shirt_top_and_waist(mask)
        widths = [sum(mask[y]) for y in range(len(mask))]
        assert shirt_top < waist < len(mask) - 1
        assert widths[waist] == min(widths[max(shirt_top + 1, round(len(mask) * 0.48)) : min(len(mask) - 1, round(len(mask) * 0.70)) + 1])
        regions = renderer._smoothed_native_regions(rows, palette, mask, shirt_top, waist)
        observed = {regions[y][x] for y in range(shirt_top, waist + 1) for x in range(len(rows[0]))}
        assert 0 in observed and 1 in observed


def test_native_boundary_render_is_deterministic_and_pixel_lane_only() -> None:
    palette, _ = runtime_kit_palette(DBDAT)
    styles = (
        {"pattern": "vertical_stripes", "colors": [[178, 48, 55], [224, 223, 223]], "shorts": [178, 48, 55]},
        {"pattern": "hoops", "colors": [[21, 28, 78], [145, 21, 64]], "shorts": [21, 28, 78]},
        {"pattern": "sleeves", "colors": [[224, 58, 63], [213, 210, 210]], "sleeves": [213, 210, 210], "shorts": [224, 58, 63]},
    )
    for archive in ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF"):
        for style in styles:
            target = _record(archive, 1)
            template = _record(archive, renderer.factory_template_carrier(archive, style))
            first = renderer.render_template_on_record(target, template, palette, style)
            second = renderer.render_template_on_record(target, template, palette, style)
            assert hashlib.sha256(first).digest() == hashlib.sha256(second).digest()
            assert validate_minifoto_bitmap(first).bitmap_length == validate_minifoto_bitmap(target.raw_bitmap).bitmap_length
            from app.bitmap_pixel_rows import bitmap_pixel_ranges
            allowed = {i for lo, hi in bitmap_pixel_ranges(target) for i in range(lo, hi)}
            assert all(a == b for i, (a, b) in enumerate(zip(first, target.raw_bitmap)) if i not in allowed)


def test_shirt_recipe_cannot_bleed_below_the_inferred_waist() -> None:
    """Use deliberately opposed colours to make a garment leak observable."""
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
    _shirt_top, waist = renderer._shirt_top_and_waist(mask)
    width, offset = int(record.width), int(record.pixel_offset)
    pixels = payload[offset : offset + width * int(record.height)]
    for y in range(waist + 2, int(record.height)):
        for x in range(width):
            index = pixels[(int(record.height) - 1 - y) * width + x]
            if not index:
                continue
            rgb = palette[index]
            if renderer._is_neutral_dark_structure(rgb):
                continue
            # The only non-structural garment base in the shorts region is
            # the green test colour after native luminance shading.
            assert rgb[1] >= rgb[0] and rgb[1] >= rgb[2]
