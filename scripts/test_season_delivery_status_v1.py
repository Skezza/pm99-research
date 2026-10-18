"""Tests for the evidence-only season delivery status report."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_delivery_status_v1 as status  # noqa: E402


def _write_json(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, sort_keys=True)
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode()).hexdigest()


def _write_canonical_json(path: Path, value: object) -> tuple[str, str, int]:
    """Write pipeline-style canonical JSON and return file/content bindings."""

    path.parent.mkdir(parents=True, exist_ok=True)
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(canonical + b"\n")
    return hashlib.sha256(canonical + b"\n").hexdigest(), hashlib.sha256(canonical).hexdigest(), len(canonical)


def _write_canonical_package_build_evidence(tmp_path: Path, *, season: str) -> tuple[str, Path, Path]:
    """Create the smallest complete canonical-package-to-runtime chain."""

    canonical_package = tmp_path / "seasons" / season / "season-package.json"
    package_file_sha, _package_semantic_sha, _ = _write_canonical_json(
        canonical_package, {"package": "registered"},
    )
    candidate = tmp_path / ".local/season-canonical-candidate-v1" / "fixture-candidate"
    candidate_package_sha, _, _ = _write_canonical_json(
        candidate / "season-package.candidate.json", {"package": "registered"},
    )
    base_fingerprint = "a" * 64
    base = {
        "schema": "pm99-verified-base-v2",
        "base_id": "fixture-base",
        "inventory": {"files_fingerprint": base_fingerprint, "file_count": 4, "total_bytes": 40},
    }
    base_file_sha, _, _ = _write_canonical_json(candidate / "verified-base.json", base)
    effective_path = candidate / "prepared/season-package.effective.json"
    effective_file_sha, effective_semantic_sha, effective_size = _write_canonical_json(
        effective_path, {"effective": "fixture"},
    )
    effective_descriptor = {
        "canonical_sha256": effective_semantic_sha,
        "canonical_size": effective_size,
        "schema": None,
    }
    candidate_plan = {
        "schema_version": "pm99-season-build-plan-candidate-v1",
        "season": season,
        "state": "blocked-before-binary-compile",
        "release_eligible": False,
        "base": {"base_id": "fixture-base", "inventory_fingerprint": base_fingerprint},
        "effective_package": {
            "relative_path": "prepared/season-package.effective.json",
            "schema": "pm99-season-package-v2",
            "sha256": effective_file_sha,
            "size": effective_size + 1,
        },
    }
    candidate_plan_sha, _, _ = _write_canonical_json(candidate / "build-plan.candidate.json", candidate_plan)
    _write_canonical_json(
        candidate / "promotion-audit.json",
        {
            "schema_version": "pm99-season-canonical-promotion-factory-v1",
            "season": season,
            "state": "canonical-workspace-candidate-only",
            "release_eligible": False,
            "input": {"verified_base_descriptor_sha256": base_file_sha},
            "outputs": {
                "package": {"relative_path": "season-package.candidate.json", "sha256": candidate_package_sha},
                "prepared_effective_package": {
                    "relative_path": "prepared/season-package.effective.json", "sha256": effective_file_sha,
                },
                "build_plan_candidate": {
                    "relative_path": "build-plan.candidate.json", "sha256": candidate_plan_sha,
                },
            },
            "static_contracts": {
                "season_package_v2_strict": "passed",
                "calendar_binding": "passed",
                "verified_base_descriptor": "passed",
                "workspace_contract": "passed",
                "workspace_prepare": "passed",
            },
        },
    )

    database_hashes = {
        "DBDAT/ENT98030.FDI": "b" * 64,
        "DBDAT/EQ98030.FDI": "c" * 64,
        "DBDAT/JUG98030.FDI": "d" * 64,
    }
    database_inventory = {
        "files": [
            {"path": path, "sha256": digest, "size": 1}
            for path, digest in sorted(database_hashes.items())
        ],
    }
    final_fingerprint = "e" * 64
    final_inventory = {
        "files_fingerprint": final_fingerprint,
        "file_count": 4,
        "total_bytes": 44,
        "files": database_inventory["files"] + [{"path": "MANAGPRE.EXE", "sha256": "f" * 64, "size": 1}],
    }
    plan = {
        "schema": "pm99-season-build-plan-v2",
        "season": season,
        "base": candidate_plan["base"],
        "season_package": effective_descriptor,
        "stages": [{"id": "database-compiler", "expected_output_inventory": database_inventory}],
        "expected_final_output_inventory": final_inventory,
    }
    plan_path = tmp_path / ".local/season-build-plans-v2" / "fixture-plan" / "build-plan.json"
    _plan_file_sha, plan_semantic_sha, _ = _write_canonical_json(plan_path, plan)
    metadata = tmp_path / ".local/season-build-plans-v2" / "fixture-plan-r1-metadata"
    manifest = {
        "schema": "pm99-season-release-manifest-v2",
        "season": season,
        "base": {
            "base_id": "fixture-base",
            "inventory_fingerprint": base_fingerprint,
            "file_count": 4,
            "total_bytes": 40,
        },
        "season_document": {"id": "season-package", **effective_descriptor},
        "output": {
            "inventory_fingerprint": final_fingerprint,
            "file_count": 4,
            "total_bytes": 44,
        },
    }
    manifest_file_sha, manifest_semantic_sha, _ = _write_canonical_json(metadata / "season-manifest.json", manifest)
    _write_canonical_json(metadata / "output.inventory.json", final_inventory)
    _write_canonical_json(
        metadata / "build-plan-receipt.json",
        {
            "schema": "pm99-season-build-plan-receipt-v2",
            "plan_sha256": plan_semantic_sha,
            "season": season,
            "base_inventory_fingerprint": base_fingerprint,
            "season_package_canonical_sha256": effective_semantic_sha,
            "final_output_inventory_fingerprint": final_fingerprint,
            "release_manifest_sha256": manifest_semantic_sha,
        },
    )
    _write_canonical_json(
        metadata / "clean-base-audit.json",
        {
            "schema_version": "pm99-season-clean-base-audit-v1",
            "result": "pass",
            "package_canonical_sha256": effective_file_sha,
            "base_inventory_fingerprint": base_fingerprint,
            "append_or_recycle_count": 0,
            "fixed_roster_tail_mismatch_count": 0,
            "output_database_sha256": database_hashes,
        },
    )
    summary_path = tmp_path / "artifacts/runtime/summary.json"
    summary_path.parent.mkdir(parents=True)
    summary_path.write_text(json.dumps({
        "success": True, "wine_debugger_detected": False, "division_count": 4, "observation_count": 80,
    }), encoding="utf-8")
    screenshot_path = summary_path.parent / "screens/fixture.png"
    screenshot_path.parent.mkdir()
    screenshot_path.write_bytes(b"fixture screenshot")
    runtime_receipt = {
        "route_kind": "selector-discovery",
        "input_binding": {
            "output_inventory_fingerprint": final_fingerprint,
            "release_manifest_file_sha256": manifest_file_sha,
        },
        "result": {
            "success": True, "wine_debugger_detected": False, "division_count": 4, "observation_count": 80,
        },
        "summary": {
            "path": str(summary_path.relative_to(tmp_path)),
            "sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
            "bytes": summary_path.stat().st_size,
        },
        "screenshot": {
            "path": str(screenshot_path.relative_to(tmp_path)),
            "sha256": hashlib.sha256(screenshot_path.read_bytes()).hexdigest(),
            "bytes": screenshot_path.stat().st_size,
        },
    }
    runtime_receipts = [runtime_receipt]
    # This sidecar deliberately need not be canonical; its content is sealed
    # by the canonical attestation below and compared structurally by the reader.
    (metadata / "runtime-receipts.json").parent.mkdir(parents=True, exist_ok=True)
    (metadata / "runtime-receipts.json").write_text(json.dumps(runtime_receipts, indent=2), encoding="utf-8")
    _write_canonical_json(
        metadata / "runtime-attestation.json",
        {
            "schema": "pm99-season-release-attestation-v2",
            "output_inventory_fingerprint": final_fingerprint,
            "release_manifest_sha256": manifest_semantic_sha,
            "runtime_receipts": runtime_receipts,
        },
    )
    return package_file_sha, summary_path, screenshot_path


def _write_verified_workspace_candidate(
    tmp_path: Path, *, season: str, draft_payload: dict, draft_sha: str, source_audit_sha: str,
    candidate_payload: dict | None = None, alias_bound: bool = False,
) -> None:
    candidate = tmp_path / ".local/season-canonical-candidate-v1" / season
    candidate_package_sha = _write_json(
        candidate / "season-package.candidate.json", candidate_payload or draft_payload,
    )
    base_sha = _write_json(candidate / "verified-base.json", {"base": True})
    output_hashes = {
        "prepared_effective_package": _write_json(candidate / "prepared/season-package.effective.json", {"effective": True}),
        "timeline": _write_json(candidate / "editorial-timeline.json", {"timeline": True}),
        "workspace": _write_json(candidate / "workspace.json", {"workspace": True}),
        "build_plan_candidate": _write_json(candidate / "build-plan.candidate.json", {"plan": True}),
    }
    _write_json(
        candidate / "promotion-audit.json",
        {
            "schema_version": "pm99-season-canonical-promotion-factory-v1",
            "season": season,
            "state": "canonical-workspace-candidate-only",
            "release_eligible": False,
            "input": {
                "calendar_bound_package_sha256": draft_sha,
                "calendar_binding_audit_sha256": source_audit_sha,
                "verified_base_descriptor_sha256": base_sha,
                **({
                    "display_alias_binding": {
                        "source_package_sha256": draft_sha,
                        "alias_package_sha256": candidate_package_sha,
                        "display_alias_audit_sha256": "a" * 64,
                        "changed_display_name_count": 1,
                    },
                } if alias_bound else {}),
            },
            "outputs": {
                "package": {"relative_path": "season-package.candidate.json", "sha256": candidate_package_sha},
                **{
                    key: {
                        "relative_path": {
                            "prepared_effective_package": "prepared/season-package.effective.json",
                            "timeline": "editorial-timeline.json",
                            "workspace": "workspace.json",
                            "build_plan_candidate": "build-plan.candidate.json",
                        }[key],
                        "sha256": value,
                    }
                    for key, value in output_hashes.items()
                },
            },
            "static_contracts": {
                "season_package_v2_strict": "passed",
                "calendar_binding": "passed",
                "verified_base_descriptor": "passed",
                "workspace_contract": "passed",
                "workspace_prepare": "passed",
                **({"display_alias_binding": "passed"} if alias_bound else {}),
            },
            "not_performed": ["binary compiler materialisation", "PM99 runtime validation"],
        },
    )


def test_bound_source_and_draft_package_remain_provisional(tmp_path: Path) -> None:
    season = "2000-01"
    source = tmp_path / ".local/season-historical-squad-backfill-v1" / season / "revisions/r1/world.json"
    intake = tmp_path / ".local/season-historical-squad-backfill-v1" / season / "revisions/r1/intake.json"
    source_sha = _write_json(source, {"source": True})
    intake_sha = _write_json(intake, {"intake": True})
    _write_json(
        source.parents[2] / "current.json",
        {
            "revision_id": "r1",
            "artifacts": {
                "source": {"path": "revisions/r1/world.json", "sha256": source_sha},
                "intake": {"path": "revisions/r1/intake.json", "sha256": intake_sha},
            },
        },
    )
    _write_json(
        tmp_path / ".local/season-authoring-final-shards-v1/a" / season / "draft-season-package.json",
        {"schema_version": "pm99-season-package-v2", "package_id": "draft"},
    )
    (tmp_path / "seasons" / season).mkdir(parents=True)

    report = status.build_report(tmp_path, remote_host=None)
    row = report["seasons"][0]

    assert row["source"]["state"] == "bound"
    assert row["package"]["state"] == "draft-package"
    assert row["compilation"]["state"] == "not-compiled"
    assert row["delivery"]["classification"] == "provisional-not-playable"
    assert "successful runtime route" in row["delivery"]["gates_missing"]


def test_current_calendar_bound_source_draft_surfaces_without_a_release_claim(tmp_path: Path) -> None:
    season = "2005-06"
    source = tmp_path / ".local/season-historical-squad-backfill-v1" / season / "revisions/r1/world.json"
    intake = tmp_path / ".local/season-historical-squad-backfill-v1" / season / "revisions/r1/intake.json"
    source_sha = _write_json(source, {"source": True})
    intake_sha = _write_json(intake, {"intake": True})
    _write_json(
        source.parents[2] / "current.json",
        {
            "revision_id": "r1",
            "artifacts": {
                "source": {"path": "revisions/r1/world.json", "sha256": source_sha},
                "intake": {"path": "revisions/r1/intake.json", "sha256": intake_sha},
            },
        },
    )
    draft = tmp_path / ".local/season-authoring-post-calendar-binding-v2" / season / "draft-season-package.json"
    draft_sha = _write_json(draft, {"schema_version": "pm99-season-package-v2", "package_id": "draft"})
    _write_json(
        draft.with_name("source-package-build-audit.json"),
        {
            "schema_version": "pm99-season-source-package-build-audit-v1",
            "draft_package_sha256": draft_sha,
            "source_intake_sha256": intake_sha,
            "template_package_sha256": "template-hash",
            "release_eligible": False,
            "coverage": {"calendar_binding_verified_count": 1},
            "calendar_binding": {
                "template_package_sha256": "template-hash",
                "audit_sha256": "calendar-audit-hash",
                "receipt_sha256": "calendar-receipt-hash",
                "executable_sha256": "calendar-executable-hash",
                "runtime_validation_pending": True,
            },
            "hard_blockers": [{"code": "ratings-reconciliation-required"}],
        },
    )
    (tmp_path / "seasons" / season).mkdir(parents=True)

    row = status.build_report(tmp_path, remote_host=None)["seasons"][0]

    assert row["package"]["state"] == "calendar-bound-source-draft"
    assert row["package"]["hard_blocker_count"] == 1
    assert row["package"]["calendar_binding"]["runtime_validation_pending"] is True
    assert row["delivery"]["classification"] == "provisional-not-playable"
    assert "canonical release package (draft packages are not releases)" in row["delivery"]["gates_missing"]


def test_frozen_baseline_surfaces_all_target_seasons_without_a_release_claim(tmp_path: Path) -> None:
    season = "2000-01"
    source = tmp_path / ".local/season-historical-squad-backfill-v1" / season / "revisions/r1/world.json"
    intake = tmp_path / ".local/season-historical-squad-backfill-v1" / season / "revisions/r1/intake.json"
    source_sha = _write_json(source, {"source": True})
    intake_sha = _write_json(intake, {"intake": True})
    _write_json(
        source.parents[2] / "current.json",
        {
            "revision_id": "r1",
            "artifacts": {
                "source": {"path": "revisions/r1/world.json", "sha256": source_sha},
                "intake": {"path": "revisions/r1/intake.json", "sha256": intake_sha},
            },
        },
    )
    package = tmp_path / ".local/season-calendar-bound-batch-v2" / season / "draft-season-package.calendar-bound.json"
    package_payload = {
        "schema_version": "pm99-season-package-v2",
        "package_id": "world-2000-01-source-draft",
        "season": {"start_year": 2000, "end_year": 2001, "label": "2000/01"},
    }
    package_sha = _write_json(package, package_payload)
    audit = package.with_name("calendar-binding-audit.json")
    audit_sha = _write_json(audit, {"schema_version": "pm99-season-calendar-package-overlay-v1"})
    _write_json(
        tmp_path / ".local/season-baselines-v1/calendar-bound-v2.json",
        {
            "schema_version": "pm99-season-baseline-index-v1",
            "state": "frozen-provisional-base",
            "seasons": [{
                "season": season,
                "base_draft": {"path": str(package.relative_to(tmp_path)), "sha256": package_sha},
                "calendar_binding_audit": {"path": str(audit.relative_to(tmp_path)), "sha256": audit_sha},
                "calendar_receipt_sha256": "a" * 64,
                "calendar_executable_sha256": "b" * 64,
            }],
        },
    )
    source_audit = tmp_path / ".local/season-authoring-post-calendar-binding-v2" / season / "source-package-build-audit.json"
    source_audit_sha = _write_json(
        source_audit,
        {
            "schema_version": "pm99-season-source-package-build-audit-v1",
            "draft_package_sha256": package_sha,
            "source_intake_sha256": intake_sha,
            "template_package_sha256": package_sha,
            "release_eligible": False,
            "coverage": {"calendar_binding_verified_count": 1},
            "calendar_binding": {
                "template_package_sha256": package_sha,
                "audit_sha256": audit_sha,
                "receipt_sha256": "calendar-receipt-hash",
                "executable_sha256": "calendar-executable-hash",
                "runtime_validation_pending": True,
            },
            "hard_blockers": [{"code": "ratings-reconciliation-required"}],
        },
    )
    _write_json(source_audit.with_name("draft-season-package.json"), package_payload)
    _write_verified_workspace_candidate(
        tmp_path,
        season=season,
        draft_payload=package_payload,
        draft_sha=package_sha,
        source_audit_sha=source_audit_sha,
    )

    row = status.build_report(tmp_path, remote_host=None)["seasons"][0]

    assert row["season"] == season
    assert row["package"]["state"] == "frozen-provisional-base"
    assert row["package"]["baseline"]["state"] == "hash-verified-frozen-provisional-base"
    assert row["package"]["hard_blocker_count"] == 1
    assert row["package"]["canonical_workspace_candidates"]["count"] == 1
    assert row["delivery"]["classification"] == "provisional-not-playable"


def test_current_draft_surfaces_verified_workspace_candidate_without_release_claim(tmp_path: Path) -> None:
    season = "2005-06"
    source = tmp_path / ".local/season-historical-squad-backfill-v1" / season / "revisions/r1/world.json"
    intake = tmp_path / ".local/season-historical-squad-backfill-v1" / season / "revisions/r1/intake.json"
    source_sha = _write_json(source, {"source": True})
    intake_sha = _write_json(intake, {"intake": True})
    _write_json(
        source.parents[2] / "current.json",
        {
            "revision_id": "r1",
            "artifacts": {
                "source": {"path": "revisions/r1/world.json", "sha256": source_sha},
                "intake": {"path": "revisions/r1/intake.json", "sha256": intake_sha},
            },
        },
    )
    draft = tmp_path / ".local/season-authoring-post-calendar-binding-v2" / season / "draft-season-package.json"
    draft_payload = {"schema_version": "pm99-season-package-v2", "package_id": "draft"}
    draft_sha = _write_json(draft, draft_payload)
    source_audit = draft.with_name("source-package-build-audit.json")
    source_audit_sha = _write_json(
        source_audit,
        {
            "schema_version": "pm99-season-source-package-build-audit-v1",
            "draft_package_sha256": draft_sha,
            "source_intake_sha256": intake_sha,
            "template_package_sha256": "template-hash",
            "release_eligible": False,
            "coverage": {"calendar_binding_verified_count": 1},
            "calendar_binding": {
                "template_package_sha256": "template-hash",
                "audit_sha256": "calendar-audit-hash",
                "receipt_sha256": "calendar-receipt-hash",
                "executable_sha256": "calendar-executable-hash",
                "runtime_validation_pending": True,
            },
            "hard_blockers": [{"code": "ratings-reconciliation-required"}],
        },
    )
    _write_verified_workspace_candidate(
        tmp_path,
        season=season,
        draft_payload=draft_payload,
        draft_sha=draft_sha,
        source_audit_sha=source_audit_sha,
    )
    (tmp_path / "seasons" / season).mkdir(parents=True)

    row = status.build_report(tmp_path, remote_host=None)["seasons"][0]

    candidates = row["package"]["canonical_workspace_candidates"]
    assert row["package"]["state"] == "calendar-bound-source-draft"
    assert candidates["state"] == "verified-ingress-only-not-release"
    assert candidates["count"] == 1
    assert candidates["candidates"][0]["outputs"]["package"]["sha256"] == draft_sha
    assert row["delivery"]["classification"] == "provisional-not-playable"
    assert "canonical release package (draft packages are not releases)" in row["delivery"]["gates_missing"]


def test_current_draft_surfaces_hash_bound_display_alias_candidate_without_release_claim(tmp_path: Path) -> None:
    season = "2005-06"
    source = tmp_path / ".local/season-historical-squad-backfill-v1" / season / "revisions/r1/world.json"
    intake = tmp_path / ".local/season-historical-squad-backfill-v1" / season / "revisions/r1/intake.json"
    source_sha = _write_json(source, {"source": True})
    intake_sha = _write_json(intake, {"intake": True})
    _write_json(
        source.parents[2] / "current.json",
        {
            "revision_id": "r1",
            "artifacts": {
                "source": {"path": "revisions/r1/world.json", "sha256": source_sha},
                "intake": {"path": "revisions/r1/intake.json", "sha256": intake_sha},
            },
        },
    )
    draft = tmp_path / ".local/season-authoring-post-calendar-binding-v2" / season / "draft-season-package.json"
    draft_payload = {"schema_version": "pm99-season-package-v2", "package_id": "draft"}
    draft_sha = _write_json(draft, draft_payload)
    source_audit = draft.with_name("source-package-build-audit.json")
    source_audit_sha = _write_json(
        source_audit,
        {
            "schema_version": "pm99-season-source-package-build-audit-v1",
            "draft_package_sha256": draft_sha,
            "source_intake_sha256": intake_sha,
            "template_package_sha256": "template-hash",
            "release_eligible": False,
            "coverage": {"calendar_binding_verified_count": 1},
            "calendar_binding": {
                "template_package_sha256": "template-hash",
                "audit_sha256": "calendar-audit-hash",
                "receipt_sha256": "calendar-receipt-hash",
                "executable_sha256": "calendar-executable-hash",
                "runtime_validation_pending": True,
            },
            "hard_blockers": [{"code": "ratings-reconciliation-required"}],
        },
    )
    _write_verified_workspace_candidate(
        tmp_path,
        season=season,
        draft_payload=draft_payload,
        candidate_payload={"schema_version": "pm99-season-package-v2", "package_id": "display-alias"},
        draft_sha=draft_sha,
        source_audit_sha=source_audit_sha,
        alias_bound=True,
    )
    (tmp_path / "seasons" / season).mkdir(parents=True)

    row = status.build_report(tmp_path, remote_host=None)["seasons"][0]

    candidate = row["package"]["canonical_workspace_candidates"]["candidates"][0]
    assert candidate["package_binding"] == {
        "state": "verified-display-alias-derivative",
        "source_package_sha256": draft_sha,
        "display_alias_audit_sha256": "a" * 64,
        "changed_display_name_count": 1,
    }
    assert row["delivery"]["classification"] == "provisional-not-playable"


def test_display_alias_candidate_with_an_unbound_derivative_is_not_surfaced(tmp_path: Path) -> None:
    season = "2005-06"
    draft_payload = {"schema_version": "pm99-season-package-v2", "package_id": "draft"}
    draft_sha = hashlib.sha256(json.dumps(draft_payload, sort_keys=True).encode()).hexdigest()
    _write_verified_workspace_candidate(
        tmp_path,
        season=season,
        draft_payload=draft_payload,
        candidate_payload={"schema_version": "pm99-season-package-v2", "package_id": "display-alias"},
        draft_sha=draft_sha,
        source_audit_sha="b" * 64,
        alias_bound=True,
    )
    audit_path = tmp_path / ".local/season-canonical-candidate-v1" / season / "promotion-audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["input"]["display_alias_binding"]["alias_package_sha256"] = "c" * 64
    _write_json(audit_path, audit)

    assert status._canonical_workspace_candidates(
        tmp_path,
        season,
        draft_sha256=draft_sha,
        source_audit_sha256="b" * 64,
    ) == []


def _write_static_ingress_receipt(tmp_path: Path, *, season: str, input_sha256: str) -> Path:
    candidate = tmp_path / ".local/season-static-ingress-v1" / f"{season}-r1"
    reconciled_sha256 = _write_json(candidate / "season-package.reconciled.json", {"package": "reconciled"})
    database = {
        "DBDAT/ENT98030.FDI": b"entities",
        "DBDAT/EQ98030.FDI": b"clubs",
        "DBDAT/JUG98030.FDI": b"players",
    }
    compiler_outputs = []
    audit_outputs = {}
    for relative, payload in database.items():
        path = candidate / "game" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        compiler_outputs.append({"path": relative, "sha256": digest, "size": len(payload)})
        audit_outputs[relative] = digest
    compiler_sha256 = _write_json(
        candidate / "compiler-receipt.json",
        {
            "schema": "pm99-season-package-compiler-receipt-v1",
            "season_package_sha256": reconciled_sha256,
            "source_season_package_sha256": reconciled_sha256,
            "outputs": compiler_outputs,
        },
    )
    audit_sha256 = _write_json(
        candidate / "clean-static-audit.json",
        {
            "schema_version": "pm99-season-clean-base-audit-v1",
            "result": "pass",
            "package_canonical_sha256": reconciled_sha256,
            "append_or_recycle_count": 0,
            "fixed_roster_tail_count": 451,
            "fixed_roster_tail_mismatch_count": 0,
            "output_database_sha256": audit_outputs,
        },
    )
    _write_json(
        candidate / "static-ingress-receipt.json",
        {
            "schema_version": "pm99-season-static-ingress-receipt-v1",
            "state": "clean-static-ingress-complete-not-playable",
            "release_eligible": False,
            "season": {"label": season.replace("-", "/", 1)},
            "input": {"package_sha256": input_sha256},
            "outputs": {
                "package_path": "season-package.reconciled.json",
                "package_sha256": reconciled_sha256,
                "compiler_receipt": "compiler-receipt.json",
                "compiler_receipt_sha256": compiler_sha256,
                "clean_static_audit": "clean-static-audit.json",
                "clean_static_audit_sha256": audit_sha256,
                "game_tree": "game",
            },
            "remaining_release_gates": ["PM99-runtime-validation", "target-season-screenshot"],
        },
    )
    return candidate


def test_hash_verified_static_ingress_is_visible_but_never_a_release(tmp_path: Path) -> None:
    season = "2000-01"
    input_sha256 = "a" * 64
    candidate = _write_static_ingress_receipt(tmp_path, season=season, input_sha256=input_sha256)

    compilation = status.compilation_status(
        tmp_path, season, {"package": {"sha256": input_sha256}},
    )

    assert compilation["state"] == "static-audited-ingress-only"
    assert compilation["static_ingress"]["state"] == "hash-verified-clean-static-ingress-not-release"
    assert compilation["static_ingress"]["count"] == 1
    assert status.delivery_status(
        {"state": "bound"},
        {"state": "frozen-provisional-base"},
        compilation,
        {"state": "no-attested-runtime-proof", "screenshots": {"state": "missing", "count": 0}},
    ) == {
        "classification": "provisional-not-playable",
        "gates_missing": [
            "canonical release package (draft packages are not releases)",
            "canonical package-bound clean static compile/audit",
            "successful runtime route",
            "runtime screenshot",
        ],
    }

    (candidate / "game/DBDAT/JUG98030.FDI").write_bytes(b"mutated")
    assert status.compilation_status(
        tmp_path, season, {"package": {"sha256": input_sha256}},
    )["state"] == "not-compiled"


def test_canonical_static_qualification_binds_complete_repair_chain(tmp_path: Path) -> None:
    season = "2007-08"
    original_sha = "a" * 64
    candidate = _write_static_ingress_receipt(tmp_path, season=season, input_sha256=original_sha)
    qualification = tmp_path / ".local/season-static-qualification-v1" / "fixture"
    qualification.parent.mkdir(parents=True)
    candidate.rename(qualification)
    receipt_path = qualification / "static-ingress-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["input"]["verified_base_sha256"] = "b" * 64
    hashes = [original_sha]
    stages = [
        ("source-write-policy-lift-audit.json", "pm99-mode1-source-write-policy-lift-v1", "season-package.source-writable.json"),
        ("display-alias-repair-audit.json", "pm99-season-package-display-alias-repair-v1", "season-package.alias-bound.json"),
        ("mode1-roster-reconciliation-audit.json", "pm99-mode1-roster-base-reconciliation-batch-v1", "season-package.reconciled.json"),
    ]
    for index, (audit_name, schema, package_name) in enumerate(stages):
        output_sha = _write_json(qualification / package_name, {"stage": index})
        _write_json(qualification / audit_name, {
            "schema_version": schema,
            "input": {"package_sha256": hashes[-1], "verified_base_sha256": receipt["input"]["verified_base_sha256"]},
            "output": {"package_path": str(qualification / package_name), "package_sha256": output_sha},
        })
        hashes.append(output_sha)
    final_sha = hashes[-1]
    receipt["outputs"]["package_sha256"] = final_sha
    receipt["outputs"]["package_path"] = "season-package.reconciled.json"
    compiler_path = qualification / "compiler-receipt.json"
    compiler = json.loads(compiler_path.read_text())
    compiler["season_package_sha256"] = final_sha
    compiler["source_season_package_sha256"] = final_sha
    receipt["outputs"]["compiler_receipt_sha256"] = _write_json(compiler_path, compiler)
    audit_path = qualification / "clean-static-audit.json"
    audit = json.loads(audit_path.read_text())
    audit["package_canonical_sha256"] = final_sha
    receipt["outputs"]["clean_static_audit_sha256"] = _write_json(audit_path, audit)
    _write_json(receipt_path, receipt)

    compilation = status.compilation_status(tmp_path, season, {
        "state": "canonical-package", "package": {"sha256": final_sha},
    })
    assert compilation["state"] == "static-audited-canonical-package"
    evidence = compilation["canonical_package_evidence"]
    assert evidence["state"] == "verified-canonical-package-bound-static-repair-chain"
    assert len(evidence["candidate"]["canonical_repair_chain"]["stages"]) == 3


def test_provisional_normalisation_lineage_surfaces_without_release_claim(tmp_path: Path) -> None:
    season = "2008-09"
    current_package_sha256 = "a" * 64
    prepared = (
        tmp_path / ".local/season-provisional-compile-packages-v1" / season
        / "draft-season-package.json"
    )
    prepared_sha256 = _write_json(prepared, {"package": "prepared-provisional"})
    _write_json(
        prepared.with_name("provisional-preparation-audit.json"),
        {
            "schema_version": "pm99-provisional-compile-package-preparation-v1",
            "state": "strict-package-ready-provisional-editorial-gaps-retained",
            "release_eligible": False,
            "season": {"label": "2008/09"},
            "input": {"package_sha256": "b" * 64},
            "output": {"package_sha256": prepared_sha256},
            "duplicate_ownership": {"editorial_review_required_count": 27},
            "outfield_handling": {"changed_player_count": 4327},
        },
    )
    candidate = _write_static_ingress_receipt(
        tmp_path, season=season, input_sha256=prepared_sha256,
    )
    calendar = b"target calendar"
    (candidate / "game/MANAGPRE.EXE").write_bytes(calendar)
    calendar_source = tmp_path / ".local/calendar-v1" / season / "MANAGPRE.EXE"
    calendar_source.parent.mkdir(parents=True)
    calendar_source.write_bytes(calendar)

    compilation = status.compilation_status(
        tmp_path, season, {"package": {"sha256": current_package_sha256}},
    )

    assert compilation["state"] == "static-audited-ingress-only"
    surfaced = compilation["static_ingress"]["candidates"][0]
    assert surfaced["package_binding"] == "provisional-derivative-unbound-current-package"
    assert surfaced["calendar"]["state"] == "target-calendar-bound"
    assert surfaced["provisional_preparation"]["editorial_ownership_gap_count"] == 27
    assert surfaced["provisional_preparation"]["outfield_handling_correction_count"] == 4327
    assert status.delivery_status(
        {"state": "bound"},
        {"state": "frozen-provisional-base"},
        compilation,
        {"state": "runtime-passed", "screenshots": {"state": "present", "count": 1}},
    )["classification"] == "provisional-not-playable"


def test_provisional_normalisation_prefers_fewer_verified_editorial_gaps(tmp_path: Path) -> None:
    season = "2000-01"
    current_package_sha256 = "a" * 64
    prepared_payload = {"package": "same-prepared-provisional"}
    prepared_sha256 = _write_json(
        tmp_path / ".local/season-provisional-compile-packages-v1" / season
        / "draft-season-package.json",
        prepared_payload,
    )
    for directory, state, gaps, source_resolved in (
        (season, "strict-package-ready-provisional-editorial-gaps-retained", 1, 0),
        (f"{season}-source-evidence-r1", "strict-package-ready-provisional", 0, 1),
    ):
        prepared = (
            tmp_path / ".local/season-provisional-compile-packages-v1" / directory
            / "draft-season-package.json"
        )
        if not prepared.exists():
            assert _write_json(prepared, prepared_payload) == prepared_sha256
        _write_json(
            prepared.with_name("provisional-preparation-audit.json"),
            {
                "schema_version": "pm99-provisional-compile-package-preparation-v1",
                "state": state,
                "release_eligible": False,
                "season": {"label": "2000/01"},
                "input": {"package_sha256": "b" * 64},
                "output": {"package_sha256": prepared_sha256},
                "duplicate_ownership": {
                    "editorial_review_required_count": gaps,
                    "source_evidence_resolved_count": source_resolved,
                },
                "outfield_handling": {"changed_player_count": 1},
            },
        )
    _write_static_ingress_receipt(tmp_path, season=season, input_sha256=prepared_sha256)

    compilation = status.compilation_status(
        tmp_path, season, {"package": {"sha256": current_package_sha256}},
    )

    surfaced = compilation["static_ingress"]["candidates"][0]["provisional_preparation"]
    assert surfaced["editorial_ownership_gap_count"] == 0
    assert surfaced["source_evidence_resolved_count"] == 1
    assert surfaced["state"] == "strict-package-ready-provisional"


def test_hash_verified_preflight_repair_is_visible_but_never_a_static_compile(tmp_path: Path) -> None:
    season = "2008-09"
    input_sha256 = "b" * 64
    candidate = tmp_path / ".local/season-static-ingress-v1" / f"{season}-r1"
    repaired_sha256 = _write_json(candidate / "season-package.stale-candidates-reconciled.json", {"package": "repaired"})
    audit_sha256 = _write_json(
        candidate / "stale-source-candidate-reconciliation-audit.json",
        {
            "schema_version": "pm99-stale-mode1-source-candidate-reconciliation-v1",
            "state": "stale-mode1-source-candidates-reconciled-static-candidate-only",
            "season": {"label": "2008/09"},
            "release_eligible": False,
            "input": {"package_sha256": input_sha256},
            "output": {"package_sha256": repaired_sha256},
            "reconciliation": {
                "policy": "replace-only-exact-one-current-source-versus-one-legacy-non-source-mode1-candidate",
                "repaired_pair_count": 2,
                "repaired": [{"player_id": "one"}, {"player_id": "two"}],
                "remaining_current_source_duplicate_group_count": 3,
            },
        },
    )
    _write_json(
        candidate / "static-ingress-preflight-blocked.json",
        {
            "schema_version": "pm99-season-static-ingress-preflight-blocked-v1",
            "state": "blocked-before-static-compilation",
            "season": {"label": "2008/09"},
            "release_eligible": False,
            "input": {"package_sha256": input_sha256},
            "completed_source_only_stages": [{
                "name": "stale-source-candidate-reconciliation",
                "audit": "stale-source-candidate-reconciliation-audit.json",
                "package": "season-package.stale-candidates-reconciled.json",
                "repaired_pair_count": 2,
            }],
            "remaining_strict_validation_error": "three current-source pairs remain",
        },
    )

    compilation = status.compilation_status(
        tmp_path, season, {"package": {"sha256": input_sha256}},
    )

    assert compilation["state"] == "static-ingress-preflight-blocked"
    preflight = compilation["static_ingress_preflight"]
    assert preflight["state"] == "hash-verified-source-repair-blocked-before-static-compilation"
    assert preflight["count"] == 1
    assert preflight["candidates"][0]["source_reconciliation_audit"]["sha256"] == audit_sha256
    assert preflight["candidates"][0]["repaired_pair_count"] == 2
    assert preflight["candidates"][0]["remaining_current_source_duplicate_group_count"] == 3
    assert status.delivery_status(
        {"state": "bound"},
        {"state": "frozen-provisional-base"},
        compilation,
        {"state": "no-attested-runtime-proof", "screenshots": {"state": "missing", "count": 0}},
    ) == {
        "classification": "provisional-not-playable",
        "gates_missing": [
            "canonical release package (draft packages are not releases)",
            "clean static compile/audit",
            "successful runtime route",
            "runtime screenshot",
        ],
    }

    (candidate / "season-package.stale-candidates-reconciled.json").write_text("mutated", encoding="utf-8")
    assert status.compilation_status(
        tmp_path, season, {"package": {"sha256": input_sha256}},
    )["state"] == "not-compiled"


def test_playable_gate_requires_screenshots() -> None:
    result = status.delivery_status(
        {"state": "bound"},
        {"state": "canonical-package"},
        {"state": "static-audited"},
        {"state": "runtime-passed", "screenshots": {"state": "missing", "count": 0}},
    )

    assert result["classification"] == "provisional-not-playable"
    assert result["gates_missing"] == ["runtime screenshot"]


def test_static_ingress_runtime_binding_uses_registered_game_root(tmp_path: Path, monkeypatch) -> None:
    """A configured static root, rather than a season-specific literal, is required."""

    season = "2005-06"
    package_path = tmp_path / "seasons" / season / "season-package.json"
    package_sha = _write_json(package_path, {"package": "registered"})
    game_root = tmp_path / ".local/fixture-static-qualification/game"
    database_files = {
        "DBDAT/ENT98030.FDI": b"ent",
        "DBDAT/EQ98030.FDI": b"eq",
        "DBDAT/JUG98030.FDI": b"jug",
        "DBDAT/MINIFOTO.PKF": b"portraits",
    }
    for relative, contents in database_files.items():
        target = game_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contents)
    database_hashes = {
        relative: hashlib.sha256(contents).hexdigest()
        for relative, contents in database_files.items()
        if relative != "DBDAT/MINIFOTO.PKF"
    }
    receipt_path = game_root.parent / "static-ingress-receipt.json"
    compiler_path = game_root.parent / "compiler-receipt.json"
    audit_path = game_root.parent / "clean-static-audit.json"
    _write_json(receipt_path, {"outputs": {"package_sha256": package_sha}})
    _write_json(
        compiler_path,
        {
            "season_package_sha256": package_sha,
            "outputs": [
                {"path": relative, "sha256": digest}
                for relative, digest in sorted(database_hashes.items())
            ],
        },
    )
    _write_json(
        audit_path,
        {
            "package_canonical_sha256": package_sha,
            "result": "pass",
            "base_inventory_fingerprint": "a" * 64,
            "output_database_sha256": database_hashes,
        },
    )
    calendar_path = tmp_path / ".local/calendar-v1" / season / "MANAGPRE.EXE"
    calendar_path.parent.mkdir(parents=True, exist_ok=True)
    calendar_path.write_bytes(b"target calendar")
    artifact_root = tmp_path / ".local/season-runtime-evidence-v1/fixture"
    summary_path = artifact_root / "summary.json"
    screenshot_path = artifact_root / "screens/return.png"
    screenshot_path.parent.mkdir(parents=True)
    _write_json(
        summary_path,
        {
            "success": True,
            "crash_detected": False,
            "wine_debugger_detected": False,
            "phase_reached": "return_from_line_up",
            "route_summaries": {
                "squad": {
                    "expected_screen_matched": True,
                    "route_signal_matched": True,
                },
            },
        },
    )
    screenshot_path.write_bytes(b"bound screenshot")
    control_path = artifact_root / "control_launch.json"
    run_tag = "fixture-target-calendar-route"
    _write_json(
        control_path,
        {
            "run_tag": run_tag,
            "child_command": [
                "runner-wrapper",
                "--dbdat-dir", str((game_root / "DBDAT").relative_to(tmp_path)),
                "--exe-file", str(calendar_path.relative_to(tmp_path)),
            ],
        },
    )

    def record(path: Path) -> dict[str, object]:
        return {
            "path": str(path.relative_to(tmp_path)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }

    _write_canonical_json(
        artifact_root / "runtime-attestation.json",
        {
            "schema": "pm99-season-static-ingress-runtime-attestation-v1",
            "season": season,
            "state": "target-calendar-bound-runtime-screenshot-attested",
            "release_eligible": False,
            "package": record(package_path),
            "static": {
                "receipt": record(receipt_path),
                "compiler_receipt": record(compiler_path),
                "audit": record(audit_path),
                "base_inventory_fingerprint": "a" * 64,
                "database_files": [record(game_root / relative) for relative in sorted(database_files)],
            },
            "calendar": record(calendar_path),
            "runtime": {
                "route_kind": "stoke-route",
                "run_tag": run_tag,
                "control_launch": record(control_path),
                "summary": record(summary_path),
                "screenshot": record(screenshot_path),
            },
        },
    )
    monkeypatch.setitem(
        status.KNOWN_RUNTIME_PROOF,
        season,
        {
            "kind": "stoke-route",
            "expected_phase": "return_from_line_up",
            "path": summary_path.relative_to(tmp_path),
            "attestation_path": (artifact_root / "runtime-attestation.json").relative_to(tmp_path),
            "static_game_root": game_root.relative_to(tmp_path),
        },
    )

    runtime = status.runtime_status(tmp_path, season)

    assert runtime["state"] == "runtime-passed"
    assert runtime["screenshots"]["count"] == 1
    assert runtime["binding"]["calendar"]["sha256"] == hashlib.sha256(b"target calendar").hexdigest()

    (game_root / "DBDAT/JUG98030.FDI").write_bytes(b"mutated")
    assert status.runtime_status(tmp_path, season)["state"] == "runtime-proof-unbound-or-invalid"


def test_registered_package_can_bind_existing_build_audit_and_runtime_evidence(tmp_path: Path, monkeypatch) -> None:
    season = "2008-09"
    package_sha, summary_path, screenshot_path = _write_canonical_package_build_evidence(
        tmp_path, season=season,
    )
    monkeypatch.setitem(
        status.KNOWN_RUNTIME_PROOF,
        season,
        {"kind": "selector-discovery", "path": summary_path.relative_to(tmp_path)},
    )

    compilation = status.compilation_status(
        tmp_path, season, {"state": "canonical-package", "package": {"sha256": package_sha}},
    )
    runtime = status.runtime_status(tmp_path, season)

    assert compilation["state"] == "static-audited-canonical-package"
    binding = compilation["canonical_package_evidence"]
    assert binding["state"] == "verified-canonical-package-bound-static-runtime-attested"
    assert binding["runtime"]["screenshot"]["path"] == "artifacts/runtime/screens/fixture.png"
    assert runtime["state"] == "runtime-passed"
    assert status.delivery_status(
        {"state": "bound"},
        {"state": "canonical-package"},
        compilation,
        runtime,
    ) == {"classification": "playable-known-good", "gates_missing": []}

    screenshot_path.write_bytes(b"mutated screenshot")
    assert status.compilation_status(
        tmp_path, season, {"state": "canonical-package", "package": {"sha256": package_sha}},
    )["state"] == "not-compiled"


def test_verified_remote_receipt_marks_removed_bentley_source(monkeypatch) -> None:
    monkeypatch.setattr(status, "BENTLEY_SOURCE", Path("/absent/Bentley/SD"))
    monkeypatch.setattr(
        status,
        "_remote_archive_status",
        lambda host, timeout: {"state": "reachable", "TRANSFER_COMPLETE": True, "VERIFIED": True},
    )

    report = status.archive_status(remote_host="192.168.1.133", remote_timeout_seconds=5)

    assert report["bentley_sd"]["source"]["exists"] is False
    assert report["bentley_sd"]["verification"]["state"] == "verified-local-removed"
