from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.opening_evidence_coverage_matrix_v1 import build_matrix, canonical_json_bytes


def _write(path: Path, value: object) -> str:
    payload = canonical_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def test_matrix_reports_exact_gaps_and_validates_bindings(tmp_path: Path) -> None:
    d = tmp_path / "base/2001-02"
    lineup_sha = _write(d / "opening-lineups.json", {
        "schema_version": "pm99-transfermarkt-opening-lineup-source-v1",
        "summary": {"source_club_count": 20, "captured_club_count": 18, "failed-club-count": 2},
    })
    preallocation_sha = _write(d / "opening-squad-preallocation.json", {
        "schema_version": "pm99-opening-squad-preallocation-v1",
        "sources": {"opening_lineup_sha256": lineup_sha},
        "summary": {"opening-xi-complete-club-count": 17, "opening-xi-incomplete-or-uncaptured-club-count": 3},
    })
    _write(d / "opening-manager-ledger.json", {
        "schema_version": "pm99-opening-manager-ledger-v1",
        "sources": {"opening_lineup_receipt_sha256": lineup_sha},
        "summary": {"resolved_manager_count": 16, "unresolved_manager_count": 4},
    })
    _write(d / "preallocation-package-audit.json", {
        "schema_version": "pm99-season-source-package-build-audit-v1",
        "opening_squad_preallocation_sha256": preallocation_sha,
        "coverage": {"exact_unique_club_match_count": 20},
        "release_eligible": False,
        "hard_blockers": [{"code": "gap"}],
    })

    result = build_matrix([tmp_path / "base"])
    assert result["coverage"] == {
        "season_count": 1,
        "lineup_captured_club_count": 18,
        "opening_xi_complete_club_count": 17,
        "resolved_manager_count": 16,
        "integrator_ready_season_count": 0,
    }
    assert result["rows"][0]["package"]["hard_blocker_count"] == 1
    assert result["rows"][0]["exact_opening_evidence_complete"] is False


def test_matrix_rejects_stale_preallocation(tmp_path: Path) -> None:
    d = tmp_path / "base/s"
    _write(d / "opening-lineups.json", {"schema_version": "pm99-transfermarkt-opening-lineup-source-v1", "summary": {}})
    _write(d / "opening-squad-preallocation.json", {
        "schema_version": "pm99-opening-squad-preallocation-v1",
        "sources": {"opening_lineup_sha256": "0" * 64},
        "summary": {},
    })
    with pytest.raises(ValueError, match="stale artifact binding"):
        build_matrix([tmp_path / "base"])


def test_matrix_marks_stale_historical_current_plan_not_ready(tmp_path: Path) -> None:
    d = tmp_path / "base/2001-02"
    _write(d / "opening-lineups.json", {
        "schema_version": "pm99-transfermarkt-opening-lineup-source-v1", "summary": {},
    })
    _write(d / "plan.json", {"source_intake": {"sha256": "a" * 64}})
    _write(tmp_path / "historical/2001-02/current.json", {
        "revision_id": "rev-current",
        "artifacts": {
            "intake": {"sha256": "b" * 64},
            "allocation": {"sha256": "c" * 64},
        },
    })

    result = build_matrix([tmp_path / "base"], historical_current_root=tmp_path / "historical")

    assert result["rows"][0]["historical_current_binding_errors"] == ["current-plan-intake-stale"]
    assert result["rows"][0]["evidence_integrator_ready"] is False
