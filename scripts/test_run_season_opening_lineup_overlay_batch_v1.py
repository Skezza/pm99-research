"""Tests for write-once historic-ID opening-XI overlay batch materialisation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import run_season_opening_lineup_overlay_batch_v1 as batch


def _write(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def test_batch_materialises_once_then_reuses_the_overlay(monkeypatch, tmp_path: Path) -> None:
    season = "2000-01"
    current_root = tmp_path / "current"
    revision = current_root / season / "revisions/r1"
    source_path = revision / "source.json"
    source_sha = _write(source_path, {"clubs": []})
    _write(current_root / season / "current.json", {
        "schema_version": batch.common.CURRENT_SCHEMA, "season": season,
        "artifacts": {"source": {"path": "revisions/r1/source.json", "sha256": source_sha}},
    })
    opening_root = tmp_path / "opening"
    _write(opening_root / season / "opening-lineup-reconciliation.json", {"clubs": [], "sources": {"source_capture_sha256": source_sha}})
    operations = tmp_path / "operations"
    _write(operations / season / "opening-lineups.allocated-historic-id-v1.json", {"clubs": []})
    baseline = tmp_path / "baseline.json"
    _write(baseline, {"seasons": []})

    def fake_build_overlay(**_kwargs):
        reconciliation = {"clubs": []}
        return (reconciliation, {
            "schema_version": batch.overlay_v1.SCHEMA, "season": season,
            "outputs": {"opening_reconciliation_sha256": hashlib.sha256(batch._bytes(reconciliation)).hexdigest()},
            "coverage": {"reconciled_xi_club_count": 3, "historic_id_supplement_reconciled_xi_club_count": 2},
        })

    monkeypatch.setattr(batch.overlay_v1, "build_overlay", fake_build_overlay)
    result = batch.run_batch(
        baseline_index=baseline, current_root=current_root, opening_root=opening_root,
        operations_root=operations, overlays_root=tmp_path / "overlays", seasons=[season],
    )
    assert result["summary"] == {
        "season_count": 1, "materialised_count": 1, "already_materialised_count": 0,
        "reconciled_xi_club_count": 3, "historic_id_supplement_reconciled_xi_club_count": 2,
    }
    repeated = batch.run_batch(
        baseline_index=baseline, current_root=current_root, opening_root=opening_root,
        operations_root=operations, overlays_root=tmp_path / "overlays", seasons=[season],
    )
    assert repeated["summary"] == {
        "season_count": 1, "materialised_count": 0, "already_materialised_count": 1,
        "reconciled_xi_club_count": 3, "historic_id_supplement_reconciled_xi_club_count": 2,
    }
