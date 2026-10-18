"""Tests for explicit immutable manager-overlay selection."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import season_manager_overlay_index_v1 as index


def _write(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _selection(*, baseline_sha: str, season: str, overlay_id: str) -> dict:
    return {
        "schema_version": index.SELECTION_SCHEMA,
        "state": "explicit-manager-overlay-selection",
        "baseline_index_sha256": baseline_sha,
        "seasons": [{"season": season, "overlay_id": overlay_id}],
    }


def test_index_uses_explicit_selection_not_the_newest_directory(tmp_path: Path) -> None:
    baseline_sha = "a" * 64
    season = "2007-08"
    overlays = tmp_path / "overlays"
    for version in (1, 2, 3):
        root = overlays / season / f"manager-v{version}"
        ledger_sha = _write(root / "opening-manager-ledger.json", {"managers": [version], "gaps": []})
        _write(root / "manager-overlay-audit.json", {
            "schema_version": index.OVERLAY_SCHEMA, "season": season,
            "base": {"baseline_index_sha256": baseline_sha},
            "outputs": {"opening_manager_ledger_sha256": ledger_sha},
            "coverage": {"resolved_manager_count": version},
        })
    baseline_path = tmp_path / "baseline.json"
    _write(baseline_path, {})
    selection_path = tmp_path / "selection.json"
    selection = _selection(baseline_sha=baseline_sha, season=season, overlay_id="manager-v2")
    selection_sha = _write(selection_path, selection)
    result = index.build_index(
        baseline={"schema_version": index.BASELINE_SCHEMA, "state": "frozen-provisional-base", "seasons": [{"season": season}]},
        baseline_sha256=baseline_sha, baseline_path=baseline_path, overlays_root=overlays,
        selection=selection, selection_sha256=selection_sha, selection_path=selection_path,
        workspace_root=tmp_path,
    )
    assert result["seasons"][0]["overlay_id"] == "manager-v2"
    assert result["seasons"][0]["coverage"] == {"resolved_manager_count": 2}
    assert result["selection_policy"] == "every-overlay-id-is-explicitly-selected; no-directory-newest-selection"


def test_index_rejects_a_missing_explicit_season(tmp_path: Path) -> None:
    baseline_sha = "a" * 64
    selection = _selection(baseline_sha=baseline_sha, season="2000-01", overlay_id="manager-v1")
    with pytest.raises(index.OverlayIndexError, match="omits baseline season 2001-02"):
        index.build_index(
            baseline={"schema_version": index.BASELINE_SCHEMA, "state": "frozen-provisional-base", "seasons": [
                {"season": "2000-01"}, {"season": "2001-02"},
            ]},
            baseline_sha256=baseline_sha, baseline_path=tmp_path / "baseline.json",
            overlays_root=tmp_path / "overlays", selection=selection,
            selection_sha256="b" * 64, selection_path=tmp_path / "selection.json",
            workspace_root=tmp_path,
        )
