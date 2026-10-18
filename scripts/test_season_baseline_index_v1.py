"""Tests for the append-only season baseline index."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_baseline_index_v1 as index  # noqa: E402


def _write(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def test_creates_one_immutable_provisional_baseline(tmp_path: Path) -> None:
    root = tmp_path / "calendar-bound"
    season = "2000-01"
    package_path = root / season / "draft-season-package.calendar-bound.json"
    package = {
        "season": {"start_year": 2000, "end_year": 2001, "label": "2000/01"},
        "calendar": {"target_year": 2000},
    }
    package_sha = _write(package_path, package)
    audit_sha = _write(package_path.with_name("calendar-binding-audit.json"), {"audit": True})
    matrix = {
        "schema_version": index.CALENDAR_BATCH_SCHEMA,
        "rows": [{
            "season": season,
            "state": "calendar-bound-provisional-draft",
            "release_eligible": False,
            "output_draft_sha256": package_sha,
            "calendar_binding_audit_sha256": audit_sha,
            "calendar_receipt_sha256": "a" * 64,
            "calendar_executable_sha256": "b" * 64,
        }],
        "summary": {"season_count": 1, "calendar_bound_draft_count": 1, "playable_count": 0},
    }
    _write(root / "calendar-binding-matrix.json", matrix)
    output = tmp_path / "baselines" / "calendar-bound-v2.json"

    result = index.write_index(calendar_bound_root=root, baseline_id="calendar-bound-v2", output=output)

    assert result["summary"]["frozen_provisional_base_count"] == 1
    assert json.loads(output.read_text())["seasons"][0]["base_draft"]["sha256"] == package_sha
    with pytest.raises(index.BaselineIndexError, match="refusing to overwrite"):
        index.write_index(calendar_bound_root=root, baseline_id="calendar-bound-v2", output=output)
