"""Structure-aware factory-kit renderer with native garment-boundary vision.

V2 selected a pattern-matched original PM99 illustration, but still painted a
simple recipe across every row of that silhouette.  At 48x64 pixels that can
make shoulder stripes expand with the sleeve outline and can soften the
shirt/shorts separation.

V3 keeps the safe V1/V2 byte contract but derives two small visual facts from
the selected *original* template at render time:

* an Otsu-colour-segmented native pattern field, smoothed inside the shirt;
  this follows PM99's existing shoulder and sleeve contours instead of
  calculating fresh bands from each row's changing width; and
* a waist seam from the silhouette's row-width valley, with a restrained
  native-luminance crease.  Shorts are never painted with the shirt recipe.

No modern source pixels are projected.  The dated source is still only a
reviewable colour/pattern recipe, while the original PM99 art supplies the
pixel geometry.
"""

from __future__ import annotations

from typing import Any

from scripts import patch_english80_reference_kits_v2 as recipe_renderer
from scripts.pm99_factory_kit_renderer_v1 import (
    _is_neutral_dark_structure,
    _luminance,
    _shade,
)
from scripts.pm99_factory_kit_renderer_v2 import FACTORY_TEMPLATE_BY_ARCHIVE_PATTERN, factory_template_carrier


RENDERER_ID = "pm99-factory-template-kit-v3-native-boundaries"
CV_POLICY = "template-chroma-otsu-with-two-pass-majority-smoothing-and-silhouette-waist-valley"
_NATIVE_PATTERN_TYPES = {"vertical_stripes", "hoops", "sleeves"}


def _row_bounds(mask: list[list[bool]], y: int) -> tuple[int, int] | None:
    return recipe_renderer.row_bounds(mask, y)


def _shirt_top_and_waist(mask: list[list[bool]]) -> tuple[int, int]:
    """Find the native shirt top and the shirt/shorts waist seam.

    The reviewed factory silhouettes have a clear narrow waist before the
    shorts widen.  Selecting the *last* equal-width valley keeps the entire
    lower shirt panel above the shorts while avoiding a hard-coded pixel row.
    """
    height = len(mask)
    nonzero = [y for y, row in enumerate(mask) if any(row)]
    if not nonzero:
        return 0, 0
    first_y, last_y = min(nonzero), max(nonzero)
    shirt_top = max(first_y, int(round(height * 0.05)))
    search_start = max(shirt_top + 1, int(round(height * 0.48)))
    search_end = min(last_y - 1, int(round(height * 0.70)))
    if search_start > search_end:
        return shirt_top, min(last_y, int(round(height * 0.62)) - 1)
    widths = {y: sum(mask[y]) for y in range(search_start, search_end + 1)}
    # Row width is a stable silhouette observation, unlike a source-kit
    # colour.  The last matching valley is the lower edge of the shirt.
    waist = min(widths, key=lambda y: (widths[y], -y))
    return shirt_top, waist


def _otsu_threshold(values: list[int]) -> int:
    """Return a deterministic 8-bit Otsu split without an OpenCV dependency."""
    if not values:
        return 32
    histogram = [0] * 256
    for value in values:
        histogram[max(0, min(255, int(value)))] += 1
    total = len(values)
    total_sum = sum(index * count for index, count in enumerate(histogram))
    weight_background = sum_background = 0
    best_threshold, best_variance = 32, -1.0
    for threshold, count in enumerate(histogram):
        weight_background += count
        if weight_background == 0:
            continue
        weight_foreground = total - weight_background
        if weight_foreground == 0:
            break
        sum_background += threshold * count
        mean_background = sum_background / weight_background
        mean_foreground = (total_sum - sum_background) / weight_foreground
        variance = weight_background * weight_foreground * (mean_background - mean_foreground) ** 2
        if variance > best_variance:
            best_threshold, best_variance = threshold, variance
    # Very low thresholds classify ordinary anti-aliasing as a kit colour;
    # very high thresholds erase a genuine coloured panel.  These conservative
    # limits were checked against the reviewed native template catalogue.
    return max(24, min(132, best_threshold))


def _smoothed_native_regions(
    rows: list[list[int]],
    palette: list[tuple[int, int, int]],
    mask: list[list[bool]],
    shirt_top: int,
    waist: int,
    *,
    smoothing_passes: int = 2,
) -> list[list[int | None]]:
    """Segment native coloured versus neutral fabric and remove one-pixel noise.

    Values are ``1`` for the template's chromatic garment panel and ``0`` for
    its neutral panel. ``None`` marks transparent pixels and protected line
    work.  Two majority passes are intentionally small: they repair colour
    speckles but cannot redraw a native shoulder contour.
    """
    height = len(rows)
    width = len(rows[0]) if height else 0
    chroma_values: list[int] = []
    for y in range(shirt_top, waist + 1):
        for x in range(width):
            index = rows[y][x]
            if not index:
                continue
            rgb = palette[index]
            if _is_neutral_dark_structure(rgb):
                continue
            chroma_values.append(max(rgb) - min(rgb))
    threshold = _otsu_threshold(chroma_values)
    regions: list[list[int | None]] = [[None for _x in range(width)] for _y in range(height)]
    for y in range(shirt_top, waist + 1):
        for x in range(width):
            index = rows[y][x]
            if not index:
                continue
            rgb = palette[index]
            if _is_neutral_dark_structure(rgb):
                continue
            regions[y][x] = int((max(rgb) - min(rgb)) > threshold)
    for _pass in range(smoothing_passes):
        next_regions = [list(row) for row in regions]
        for y in range(shirt_top + 1, waist):
            for x in range(1, width - 1):
                current = regions[y][x]
                if current is None:
                    continue
                neighbours = [
                    regions[ny][nx]
                    for ny in range(y - 1, y + 2)
                    for nx in range(x - 1, x + 2)
                    if (nx, ny) != (x, y) and regions[ny][nx] is not None
                ]
                if len(neighbours) < 5:
                    continue
                alternate = 1 - int(current)
                if sum(value == alternate for value in neighbours) >= 5:
                    next_regions[y][x] = alternate
        regions = next_regions
    return regions


def _chroma(rgb: tuple[int, int, int]) -> int:
    return max(rgb) - min(rgb)


def _native_pattern_colour(
    style_row: dict[str, Any], pattern: str, native_region: int | None
) -> tuple[int, int, int] | None:
    colours = [recipe_renderer.color_rgb(value) for value in style_row.get("colors", ("white",))]
    if pattern in {"vertical_stripes", "hoops"} and len(colours) >= 2 and native_region is not None:
        # Map the template's chromatic panel to the source recipe's more
        # chromatic colour.  This makes blue/white and white/blue sources land
        # on the same natural PM99 stripe geometry instead of arbitrarily
        # reversing at the shoulder.
        high_index = max(range(len(colours)), key=lambda index: (_chroma(colours[index]), -index))
        low_index = min(range(len(colours)), key=lambda index: (_chroma(colours[index]), index))
        return colours[high_index] if native_region else colours[low_index]
    if pattern == "sleeves" and native_region is not None:
        body = colours[0]
        sleeve = recipe_renderer.color_rgb(style_row.get("sleeves") if style_row.get("sleeves") is not None else colours[-1])
        return body if native_region else sleeve
    return None


def render_rows(
    rows: list[list[int]],
    palette: list[tuple[int, int, int]],
    mapper: recipe_renderer.PaletteMapper,
    style_row: dict[str, Any],
) -> list[list[int]]:
    """Render a dated recipe using native pattern and garment-boundary masks."""
    height = len(rows)
    if height == 0:
        return []
    width = len(rows[0])
    mask = [[index != 0 for index in row] for row in rows]
    if not any(any(row) for row in mask):
        return [list(row) for row in rows]
    shirt_top, waist = _shirt_top_and_waist(mask)
    pattern = str(style_row.get("pattern", "solid"))
    native_regions = _smoothed_native_regions(rows, palette, mask, shirt_top, waist)
    shorts_rgb = recipe_renderer.color_rgb(style_row.get("shorts") or "white")
    out = [list(row) for row in rows]
    for y, row in enumerate(rows):
        bounds = _row_bounds(mask, y)
        if bounds is None:
            continue
        row_min, row_max = bounds
        row_center = (row_min + row_max) / 2.0
        row_width = max(1, row_max - row_min + 1)
        for x, original_index in enumerate(row):
            if original_index == 0:
                out[y][x] = 0
                continue
            original_rgb = palette[original_index]
            if _is_neutral_dark_structure(original_rgb):
                out[y][x] = original_index
                continue
            if y <= waist:
                base_rgb = _native_pattern_colour(style_row, pattern, native_regions[y][x])
                if base_rgb is None:
                    base_rgb = recipe_renderer.style_color(
                        style_row, x, y, row_min, row_max, shirt_top, waist
                    )
                    base_rgb = recipe_renderer.apply_detail_overlays(
                        base_rgb,
                        style_row,
                        x,
                        y,
                        row_min,
                        row_max,
                        row_center,
                        row_width,
                        shirt_top,
                        waist,
                    )
            else:
                base_rgb = shorts_rgb
            factor = 0.66 + (max(0.0, min(255.0, _luminance(original_rgb))) / 255.0) * 0.42
            if recipe_renderer.edge_pixel(mask, x, y):
                factor *= 0.94
            # The row-width valley is the native waist.  Darkening only the
            # two seam rows preserves a readable garment cut without creating
            # an artificial graphic stripe or recolouring either garment.
            if y in {waist, waist + 1}:
                factor *= 0.76
            shaded = tuple(
                max(0, min(255, int(round(channel * factor)))) for channel in base_rgb
            )
            out[y][x] = mapper.nearest(shaded)
    return out


def render_record(record: Any, palette: list[tuple[int, int, int]], style_row: dict[str, Any]) -> bytes:
    rows = recipe_renderer.record_to_top_down_indices(record)
    mapper = recipe_renderer.PaletteMapper(palette)
    return recipe_renderer.top_down_indices_to_raw(record, render_rows(rows, palette, mapper, style_row))


def render_template_on_record(target_record: Any, template_record: Any, palette: list[tuple[int, int, int]], style_row: dict[str, Any]) -> bytes:
    target_size = (int(target_record.width), int(target_record.height))
    template_size = (int(template_record.width), int(template_record.height))
    if target_size != template_size:
        raise ValueError(f"factory template dimensions {template_size} do not fit target {target_size}")
    rows = recipe_renderer.record_to_top_down_indices(template_record)
    mapper = recipe_renderer.PaletteMapper(palette)
    return recipe_renderer.top_down_indices_to_raw(target_record, render_rows(rows, palette, mapper, style_row))
