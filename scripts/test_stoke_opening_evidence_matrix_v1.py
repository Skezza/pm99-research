from __future__ import annotations

from pathlib import Path

from scripts.stoke_opening_evidence_matrix_v1 import build_matrix, canonical_json_bytes


def test_stoke_matrix_requires_xi_manager_formation_and_preallocation(tmp_path: Path) -> None:
    d = tmp_path / "2001-02"; d.mkdir()
    selector = {"country_catalog": "eng", "competition_catalog": "d2", "club_name": "Stoke City"}
    xi = [{"display_name": f"Player {i}", "source_position": "G" if i == 0 else "D" if i < 5 else "M" if i < 9 else "F"} for i in range(11)]
    (d / "opening-lineups.json").write_bytes(canonical_json_bytes({"clubs": [{"source_selector": selector, "first_league_fixture_date": "2001-08-11", "source_match_id": "1", "lineup_source_url": "https://example/match", "formation": None, "starting_xi": xi}]}))
    (d / "opening-manager-ledger.json").write_bytes(canonical_json_bytes({"managers": [{"source_selector": selector, "manager_name": "Manager", "evidence": {"source_url": "https://example/manager"}}]}))
    (d / "opening-squad-preallocation.json").write_bytes(canonical_json_bytes({"source_clubs": [{"selector": selector, "opening_xi_complete": True}]}))
    matrix = build_matrix([tmp_path])
    row = next(row for row in matrix["rows"] if row["season"] == "2001-02")
    assert row["screenshot_preflight_ready"] is True
    assert row["formation"] == "4-4-2"
    assert matrix["coverage"] == {"season_count": 25, "screenshot_preflight_ready_count": 1, "blocked_count": 24}


def test_stoke_matrix_rejects_a_stale_historical_current_plan(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence" / "2001-02"
    current = tmp_path / "historical" / "2001-02"
    evidence.mkdir(parents=True)
    current.mkdir(parents=True)
    (evidence / "opening-lineups.json").write_bytes(canonical_json_bytes({"clubs": []}))
    (evidence / "plan.json").write_bytes(canonical_json_bytes({"source_intake": {"sha256": "a" * 64}}))
    (current / "current.json").write_bytes(canonical_json_bytes({
        "revision_id": "rev-current",
        "artifacts": {"intake": {"sha256": "b" * 64}},
    }))

    matrix = build_matrix([tmp_path / "evidence"], historical_current_root=tmp_path / "historical")

    row = next(row for row in matrix["rows"] if row["season"] == "2001-02")
    assert row["status"] == "historical-current-binding-stale"
    assert row["screenshot_preflight_ready"] is False
