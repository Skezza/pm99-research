from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import foreign_host_capture_tile_v1 as tiles  # noqa: E402


def _capture() -> dict[str, object]:
    return {
        "schema": tiles.SCHEMA,
        "capture_id": "spain-sweep",
        "route_selection_limit": 1,
        "country": {"canonical_name": "Spain", "ui_label": "SPAIN", "flag_selector": {"x": 67, "y": 250}},
        "tiles": [
            {"tile_index": 4, "selector": {"x": 155, "y": 382}, "eq_record_id": 5, "reviewed_visible_club_name": "Athletic Club", "screenshot": "screens/23_spain_tile_382_4.png", "reviewed_frame_sha256": "a" * 64}
        ],
    }


def test_prepare_makes_a_single_fresh_route_with_a_failing_placeholder_digest() -> None:
    prepared = tiles.prepare(capture=_capture(), tile_index=4)
    assert prepared["capture_id"] == "spain-sweep-tile-4-fresh-route"
    assert prepared["route_selection_limit"] == 1
    assert prepared["tiles"][0]["screenshot"] == "screens/19_spain_tile_382_4.png"
    assert prepared["tiles"][0]["reviewed_frame_sha256"] == "0" * 64


def test_review_binds_the_actual_fresh_screenshot(tmp_path: Path) -> None:
    prepared = tiles.prepare(capture=_capture(), tile_index=4)
    screenshot = tmp_path / "screens" / "19_spain_tile_382_4.png"
    screenshot.parent.mkdir()
    screenshot.write_bytes(b"fresh-screen")
    reviewed = tiles.review(capture=prepared, capture_root=tmp_path)
    assert reviewed["tiles"][0]["reviewed_frame_sha256"] == hashlib.sha256(b"fresh-screen").hexdigest()


def test_prepare_rejects_an_unknown_tile() -> None:
    with pytest.raises(ValueError, match="exactly one tile_index"):
        tiles.prepare(capture=_capture(), tile_index=7)
