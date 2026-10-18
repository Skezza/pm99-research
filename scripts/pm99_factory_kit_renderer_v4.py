"""V4 factory-kit renderer with a smooth native right-hem contour.

The factory silhouette is deliberately asymmetric: near the waist it shifts
right by several pixels before the shorts broaden.  A flat shirt/shorts split
therefore leaves a visibly stepped lower-right shirt tail.  V4 retains V3's
native colour-region and no-bleed work but derives a short two-pixel hem
contour from that silhouette's own waist width and centre.  The contour only
acts on the lower-right overlap where the wobble occurs; it never redraws the
outline or widens either garment.
"""

from __future__ import annotations

from typing import Any

from scripts import pm99_factory_kit_renderer_v3 as boundary_renderer


RENDERER_ID = "pm99-factory-template-kit-v4-native-hem-contour"
CV_POLICY = (
    "template-chroma-otsu-with-two-pass-majority-smoothing, silhouette-waist-valley, "
    "and silhouette-derived-right-hem-contour"
)
FACTORY_TEMPLATE_BY_ARCHIVE_PATTERN = boundary_renderer.FACTORY_TEMPLATE_BY_ARCHIVE_PATTERN
factory_template_carrier = boundary_renderer.factory_template_carrier


def _hem_by_column(mask: list[list[bool]], waist: int) -> list[int]:
    """Return the shirt hem row for each column of the native silhouette.

    The available compact art is right-shifted around the waist.  Measure its
    centre and half-width at that valley, then gently lift only the final
    right-third of the hem by one or two pixels.  This removes the artificial
    flat-edge overlap while retaining the PM99 silhouette and its scale.
    """
    width = len(mask[0]) if mask else 0
    bounds = boundary_renderer._row_bounds(mask, waist)
    if bounds is None:
        return [waist] * width
    left, right = bounds
    centre = (left + right) / 2.0
    half_width = max(1.0, (right - left + 1) / 2.0)
    hems: list[int] = []
    for x in range(width):
        rightness = (x - centre) / half_width
        if rightness <= 1.0 / 3.0:
            lift = 0
        elif rightness <= 2.0 / 3.0:
            lift = 1
        else:
            lift = 2
        hems.append(waist - lift)
    return hems


def render_rows(
    rows: list[list[int]],
    palette: list[tuple[int, int, int]],
    mapper: boundary_renderer.recipe_renderer.PaletteMapper,
    style_row: dict[str, Any],
) -> list[list[int]]:
    """Use V3's native pattern field with a per-column shirt/shorts seam."""
    height = len(rows)
    if height == 0:
        return []
    width = len(rows[0])
    mask = [[index != 0 for index in row] for row in rows]
    if not any(any(row) for row in mask):
        return [list(row) for row in rows]
    shirt_top, waist = boundary_renderer._shirt_top_and_waist(mask)
    hems = _hem_by_column(mask, waist)
    pattern = str(style_row.get("pattern", "solid"))
    native_regions = boundary_renderer._smoothed_native_regions(rows, palette, mask, shirt_top, waist)
    shorts_rgb = boundary_renderer.recipe_renderer.color_rgb(style_row.get("shorts") or "white")
    out = [list(row) for row in rows]
    for y, row in enumerate(rows):
        bounds = boundary_renderer._row_bounds(mask, y)
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
            if boundary_renderer._is_neutral_dark_structure(original_rgb):
                out[y][x] = original_index
                continue
            hem = hems[x]
            if y <= hem:
                base_rgb = boundary_renderer._native_pattern_colour(style_row, pattern, native_regions[y][x])
                if base_rgb is None:
                    base_rgb = boundary_renderer.recipe_renderer.style_color(
                        style_row, x, y, row_min, row_max, shirt_top, waist
                    )
                    base_rgb = boundary_renderer.recipe_renderer.apply_detail_overlays(
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
            factor = 0.66 + (max(0.0, min(255.0, boundary_renderer._luminance(original_rgb))) / 255.0) * 0.42
            if boundary_renderer.recipe_renderer.edge_pixel(mask, x, y):
                factor *= 0.94
            # A narrow asymmetric hem needs a readable contour even where a
            # club deliberately uses a shirt and shorts of similar colour.
            # Keep the lower shorts row gentle; only the native shirt-edge
            # pixel receives the deeper crease.
            if y == hem:
                factor *= 0.60
            elif y == hem + 1:
                factor *= 0.85
            shaded = tuple(max(0, min(255, int(round(channel * factor)))) for channel in base_rgb)
            out[y][x] = mapper.nearest(shaded)
    return out


def render_record(record: Any, palette: list[tuple[int, int, int]], style_row: dict[str, Any]) -> bytes:
    rows = boundary_renderer.recipe_renderer.record_to_top_down_indices(record)
    mapper = boundary_renderer.recipe_renderer.PaletteMapper(palette)
    return boundary_renderer.recipe_renderer.top_down_indices_to_raw(record, render_rows(rows, palette, mapper, style_row))


def render_template_on_record(target_record: Any, template_record: Any, palette: list[tuple[int, int, int]], style_row: dict[str, Any]) -> bytes:
    target_size = (int(target_record.width), int(target_record.height))
    template_size = (int(template_record.width), int(template_record.height))
    if target_size != template_size:
        raise ValueError(f"factory template dimensions {template_size} do not fit target {target_size}")
    rows = boundary_renderer.recipe_renderer.record_to_top_down_indices(template_record)
    mapper = boundary_renderer.recipe_renderer.PaletteMapper(palette)
    return boundary_renderer.recipe_renderer.top_down_indices_to_raw(target_record, render_rows(rows, palette, mapper, style_row))
