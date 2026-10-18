#!/usr/bin/env python3
"""Shared safe rasterisation primitives for PM99 compact-kit records.

PM99 compact-kit bitmaps are indexed OS/2 BMPs. Index zero is transparent;
the remaining indices are the game's own palette. Recolouring must preserve
the native record, its transparent silhouette, and its light/dark modelling.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from app.bitmap_pixel_rows import read_top_down_bitmap_rows, replace_top_down_bitmap_rows


Rgb = tuple[int, int, int]


def luminance(rgb: Rgb) -> float:
    return (0.299 * rgb[0]) + (0.587 * rgb[1]) + (0.114 * rgb[2])


def shade_rgb(rgb: Rgb, factor: float) -> Rgb:
    return tuple(max(0, min(255, int(round(channel * factor)))) for channel in rgb)  # type: ignore[return-value]


def nearest_nontransparent_palette_index(
    rgb: Rgb,
    palette: list[Rgb],
    cache: dict[Rgb, int] | None = None,
) -> int:
    """Map RGB to a visible palette entry; PM99 index zero is transparent."""
    if len(palette) < 2:
        raise ValueError("PM99 kit palette must have a non-transparent colour")
    if cache is not None and rgb in cache:
        return cache[rgb]
    index = min(
        range(1, len(palette)),
        key=lambda candidate: (
            (rgb[0] - palette[candidate][0]) ** 2
            + (rgb[1] - palette[candidate][1]) ** 2
            + (rgb[2] - palette[candidate][2]) ** 2,
            candidate,
        ),
    )
    if cache is not None:
        cache[rgb] = index
    return index


def _edge_pixel(mask: list[list[bool]], x: int, y: int) -> bool:
    height = len(mask)
    width = len(mask[0])
    for next_x, next_y in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
        if (
            next_x < 0
            or next_y < 0
            or next_x >= width
            or next_y >= height
            or not mask[next_y][next_x]
        ):
            return True
    return False


def rasterize_preserving_native_shading(
    record: Any,
    palette: list[Rgb],
    colour_at: Callable[[int, int], Rgb | None],
    *,
    nearest_cache: dict[Rgb, int] | None = None,
) -> bytes:
    """Apply historical colours while retaining native shading and outline.

    ``colour_at`` supplies the desired top-down colour, or ``None`` to retain
    the native pixel. The native indexed bitmap supplies the alpha mask and
    brightness variation. Bytes outside the pixel lane remain byte-identical,
    and a non-transparent pixel can never become transparent through palette
    quantisation.
    """
    width, height = int(record.width), int(record.height)
    pixel_offset = int(record.pixel_offset)
    pixel_count = width * height
    raw = bytes(record.raw_bitmap)
    if width <= 0 or height <= 0:
        raise ValueError("compact-kit record has an invalid indexed-pixel lane")
    source_rows = read_top_down_bitmap_rows(record)
    mask = [[index != 0 for index in row] for row in source_rows]
    top_down = bytearray(pixel_count)
    for y in range(height):
        for x in range(width):
            source_index = source_rows[y][x]
            if source_index == 0:
                continue
            desired_rgb = colour_at(x, y)
            if desired_rgb is None:
                top_down[y * width + x] = source_index
                continue
            if source_index >= len(palette):
                raise ValueError("compact-kit record references a palette index outside its palette")
            source_luma = max(0.0, min(255.0, luminance(palette[source_index])))
            factor = 0.82 + (source_luma / 255.0) * 0.35
            if _edge_pixel(mask, x, y):
                factor *= 0.90
            if y > height * 0.78:
                factor *= 0.96
            top_down[y * width + x] = nearest_nontransparent_palette_index(
                shade_rgb(desired_rgb, factor), palette, nearest_cache
            )

    return replace_top_down_bitmap_rows(record, [list(top_down[row * width:(row + 1) * width])
                                               for row in range(height)])
