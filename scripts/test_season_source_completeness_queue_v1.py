"""Tests for the fixed-carrier historical source-completeness queue."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_source_completeness_queue_v1 as queue  # noqa: E402


HASH = "a" * 64


def _write_json(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode()).hexdigest()


def _selector(club: str) -> dict[str, str]:
    return {"country_catalog": "eng", "competition_catalog": "prem", "club_name": club}


def _players() -> list[dict]:
    return [
        {"facts": {"unresolved_fields": ["height_cm"] if number == 1 else []}}
        for number in range(11)
    ]


def _xi() -> list[dict]:
    return [
        *[{"source_position": "G"}],
        *[{"source_position": "D"} for _ in range(4)],
        *[{"source_position": "M"} for _ in range(4)],
        *[{"source_position": "F"} for _ in range(2)],
    ]


def _inputs(tmp_path: Path) -> dict[str, Path]:
    season = "2000-01"
    current_root = tmp_path / "current"
    revision = current_root / season / "revisions/r1"
    source_path = revision / "source.json"
    intake_path = revision / "intake.json"
    allocation_path = revision / "allocation.json"
    source_sha = _write_json(source_path, {"clubs": [{"club_name": "Alpha"}, {"club_name": "Bravo"}]})
    _write_json(
        intake_path,
        {"source_clubs": [
            {"selector": _selector("Alpha"), "players": _players()},
            {"selector": _selector("Bravo"), "players": _players()},
        ]},
    )
    intake_sha = hashlib.sha256(intake_path.read_bytes()).hexdigest()
    _write_json(
        allocation_path,
        {"assignments": [
            {"carrier_id": 10, "club_name": "Alpha", "roster_capacity": 15, "source_selector": _selector("Alpha")},
            {"carrier_id": 20, "club_name": "Bravo", "roster_capacity": 11, "source_selector": _selector("Bravo")},
        ], "gaps": []},
    )
    allocation_sha = hashlib.sha256(allocation_path.read_bytes()).hexdigest()
    _write_json(
        current_root / season / "current.json",
        {"schema_version": queue.CURRENT_SCHEMA, "season": season, "revision_id": "r1", "artifacts": {
            "source": {"path": "revisions/r1/source.json", "sha256": source_sha},
            "intake": {"path": "revisions/r1/intake.json", "sha256": intake_sha},
            "allocation": {"path": "revisions/r1/allocation.json", "sha256": allocation_sha},
        }},
    )
    opening_root = tmp_path / "opening"
    _write_json(
        opening_root / season / "opening-manager-ledger.json",
        {"managers": [{
            "source_selector": _selector("Alpha"), "manager_name": "Exact Manager",
            "opening_fixture_date": "2000-08-12",
            "evidence": {"source_url": "https://example.test/report", "source_snapshot_sha256": HASH},
        }], "gaps": [{
            "source_selector": _selector("Bravo"), "reason": "no-first-league-match-report-capture",
        }]},
    )
    _write_json(
        opening_root / season / "opening-lineup-reconciliation.json",
        {"clubs": [
            {"source_selector": _selector("Alpha"), "first_league_fixture_date": "2000-08-12",
             "starting_xi_reconciled": True, "formation": None, "starting_xi": _xi()},
            {"source_selector": _selector("Bravo"), "first_league_fixture_date": "2000-08-13",
             "starting_xi_reconciled": False, "formation": "4-4-2", "starting_xi": _xi()},
        ]},
    )
    kit_root = tmp_path / "kits"
    catalogue_path = kit_root / season / "kit-catalogue-v1.json"
    catalogue_sha = _write_json(
        catalogue_path,
        {"rows": [
            {"carrier_id": 10, "carrier_status": "continuing", "status": "source-ready"},
            {"carrier_id": 20, "carrier_status": "exited", "status": "native-fallback-authorized"},
        ]},
    )
    binding_root = tmp_path / "bindings"
    artifact = binding_root / season / "artifacts/alpha.bmp"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"alpha-kit")
    artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    _write_json(
        binding_root / season / "kit-render-bindings-v1.json",
        {"kit_catalogue_sha256": catalogue_sha, "clubs": [{"carrier_id": 10, "artifacts": [{
            "relative_path": "artifacts/alpha.bmp", "sha256": artifact_sha,
        }]}]},
    )
    return {
        "current": current_root, "opening": opening_root, "kits": kit_root,
        "bindings": binding_root, "calendar": tmp_path / "calendar", "output": tmp_path / "output",
    }


def test_queue_scopes_to_fixed_carriers_and_applies_authorised_fallbacks(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)

    report = queue.build_report(
        current_root=paths["current"], opening_root=paths["opening"], kit_root=paths["kits"],
        kit_bindings_root=paths["bindings"], calendar_root=paths["calendar"], output_root=paths["output"],
    )

    row = report["seasons"][0]
    assert row["scope"]["assigned_fixed_carrier_count"] == 2
    assert row["manager_identity"]["exact_dated_hash_backed"] == 1
    assert row["manager_identity"]["queue_total"] == 1
    assert row["manager_identity"]["required_carriers"] == 2
    assert row["manager_identity"]["unresolved"] == 1
    assert row["opening_xi_and_august_squad"]["opening_xi"]["usable_deterministic_formation"] == 1
    assert len(row["work_queues"]["opening_xi"]) == 1
    assert row["opening_xi_and_august_squad"]["opening_squad"]["under_eleven_player_rows"] == 0
    assert row["secondary_player_facts"]["unresolved_field_counts"] == {"height_cm": 2}
    assert row["kits"]["coverage"]["native_exited_fallback_authorized"] == 1
    assert row["kits"]["coverage"]["source_ready_rendered"] == 1
    assert row["kits"]["coverage"]["queue_total"] == 0
    assert report["summary"]["playable_count"] == 0
    assert "not a release or playable-game claim" in queue.markdown_report(report)


def test_invalid_manager_evidence_stays_an_explicit_manager_queue_item(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    ledger = paths["opening"] / "2000-01/opening-manager-ledger.json"
    document = json.loads(ledger.read_text(encoding="utf-8"))
    document["managers"][0]["evidence"]["source_snapshot_sha256"] = "missing"
    _write_json(ledger, document)

    report = queue.build_report(
        current_root=paths["current"], opening_root=paths["opening"], kit_root=paths["kits"],
        kit_bindings_root=paths["bindings"], calendar_root=paths["calendar"], output_root=paths["output"],
    )

    items = report["seasons"][0]["work_queues"]["manager"]
    assert report["seasons"][0]["manager_identity"]["invalid_evidence"] == 1
    assert items[0]["reason"] == "dated-manager-source-snapshot-missing-or-invalid"
    assert items[0]["required_resolution"].startswith("replace with one exact")


def test_queue_can_use_an_explicit_hash_bound_manager_overlay(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    season = "2000-01"
    source_path = paths["current"] / season / "revisions/r1/source.json"
    source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    lineups_path = paths["opening"] / season / "opening-lineups.json"
    lineups_sha = _write_json(lineups_path, {"opening": "immutable-input"})
    overlay_root = tmp_path / "overlays"
    overlay_dir = overlay_root / season / "manager-v2"
    ledger_path = overlay_dir / "opening-manager-ledger.json"
    ledger_sha = _write_json(ledger_path, {"managers": [
        {
            "source_selector": _selector("Alpha"), "manager_name": "Exact Manager",
            "opening_fixture_date": "2000-08-12",
            "evidence": {"source_url": "https://example.test/alpha", "source_snapshot_sha256": HASH},
        },
        {
            "source_selector": _selector("Bravo"), "manager_name": "New Exact Manager",
            "opening_fixture_date": "2000-08-13",
            "evidence": {"source_url": "https://example.test/bravo", "source_snapshot_sha256": "b" * 64},
        },
    ], "gaps": []})
    _write_json(overlay_dir / "manager-overlay-audit.json", {
        "schema_version": queue.MANAGER_OVERLAY_SCHEMA,
        "season": season,
        "inputs": {"source_capture_sha256": source_sha, "opening_lineups_sha256": lineups_sha},
        "outputs": {"opening_manager_ledger_sha256": ledger_sha},
    })

    report = queue.build_report(
        current_root=paths["current"], opening_root=paths["opening"], kit_root=paths["kits"],
        kit_bindings_root=paths["bindings"], calendar_root=paths["calendar"], output_root=paths["output"],
        manager_overlay_root=overlay_root, manager_overlay_id="manager-v2",
    )

    row = report["seasons"][0]
    assert row["manager_identity"]["exact_dated_hash_backed"] == 2
    assert row["manager_identity"]["queue_total"] == 0
    assert row["inputs"]["manager_overlay"]["overlay_id"] == "manager-v2"


def test_queue_can_use_a_per_season_hash_bound_manager_overlay_index(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    season = "2000-01"
    source_path = paths["current"] / season / "revisions/r1/source.json"
    source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    lineups_path = paths["opening"] / season / "opening-lineups.json"
    lineups_sha = _write_json(lineups_path, {"opening": "immutable-input"})
    overlay_dir = tmp_path / "overlays" / season / "manager-v2"
    ledger_path = overlay_dir / "opening-manager-ledger.json"
    ledger_sha = _write_json(ledger_path, {"managers": [
        {
            "source_selector": _selector("Alpha"), "manager_name": "Exact Manager",
            "opening_fixture_date": "2000-08-12",
            "evidence": {"source_url": "https://example.test/alpha", "source_snapshot_sha256": HASH},
        },
        {
            "source_selector": _selector("Bravo"), "manager_name": "New Exact Manager",
            "opening_fixture_date": "2000-08-13",
            "evidence": {"source_url": "https://example.test/bravo", "source_snapshot_sha256": "b" * 64},
        },
    ], "gaps": []})
    baseline_path = tmp_path / "baseline.json"
    baseline_sha = _write_json(baseline_path, {
        "schema_version": "pm99-season-baseline-index-v1", "state": "frozen-provisional-base",
        "seasons": [{"season": season}],
    })
    audit_path = overlay_dir / "manager-overlay-audit.json"
    audit_sha = _write_json(audit_path, {
        "schema_version": queue.MANAGER_OVERLAY_SCHEMA, "season": season,
        "base": {"baseline_index_sha256": baseline_sha},
        "inputs": {"source_capture_sha256": source_sha, "opening_lineups_sha256": lineups_sha},
        "outputs": {"opening_manager_ledger_sha256": ledger_sha},
    })
    selection_path = tmp_path / "selection.json"
    selection_sha = _write_json(selection_path, {
        "schema_version": queue.MANAGER_OVERLAY_SELECTION_SCHEMA,
        "state": "explicit-manager-overlay-selection", "baseline_index_sha256": baseline_sha,
        "seasons": [{"season": season, "overlay_id": "manager-v2"}],
    })
    index_path = tmp_path / "index.json"
    _write_json(index_path, {
        "schema_version": queue.MANAGER_OVERLAY_INDEX_SCHEMA,
        "state": "frozen-manager-overlay-selection",
        "selection_policy": "every-overlay-id-is-explicitly-selected; no-directory-newest-selection",
        "baseline_index_sha256": baseline_sha,
        "baseline_index": {"path": "baseline.json", "sha256": baseline_sha},
        "selection_manifest": {"path": "selection.json", "sha256": selection_sha},
        "seasons": [{
            "season": season, "overlay_id": "manager-v2",
            "manager_overlay_audit": {"path": "overlays/2000-01/manager-v2/manager-overlay-audit.json", "sha256": audit_sha},
            "opening_manager_ledger": {"path": "overlays/2000-01/manager-v2/opening-manager-ledger.json", "sha256": ledger_sha},
        }],
    })

    report = queue.build_report(
        current_root=paths["current"], opening_root=paths["opening"], kit_root=paths["kits"],
        kit_bindings_root=paths["bindings"], calendar_root=paths["calendar"], output_root=paths["output"],
        manager_overlay_index_path=index_path, manager_overlay_index_root=tmp_path,
    )

    row = report["seasons"][0]
    assert row["manager_identity"]["exact_dated_hash_backed"] == 2
    assert row["inputs"]["manager_overlay"]["overlay_id"] == "manager-v2"
    assert report["inputs"]["manager_overlay_index"]["sha256"] == hashlib.sha256(index_path.read_bytes()).hexdigest()


def test_queue_rejects_a_stale_manager_overlay_index_binding(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    season = "2000-01"
    source_path = paths["current"] / season / "revisions/r1/source.json"
    source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    lineups_path = paths["opening"] / season / "opening-lineups.json"
    lineups_sha = _write_json(lineups_path, {"opening": "immutable-input"})
    overlay_dir = tmp_path / "overlays" / season / "manager-v1"
    ledger_path = overlay_dir / "opening-manager-ledger.json"
    ledger_sha = _write_json(ledger_path, {"managers": [], "gaps": []})
    baseline_path = tmp_path / "baseline.json"
    baseline_sha = _write_json(baseline_path, {
        "schema_version": "pm99-season-baseline-index-v1", "state": "frozen-provisional-base",
        "seasons": [{"season": season}],
    })
    audit_path = overlay_dir / "manager-overlay-audit.json"
    audit_sha = _write_json(audit_path, {
        "schema_version": queue.MANAGER_OVERLAY_SCHEMA, "season": season,
        "base": {"baseline_index_sha256": baseline_sha},
        "inputs": {"source_capture_sha256": source_sha, "opening_lineups_sha256": lineups_sha},
        "outputs": {"opening_manager_ledger_sha256": ledger_sha},
    })
    selection_path = tmp_path / "selection.json"
    selection_sha = _write_json(selection_path, {
        "schema_version": queue.MANAGER_OVERLAY_SELECTION_SCHEMA,
        "state": "explicit-manager-overlay-selection", "baseline_index_sha256": baseline_sha,
        "seasons": [{"season": season, "overlay_id": "manager-v1"}],
    })
    index_path = tmp_path / "index.json"
    _write_json(index_path, {
        "schema_version": queue.MANAGER_OVERLAY_INDEX_SCHEMA,
        "state": "frozen-manager-overlay-selection",
        "selection_policy": "every-overlay-id-is-explicitly-selected; no-directory-newest-selection",
        "baseline_index_sha256": baseline_sha,
        "baseline_index": {"path": "baseline.json", "sha256": baseline_sha},
        "selection_manifest": {"path": "selection.json", "sha256": selection_sha},
        "seasons": [{
            "season": season, "overlay_id": "manager-v1",
            "manager_overlay_audit": {"path": "overlays/2000-01/manager-v1/manager-overlay-audit.json", "sha256": audit_sha},
            "opening_manager_ledger": {"path": "overlays/2000-01/manager-v1/opening-manager-ledger.json", "sha256": ledger_sha},
        }],
    })
    _write_json(ledger_path, {"managers": [{"later": "mutation"}], "gaps": []})

    with pytest.raises(queue.QueueError, match="selected manager ledger is stale or missing"):
        queue.build_report(
            current_root=paths["current"], opening_root=paths["opening"], kit_root=paths["kits"],
            kit_bindings_root=paths["bindings"], calendar_root=paths["calendar"], output_root=paths["output"],
            manager_overlay_index_path=index_path, manager_overlay_index_root=tmp_path,
        )


def test_queue_can_use_an_explicit_hash_bound_opening_xi_overlay(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    season = "2000-01"
    source_path = paths["current"] / season / "revisions/r1/source.json"
    source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    base_path = paths["opening"] / season / "opening-lineup-reconciliation.json"
    base_sha = hashlib.sha256(base_path.read_bytes()).hexdigest()
    overlay_root = tmp_path / "overlays"
    overlay_dir = overlay_root / season / "opening-xi-v1"
    overlay_reconciliation = json.loads(base_path.read_text(encoding="utf-8"))
    overlay_reconciliation["clubs"][1].update({"starting_xi_reconciled": True, "formation": None})
    overlay_path = overlay_dir / "opening-lineup-reconciliation.json"
    overlay_sha = _write_json(overlay_path, overlay_reconciliation)
    _write_json(overlay_dir / "opening-lineup-overlay-audit.json", {
        "schema_version": queue.OPENING_XI_OVERLAY_SCHEMA,
        "season": season,
        "inputs": {"source_capture_sha256": source_sha, "base_reconciliation_sha256": base_sha},
        "outputs": {"opening_reconciliation_sha256": overlay_sha},
    })

    report = queue.build_report(
        current_root=paths["current"], opening_root=paths["opening"], kit_root=paths["kits"],
        kit_bindings_root=paths["bindings"], calendar_root=paths["calendar"], output_root=paths["output"],
        opening_xi_overlay_root=overlay_root, opening_xi_overlay_id="opening-xi-v1",
    )

    row = report["seasons"][0]
    assert row["opening_xi_and_august_squad"]["opening_xi"]["usable_deterministic_formation"] == 2
    assert row["opening_xi_and_august_squad"]["opening_xi"]["queue_total"] == 0
    assert row["inputs"]["opening_xi_overlay"]["overlay_id"] == "opening-xi-v1"
