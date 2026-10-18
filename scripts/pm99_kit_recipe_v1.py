#!/usr/bin/env python3
"""Derive a compact, reproducible PM99 kit recipe from a dated shirt image.

PM99's kit asset is a tiny illustrated shirt-and-shorts silhouette, not a
rectangular texture slot.  This module deliberately extracts only the visual
facts that can survive that format: two dominant shirt colours, simple
geometry, and a conservative shorts colour.  It never projects pixels from a
modern shirt image onto the PM99 carrier.
"""

from __future__ import annotations

import colorsys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from PIL import Image


Rgb = tuple[int, int, int]


def _family(rgb: Rgb) -> str:
    """Return a stable broad colour family while discarding source shading."""
    red, green, blue = (channel / 255.0 for channel in rgb)
    hue, saturation, value = colorsys.rgb_to_hsv(red, green, blue)
    if saturation < 0.14:
        if value < 0.26:
            return "black"
        # Shirt renders commonly shade an otherwise white panel down to a
        # mid-grey.  Treat those pixels as the same white garment colour, not
        # as a second stripe family; otherwise all-white kits become false
        # grey vertical stripes.
        if value > 0.45:
            return "white"
        return "grey"
    degree = hue * 360.0
    if degree < 15.0 or degree >= 342.0:
        return "red"
    if degree < 42.0:
        return "orange"
    if degree < 70.0:
        return "yellow"
    if degree < 164.0:
        return "green"
    if degree < 194.0:
        return "cyan"
    if degree < 258.0:
        return "blue"
    if degree < 288.0:
        return "purple"
    if degree < 325.0:
        return "pink"
    return "red"


def _average(colours: list[Rgb]) -> Rgb:
    return tuple(round(sum(colour[channel] for colour in colours) / len(colours)) for channel in range(3))  # type: ignore[return-value]


def _brightness(rgb: Rgb) -> float:
    return (0.299 * rgb[0]) + (0.587 * rgb[1]) + (0.114 * rgb[2])


def _categorised_pixels(image: Image.Image) -> tuple[list[tuple[int, int, str]], dict[str, Rgb], dict[str, int]]:
    rgba = image.convert("RGBA")
    grouped: dict[str, list[Rgb]] = defaultdict(list)
    pixels: list[tuple[int, int, str]] = []
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, alpha = rgba.getpixel((x, y))
            if alpha < 160:
                continue
            rgb = (int(red), int(green), int(blue))
            family = _family(rgb)
            grouped[family].append(rgb)
            pixels.append((x, y, family))
    averages = {family: _average(values) for family, values in grouped.items()}
    counts = {family: len(values) for family, values in grouped.items()}
    return pixels, averages, counts


def _two_main_families(counts: dict[str, int]) -> list[str]:
    """Prefer garment colours over small monochrome logos and collar details."""
    total = sum(counts.values())
    ranked = sorted(counts, key=lambda family: (-counts[family], family))
    if not ranked:
        raise ValueError("kit source has no sufficiently opaque pixels")
    selected = [ranked[0]]
    for family in ranked[1:]:
        share = counts[family] / total if total else 0.0
        if share >= 0.15:
            selected.append(family)
            break
    return selected


def _pair_transition_rates(
    pixels: list[tuple[int, int, str]], width: int, height: int, first: str, second: str
) -> tuple[float, float]:
    selected = {(x, y): family for x, y, family in pixels if family in {first, second}}
    horizontal_changes = horizontal_pairs = vertical_changes = vertical_pairs = 0
    for (x, y), family in selected.items():
        other = selected.get((x + 1, y))
        if other is not None:
            horizontal_pairs += 1
            horizontal_changes += int(other != family)
        other = selected.get((x, y + 1))
        if other is not None:
            vertical_pairs += 1
            vertical_changes += int(other != family)
    return (
        horizontal_changes / horizontal_pairs if horizontal_pairs else 0.0,
        vertical_changes / vertical_pairs if vertical_pairs else 0.0,
    )


def _second_at_edges(pixels: list[tuple[int, int, str]], width: int, first: str, second: str) -> float:
    second_pixels = [(x, y) for x, y, family in pixels if family == second]
    if not second_pixels:
        return 0.0
    edge = sum(1 for x, _y in second_pixels if x <= width * 0.24 or x >= width * 0.76)
    return edge / len(second_pixels)


def _halves_separation(pixels: list[tuple[int, int, str]], width: int, first: str, second: str) -> float:
    first_x = [x for x, _y, family in pixels if family == first]
    second_x = [x for x, _y, family in pixels if family == second]
    if not first_x or not second_x:
        return 0.0
    return abs((sum(first_x) / len(first_x)) - (sum(second_x) / len(second_x))) / max(1, width - 1)


def recipe_from_source(path: Path) -> dict[str, Any]:
    """Extract an editable, deliberately low-detail PM99 rendering recipe."""
    with Image.open(path) as opened:
        image = opened.convert("RGBA")
    pixels, averages, counts = _categorised_pixels(image)
    if not pixels:
        raise ValueError("kit source has no sufficiently opaque pixels")
    total = len(pixels)
    families = _two_main_families(counts)
    primary = families[0]
    colours: list[Rgb] = [averages[primary]]
    pattern = "solid"
    diagnostics: dict[str, Any] = {
        "pixel_count": total,
        "colour_families": [
            {"family": family, "pixel_count": counts[family], "share": round(counts[family] / total, 6), "rgb": list(averages[family])}
            for family in sorted(counts, key=lambda item: (-counts[item], item))
        ],
    }
    secondary: str | None = None
    if len(families) == 2:
        secondary = families[1]
        colours.append(averages[secondary])
        horizontal, vertical = _pair_transition_rates(pixels, image.width, image.height, primary, secondary)
        edge_share = _second_at_edges(pixels, image.width, primary, secondary)
        halves = _halves_separation(pixels, image.width, primary, secondary)
        diagnostics.update(
            {
                "primary_family": primary,
                "secondary_family": secondary,
                "horizontal_transition_rate": round(horizontal, 6),
                "vertical_transition_rate": round(vertical, 6),
                "secondary_edge_share": round(edge_share, 6),
                "horizontal_centroid_separation": round(halves, 6),
            }
        )
        if edge_share >= 0.82:
            pattern = "sleeves"
        # Real kit images include anti-aliasing, gradients and collars, so a
        # broad band can have a modest neighbour-boundary rate.  The direction
        # ratio is the stronger signal; the floor merely rejects logo noise.
        elif horizontal >= 0.015 and horizontal >= vertical * 1.55:
            pattern = "vertical_stripes"
        elif vertical >= 0.015 and vertical >= horizontal * 1.55:
            pattern = "hoops"
        elif halves >= 0.28:
            pattern = "halves"
    # Source images cover the shirt only.  If the second dominant shirt colour
    # is substantially darker, it is the least speculative shorts fallback;
    # otherwise retain the main shirt colour.  The field remains editable.
    shorts = colours[0]
    if len(colours) == 2 and _brightness(colours[1]) + 28 < _brightness(colours[0]):
        shorts = colours[1]
    recipe: dict[str, Any] = {
        "renderer": "pm99-abstract-kit-recipe-v1",
        "pattern": pattern,
        "colors": [list(colour) for colour in colours],
        "shorts": list(shorts),
        "trim": None,
        "source_image_dimensions": {"width": image.width, "height": image.height},
        "derivation": "dominant-source-colours-and-simple-geometry; no-source-pixel-projection",
        "diagnostics": diagnostics,
    }
    if pattern == "sleeves" and len(colours) == 2:
        recipe["sleeves"] = list(colours[1])
    if pattern == "vertical_stripes":
        recipe["stripe_count"] = 6
    if pattern == "hoops":
        recipe["band_count"] = 6
    return recipe
