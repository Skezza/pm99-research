#!/usr/bin/env python3
"""Render a centred, front-facing PM99 shirt-and-shorts icon.

Legacy carrier records contain unrelated, inconsistent player artwork.  A
modern kit cannot be safely centred within those silhouettes.  This module
keeps each record's OS/2 BMP container untouched while replacing only its
indexed pixel lane with the same deliberately simple PM99-scale shirt and
shorts illustration.
"""

from __future__ import annotations

from typing import Any, Mapping

from PIL import Image, ImageDraw

from scripts import patch_english80_reference_kits_v2 as renderer


TEMPLATE_ID = "pm99-centred-front-shirt-and-shorts-v1"


def _scale_points(width: int, height: int, points: tuple[tuple[int, int], ...]) -> list[tuple[int, int]]:
    return [
        (max(0, min(width - 1, round(x * (width - 1) / 47))), max(0, min(height - 1, round(y * (height - 1) / 63))))
        for x, y in points
    ]


def _mask(width: int, height: int, points: tuple[tuple[int, int], ...]) -> list[list[bool]]:
    image = Image.new("1", (width, height), 0)
    ImageDraw.Draw(image).polygon(_scale_points(width, height, points), fill=1)
    return [[bool(image.getpixel((x, y))) for x in range(width)] for y in range(height)]


def masks(width: int, height: int) -> tuple[list[list[bool]], list[list[bool]]]:
    """Return deterministic shirt and shorts masks scaled from a 48x64 icon."""
    if width < 4 or height < 4:
        raise ValueError("compact-kit dimensions are too small for the centred template")
    shirt = _mask(
        width,
        height,
        (
            (17, 3), (30, 3), (33, 6), (41, 10), (39, 25), (33, 23),
            (33, 38), (14, 38), (14, 23), (8, 25), (6, 10), (14, 6),
        ),
    )
    shorts = _mask(
        width,
        height,
        (
            (14, 37), (33, 37), (35, 47), (30, 51), (30, 60), (25, 60),
            (24, 51), (23, 51), (22, 60), (17, 60), (17, 51), (12, 47),
        ),
    )
    return shirt, shorts


def _edge(mask: list[list[bool]], x: int, y: int) -> bool:
    height, width = len(mask), len(mask[0])
    return any(
        nx < 0 or ny < 0 or nx >= width or ny >= height or not mask[ny][nx]
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
    )


def _bounds(mask: list[list[bool]], y: int) -> tuple[int, int] | None:
    xs = [x for x, selected in enumerate(mask[y]) if selected]
    return (min(xs), max(xs)) if xs else None


def render(record: Any, palette: list[tuple[int, int, int]], style: Mapping[str, Any]) -> bytes:
    """Render ``style`` into a fresh centred shirt-and-shorts pixel lane."""
    width, height = int(record.width), int(record.height)
    offset = int(record.pixel_offset)
    count = width * height
    raw = bytes(record.raw_bitmap)
    if width <= 0 or height <= 0 or len(raw) < offset + count:
        raise ValueError("compact-kit record has an invalid indexed pixel lane")
    shirt, shorts = masks(width, height)
    mapper = renderer.PaletteMapper(palette)
    top_down = bytearray(count)
    shirt_top = max(0, round(3 * (height - 1) / 63))
    shirt_bottom = max(shirt_top, round(38 * (height - 1) / 63))
    shorts_rgb = renderer.color_rgb(style.get("shorts") if style.get("shorts") is not None else "white")
    for y in range(height):
        bounds = _bounds(shirt, y)
        for x in range(width):
            if shirt[y][x]:
                if bounds is None:
                    continue
                row_min, row_max = bounds
                row_width = max(1, row_max - row_min + 1)
                row_center = (row_min + row_max) / 2.0
                rgb = renderer.style_color(dict(style), x, y, row_min, row_max, shirt_top, shirt_bottom)
                rgb = renderer.apply_detail_overlays(
                    rgb, dict(style), x, y, row_min, row_max, row_center, row_width, shirt_top, shirt_bottom
                )
                factor = 0.72 if _edge(shirt, x, y) else 1.0
                top_down[y * width + x] = mapper.nearest(renderer.shade_rgb(rgb, factor))
            elif shorts[y][x]:
                factor = 0.72 if _edge(shorts, x, y) else 1.0
                top_down[y * width + x] = mapper.nearest(renderer.shade_rgb(shorts_rgb, factor))
    output = bytearray(raw)
    output[offset : offset + count] = b"".join(
        reversed([top_down[row * width : (row + 1) * width] for row in range(height)])
    )
    return bytes(output)


def transparency_mask(width: int, height: int) -> list[bool]:
    shirt, shorts = masks(width, height)
    return [not (shirt[y][x] or shorts[y][x]) for y in range(height) for x in range(width)]
