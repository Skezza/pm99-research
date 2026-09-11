"""V5 factory-kit renderer with native tonal-depth transfer.

V4 fixed the compact kit silhouette, pattern boundaries, shirt/shorts bleed
and the asymmetric right hem.  It still used a narrow absolute-luminance
multiplier, however, so several distinct factory highlights and folds could
quantise to the same runtime-palette index.  The result was structurally safe
but visibly flatter than PM99's original artwork.

V5 treats the selected original PM99 illustration as a *relative* depth map.
Within each garment and native pattern panel it measures the factory shadow,
midtone and highlight percentiles.  Shadows are mapped away from the recipe
colour towards black; highlights are mapped towards white.  This preserves
the original artist's spatial folds and specular accents without copying a
modern source image or introducing generated pixels.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from scripts import pm99_factory_kit_renderer_v4 as hem_renderer


RENDERER_ID = "pm99-factory-template-kit-v5-native-tone-transfer"
CV_POLICY = (
    "template-chroma-otsu-with-two-pass-majority-smoothing, silhouette-waist-valley, "
    "silhouette-derived-right-hem-contour, and per-panel factory-luminance percentile transfer"
)
FACTORY_TEMPLATE_BY_ARCHIVE_PATTERN = hem_renderer.FACTORY_TEMPLATE_BY_ARCHIVE_PATTERN
factory_template_carrier = hem_renderer.factory_template_carrier

_NATIVE_PATTERN_TYPES = {"vertical_stripes", "hoops", "sleeves"}
_SHADOW_FLOOR = 0.38
_HIGHLIGHT_BLEND = 0.46


def _percentile(values: list[float], fraction: float) -> float:
    """Return a linearly interpolated deterministic percentile."""
    if not values:
        return 128.0
    ordered = sorted(values)
    position = max(0.0, min(1.0, fraction)) * (len(ordered) - 1)
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _profile(values: list[float]) -> tuple[float, float, float]:
    """Return robust shadow, midtone and highlight anchors."""
    low = _percentile(values, 0.08)
    middle = _percentile(values, 0.50)
    high = _percentile(values, 0.94)
    # Tiny sprites and dark patterns can have only a few source levels.  A
    # non-zero denominator keeps their ordering without fabricating noise.
    if middle - low < 1.0:
        low = middle - 1.0
    if high - middle < 1.0:
        high = middle + 1.0
    return low, middle, high


def _tone_key(
    *,
    pattern: str,
    native_region: int | None,
    y: int,
    hem: int,
) -> tuple[str, int | None]:
    if y > hem:
        return ("shorts", None)
    panel = native_region if pattern in _NATIVE_PATTERN_TYPES else None
    return ("shirt", panel)


def _tone_profiles(
    rows: list[list[int]],
    palette: list[tuple[int, int, int]],
    mask: list[list[bool]],
    native_regions: list[list[int | None]],
    hems: list[int],
    pattern: str,
) -> dict[tuple[str, int | None], tuple[float, float, float]]:
    values: dict[tuple[str, int | None], list[float]] = defaultdict(list)
    for y, row in enumerate(rows):
        for x, source_index in enumerate(row):
            if not mask[y][x] or not source_index:
                continue
            source_rgb = palette[source_index]
            if hem_renderer.boundary_renderer._is_neutral_dark_structure(source_rgb):
                continue
            key = _tone_key(
                pattern=pattern,
                native_region=native_regions[y][x],
                y=y,
                hem=hems[x],
            )
            values[key].append(hem_renderer.boundary_renderer._luminance(source_rgb))
    return {key: _profile(samples) for key, samples in values.items()}


def _transfer_tone(
    base_rgb: tuple[int, int, int],
    source_luma: float,
    profile: tuple[float, float, float],
) -> tuple[int, int, int]:
    """Transfer a factory pixel's relative tone to a target fabric colour."""
    low, middle, high = profile
    if source_luma <= middle:
        depth = min(1.0, max(0.0, (middle - source_luma) / (middle - low)))
        # A slightly concave curve keeps midtone folds visible while retaining
        # the deepest factory creases as real shadows.
        factor = 1.0 - (1.0 - _SHADOW_FLOOR) * (depth ** 0.78)
        return tuple(max(0, min(255, int(round(channel * factor)))) for channel in base_rgb)
    lift = min(1.0, max(0.0, (source_luma - middle) / (high - middle)))
    blend = _HIGHLIGHT_BLEND * (lift ** 0.82)
    return tuple(
        max(0, min(255, int(round(channel + (255 - channel) * blend))))
        for channel in base_rgb
    )


def _darken(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(round(channel * factor)))) for channel in rgb)


def render_rows(
    rows: list[list[int]],
    palette: list[tuple[int, int, int]],
    mapper: hem_renderer.boundary_renderer.recipe_renderer.PaletteMapper,
    style_row: dict[str, Any],
) -> list[list[int]]:
    """Render recipe colours through the original PM99 tonal structure."""
    height = len(rows)
    if height == 0:
        return []
    width = len(rows[0])
    mask = [[index != 0 for index in row] for row in rows]
    if not any(any(row) for row in mask):
        return [list(row) for row in rows]
    shirt_top, waist = hem_renderer.boundary_renderer._shirt_top_and_waist(mask)
    hems = hem_renderer._hem_by_column(mask, waist)
    pattern = str(style_row.get("pattern", "solid"))
    native_regions = hem_renderer.boundary_renderer._smoothed_native_regions(
        rows, palette, mask, shirt_top, waist
    )
    profiles = _tone_profiles(rows, palette, mask, native_regions, hems, pattern)
    shorts_rgb = hem_renderer.boundary_renderer.recipe_renderer.color_rgb(
        style_row.get("shorts") or "white"
    )
    out = [list(row) for row in rows]
    for y, row in enumerate(rows):
        bounds = hem_renderer.boundary_renderer._row_bounds(mask, y)
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
            if hem_renderer.boundary_renderer._is_neutral_dark_structure(original_rgb):
                out[y][x] = original_index
                continue
            hem = hems[x]
            if y <= hem:
                base_rgb = hem_renderer.boundary_renderer._native_pattern_colour(
                    style_row, pattern, native_regions[y][x]
                )
                if base_rgb is None:
                    base_rgb = hem_renderer.boundary_renderer.recipe_renderer.style_color(
                        style_row, x, y, row_min, row_max, shirt_top, waist
                    )
                    base_rgb = hem_renderer.boundary_renderer.recipe_renderer.apply_detail_overlays(
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
            key = _tone_key(
                pattern=pattern,
                native_region=native_regions[y][x],
                y=y,
                hem=hem,
            )
            profile = profiles.get(key, (64.0, 160.0, 240.0))
            shaded = _transfer_tone(
                base_rgb,
                hem_renderer.boundary_renderer._luminance(original_rgb),
                profile,
            )
            if hem_renderer.boundary_renderer.recipe_renderer.edge_pixel(mask, x, y):
                shaded = _darken(shaded, 0.90)
            if y == hem:
                shaded = _darken(shaded, 0.58)
            elif y == hem + 1:
                shaded = _darken(shaded, 0.82)
            out[y][x] = mapper.nearest(shaded)
    return out


def render_record(record: Any, palette: list[tuple[int, int, int]], style_row: dict[str, Any]) -> bytes:
    rows = hem_renderer.boundary_renderer.recipe_renderer.record_to_top_down_indices(record)
    mapper = hem_renderer.boundary_renderer.recipe_renderer.PaletteMapper(palette)
    return hem_renderer.boundary_renderer.recipe_renderer.top_down_indices_to_raw(
        record, render_rows(rows, palette, mapper, style_row)
    )


def render_template_on_record(
    target_record: Any,
    template_record: Any,
    palette: list[tuple[int, int, int]],
    style_row: dict[str, Any],
) -> bytes:
    target_size = (int(target_record.width), int(target_record.height))
    template_size = (int(template_record.width), int(template_record.height))
    if target_size != template_size:
        raise ValueError(f"factory template dimensions {template_size} do not fit target {target_size}")
    rows = hem_renderer.boundary_renderer.recipe_renderer.record_to_top_down_indices(template_record)
    mapper = hem_renderer.boundary_renderer.recipe_renderer.PaletteMapper(palette)
    return hem_renderer.boundary_renderer.recipe_renderer.top_down_indices_to_raw(
        target_record, render_rows(rows, palette, mapper, style_row)
    )
