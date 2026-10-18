"""Deterministic checks for the V2 pattern-structured template policy."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import iter_obfuscated_bmp_records  # noqa: E402
from scripts import pm99_factory_kit_renderer_v2 as renderer  # noqa: E402


DBDAT = ROOT / ".local" / "season-pipeline-v2" / "pm99-base-clean" / "DBDAT"


def test_pattern_template_policy_is_explicit_for_all_compact_archives() -> None:
    expected = {
        "solid": 4,
        "vertical_stripes": 2,
        "hoops": 1252,
        "halves": 3,
        "sleeves": 309,
    }
    for archive in ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF"):
        for pattern, carrier in expected.items():
            assert renderer.factory_template_carrier(archive, {"pattern": pattern}) == carrier
            records = iter_obfuscated_bmp_records(DBDAT / archive, file_name_pattern=rf"^EQ96{carrier:04d}\.BMP$")
            assert len(records) == 1


def test_v2_keeps_the_v1_pixel_lane_renderer() -> None:
    assert renderer.render_rows.__module__ == "scripts.pm99_factory_kit_renderer_v1"
    assert renderer.render_template_on_record.__module__ == "scripts.pm99_factory_kit_renderer_v1"
