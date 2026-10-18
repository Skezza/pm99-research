from pathlib import Path
from scripts import pm99_factory_kit_renderer_v6 as renderer
from scripts.pm99_kit_palette_v1 import runtime_kit_palette
from app.minifoto_bitmap_archive import iter_obfuscated_bmp_records

ROOT = Path(__file__).resolve().parents[1]
DBDAT = ROOT / '.local/season-pipeline-v2/pm99-base-clean/DBDAT'


def test_tiny_stripes_keep_the_factory_chromatic_panels_and_white_shorts():
    palette, _ = runtime_kit_palette(DBDAT)
    record = next(r for r in iter_obfuscated_bmp_records(DBDAT / 'NANOESC.PKF')
                  if r.file_name == 'EQ960002.BMP')
    style = {'pattern': 'vertical_stripes', 'colors': ['white', 'red'], 'shorts': 'white'}
    payload = renderer.render_record(record, palette, style)
    bitmap = renderer.hem_renderer.boundary_renderer.recipe_renderer
    rows = bitmap.record_to_top_down_indices(record)
    mask = [[i != 0 for i in row] for row in rows]
    native = renderer.hem_renderer.boundary_renderer
    top, waist = native._shirt_top_and_waist(mask)
    regions = native._smoothed_native_regions(rows, palette, mask, top, waist, smoothing_passes=0)
    raw = payload[record.pixel_offset:record.pixel_offset + record.width * record.height]
    output = [list(raw[(record.height - 1 - y) * record.width:(record.height - y) * record.width])
              for y in range(record.height)]
    red_pixels = 0
    for y in range(top, waist):
        for x in range(record.width):
            if regions[y][x] == 1:
                r, g, b = palette[output[y][x]]
                assert r > g and r > b, (x, y, (r, g, b))
                red_pixels += 1
    assert red_pixels > 60
    assert payload[:record.pixel_offset] == record.raw_bitmap[:record.pixel_offset]
    assert len(payload) == len(record.raw_bitmap)
    assert [i == 0 for i in raw] == [i == 0 for i in record.raw_bitmap[record.pixel_offset:record.pixel_offset + record.width * record.height]]
    hems = renderer.hem_renderer._hem_by_column(mask, waist)
    for y, row in enumerate(output):
        for x, i in enumerate(row):
            if i and y > hems[x] + 1:
                colour = palette[i]
                assert max(colour) - min(colour) <= 16
    assert renderer.render_record(record, palette, style) == payload
