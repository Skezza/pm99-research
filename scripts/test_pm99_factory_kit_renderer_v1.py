"""Deterministic checks for the candidate factory-kit renderer."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import iter_obfuscated_bmp_records, validate_minifoto_bitmap  # noqa: E402
from app.bitmap_pixel_rows import bitmap_pixel_ranges
from scripts import pm99_factory_kit_renderer_v1 as renderer  # noqa: E402
from scripts.pm99_kit_palette_v1 import runtime_kit_palette  # noqa: E402


DBDAT = ROOT / ".local" / "season-pipeline-v2" / "pm99-base-clean" / "DBDAT"


def _record(archive: str, carrier: int):
    records = iter_obfuscated_bmp_records(DBDAT / archive, file_name_pattern=rf"^EQ96{carrier:04d}\.BMP$")
    assert len(records) == 1
    return records[0]


def test_template_selection_is_explicit_for_each_compact_archive() -> None:
    assert renderer.factory_template_carrier("MINIESC.PKF", {"pattern": "solid"}) == 4
    assert renderer.factory_template_carrier("NANOESC.PKF", {"pattern": "hoops"}) == 4
    assert renderer.factory_template_carrier("RIDIESC.PKF", {"pattern": "vertical_stripes"}) == 2
    assert renderer.factory_template_carrier("RIDIESC.PKF", {"pattern": "hoops"}) == 1


def test_factory_template_changes_only_target_pixel_lane_and_is_deterministic() -> None:
    palette, _info = runtime_kit_palette(DBDAT)
    style = {
        "pattern": "vertical_stripes",
        "colors": [[178, 48, 55], [224, 223, 223]],
        "shorts": [178, 48, 55],
        "stripe_count": 6,
        "trim": None,
    }
    for archive in ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF"):
        target = _record(archive, 1)
        template = _record(archive, renderer.factory_template_carrier(archive, style))
        first = renderer.render_template_on_record(target, template, palette, style)
        second = renderer.render_template_on_record(target, template, palette, style)
        assert hashlib.sha256(first).digest() == hashlib.sha256(second).digest()
        assert validate_minifoto_bitmap(first).bitmap_length == validate_minifoto_bitmap(target.raw_bitmap).bitmap_length
        allowed = {i for lo, hi in bitmap_pixel_ranges(target) for i in range(lo, hi)}
        assert all(a == b for i, (a, b) in enumerate(zip(first, target.raw_bitmap)) if i not in allowed)
