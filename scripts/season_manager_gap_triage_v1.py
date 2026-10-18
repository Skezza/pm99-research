#!/usr/bin/env python3
"""Classify fixed-carrier opening-manager gaps without changing evidence.

The selected manager overlay is intentionally immutable.  Separately captured
allocated-manager supplements can therefore be ahead of it.  This tool joins
the selected overlay, the current source/allocation pointer and the raw
allocated-manager receipts, all by SHA-256, and writes a read-only receipt.

It never fetches a page, chooses between conflicting manager candidates,
changes a ledger, or applies a native/current-manager fallback.  A gap is
classified only as one of:

* ``already-captured-not-integrated`` -- one or more agreeing dated candidates
  exist in a receipt bound to the current source and allocation;
* ``existing-dated-conflicting-candidate`` -- two or more dated identities
  disagree, so a human must select/re-capture before an overlay is extended;
* ``genuinely-uncaptured`` -- no qualified dated candidate currently exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import materialise_opening_manager_ledger_v1 as ledger_v1  # noqa: E402


SCHEMA = "pm99-season-manager-gap-triage-v1"
CURRENT_SCHEMA = "pm99-historical-squad-backfill-current-v1"
OVERLAY_INDEX_SCHEMA = "pm99-season-manager-overlay-index-v1"
OVERLAY_SCHEMA = "pm99-season-manager-overlay-v1"
SUPPLEMENT_SCHEMA = "pm99-opening-manager-supplement-v1"
ALLOCATION_SCHEMA = "pm99-season-carrier-allocation-v1"
SHA256_RE = ledger_v1.SHA256_RE


class ManagerGapTriageError(ValueError):
    """The input evidence cannot be safely compared."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManagerGapTriageError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ManagerGapTriageError(f"{label} must be a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _relative(path: Path, *, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ManagerGapTriageError(f"{label} must be a lowercase SHA-256")
    return value


def _selector(value: Mapping[str, Any]) -> tuple[str, str, str]:
    result = tuple(str(value.get(field) or "").strip() for field in (
        "country_catalog", "competition_catalog", "club_name",
    ))
    if not all(result):
        raise ManagerGapTriageError("manager evidence has an incomplete source selector")
    return result  # type: ignore[return-value]


def _selector_object(selector: tuple[str, str, str]) -> dict[str, str]:
    return dict(zip(("country_catalog", "competition_catalog", "club_name"), selector))


def _safe_child(parent: Path, relative: Any, label: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ManagerGapTriageError(f"{label} path is unsafe")
    path = (parent / relative).resolve()
    if parent.resolve() not in path.parents:
        raise ManagerGapTriageError(f"{label} path escapes its parent")
    return path


def _bound_current_artifact(pointer_path: Path, pointer: Mapping[str, Any], name: str) -> tuple[Path, dict[str, Any], str]:
    artifact = (pointer.get("artifacts") or {}).get(name)
    if not isinstance(artifact, Mapping):
        raise ManagerGapTriageError(f"{pointer_path}: missing {name} artifact")
    path = _safe_child(pointer_path.parent, artifact.get("path"), f"{name} artifact")
    expected = _sha256(artifact.get("sha256"), f"{name} artifact hash")
    document, actual = _read(path, name)
    if actual != expected:
        raise ManagerGapTriageError(f"{pointer_path}: {name} artifact hash mismatch")
    return path, document, actual


def _allocation_rows(allocation: Mapping[str, Any], *, source_sha256: str) -> dict[tuple[str, str, str], int]:
    if allocation.get("schema_version") != ALLOCATION_SCHEMA:
        raise ManagerGapTriageError("carrier allocation has an unsupported schema")
    if allocation.get("source_sha256") != source_sha256:
        raise ManagerGapTriageError("carrier allocation is not bound to the current source capture")
    rows = allocation.get("assignments")
    if not isinstance(rows, list) or not rows:
        raise ManagerGapTriageError("carrier allocation has no assignments")
    result: dict[tuple[str, str, str], int] = {}
    carriers: set[int] = set()
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("source_selector"), Mapping):
            raise ManagerGapTriageError("carrier allocation has a malformed assignment")
        selector_data = dict(row["source_selector"])
        selector_data["club_name"] = row.get("club_name")
        selector = _selector(selector_data)
        carrier = row.get("carrier_id")
        if not isinstance(carrier, int) or carrier <= 0:
            raise ManagerGapTriageError("carrier allocation has an invalid carrier ID")
        if selector in result or carrier in carriers:
            raise ManagerGapTriageError("carrier allocation duplicates a source selector or carrier ID")
        result[selector] = carrier
        carriers.add(carrier)
    return result


def _source_selectors(source: Mapping[str, Any]) -> set[tuple[str, str, str]]:
    rows = source.get("clubs")
    if not isinstance(rows, list) or not rows:
        raise ManagerGapTriageError("current source capture has no clubs")
    result: set[tuple[str, str, str]] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ManagerGapTriageError("current source capture has a malformed club")
        selector = _selector(row)
        if selector in result:
            raise ManagerGapTriageError(f"current source capture duplicates {selector}")
        result.add(selector)
    return result


def _index_row(index: Mapping[str, Any], season: str) -> Mapping[str, Any]:
    if index.get("schema_version") != OVERLAY_INDEX_SCHEMA or index.get("state") != "frozen-manager-overlay-selection":
        raise ManagerGapTriageError("manager overlay index has an unsupported schema or state")
    rows = [
        row for row in index.get("seasons", [])
        if isinstance(row, Mapping) and row.get("season") == season
    ]
    if len(rows) != 1:
        raise ManagerGapTriageError(f"manager overlay index does not select exactly one {season} ledger")
    return rows[0]


def _overlay_ledger(
    *, index_row: Mapping[str, Any], season: str, root: Path, source_sha256: str,
) -> tuple[Path, dict[str, Any], str, Path, dict[str, Any], str]:
    ledger_info = index_row.get("opening_manager_ledger")
    audit_info = index_row.get("manager_overlay_audit")
    if not isinstance(ledger_info, Mapping) or not isinstance(audit_info, Mapping):
        raise ManagerGapTriageError(f"{season}: selected overlay lacks its ledger or audit")
    ledger_path = _safe_child(root, ledger_info.get("path"), f"{season} selected ledger")
    audit_path = _safe_child(root, audit_info.get("path"), f"{season} selected overlay audit")
    ledger, ledger_sha = _read(ledger_path, f"{season} selected manager ledger")
    audit, audit_sha = _read(audit_path, f"{season} selected manager overlay audit")
    if ledger_sha != _sha256(ledger_info.get("sha256"), f"{season} selected ledger hash"):
        raise ManagerGapTriageError(f"{season}: selected manager ledger hash mismatch")
    if audit_sha != _sha256(audit_info.get("sha256"), f"{season} selected audit hash"):
        raise ManagerGapTriageError(f"{season}: selected manager overlay audit hash mismatch")
    if audit.get("schema_version") != OVERLAY_SCHEMA or audit.get("season") != season:
        raise ManagerGapTriageError(f"{season}: selected manager overlay audit has an unexpected schema or season")
    outputs = audit.get("outputs")
    if not isinstance(outputs, Mapping) or outputs.get("opening_manager_ledger_sha256") != ledger_sha:
        raise ManagerGapTriageError(f"{season}: selected overlay audit does not bind its ledger")
    if (ledger.get("sources") or {}).get("squad_source_capture_sha256") != source_sha256:
        raise ManagerGapTriageError(f"{season}: selected manager ledger is not bound to the current source capture")
    return ledger_path, ledger, ledger_sha, audit_path, audit, audit_sha


def _ledger_gap_rows(
    ledger: Mapping[str, Any], *, allocation: Mapping[tuple[str, str, str], int], season: str,
) -> dict[tuple[str, str, str], str]:
    managers = ledger.get("managers")
    gaps = ledger.get("gaps")
    if not isinstance(managers, list) or not isinstance(gaps, list):
        raise ManagerGapTriageError(f"{season}: selected manager ledger lacks managers or gaps")
    resolved: set[tuple[str, str, str]] = set()
    for row in managers:
        if not isinstance(row, Mapping) or not isinstance(row.get("source_selector"), Mapping):
            raise ManagerGapTriageError(f"{season}: selected manager ledger has a malformed manager")
        selector = _selector(row["source_selector"])
        if selector in resolved:
            raise ManagerGapTriageError(f"{season}: selected manager ledger duplicates a manager selector")
        resolved.add(selector)
    result: dict[tuple[str, str, str], str] = {}
    for row in gaps:
        if not isinstance(row, Mapping) or not isinstance(row.get("source_selector"), Mapping):
            raise ManagerGapTriageError(f"{season}: selected manager ledger has a malformed gap")
        selector = _selector(row["source_selector"])
        if selector in resolved or selector in result:
            raise ManagerGapTriageError(f"{season}: selected manager ledger overlaps or duplicates a gap selector")
        result[selector] = str(row.get("reason") or "").strip()
    missing = sorted(set(allocation) - resolved - set(result))
    if missing:
        raise ManagerGapTriageError(f"{season}: selected manager ledger has no resolution state for allocated {missing[0]}")
    return {selector: result[selector] for selector in sorted(set(result) & set(allocation))}


def _audit_supplement_inputs(audit: Mapping[str, Any], *, root: Path, season: str) -> list[dict[str, str]]:
    inputs = audit.get("inputs")
    rows = inputs.get("supplements") if isinstance(inputs, Mapping) else None
    if not isinstance(rows, list):
        raise ManagerGapTriageError(f"{season}: selected overlay audit has no supplement input ledger")
    result: list[dict[str, str]] = []
    seen: set[Path] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ManagerGapTriageError(f"{season}: selected overlay audit has a malformed supplement input")
        path = _safe_child(root, row.get("path"), f"{season} selected supplement")
        digest = _sha256(row.get("sha256"), f"{season} selected supplement hash")
        if path in seen or _sha256_file(path) != digest:
            raise ManagerGapTriageError(f"{season}: selected overlay supplement is duplicated, missing or hash-mismatched")
        seen.add(path)
        result.append({"path": _relative(path, root=root), "sha256": digest})
    return sorted(result, key=lambda row: row["path"])


def _candidate_documents(
    *, operations_root: Path, season: str, source_sha256: str, allocation_sha256: str,
    allocation: Mapping[tuple[str, str, str], int], root: Path,
) -> tuple[list[dict[str, Any]], dict[tuple[str, str, str], list[dict[str, Any]]], dict[tuple[str, str, str], list[str]]]:
    """Return all inspected receipt metadata plus qualified dated candidates/gaps."""
    directory = operations_root / season
    paths = sorted(path for path in directory.glob("opening-manager-supplement*.json") if path.is_file())
    documents: list[dict[str, Any]] = []
    candidates: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    capture_gaps: dict[tuple[str, str, str], list[str]] = {}
    for path in paths:
        document, digest = _read(path, f"{season} raw manager supplement")
        row: dict[str, Any] = {
            "path": _relative(path, root=root), "sha256": digest,
            "qualified_for_current_allocation": False,
        }
        if document.get("schema_version") != SUPPLEMENT_SCHEMA:
            row["rejection_reason"] = "unsupported-schema"
            documents.append(row)
            continue
        if document.get("season_start_year") != int(season[:4]):
            row["rejection_reason"] = "wrong-season-start-year"
            documents.append(row)
            continue
        sources = document.get("sources")
        if not isinstance(sources, Mapping):
            row["rejection_reason"] = "missing-source-bindings"
            documents.append(row)
            continue
        if sources.get("full_source_capture_sha256") != source_sha256:
            row["rejection_reason"] = "source-capture-hash-mismatch"
            documents.append(row)
            continue
        if sources.get("carrier_allocation_sha256") != allocation_sha256:
            row["rejection_reason"] = "carrier-allocation-hash-mismatch"
            documents.append(row)
            continue
        try:
            managers = ledger_v1._supplements(document, season_start_year=int(season[:4]))
        except ledger_v1.ManagerLedgerError as exc:
            row["rejection_reason"] = f"invalid-manager-rows: {exc}"
            documents.append(row)
            continue
        unknown = sorted(set(managers) - set(allocation))
        if unknown:
            row["rejection_reason"] = "manager-selector-outside-current-allocation"
            documents.append(row)
            continue
        gaps = document.get("gaps")
        if not isinstance(gaps, list):
            row["rejection_reason"] = "missing-capture-gap-list"
            documents.append(row)
            continue
        gap_rows: dict[tuple[str, str, str], str] = {}
        try:
            for gap in gaps:
                if not isinstance(gap, Mapping) or not isinstance(gap.get("source_selector"), Mapping):
                    raise ManagerGapTriageError("malformed-capture-gap")
                selector = _selector(gap["source_selector"])
                if selector not in allocation or selector in gap_rows:
                    raise ManagerGapTriageError("capture-gap-outside-or-duplicates-current-allocation")
                gap_rows[selector] = str(gap.get("reason") or "").strip()
        except ManagerGapTriageError as exc:
            row["rejection_reason"] = str(exc)
            documents.append(row)
            continue
        overlap = sorted(set(managers) & set(gap_rows))
        if overlap:
            row["rejection_reason"] = "capture-manager-and-gap-overlap"
            documents.append(row)
            continue
        row.update({
            "qualified_for_current_allocation": True,
            "manager_row_count": len(managers),
            "capture_gap_count": len(gap_rows),
        })
        documents.append(row)
        for selector, manager in managers.items():
            candidate = {
                "manager_name": manager["manager_name"],
                "opening_fixture_date": manager["opening_fixture_date"],
                "source_name": manager["source_name"],
                "source_url": manager["source_url"],
                "source_snapshot_sha256": manager["source_snapshot_sha256"],
                "reason": manager["reason"],
                "candidate_input": {"path": row["path"], "sha256": digest},
            }
            candidates.setdefault(selector, []).append(candidate)
        for selector, reason in gap_rows.items():
            capture_gaps.setdefault(selector, []).append(reason)
    return documents, candidates, capture_gaps


def _distinct_identity(candidates: Sequence[Mapping[str, Any]]) -> list[tuple[str, str]]:
    return sorted({(str(row["opening_fixture_date"]), str(row["manager_name"])) for row in candidates})


def _classify_gap(
    *, selector: tuple[str, str, str], carrier_id: int, ledger_reason: str,
    candidates: Sequence[Mapping[str, Any]], capture_gap_reasons: Sequence[str],
) -> dict[str, Any]:
    identities = _distinct_identity(candidates)
    result: dict[str, Any] = {
        "carrier_id": carrier_id,
        "source_selector": _selector_object(selector),
        "selected_ledger_gap_reason": ledger_reason,
    }
    if len(identities) == 1:
        result["classification"] = "already-captured-not-integrated"
        result["dated_candidates"] = sorted((dict(row) for row in candidates), key=lambda row: (
            row["opening_fixture_date"], row["manager_name"], row["candidate_input"]["path"],
        ))
        result["integration_disposition"] = "safe-to-compose-as-a-new-manager-overlay-version"
    elif len(identities) > 1:
        result["classification"] = "existing-dated-conflicting-candidate"
        result["dated_candidates"] = sorted((dict(row) for row in candidates), key=lambda row: (
            row["opening_fixture_date"], row["manager_name"], row["candidate_input"]["path"],
        ))
        result["conflicting_identities"] = [
            {"opening_fixture_date": date, "manager_name": name}
            for date, name in identities
        ]
        result["integration_disposition"] = "manual-source-decision-required-before-overlay-extension"
    else:
        result["classification"] = "genuinely-uncaptured"
        if capture_gap_reasons:
            result["allocated-manager-capture_reasons"] = sorted(set(capture_gap_reasons))
        else:
            result["allocated-manager-capture_reasons"] = ["no-qualified-current-allocation-manager-capture"]
        result["integration_disposition"] = "capture-new-dated-manager-evidence;-native-manager-fallback-forbidden"
    return result


def build_report(
    *, current_root: Path, overlay_index_path: Path, operations_root: Path,
    root: Path = ROOT, seasons: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build one deterministic, non-mutating manager-gap triage receipt."""
    overlay_index, overlay_index_sha = _read(overlay_index_path, "manager overlay index")
    if overlay_index.get("schema_version") != OVERLAY_INDEX_SCHEMA:
        raise ManagerGapTriageError("manager overlay index has an unsupported schema")
    requested = set(seasons or ())
    pointer_paths = sorted(current_root.glob("*/current.json"))
    if requested:
        pointer_paths = [path for path in pointer_paths if path.parent.name in requested]
        missing = requested - {path.parent.name for path in pointer_paths}
        if missing:
            raise ManagerGapTriageError(f"missing current pointers: {', '.join(sorted(missing))}")
    if not pointer_paths:
        raise ManagerGapTriageError("no seasons selected")

    season_rows: list[dict[str, Any]] = []
    totals = {
        "fixed_carrier_manager_gap_count": 0,
        "already_captured_not_integrated_count": 0,
        "existing_dated_conflicting_candidate_count": 0,
        "genuinely_uncaptured_count": 0,
    }
    ready: list[dict[str, Any]] = []
    for pointer_path in pointer_paths:
        season = pointer_path.parent.name
        pointer, pointer_sha = _read(pointer_path, f"{season} current pointer")
        if pointer.get("schema_version") != CURRENT_SCHEMA or pointer.get("season") != season:
            raise ManagerGapTriageError(f"{season}: current pointer has an unsupported schema or season")
        source_path, source, source_sha = _bound_current_artifact(pointer_path, pointer, "source")
        allocation_path, allocation, allocation_sha = _bound_current_artifact(pointer_path, pointer, "allocation")
        source_selectors = _source_selectors(source)
        allocation_rows = _allocation_rows(allocation, source_sha256=source_sha)
        unknown_allocation = sorted(set(allocation_rows) - source_selectors)
        if unknown_allocation:
            raise ManagerGapTriageError(f"{season}: allocation has a selector absent from current source: {unknown_allocation[0]}")
        selected = _index_row(overlay_index, season)
        ledger_path, ledger, ledger_sha, audit_path, audit, audit_sha = _overlay_ledger(
            index_row=selected, season=season, root=root, source_sha256=source_sha,
        )
        selected_supplements = _audit_supplement_inputs(audit, root=root, season=season)
        ledger_gaps = _ledger_gap_rows(ledger, allocation=allocation_rows, season=season)
        documents, candidates_by_selector, capture_gaps = _candidate_documents(
            operations_root=operations_root, season=season, source_sha256=source_sha,
            allocation_sha256=allocation_sha, allocation=allocation_rows, root=root,
        )
        gaps = [
            _classify_gap(
                selector=selector, carrier_id=allocation_rows[selector], ledger_reason=ledger_gaps[selector],
                candidates=candidates_by_selector.get(selector, []),
                capture_gap_reasons=capture_gaps.get(selector, []),
            )
            for selector in sorted(ledger_gaps)
        ]
        counts = {
            "fixed_carrier_manager_gap_count": len(gaps),
            "already_captured_not_integrated_count": sum(
                row["classification"] == "already-captured-not-integrated" for row in gaps
            ),
            "existing_dated_conflicting_candidate_count": sum(
                row["classification"] == "existing-dated-conflicting-candidate" for row in gaps
            ),
            "genuinely_uncaptured_count": sum(
                row["classification"] == "genuinely-uncaptured" for row in gaps
            ),
        }
        for field, count in counts.items():
            totals[field] += int(count)
        qualified = [row for row in documents if row["qualified_for_current_allocation"]]
        integration_inputs = [
            *selected_supplements,
            *[
                {"path": row["path"], "sha256": row["sha256"]}
                for row in qualified if int(row.get("manager_row_count") or 0) > 0
            ],
        ]
        integration_inputs.sort(key=lambda row: row["path"])
        if counts["already_captured_not_integrated_count"] and not counts["existing_dated_conflicting_candidate_count"]:
            ready.append({
                "season": season,
                "captured_manager_count": counts["already_captured_not_integrated_count"],
                "candidate_supplement_inputs": integration_inputs,
                "required_output": f".local/season-overlays-v1/{season}/manager-vNEXT/",
                "instruction": "compose the selected overlay inputs plus the listed current allocation-bound raw receipt(s); retain unresolved gaps and create a new overlay version",
            })
        season_rows.append({
            "season": season,
            "inputs": {
                "current_pointer": {"path": _relative(pointer_path, root=root), "sha256": pointer_sha},
                "current_source_capture": {"path": _relative(source_path, root=root), "sha256": source_sha},
                "current_carrier_allocation": {"path": _relative(allocation_path, root=root), "sha256": allocation_sha},
                "selected_manager_overlay_audit": {"path": _relative(audit_path, root=root), "sha256": audit_sha},
                "selected_manager_ledger": {"path": _relative(ledger_path, root=root), "sha256": ledger_sha},
                "selected_overlay_supplement_inputs": selected_supplements,
                "inspected_allocated_manager_capture_receipts": documents,
            },
            "summary": {
                "allocated_carrier_count": len(allocation_rows),
                **counts,
            },
            "fixed_carrier_manager_gaps": gaps,
        })
    first_tranche = ready[:1]
    return {
        "schema_version": SCHEMA,
        "state": "read-only-manager-gap-classification",
        "policy": {
            "selection": "selected immutable manager overlay plus only raw receipts bound to the exact current source and carrier allocation",
            "manager_accuracy": "correct manager at the sourced opening fixture; native/current-manager fallback is forbidden",
            "not_performed": [
                "web fetch", "manager selection", "ledger write", "overlay write", "package write", "database compilation",
            ],
        },
        "inputs": {
            "manager_overlay_index": {"path": _relative(overlay_index_path, root=root), "sha256": overlay_index_sha},
            "current_root": _relative(current_root, root=root),
            "allocated_manager_capture_root": _relative(operations_root, root=root),
        },
        "seasons": season_rows,
        "summary": {"season_count": len(season_rows), **totals},
        "first_actionable_automated_integration_tranche": {
            "status": "ready" if first_tranche else "none",
            "maximum_season_count": 1,
            "seasons": first_tranche,
            "blocked_by": "dated-candidate-conflicts" if not first_tranche and totals["existing_dated_conflicting_candidate_count"] else None,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-root", type=Path, default=ROOT / ".local/season-historical-squad-backfill-v1")
    parser.add_argument("--overlay-index", type=Path,
                        default=ROOT / ".local/season-overlay-index-v1/calendar-bound-v2-manager-overlays-v1.json")
    parser.add_argument("--operations-root", type=Path, default=ROOT / ".local/operations")
    parser.add_argument("--season", action="append", dest="seasons")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ManagerGapTriageError(f"refusing to overwrite triage receipt: {args.output}")
        result = build_report(
            current_root=args.current_root, overlay_index_path=args.overlay_index,
            operations_root=args.operations_root, seasons=args.seasons,
        )
    except (OSError, ManagerGapTriageError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
