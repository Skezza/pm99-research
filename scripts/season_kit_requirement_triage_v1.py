#!/usr/bin/env python3
"""Audit every allocated historical kit requirement without changing any asset.

The kit capture, catalogue and renderer are deliberately separate stages.  A
render artifact is not an eligible release input unless the immutable current
allocation which requested it still matches the capture provenance.  This tool
keeps those two questions distinct:

* ``classification`` is the current, fail-closed release classification; and
* ``stale_artifact_diagnostic_classification`` explains the useful backlog in
  the retained artifacts even when their allocation provenance is stale.

It never acquires source pages, renders artwork, writes a kit archive or edits
a season package.  The output is a content-addressed ledger that is intended
to drive a later, separately implemented, kit-archive materialiser.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any


SCHEMA = "pm99-season-kit-requirement-triage-v1"
CURRENT_SCHEMA = "pm99-historical-squad-backfill-current-v1"
CAPTURE_SCHEMA = "pm99-season-kit-source-capture-v1"
CATALOGUE_SCHEMA = "pm99-season-kit-catalogue-v1"
BINDING_SCHEMA = "pm99-season-kit-render-bindings-v1"
RECEIPT_SCHEMA = "pm99-season-kit-render-receipt-v1"

CLASSIFICATIONS = (
    "rendered-and-bound",
    "captured-but-unrendered",
    "renderable-but-unbound",
    "genuinely-uncaptured",
    "conflicting",
)


class KitTriageError(ValueError):
    """A triage input cannot be interpreted as a kit-stage artifact."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def document_sha256(document: Mapping[str, Any]) -> str:
    """Match the renderer's canonical catalogue-digest contract."""
    return sha256_bytes(canonical_json_bytes(dict(document)))


def _read_object(path: Path, errors: list[str], label: str) -> dict[str, Any] | None:
    if not path.is_file():
        errors.append(f"missing-{label}")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"invalid-{label}: {type(exc).__name__}")
        return None
    if not isinstance(value, dict):
        errors.append(f"invalid-{label}: object-required")
        return None
    return value


def _season_label(document: Mapping[str, Any]) -> str:
    season = document.get("season")
    if not isinstance(season, Mapping):
        return ""
    return str(season.get("label") or "")


def _indexed_rows(document: Mapping[str, Any] | None, field: str, errors: list[str], label: str) -> dict[int, dict[str, Any]]:
    if document is None:
        return {}
    values = document.get(field)
    if not isinstance(values, list):
        errors.append(f"invalid-{label}: {field}-list-required")
        return {}
    result: dict[int, dict[str, Any]] = {}
    for value in values:
        if not isinstance(value, Mapping) or not isinstance(value.get("carrier_id"), int):
            errors.append(f"invalid-{label}: carrier-id-required")
            continue
        carrier = int(value["carrier_id"])
        if carrier in result:
            errors.append(f"invalid-{label}: duplicate-carrier-{carrier}")
            continue
        result[carrier] = dict(value)
    return result


def _same_identity(left: Mapping[str, Any] | None, right: Mapping[str, Any] | None) -> bool:
    return (
        isinstance(left, Mapping)
        and isinstance(right, Mapping)
        and str(left.get("club_name") or "") == str(right.get("club_name") or "")
    )


def _artifact_problems(binding_row: Mapping[str, Any] | None, receipt_row: Mapping[str, Any] | None, render_dir: Path) -> list[str]:
    """Return exact binding/receipt/artifact mismatches for one rendered row."""
    problems: list[str] = []
    receipt_artifacts = receipt_row.get("artifacts") if isinstance(receipt_row, Mapping) else None
    binding_artifacts = binding_row.get("artifacts") if isinstance(binding_row, Mapping) else None
    if not isinstance(receipt_artifacts, list) or not receipt_artifacts:
        return ["rendered-receipt-has-no-artifacts"]
    if not isinstance(binding_artifacts, list) or not binding_artifacts:
        return ["rendered-receipt-has-no-binding"]

    def token(value: Any) -> tuple[str, str, str]:
        if not isinstance(value, Mapping):
            return ("", "", "")
        return (str(value.get("id") or ""), str(value.get("sha256") or ""), str(value.get("relative_path") or ""))

    if sorted(token(value) for value in receipt_artifacts) != sorted(token(value) for value in binding_artifacts):
        problems.append("binding-artifacts-differ-from-receipt")
    for artifact in binding_artifacts:
        if not isinstance(artifact, Mapping):
            problems.append("binding-artifact-not-object")
            continue
        relative = str(artifact.get("relative_path") or "")
        expected = str(artifact.get("sha256") or "")
        relative_path = Path(relative)
        candidate = render_dir / relative_path
        if not relative or relative_path.is_absolute() or ".." in relative_path.parts:
            problems.append("binding-artifact-path-invalid")
        elif not candidate.is_file():
            problems.append("binding-artifact-missing")
        elif sha256_file(candidate) != expected:
            problems.append("binding-artifact-hash-mismatch")
    return sorted(set(problems))


def _current_context(
    *, current: Mapping[str, Any] | None, allocation_path: Path, capture: Mapping[str, Any] | None,
    current_path: Path, errors: list[str],
) -> tuple[dict[str, Any], dict[int, dict[str, Any]]]:
    """Validate the allocation pointer and the capture's immutable provenance."""
    allocation = _read_object(allocation_path, errors, "carrier-allocation")
    assignments = _indexed_rows(allocation, "assignments", errors, "carrier-allocation")
    issues: list[str] = []
    current_sha = sha256_file(current_path) if current_path.is_file() else None
    allocation_sha = sha256_file(allocation_path) if allocation_path.is_file() else None
    if current is None or current.get("schema_version") != CURRENT_SCHEMA:
        issues.append("current-pointer-invalid")
    else:
        artifact = ((current.get("artifacts") or {}).get("allocation") or {})
        if artifact.get("sha256") != allocation_sha:
            issues.append("current-allocation-hash-mismatch")
        if not str(current.get("revision_id") or ""):
            issues.append("current-revision-id-missing")
    if capture is None or capture.get("schema_version") != CAPTURE_SCHEMA:
        issues.append("capture-invalid")
    elif current is not None:
        provenance = capture.get("provenance") if isinstance(capture.get("provenance"), Mapping) else {}
        expected = {
            "historical_revision_id": current.get("revision_id"),
            "historical_current_sha256": current_sha,
            "historical_allocation_file_sha256": allocation_sha,
        }
        for key, value in expected.items():
            if provenance.get(key) != value:
                issues.append(f"capture-{key}-mismatch")
        if provenance.get("allocation_sha256") != allocation_sha:
            issues.append("capture-allocation-sha256-mismatch")
    return {
        "valid": not issues,
        "issues": sorted(set(issues)),
        "current_sha256": current_sha,
        "allocation_sha256": allocation_sha,
        "current_revision_id": current.get("revision_id") if current is not None else None,
    }, assignments


def _diagnostic_classification(
    *, assignment: Mapping[str, Any], capture: Mapping[str, Any] | None,
    catalogue: Mapping[str, Any] | None, receipt: Mapping[str, Any] | None,
    binding: Mapping[str, Any] | None, render_dir: Path,
) -> tuple[str, list[str]]:
    """Classify an artifact chain without asserting that it is current."""
    problems: list[str] = []
    if catalogue is None:
        return "genuinely-uncaptured", ["catalogue-row-missing"]
    if not _same_identity(assignment, catalogue):
        problems.append("allocation-catalogue-club-name-mismatch")
    if capture is None:
        problems.append("capture-row-missing")
    elif not _same_identity(assignment, capture):
        problems.append("allocation-capture-club-name-mismatch")
    elif catalogue.get("status") == "source-ready" and capture.get("status") != "revision-captured-home-fields-ready":
        problems.append("catalogue-source-ready-capture-not-ready")
    elif catalogue.get("status") != "source-ready" and capture.get("status") == "revision-captured-home-fields-ready":
        problems.append("capture-ready-catalogue-not-source-ready")
    if receipt is None:
        problems.append("render-receipt-row-missing")
    elif not _same_identity(assignment, receipt):
        problems.append("allocation-receipt-club-name-mismatch")
    if problems:
        return "conflicting", sorted(set(problems))
    if catalogue.get("status") != "source-ready":
        return "genuinely-uncaptured", [str(catalogue.get("reason") or catalogue.get("status") or "catalogue-gap")]
    receipt_status = str((receipt or {}).get("status") or "")
    if receipt_status in {"not-rendered-exact-pattern-unavailable", "not-rendered-clean-base-record-missing", "not-rendered-unsupported-contract"}:
        return "captured-but-unrendered", [str((receipt or {}).get("reason") or receipt_status)]
    if receipt_status != "rendered-source-ready":
        return "conflicting", [f"unexpected-render-receipt-status:{receipt_status or 'missing'}"]
    if binding is None:
        # The receipt/artifact is proof that the input is renderable.  It has
        # not become an installable binding yet.
        return "renderable-but-unbound", ["rendered-receipt-has-no-binding"]
    artifact_problems = _artifact_problems(binding, receipt, render_dir)
    if artifact_problems == ["rendered-receipt-has-no-binding"]:
        return "renderable-but-unbound", artifact_problems
    if artifact_problems:
        return "conflicting", artifact_problems
    return "rendered-and-bound", []


def _season_paths(root: Path) -> set[str]:
    if not root.is_dir():
        return set()
    return {path.name for path in root.iterdir() if path.is_dir()}


def build_triage(historical_root: Path, catalogue_root: Path, render_root: Path) -> dict[str, Any]:
    """Build the read-only, hash-bound kit requirement ledger."""
    labels = sorted(_season_paths(historical_root) | _season_paths(catalogue_root) | _season_paths(render_root))
    season_rows: list[dict[str, Any]] = []
    all_requirements: list[dict[str, Any]] = []
    input_rows: list[dict[str, Any]] = []
    for season in labels:
        historical_dir, catalogue_dir, render_dir = historical_root / season, catalogue_root / season, render_root / season
        errors: list[str] = []
        current_path = historical_dir / "current.json"
        allocation_path = historical_dir / "carrier-allocation.json"
        capture_path = catalogue_dir / "kit-source-capture-v1.json"
        request_path = catalogue_dir / "kit-catalogue-request-v1.json"
        catalogue_path = catalogue_dir / "kit-catalogue-v1.json"
        binding_path = render_dir / "kit-render-bindings-v1.json"
        receipt_path = render_dir / "kit-render-receipt-v1.json"
        current = _read_object(current_path, errors, "current-pointer")
        capture = _read_object(capture_path, errors, "kit-capture")
        request = _read_object(request_path, errors, "kit-catalogue-request")
        catalogue = _read_object(catalogue_path, errors, "kit-catalogue")
        binding_document = _read_object(binding_path, errors, "kit-render-bindings")
        receipt_document = _read_object(receipt_path, errors, "kit-render-receipt")
        context, assignments = _current_context(
            current=current, allocation_path=allocation_path, capture=capture, current_path=current_path, errors=errors,
        )
        capture_rows = _indexed_rows(capture, "rows", errors, "kit-capture")
        catalogue_rows = _indexed_rows(catalogue, "rows", errors, "kit-catalogue")
        receipt_rows = _indexed_rows(receipt_document, "rows", errors, "kit-render-receipt")
        binding_rows = _indexed_rows(binding_document, "clubs", errors, "kit-render-bindings")
        catalogue_sha = document_sha256(catalogue) if catalogue is not None else None
        request_sha = sha256_file(request_path) if request_path.is_file() else None
        render_document_issues: list[str] = []
        if catalogue is None or catalogue.get("schema_version") != CATALOGUE_SCHEMA:
            render_document_issues.append("catalogue-schema-invalid")
        if capture is None or capture.get("schema_version") != CAPTURE_SCHEMA:
            render_document_issues.append("capture-schema-invalid")
        if request is None:
            render_document_issues.append("catalogue-request-invalid")
        elif catalogue is not None and ((catalogue.get("provenance") or {}).get("request_sha256") != request_sha):
            render_document_issues.append("catalogue-request-hash-mismatch")
        for document, expected_schema, name in (
            (binding_document, BINDING_SCHEMA, "binding"),
            (receipt_document, RECEIPT_SCHEMA, "receipt"),
        ):
            if document is None or document.get("schema_version") != expected_schema:
                render_document_issues.append(f"{name}-schema-invalid")
            elif document.get("kit_catalogue_sha256") != catalogue_sha:
                render_document_issues.append(f"{name}-catalogue-hash-mismatch")
        target_label = _season_label(catalogue or {}) or _season_label(capture or {})
        if target_label and not target_label.replace("/", "-") == season:
            render_document_issues.append("season-directory-label-mismatch")
        # The source request itself is a useful check that the catalogue's
        # carrier universe did not silently drift before rendering.
        request_rows = _indexed_rows(request, "clubs", errors, "kit-catalogue-request")
        if set(catalogue_rows) != set(request_rows):
            render_document_issues.append("catalogue-request-carrier-set-mismatch")

        season_requirements: list[dict[str, Any]] = []
        for carrier, assignment in sorted(assignments.items()):
            diagnostic, diagnostic_reasons = _diagnostic_classification(
                assignment=assignment,
                capture=capture_rows.get(carrier), catalogue=catalogue_rows.get(carrier),
                receipt=receipt_rows.get(carrier), binding=binding_rows.get(carrier), render_dir=render_dir,
            )
            current_reasons = list(context["issues"]) + list(render_document_issues)
            if diagnostic == "conflicting":
                current_reasons.extend(diagnostic_reasons)
            classification = "conflicting" if current_reasons else diagnostic
            row = {
                "season": season,
                "carrier_id": carrier,
                "club_name": assignment.get("club_name"),
                "classification": classification,
                "stale_artifact_diagnostic_classification": diagnostic,
                "reasons": sorted(set(current_reasons if classification == "conflicting" else diagnostic_reasons)),
                "stale_artifact_diagnostic_reasons": diagnostic_reasons,
            }
            season_requirements.append(row)
        requirements_by_classification = Counter(row["classification"] for row in season_requirements)
        diagnostic_by_classification = Counter(row["stale_artifact_diagnostic_classification"] for row in season_requirements)
        season_errors = sorted(set(errors))
        input_hashes = {
            name: (sha256_file(path) if path.is_file() else None)
            for name, path in (
                ("current_json_sha256", current_path),
                ("carrier_allocation_sha256", allocation_path),
                ("kit_source_capture_sha256", capture_path),
                ("kit_catalogue_request_sha256", request_path),
                ("kit_catalogue_file_sha256", catalogue_path),
                ("kit_render_bindings_sha256", binding_path),
                ("kit_render_receipt_sha256", receipt_path),
            )
        }
        input_hashes["kit_catalogue_canonical_sha256"] = catalogue_sha
        season_row = {
            "season": season,
            "current_context": context,
            "document_issues": sorted(set(render_document_issues)),
            "read_errors": season_errors,
            "coverage": {
                "allocated_requirement_count": len(season_requirements),
                "classification_counts": {key: requirements_by_classification.get(key, 0) for key in CLASSIFICATIONS},
                "stale_artifact_diagnostic_counts": {key: diagnostic_by_classification.get(key, 0) for key in CLASSIFICATIONS},
                "orphan_catalogue_carrier_count": len(set(catalogue_rows) - set(assignments)),
                "orphan_binding_carrier_count": len(set(binding_rows) - set(assignments)),
            },
            "inputs": input_hashes,
        }
        season_rows.append(season_row)
        all_requirements.extend(season_requirements)
        input_rows.append({"season": season, **season_row["inputs"]})
    coverage = Counter(row["classification"] for row in all_requirements)
    diagnostic = Counter(row["stale_artifact_diagnostic_classification"] for row in all_requirements)
    current_clean_seasons = [row["season"] for row in season_rows if row["current_context"]["valid"] and not row["document_issues"] and not row["read_errors"]]
    safe_binding_inputs = [
        {"season": row["season"], "carrier_id": row["carrier_id"], "club_name": row["club_name"]}
        for row in all_requirements if row["classification"] == "rendered-and-bound"
    ]
    return {
        "schema_version": SCHEMA,
        "policy": {
            "classification": "fail-closed-current-allocation-provenance-before-artifact-status",
            "captured_but_unrendered": "source-ready catalogue with a retained renderer prerequisite gap",
            "renderable_but_unbound": "renderer receipt proves artifacts, but no matching artifact binding is present",
            "genuinely_uncaptured": "current artefact chain has no source-ready catalogue row",
            "conflicting": "current provenance or any capture/catalogue/render identity/hash contract is inconsistent",
            "writes": "none; read-only triage",
        },
        "provenance": {
            "historical_root": str(historical_root.resolve()),
            "catalogue_root": str(catalogue_root.resolve()),
            "render_root": str(render_root.resolve()),
            "inputs": input_rows,
        },
        "coverage": {
            "season_count": len(season_rows),
            "allocated_requirement_count": len(all_requirements),
            "classification_counts": {key: coverage.get(key, 0) for key in CLASSIFICATIONS},
            "stale_artifact_diagnostic_counts": {key: diagnostic.get(key, 0) for key in CLASSIFICATIONS},
            "current_clean_season_count": len(current_clean_seasons),
        },
        "safe_automated_integration": {
            "eligible": bool(safe_binding_inputs),
            "candidate_count": len(safe_binding_inputs),
            "candidates": safe_binding_inputs,
            "blocked_by": ([] if safe_binding_inputs else [
                "no-rendered-and-bound-requirement-is-currently-bound-to-its-current-allocation",
                "generic-target-season-kit-archive-materialiser-is-not-yet-implemented",
            ]),
        },
        "seasons": season_rows,
        "requirements": all_requirements,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-root", type=Path, required=True, help="current.json and carrier-allocation.json root")
    parser.add_argument("--catalogue-root", type=Path, required=True, help="kit capture/catalogue root")
    parser.add_argument("--render-root", type=Path, required=True, help="kit render binding/receipt root")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = build_triage(args.historical_root, args.catalogue_root, args.render_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(document))
    print(json.dumps(document["coverage"], indent=2, sort_keys=True))
    print(json.dumps({"safe_automated_integration": document["safe_automated_integration"]["candidate_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
