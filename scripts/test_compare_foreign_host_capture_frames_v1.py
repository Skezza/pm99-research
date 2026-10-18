from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import compare_foreign_host_capture_frames_v1 as comparison


def _capture() -> dict[str, object]:
    return {
        "schema": comparison.SCHEMA,
        "capture_id": "fixture",
        "tiles": [
            {"tile_index": 0, "eq_record_id": 1, "reviewed_visible_club_name": "One", "screenshot": "screens/one.png"},
            {"tile_index": 1, "eq_record_id": 2, "reviewed_visible_club_name": "Two", "screenshot": "screens/two.png"},
            {"tile_index": 2, "eq_record_id": 3, "reviewed_visible_club_name": "Three", "screenshot": "screens/three.png"},
        ],
    }


def _write_root(root: Path, values: tuple[bytes, bytes, bytes]) -> Path:
    (root / "screens").mkdir(parents=True)
    for name, value in zip(("one.png", "two.png", "three.png"), values):
        (root / "screens" / name).write_bytes(value)
    return root


def test_compare_identifies_repeated_deterministic_picker_frame(tmp_path: Path) -> None:
    root_a = _write_root(tmp_path / "a", (b"one", b"same", b"same"))
    root_b = _write_root(tmp_path / "b", (b"one", b"same", b"same"))

    report = comparison.compare(capture=_capture(), roots=[root_a, root_b])

    assert report["exact_per_tile_sequence_match"] is True
    assert report["counts"]["unique_first_capture_frames"] == 2
    assert report["repeated_first_capture_frames"][0]["tile_indices"] == [1, 2]
    assert "not one-to-one" in report["interpretation"]


def test_compare_does_not_claim_determinism_when_frames_differ(tmp_path: Path) -> None:
    root_a = _write_root(tmp_path / "a", (b"one", b"two", b"three"))
    root_b = _write_root(tmp_path / "b", (b"one", b"changed", b"three"))

    report = comparison.compare(capture=_capture(), roots=[root_a, root_b])

    assert report["exact_per_tile_sequence_match"] is False
    assert report["tiles"][1]["status"] == "not-proven"
