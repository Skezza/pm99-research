from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_manager_gap_triage_v1 as triage  # noqa: E402


def _write(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _selector(name: str) -> dict[str, str]:
    return {"country_catalog": "eng", "competition_catalog": "prem", "club_name": name}


def _manager(name: str, manager: str) -> dict:
    return {
        "source_selector": _selector(name), "opening_fixture_date": "2000-08-12",
        "manager_name": manager, "source_name": "Archived manager list",
        "source_url": f"https://example.test/{name}", "source_snapshot_sha256": "a" * 64,
        "reason": "dated evidence",
    }


def _setup(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    root = tmp_path / "repo"
    current_root = root / "current"
    operations_root = root / "operations"
    season = "2000-01"
    revision = current_root / season / "revisions/r1"
    source = {"clubs": [_selector("Captured"), _selector("Conflict"), _selector("Missing")]}
    source_sha = _write(revision / "source.json", source)
    allocation = {
        "schema_version": triage.ALLOCATION_SCHEMA, "source_sha256": source_sha,
        "assignments": [
            {"carrier_id": 1, "club_name": "Captured", "source_selector": _selector("Captured")},
            {"carrier_id": 2, "club_name": "Conflict", "source_selector": _selector("Conflict")},
            {"carrier_id": 3, "club_name": "Missing", "source_selector": _selector("Missing")},
        ],
    }
    allocation_sha = _write(revision / "allocation.json", allocation)
    _write(current_root / season / "current.json", {
        "schema_version": triage.CURRENT_SCHEMA, "season": season,
        "artifacts": {
            "source": {"path": "revisions/r1/source.json", "sha256": source_sha},
            "allocation": {"path": "revisions/r1/allocation.json", "sha256": allocation_sha},
        },
    })
    ledger = {
        "schema_version": "pm99-opening-manager-ledger-v1",
        "sources": {"squad_source_capture_sha256": source_sha}, "managers": [],
        "gaps": [{"source_selector": _selector(name), "reason": "missing manager"}
                 for name in ("Captured", "Conflict", "Missing")],
    }
    ledger_path = root / "overlays/2000-01/manager-v1/opening-manager-ledger.json"
    ledger_sha = _write(ledger_path, ledger)
    audit_path = root / "overlays/2000-01/manager-v1/manager-overlay-audit.json"
    audit_sha = _write(audit_path, {
        "schema_version": triage.OVERLAY_SCHEMA, "season": season,
        "inputs": {"supplements": []}, "outputs": {"opening_manager_ledger_sha256": ledger_sha},
    })
    index = root / "overlay-index.json"
    _write(index, {
        "schema_version": triage.OVERLAY_INDEX_SCHEMA, "state": "frozen-manager-overlay-selection",
        "seasons": [{"season": season, "opening_manager_ledger": {
            "path": "overlays/2000-01/manager-v1/opening-manager-ledger.json", "sha256": ledger_sha,
        }, "manager_overlay_audit": {
            "path": "overlays/2000-01/manager-v1/manager-overlay-audit.json", "sha256": audit_sha,
        }}],
    })
    common = {
        "schema_version": triage.SUPPLEMENT_SCHEMA, "season_start_year": 2000,
        "sources": {"full_source_capture_sha256": source_sha, "carrier_allocation_sha256": allocation_sha},
        "gaps": [],
    }
    _write(operations_root / season / "opening-manager-supplement.allocated-transfermarkt-v1.json", {
        **common, "managers": [_manager("Captured", "Exact Manager"), _manager("Conflict", "First Manager")],
    })
    _write(operations_root / season / "opening-manager-supplement.allocated-transfermarkt-v2.json", {
        **common, "managers": [_manager("Conflict", "Second Manager")],
    })
    return root, current_root, operations_root, str(index)


def test_classifies_capture_conflict_and_uncaptured_without_writing(tmp_path: Path) -> None:
    root, current_root, operations_root, index = _setup(tmp_path)
    report = triage.build_report(
        current_root=current_root, overlay_index_path=Path(index), operations_root=operations_root, root=root,
    )
    assert report["summary"] == {
        "season_count": 1, "fixed_carrier_manager_gap_count": 3,
        "already_captured_not_integrated_count": 1,
        "existing_dated_conflicting_candidate_count": 1, "genuinely_uncaptured_count": 1,
    }
    rows = report["seasons"][0]["fixed_carrier_manager_gaps"]
    assert {row["source_selector"]["club_name"]: row["classification"] for row in rows} == {
        "Captured": "already-captured-not-integrated",
        "Conflict": "existing-dated-conflicting-candidate",
        "Missing": "genuinely-uncaptured",
    }
    assert report["first_actionable_automated_integration_tranche"]["status"] == "none"


def test_rejects_stale_capture_receipt_from_current_candidate_set(tmp_path: Path) -> None:
    root, current_root, operations_root, index = _setup(tmp_path)
    path = operations_root / "2000-01/opening-manager-supplement.allocated-transfermarkt-v1.json"
    value = json.loads(path.read_text())
    value["sources"]["full_source_capture_sha256"] = "b" * 64
    _write(path, value)
    report = triage.build_report(
        current_root=current_root, overlay_index_path=Path(index), operations_root=operations_root, root=root,
    )
    rows = report["seasons"][0]["fixed_carrier_manager_gaps"]
    assert next(row for row in rows if row["carrier_id"] == 1)["classification"] == "genuinely-uncaptured"
    docs = report["seasons"][0]["inputs"]["inspected_allocated_manager_capture_receipts"]
    assert docs[0]["rejection_reason"] == "source-capture-hash-mismatch"
