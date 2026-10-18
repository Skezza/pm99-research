"""Tests for write-once manager-overlay batching."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import run_season_manager_overlay_batch_v1 as batch


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode())


def test_overlay_batch_materialises_once_then_skips(monkeypatch, tmp_path: Path) -> None:
    season = "2002-03"
    operations = tmp_path / "operations"
    _write(operations / season / "opening-manager-supplement.allocated-transfermarkt-v1.json", {"schema_version": "pm99-opening-manager-supplement-v1"})
    monkeypatch.setattr(batch, "_source_path", lambda *_args: tmp_path / "source.json")

    def fake_write_overlay(**kwargs):
        output = kwargs["output_root"]
        output.mkdir(parents=True)
        _write(output / "manager-overlay-audit.json", {"schema_version": batch.overlay_v1.SCHEMA, "coverage": {"resolved_manager_count": 7}})
        return {"coverage": {"resolved_manager_count": 7}}

    monkeypatch.setattr(batch.overlay_v1, "write_overlay", fake_write_overlay)
    result = batch.run_batch(
        baseline_index=tmp_path / "baseline.json", current_root=tmp_path / "current", opening_root=tmp_path / "opening",
        operations_root=operations, overlays_root=tmp_path / "overlays", seasons=[season],
    )
    assert result["summary"] == {"season_count": 1, "materialised_count": 1, "already_materialised_count": 0, "resolved_manager_count": 7}

    repeated = batch.run_batch(
        baseline_index=tmp_path / "baseline.json", current_root=tmp_path / "current", opening_root=tmp_path / "opening",
        operations_root=operations, overlays_root=tmp_path / "overlays", seasons=[season],
    )
    assert repeated["summary"] == {"season_count": 1, "materialised_count": 0, "already_materialised_count": 1, "resolved_manager_count": 7}
