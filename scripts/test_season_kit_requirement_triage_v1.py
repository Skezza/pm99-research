import hashlib
import json
from pathlib import Path

from scripts.season_kit_requirement_triage_v1 import build_triage, canonical_json_bytes


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(root: Path, stem: str) -> dict:
    payload = stem.encode("ascii")
    digest = hashlib.sha256(payload).hexdigest()
    relative = f"artifacts/{stem}.bmp"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {"id": f"kit-render-test-{stem}", "kind": "kit-render", "sha256": digest, "relative_path": relative}


def test_triage_separates_current_status_from_stale_artifact_diagnostic(tmp_path: Path) -> None:
    historical, source, render = tmp_path / "historical", tmp_path / "source", tmp_path / "render"
    season = "2000-01"
    assignments = [{"carrier_id": carrier, "club_name": f"Club {carrier}"} for carrier in range(1, 6)]
    allocation = {"assignments": assignments}
    allocation_path = historical / season / "carrier-allocation.json"
    _write(allocation_path, allocation)
    current = {
        "schema_version": "pm99-historical-squad-backfill-current-v1",
        "revision_id": "rev-test",
        "artifacts": {"allocation": {"sha256": _sha(allocation_path)}},
    }
    current_path = historical / season / "current.json"
    _write(current_path, current)
    provenance = {
        "historical_revision_id": "rev-test",
        "historical_current_sha256": _sha(current_path),
        "historical_allocation_file_sha256": _sha(allocation_path),
        "allocation_sha256": _sha(allocation_path),
    }
    capture = {
        "schema_version": "pm99-season-kit-source-capture-v1",
        "season": {"label": "2000/01"},
        "provenance": provenance,
        "rows": [
            {"carrier_id": 1, "club_name": "Club 1", "status": "revision-captured-home-fields-ready"},
            {"carrier_id": 2, "club_name": "Club 2", "status": "revision-captured-home-fields-ready"},
            {"carrier_id": 3, "club_name": "Club 3", "status": "blocked-no-exact-season-page"},
            {"carrier_id": 4, "club_name": "Club 4", "status": "revision-captured-home-fields-ready"},
            {"carrier_id": 5, "club_name": "Club 5", "status": "revision-captured-home-fields-ready"},
        ],
    }
    request = {"clubs": assignments}
    request_path = source / season / "kit-catalogue-request-v1.json"
    _write(request_path, request)
    catalogue = {
        "schema_version": "pm99-season-kit-catalogue-v1",
        "season": {"label": "2000/01"},
        "provenance": {"request_sha256": _sha(request_path)},
        "rows": [
            {"carrier_id": 1, "club_name": "Club 1", "status": "source-ready"},
            {"carrier_id": 2, "club_name": "Club 2", "status": "source-ready"},
            {"carrier_id": 3, "club_name": "Club 3", "status": "blocked-no-target-season-source", "reason": "no-source"},
            {"carrier_id": 4, "club_name": "Different Club", "status": "source-ready"},
            {"carrier_id": 5, "club_name": "Club 5", "status": "source-ready"},
        ],
    }
    catalogue_path = source / season / "kit-catalogue-v1.json"
    _write(catalogue_path, catalogue)
    _write(source / season / "kit-source-capture-v1.json", capture)
    catalogue_sha = hashlib.sha256(canonical_json_bytes(catalogue)).hexdigest()
    artifacts = {carrier: [_artifact(render / season, f"{carrier}-a")] for carrier in (2, 4, 5)}
    receipt = {
        "schema_version": "pm99-season-kit-render-receipt-v1",
        "kit_catalogue_sha256": catalogue_sha,
        "rows": [
            {"carrier_id": 1, "club_name": "Club 1", "status": "not-rendered-exact-pattern-unavailable", "reason": "cache-miss"},
            {"carrier_id": 2, "club_name": "Club 2", "status": "rendered-source-ready", "artifacts": artifacts[2]},
            {"carrier_id": 3, "club_name": "Club 3", "status": "not-rendered-catalogue-gap"},
            {"carrier_id": 4, "club_name": "Different Club", "status": "rendered-source-ready", "artifacts": artifacts[4]},
            {"carrier_id": 5, "club_name": "Club 5", "status": "rendered-source-ready", "artifacts": artifacts[5]},
        ],
    }
    binding = {
        "schema_version": "pm99-season-kit-render-bindings-v1",
        "kit_catalogue_sha256": catalogue_sha,
        "clubs": [
            {"carrier_id": 4, "artifacts": artifacts[4]},
            {"carrier_id": 5, "artifacts": artifacts[5]},
        ],
    }
    _write(render / season / "kit-render-receipt-v1.json", receipt)
    _write(render / season / "kit-render-bindings-v1.json", binding)

    first = build_triage(historical, source, render)
    second = build_triage(historical, source, render)
    assert first == second
    assert first["coverage"]["classification_counts"] == {
        "rendered-and-bound": 1,
        "captured-but-unrendered": 1,
        "renderable-but-unbound": 1,
        "genuinely-uncaptured": 1,
        "conflicting": 1,
    }
    assert first["safe_automated_integration"]["candidates"] == [
        {"season": "2000-01", "carrier_id": 5, "club_name": "Club 5"}
    ]

    # Altering only the immutable pointer invalidates every otherwise good
    # artifact for release use, while retaining the actionable diagnosis.
    stale = json.loads(current_path.read_text(encoding="utf-8"))
    stale["revision_id"] = "rev-new"
    _write(current_path, stale)
    triage = build_triage(historical, source, render)
    assert triage["coverage"]["classification_counts"]["conflicting"] == 5
    assert triage["coverage"]["stale_artifact_diagnostic_counts"]["rendered-and-bound"] == 1
    assert triage["safe_automated_integration"]["candidate_count"] == 0
