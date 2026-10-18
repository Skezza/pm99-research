from types import SimpleNamespace

from scripts import pm99_kit_raster_v1 as raster


def _record() -> SimpleNamespace:
    width = height = 6
    top_down = [
        [0, 2, 10, 20, 30, 0],
        [2, 10, 20, 30, 40, 50],
        [10, 20, 30, 40, 50, 2],
        [20, 30, 40, 50, 2, 10],
        [30, 40, 50, 2, 10, 20],
        [0, 50, 2, 10, 20, 0],
    ]
    pixels = b"".join(bytes(row) for row in reversed(top_down))
    return SimpleNamespace(
        width=width,
        height=height,
        pixel_offset=4,
        raw_bitmap=b"head" + pixels + b"tail",
    )


def _top_down(record: SimpleNamespace, payload: bytes) -> list[list[int]]:
    pixels = payload[record.pixel_offset : record.pixel_offset + record.width * record.height]
    return [
        list(pixels[(record.height - 1 - y) * record.width : (record.height - y) * record.width])
        for y in range(record.height)
    ]


def test_raster_retains_transparency_container_and_native_shading() -> None:
    record = _record()
    palette = [(0, 0, 0), *[(value, 0, 0) for value in range(5, 256, 5)]]

    payload = raster.rasterize_preserving_native_shading(
        record,
        palette,
        lambda _x, _y: (190, 0, 0),
    )

    original = _top_down(record, record.raw_bitmap)
    rendered = _top_down(record, payload)
    assert payload[: record.pixel_offset] == record.raw_bitmap[: record.pixel_offset]
    assert payload[-4:] == record.raw_bitmap[-4:]
    assert all(
        (rendered[y][x] == 0) == (original[y][x] == 0)
        for y in range(record.height)
        for x in range(record.width)
    )
    visible = {rendered[y][x] for y in range(record.height) for x in range(record.width) if rendered[y][x]}
    assert len(visible) >= 3
    assert 0 not in visible
