"""Render dated-kit recipes through a reviewed original PM99 kit illustration.

This is intentionally unlike the first 2015 renderer: it never projects a
modern shirt PNG over a PM99 sprite and it never replaces the artwork with a
new generic glyph.  A clean, hash-bound PM99 illustration supplies the
silhouette, seams, collar, anti-aliasing and shading.  The dated source only
supplies a small colour/pattern recipe.

The module is a candidate renderer.  Its visual results need an explicit
contact-sheet review before they can be materialised into a season package.
"""

from __future__ import annotations

from typing import Any

from scripts import patch_english80_reference_kits_v2 as recipe_renderer


RENDERER_ID = "pm99-factory-template-kit-v1"
# Selected from the unmodified PM99 catalogue: a light, front-facing kit with
# clear pixel-art shading.  The value is deliberately part of every receipt.
FACTORY_TEMPLATE_CARRIER = 4
# RIDIESC is not a reduced shirt silhouette: it is PM99's tiny patterned-kit
# swatch.  It needs a pattern-appropriate original swatch, whereas MINIESC
# and NANOESC use the same front-facing shirt illustration.
FACTORY_TEMPLATE_BY_ARCHIVE_PATTERN = {
    "MINIESC.PKF": {"default": 4},
    "NANOESC.PKF": {"default": 4},
    "RIDIESC.PKF": {
        "default": 4,
        "vertical_stripes": 2,
        "hoops": 1,
        "halves": 3,
        "quarters": 3,
        "sleeves": 4,
        "chest_band": 1,
        "diagonal_sash": 3,
    },
}


def factory_template_carrier(archive: str, style_row: dict[str, Any]) -> int:
    """Return the consciously selected original template for this asset role."""
    choices = FACTORY_TEMPLATE_BY_ARCHIVE_PATTERN.get(archive)
    if choices is None:
        raise ValueError(f"unsupported factory-kit archive: {archive}")
    return int(choices.get(str(style_row.get("pattern", "solid")), choices["default"]))


def _luminance(rgb: tuple[int, int, int]) -> float:
    return (0.299 * rgb[0]) + (0.587 * rgb[1]) + (0.114 * rgb[2])


def _is_neutral_dark_structure(rgb: tuple[int, int, int]) -> bool:
    """Keep template line work instead of tinting it as if it were fabric."""
    spread = max(rgb) - min(rgb)
    return spread <= 16 and _luminance(rgb) <= 112


def _shade(rgb: tuple[int, int, int], source_luma: float, *, edge: bool) -> tuple[int, int, int]:
    # The reviewed light template's highlights and folds become shades of the
    # target club colour.  This is intentionally gentler than the rejected
    # V4 renderer, which flattened the original sprite into dark blocks.
    factor = 0.66 + (max(0.0, min(255.0, source_luma)) / 255.0) * 0.42
    if edge:
        factor *= 0.94
    return tuple(max(0, min(255, int(round(channel * factor)))) for channel in rgb)


def render_rows(
    rows: list[list[int]],
    palette: list[tuple[int, int, int]],
    mapper: recipe_renderer.PaletteMapper,
    style_row: dict[str, Any],
) -> list[list[int]]:
    """Render a recipe within a clean PM99 template's garment silhouette.

    The source template contains a shirt above a pair of shorts.  The split is
    normalised, therefore it applies consistently to MINI, NANO and RIDI
    versions of the same original PM99 kit illustration.
    """
    height = len(rows)
    if height == 0:
        return []
    width = len(rows[0])
    mask = [[index != 0 for index in row] for row in rows]
    nonzero = [y for y, row in enumerate(mask) if any(row)]
    if not nonzero:
        return [list(row) for row in rows]
    shirt_top = max(min(nonzero), int(round(height * 0.05)))
    shorts_top = min(max(nonzero), int(round(height * 0.62)))
    shirt_bottom = max(shirt_top, shorts_top - 1)
    shorts_rgb = recipe_renderer.color_rgb(style_row.get("shorts") or "white")
    out = [list(row) for row in rows]
    for y, row in enumerate(rows):
        bounds = recipe_renderer.row_bounds(mask, y)
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
                # Collar opening, line work and deepest creases remain actual
                # factory pixels.  That is what gives the derivative a PM99
                # visual language instead of a newly-drawn flat icon.
                out[y][x] = original_index
                continue
            if y <= shirt_bottom:
                base_rgb = recipe_renderer.style_color(
                    style_row, x, y, row_min, row_max, shirt_top, shirt_bottom
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
                    shirt_bottom,
                )
            else:
                base_rgb = shorts_rgb
            out[y][x] = mapper.nearest(
                _shade(
                    base_rgb,
                    _luminance(original_rgb),
                    edge=recipe_renderer.edge_pixel(mask, x, y),
                )
            )
    return out


def render_record(
    record: Any,
    palette: list[tuple[int, int, int]],
    style_row: dict[str, Any],
) -> bytes:
    """Return a structurally identical raw bitmap with factory template art."""
    rows = recipe_renderer.record_to_top_down_indices(record)
    mapper = recipe_renderer.PaletteMapper(palette)
    return recipe_renderer.top_down_indices_to_raw(record, render_rows(rows, palette, mapper, style_row))


def render_template_on_record(
    target_record: Any,
    template_record: Any,
    palette: list[tuple[int, int, int]],
    style_row: dict[str, Any],
) -> bytes:
    """Put template pixels into a target carrier without changing its wrapper.

    Compact BMP records are embedded in an obfuscated archive and can carry
    carrier-specific bytes outside the pixel lane.  Reusing the *whole*
    template record would risk transplanting those bytes.  Only the reviewed
    template's indexed pixels move; target header and suffix bytes remain
    byte-for-byte unchanged.
    """
    target_size = (int(target_record.width), int(target_record.height))
    template_size = (int(template_record.width), int(template_record.height))
    if target_size != template_size:
        raise ValueError(f"factory template dimensions {template_size} do not fit target {target_size}")
    rows = recipe_renderer.record_to_top_down_indices(template_record)
    mapper = recipe_renderer.PaletteMapper(palette)
    return recipe_renderer.top_down_indices_to_raw(
        target_record,
        render_rows(rows, palette, mapper, style_row),
    )
