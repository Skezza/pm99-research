from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import foreign_host_mapping_v1 as mapping


def _capture() -> dict[str, object]:
    return {
        "schema": mapping.SCHEMA,
        "capture_id": "fixture",
        "route_selection_limit": 1,
        "country": {"canonical_name": "Spain", "ui_label": "SPAIN", "flag_selector": {"x": 67, "y": 250}},
        "tiles": [
            {"tile_index": 0, "selector": {"x": 27, "y": 382}, "eq_record_id": 1, "reviewed_visible_club_name": "F.C. Barcelona", "screenshot": "screens/one.png", "reviewed_frame_sha256": hashlib.sha256(b"one").hexdigest()},
            {"tile_index": 1, "selector": {"x": 59, "y": 382}, "eq_record_id": 2, "reviewed_visible_club_name": "R.C. Deportivo", "screenshot": "screens/two.png", "reviewed_frame_sha256": hashlib.sha256(b"two").hexdigest()},
        ],
    }


def test_verify_accepts_fresh_frames_and_exact_decoded_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "capture"
    (root / "screens").mkdir(parents=True)
    (root / "screens" / "one.png").write_bytes(b"one")
    (root / "screens" / "two.png").write_bytes(b"two")
    dbdat = tmp_path / "dbdat"
    dbdat.mkdir()
    (dbdat / "EQ98030.FDI").write_bytes(b"eq")
    (dbdat / "JUG98030.FDI").write_bytes(b"jug")
    monkeypatch.setattr(mapping, "_eq_short_names", lambda _dbdat: {1: "F.C. Barcelona", 2: "R.C. Deportivo"})

    report = mapping.verify_capture(capture=_capture(), dbdat=dbdat, capture_root=root)

    assert report["counts"] == {"captured": 2, "accepted": 1, "unresolved": 1}
    assert [row["eq_record_id"] for row in report["accepted_host_mappings"]] == [1]
    assert report["tiles"][1]["reason"] == "route-selection-capacity-exhausted"


def test_verify_keeps_first_selection_and_fails_open_after_route_capacity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "capture"
    (root / "screens").mkdir(parents=True)
    for name in ("one.png", "two.png"):
        (root / "screens" / name).write_bytes(b"same")
    capture = _capture()
    frame_hash = hashlib.sha256(b"same").hexdigest()
    for item in capture["tiles"]:  # type: ignore[index]
        item["reviewed_frame_sha256"] = frame_hash
    dbdat = tmp_path / "dbdat"
    dbdat.mkdir()
    (dbdat / "EQ98030.FDI").write_bytes(b"eq")
    (dbdat / "JUG98030.FDI").write_bytes(b"jug")
    monkeypatch.setattr(mapping, "_eq_short_names", lambda _dbdat: {1: "F.C. Barcelona", 2: "R.C. Deportivo"})

    report = mapping.verify_capture(capture=capture, dbdat=dbdat, capture_root=root)

    # The first frame is a valid post-click proof. The next tile is deliberately
    # rejected because it is no longer an independent fresh route.
    assert report["counts"] == {"captured": 2, "accepted": 1, "unresolved": 1}
    assert report["tiles"][0]["status"] == "accepted"
    assert report["tiles"][1]["reason"] == "route-selection-capacity-exhausted"


def test_verify_fails_open_on_changed_reviewed_frame(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "capture"
    (root / "screens").mkdir(parents=True)
    (root / "screens" / "one.png").write_bytes(b"changed")
    (root / "screens" / "two.png").write_bytes(b"two")
    dbdat = tmp_path / "dbdat"
    dbdat.mkdir()
    (dbdat / "EQ98030.FDI").write_bytes(b"eq")
    (dbdat / "JUG98030.FDI").write_bytes(b"jug")
    monkeypatch.setattr(mapping, "_eq_short_names", lambda _dbdat: {1: "F.C. Barcelona", 2: "R.C. Deportivo"})

    report = mapping.verify_capture(capture=_capture(), dbdat=dbdat, capture_root=root)

    assert report["tiles"][0]["reason"] == "reviewed-frame-sha256-mismatch"


def test_verify_rejects_duplicate_carrier_and_unsafe_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mapping, "_eq_short_names", lambda _dbdat: {1: "F.C. Barcelona", 2: "R.C. Deportivo"})
    payload = _capture()
    payload["tiles"][1]["eq_record_id"] = 1  # type: ignore[index]
    with pytest.raises(ValueError, match="duplicate eq_record_id"):
        mapping.verify_capture(capture=payload, dbdat=Path("/unused"), capture_root=Path("/unused"))

    payload = _capture()
    payload["tiles"][0]["screenshot"] = "../not-safe.png"  # type: ignore[index]
    with pytest.raises(ValueError, match="safe relative"):
        mapping.verify_capture(capture=payload, dbdat=Path("/unused"), capture_root=Path("/unused"))


def test_verify_refuses_a_multi_selection_route_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mapping, "_eq_short_names", lambda _dbdat: {1: "F.C. Barcelona", 2: "R.C. Deportivo"})
    payload = _capture()
    payload["route_selection_limit"] = 2
    with pytest.raises(ValueError, match="exactly 1"):
        mapping.verify_capture(capture=payload, dbdat=Path("/unused"), capture_root=Path("/unused"))
