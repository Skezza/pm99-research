"""Tests for the serial, write-once allocated-manager batch runner."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import capture_allocated_manager_history_v1 as capture
from scripts import run_allocated_manager_backfill_batch_v1 as batch


def _write(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def test_batch_writes_once_then_reports_the_existing_receipt(monkeypatch, tmp_path: Path) -> None:
    season = "2000-01"
    current_root = tmp_path / "current"
    revision = current_root / season / "revisions/r1"
    source_path = revision / "source.json"
    allocation_path = revision / "allocation.json"
    source_sha = _write(source_path, {"clubs": []})
    allocation_sha = _write(allocation_path, {"assignments": []})
    _write(current_root / season / "current.json", {
        "schema_version": batch.CURRENT_SCHEMA, "season": season,
        "artifacts": {
            "source": {"path": "revisions/r1/source.json", "sha256": source_sha},
            "allocation": {"path": "revisions/r1/allocation.json", "sha256": allocation_sha},
        },
    })
    opening_root = tmp_path / "opening"
    _write(opening_root / season / "competition-map.json", {
        "schema_version": "pm99-transfermarkt-opening-lineup-competition-map-v1", "competitions": [{
            "country_catalog": "eng", "competition_catalog": "prem", "source_competition_code": "GB1",
        }],
    })
    _write(opening_root / season / "opening-manager-ledger.json", {"managers": [], "gaps": [], "sources": {}})

    def fake_capture(**_kwargs):
        return {"schema_version": capture.SCHEMA, "summary": {"supplemented_manager_count": 3}, "managers": [], "gaps": []}

    monkeypatch.setattr(batch.capture_v1, "capture", fake_capture)
    result = batch.run_batch(
        current_root=current_root, opening_root=opening_root, cache_dir=tmp_path / "cache",
        operations_root=tmp_path / "operations", seasons=[season], offline=True, delay=0,
    )
    assert result["summary"] == {"season_count": 1, "captured_count": 1, "already_captured_count": 0, "new_dated_manager_count": 3}

    repeated = batch.run_batch(
        current_root=current_root, opening_root=opening_root, cache_dir=tmp_path / "cache",
        operations_root=tmp_path / "operations", seasons=[season], offline=True, delay=0,
    )
    assert repeated["summary"] == {"season_count": 1, "captured_count": 0, "already_captured_count": 1, "new_dated_manager_count": 0}


def test_batch_prefers_the_latest_existing_version(tmp_path: Path) -> None:
    operations = tmp_path / "operations"
    first = operations / "2007-08/opening-manager-supplement.allocated-transfermarkt-v1.json"
    later = operations / "2007-08/opening-manager-supplement.allocated-transfermarkt-v2.json"
    _write(first, {"schema_version": capture.SCHEMA})
    _write(later, {"schema_version": capture.SCHEMA})
    assert batch._existing_output(operations, "2007-08") == later
