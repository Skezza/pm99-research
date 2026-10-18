from types import SimpleNamespace

from scripts.pm99_compact_kit_template_v1 import render, transparency_mask


def _record() -> SimpleNamespace:
    width, height, offset = 48, 64, 4
    return SimpleNamespace(width=width, height=height, pixel_offset=offset, raw_bitmap=b"head" + bytes([4]) * (width * height) + b"tail")


def test_centred_template_replaces_only_the_pixel_lane_and_is_centred() -> None:
    record = _record()
    palette = [(0, 0, 0), *[(value, value, value) for value in range(1, 256)]]
    payload = render(record, palette, {"pattern": "solid", "colors": [[220, 20, 30]], "shorts": [20, 30, 160], "trim": None})
    assert payload[:4] == b"head"
    assert payload[-4:] == b"tail"
    pixels = payload[4:-4]
    top_down = b"".join(reversed([pixels[row * 48 : (row + 1) * 48] for row in range(64)]))
    assert [value == 0 for value in top_down] == transparency_mask(48, 64)
    visible_x = [x for y in range(64) for x in range(48) if top_down[y * 48 + x]]
    assert min(visible_x) >= 5 and max(visible_x) <= 41
