"""Pattern-structured successor to the reviewed factory-kit renderer.

V1 established the important safety contract: recipe-only input, the true
runtime palette, and only a target record's indexed pixels may change.  V2
keeps that contract but selects an original PM99 template whose native pixel
art matches the recipe geometry.  This preserves the artist's real shirt
folds, waistband cuts and trouser-leg shadowing for the patterns the dated
2015 recipes actually use.
"""

from __future__ import annotations

from typing import Any

from scripts.pm99_factory_kit_renderer_v1 import (
    render_record,
    render_rows,
    render_template_on_record,
)


RENDERER_ID = "pm99-factory-template-kit-v2-pattern-structure"

# Every carrier was reviewed against the unmodified PM99 catalogue.  The
# policy is explicit and receipt-bound: a later style change cannot drift
# previously generated candidates.  Compact templates exist in all three
# archive roles and are only used as artwork sources; the target carrier's
# header, suffix and binding remain untouched.
PATTERN_TEMPLATE_CARRIERS = {
    "default": 4,             # clean plain shirt, clear collar and shorts
    "vertical_stripes": 2,    # native stripes and strong shirt-fold shading
    "hoops": 1252,            # native horizontal bands and waistband cut
    "halves": 3,              # native split-front illustration
    "quarters": 3,
    "sleeves": 309,           # native contrasting-sleeve shoulder cut
    "chest_band": 1,
    "diagonal_sash": 3,
}
FACTORY_TEMPLATE_BY_ARCHIVE_PATTERN = {
    archive: dict(PATTERN_TEMPLATE_CARRIERS)
    for archive in ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")
}


def factory_template_carrier(archive: str, style_row: dict[str, Any]) -> int:
    """Return the reviewed original PM99 artwork for the recipe pattern."""
    choices = FACTORY_TEMPLATE_BY_ARCHIVE_PATTERN.get(archive)
    if choices is None:
        raise ValueError(f"unsupported factory-kit archive: {archive}")
    return int(choices.get(str(style_row.get("pattern", "solid")), choices["default"]))
