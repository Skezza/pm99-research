#!/usr/bin/env python3
"""Batch the generic raw season-source intake without choosing historic data.

The normal ``season_source_intake_v1`` command deliberately accepts one
hash-locked squad capture.  This companion is its safe batch coordinator:

* it discovers season directories (or accepts explicit season IDs),
* finds the *canonical* capture whose whole-document SHA-256 is declared by
  the active carrier assignment (a verified season-local source bundle may
  declare a derived assignment; otherwise the base assignment is used), and
* builds the raw intake and its coverage receipt in memory.

It never selects a capture because of its filename, never falls back to a
candidate assignment, and never merges multiple captures.  Those situations
are reported in a compact canonical matrix as explicit blockers.  By default
the matrix is written to stdout only.  ``--write`` may materialise missing
``source-intake.json`` and ``source-intake-audit.json`` for eligible seasons;
it will not overwrite, repair or replace an existing receipt.

This is a source-only authoring tool.  It neither reads nor writes PM99 game
files, and it has no season-specific or 2015-specific code path.

Examples:

    python3 scripts/season_source_intake_batch_v1.py --seasons-root seasons
    python3 scripts/season_source_intake_batch_v1.py --seasons-root seasons \
      --season 2000-01 --season 2001-02 --write
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import foreign_carrier_assignment_v1 as assignment_lib  # noqa: E402
from scripts import season_source_bundle_v1 as bundle_lib  # noqa: E402
from scripts import season_source_intake_v1 as intake_lib  # noqa: E402
from scripts import world_fixed_carrier_ledger_v2 as registry_lib  # noqa: E402


SCHEMA = "pm99-season-source-intake-batch-v1"
SEASON_ID_RE = re.compile(r"^(?:1999|20(?:0[0-9]|1[0-9]|2[0-5]))-[0-9]{2}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
BASE_ASSIGNMENT_NAME = "foreign-carrier-assignment.json"
CANDIDATE_ASSIGNMENT_NAME = "foreign-carrier-assignment-candidates.json"
REGISTRY_NAME = "fixed-carrier-registry.json"
INTAKE_NAME = "source-intake.json"
AUDIT_NAME = "source-intake-audit.json"
SOURCE_BUNDLE_NAME = "source-bundle.json"


class BatchError(ValueError):
    """The batch invocation, rather than one season's data, is invalid."""


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Use the same canonical encoding as all input and receipt contracts."""

    return assignment_lib.canonical_json_bytes(value)


def _sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _relative_path(*, seasons_root: Path, path: Path) -> str:
    """Return a portable path without leaking a workstation-specific root."""

    try:
        return path.relative_to(seasons_root.parent).as_posix()
    except ValueError:
        return path.as_posix()


def _read_canonical(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    """Read a canonical document without making an unsafe recovery attempt."""

    return assignment_lib.read_canonical_json(path, label=label)


def _block(code: str, **details: Any) -> dict[str, Any]:
    return {"code": code, **details}


def _candidate_summary(path: Path, *, seasons_root: Path) -> dict[str, Any] | None:
    """Describe, but never use, a separate candidate-only assignment ledger."""

    if not path.is_file():
        return None
    try:
        document, digest = _read_canonical(path, label="candidate carrier assignment")
    except assignment_lib.AssignmentError as exc:
        return {
            "path": _relative_path(seasons_root=seasons_root, path=path),
            "status": "invalid",
            "error": str(exc),
        }
    rows = document.get("assignments")
    counts = Counter(
        str(row.get("status")) for row in rows if isinstance(row, dict)
    ) if isinstance(rows, list) else Counter()
    return {
        "path": _relative_path(seasons_root=seasons_root, path=path),
        "sha256": digest,
        "status": "present",
        "assignment_status_counts": dict(sorted(counts.items())),
    }


def _discover_capture_documents(
    *, season_dir: Path, seasons_root: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Discover only canonical FootballSquads capture documents.

    Other JSON evidence can live under ``sources`` without becoming a capture.
    Only a document that declares the canonical capture schema is required to
    use canonical JSON bytes; an availability receipt or web-snapshot manifest
    must not poison a valid, separately hash-bound capture.
    """

    source_dir = season_dir / "sources"
    if not source_dir.is_dir():
        return [], [], False
    captures: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for path in sorted(source_dir.rglob("*.json")):
        try:
            raw = path.read_bytes()
            document = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            # It cannot declare a usable source-capture schema, so it is
            # ancillary evidence rather than a candidate for selection.
            continue
        if not isinstance(document, dict) or document.get("schema_version") != assignment_lib.SOURCE_SCHEMA:
            continue
        try:
            canonical_document, digest = _read_canonical(path, label="historic squad capture")
        except assignment_lib.AssignmentError as exc:
            invalid.append(
                {
                    "path": _relative_path(seasons_root=seasons_root, path=path),
                    "error": str(exc),
                }
            )
            continue
        captures.append(
            {
                "path": path,
                "relative_path": _relative_path(seasons_root=seasons_root, path=path),
                "document": canonical_document,
                "sha256": digest,
            }
        )
    return captures, invalid, True


def _composed_capture_inputs(
    *, capture: Mapping[str, Any], captures: list[dict[str, Any]]
) -> tuple[bool, int]:
    """Verify a bound composition against its individually retained inputs.

    A composed capture is usable only when its ``source.inputs`` rows name
    existing raw documents by both filename and complete-document digest.
    This lets the batch distinguish an explicit composition from a directory
    containing several competing partial captures.
    """

    source = capture.get("source")
    inputs = source.get("inputs") if isinstance(source, Mapping) else None
    if not isinstance(inputs, list) or len(inputs) < 2:
        return False, 0
    expected: set[tuple[str, str]] = set()
    for item in inputs:
        if not isinstance(item, Mapping):
            return False, 0
        name, digest = item.get("capture_name"), item.get("sha256")
        if not isinstance(name, str) or Path(name).name != name:
            return False, 0
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            return False, 0
        expected.add((name, digest))
    if len(expected) != len(inputs):
        return False, 0
    available = {(str(item["path"].name), str(item["sha256"])) for item in captures}
    return expected.issubset(available), len(expected)


def _compact_coverage(audit: Mapping[str, Any]) -> dict[str, Any]:
    coverage = audit["coverage"]
    return {
        "assignment_status_counts": dict(coverage["assignment_status_counts"]),
        "fixed_carrier_count": int(coverage["fixed_carrier_count"]),
        "fixed_roster_slot_count": int(coverage["fixed_roster_slot_count"]),
        "source_club_count": int(coverage["source_club_count"]),
        "source_player_row_count": int(coverage["source_player_row_count"]),
        "source_player_rows_with_unresolved_facts": int(coverage["source_player_rows_with_unresolved_facts"]),
    }


def _write_missing(path: Path, value: Mapping[str, Any]) -> None:
    """Materialise a receipt exactly once; never turn batch mode into repair."""

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(canonical_json_bytes(value))
    except FileExistsError as exc:
        raise BatchError(f"refusing to overwrite existing receipt: {path}") from exc


def _receipt_state(
    *,
    path: Path,
    expected: Mapping[str, Any],
    label: str,
    seasons_root: Path,
    write: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Validate an existing receipt or optionally write its exact expected form."""

    display_path = _relative_path(seasons_root=seasons_root, path=path)
    if not path.exists():
        if write:
            _write_missing(path, expected)
            return {"path": display_path, "status": "materialised", "sha256": _sha256(expected)}, []
        return {"path": display_path, "status": "missing"}, []
    if not path.is_file():
        return {"path": display_path, "status": "invalid"}, [_block("existing-receipt-not-a-file", path=display_path)]
    try:
        existing, digest = _read_canonical(path, label=label)
    except assignment_lib.AssignmentError as exc:
        return {"path": display_path, "status": "invalid"}, [
            _block("existing-receipt-invalid", path=display_path, error=str(exc))
        ]
    if existing != dict(expected):
        return {"path": display_path, "status": "stale", "sha256": digest}, [
            _block("existing-receipt-does-not-match-inputs", path=display_path)
        ]
    return {"path": display_path, "status": "validated", "sha256": digest}, []


def _active_assignment(
    *, season_dir: Path, seasons_root: Path, requested_name: str | None
) -> tuple[str | None, dict[str, Any] | None, dict[str, Any] | None]:
    """Select an explicit assignment, or a verified data-only source bundle.

    An explicitly supplied filename keeps diagnostic/backward-compatible
    behaviour.  In normal batch mode a season-local source-bundle manifest is
    the authoritative declaration that its derived composed assignment is
    active.  We recompute its outputs before trusting it, so this never turns
    a convenient filename into an unverified source choice.
    """

    if requested_name is not None:
        return requested_name, None, None
    bundle_path = season_dir / SOURCE_BUNDLE_NAME
    if not bundle_path.exists():
        return BASE_ASSIGNMENT_NAME, None, None
    try:
        bundle = bundle_lib.read_bundle(bundle_path)
        receipt = bundle_lib.verify_bundle(bundle_path=bundle_path, bundle=bundle)
    except (OSError, bundle_lib.SourceBundleError) as exc:
        return None, None, _block("source-bundle-invalid", error=str(exc))
    assignment_name = str(bundle["assignment_rebinding"]["output_relative_path"])
    return assignment_name, {
        "path": _relative_path(seasons_root=seasons_root, path=bundle_path),
        "bundle_id": bundle["bundle_id"],
        "status": "verified",
        "capture_sha256": receipt["capture_output"]["sha256"],
        "assignment_sha256": receipt["assignment_output"]["sha256"],
    }, None


def _season_row(*, season_id: str, seasons_root: Path, assignment_name: str | None, write: bool) -> dict[str, Any]:
    """Build one non-release row without allowing a failed season to abort all."""

    season_dir = seasons_root / season_id
    row: dict[str, Any] = {
        "season_id": season_id,
        "season_directory": _relative_path(seasons_root=seasons_root, path=season_dir),
        "registry": None,
        "source_bundle": None,
        "base_assignment": None,
        "candidate_assignment": None,
        "source_captures": {"canonical_capture_count": 0, "matching_capture": None},
        "source_intake": {"path": _relative_path(seasons_root=seasons_root, path=season_dir / INTAKE_NAME), "status": "not-evaluated"},
        "source_intake_audit": {"path": _relative_path(seasons_root=seasons_root, path=season_dir / AUDIT_NAME), "status": "not-evaluated"},
        "coverage": None,
        "blockers": [],
    }
    blockers: list[dict[str, Any]] = row["blockers"]
    if not season_dir.is_dir():
        blockers.append(_block("season-directory-missing"))
        return row

    active_assignment_name, bundle_state, bundle_blocker = _active_assignment(
        season_dir=season_dir,
        seasons_root=seasons_root,
        requested_name=assignment_name,
    )
    row["source_bundle"] = bundle_state
    if bundle_blocker is not None:
        blockers.append(bundle_blocker)
        return row
    assert active_assignment_name is not None

    registry_path = season_dir / REGISTRY_NAME
    try:
        registry, registry_digest = _read_canonical(registry_path, label="fixed-carrier registry")
        registry_lib.validate_registry(registry)
    except (assignment_lib.AssignmentError, registry_lib.WorldLedgerError) as exc:
        blockers.append(_block("registry-missing-or-invalid", error=str(exc)))
        registry = None
    else:
        row["registry"] = {
            "path": _relative_path(seasons_root=seasons_root, path=registry_path),
            "sha256": registry_digest,
        }

    assignment_path = season_dir / active_assignment_name
    try:
        assignment, assignment_digest = _read_canonical(assignment_path, label="base carrier assignment")
    except assignment_lib.AssignmentError as exc:
        assignment = None
        blockers.append(_block("no-assignment", error=str(exc)))
    else:
        expected_capture_hash = assignment.get("source_capture_sha256")
        if not isinstance(expected_capture_hash, str) or not SHA256_RE.fullmatch(expected_capture_hash):
            blockers.append(_block("base-assignment-invalid-source-capture-hash"))
            assignment = None
        else:
            row["base_assignment"] = {
                "path": _relative_path(seasons_root=seasons_root, path=assignment_path),
                "sha256": assignment_digest,
                "source_capture_sha256": expected_capture_hash,
            }

    row["candidate_assignment"] = _candidate_summary(
        season_dir / CANDIDATE_ASSIGNMENT_NAME, seasons_root=seasons_root
    )
    captures, invalid_sources, source_dir_exists = _discover_capture_documents(
        season_dir=season_dir, seasons_root=seasons_root
    )
    matching: list[dict[str, Any]] = []
    if assignment is not None:
        matching = [item for item in captures if item["sha256"] == assignment["source_capture_sha256"]]
    composition_ready = False
    composition_input_count = 0
    if len(matching) == 1:
        composition_ready, composition_input_count = _composed_capture_inputs(
            capture=matching[0]["document"], captures=captures
        )
    source_capture_state: dict[str, Any] = {
        "canonical_capture_count": len(captures),
        "matching_capture": (
            {"path": matching[0]["relative_path"], "sha256": matching[0]["sha256"]}
            if len(matching) == 1
            else None
        ),
    }
    if composition_ready:
        source_capture_state["composition"] = {
            "status": "validated",
            "input_capture_count": composition_input_count,
        }
    row["source_captures"] = source_capture_state
    if not source_dir_exists or not captures:
        blockers.append(_block("missing-source", invalid_document_count=len(invalid_sources)))
    elif invalid_sources:
        blockers.append(_block("source-capture-invalid", document_count=len(invalid_sources)))
    if assignment is not None and captures and not matching:
        blockers.append(
            _block(
                "source-capture-hash-mismatch",
                expected_sha256=assignment["source_capture_sha256"],
                available_capture_count=len(captures),
            )
        )
    elif assignment is not None and len(matching) > 1:
        blockers.append(_block("source-capture-hash-ambiguous", matching_capture_count=len(matching)))
    if len(captures) > 1 and not composition_ready:
        blockers.append(
            _block(
                "multi-source-composition-required",
                canonical_capture_count=len(captures),
            )
        )

    # The single-capture source-intake contract is intentionally narrow.  Do
    # not run it if discovery has already shown that a composition is needed.
    if (
        registry is None
        or assignment is None
        or bool(invalid_sources)
        or (len(captures) != 1 and not composition_ready)
        or len(matching) != 1
    ):
        return row

    capture = matching[0]["document"]
    try:
        generated_intake = intake_lib.build_intake(
            registry=registry,
            source_capture=capture,
            assignment=assignment,
            intake_id=f"world-{season_id}-source-intake",
        )
        generated_audit = intake_lib.audit_intake(
            intake=generated_intake,
            registry=registry,
            source_capture=capture,
            assignment=assignment,
        )
    except (intake_lib.SourceIntakeError, assignment_lib.AssignmentError, registry_lib.WorldLedgerError) as exc:
        blockers.append(_block("source-intake-rejected", error=str(exc)))
        return row

    row["coverage"] = _compact_coverage(generated_audit)
    intake_state, intake_blockers = _receipt_state(
        path=season_dir / INTAKE_NAME,
        expected=generated_intake,
        label="season source intake",
        seasons_root=seasons_root,
        write=write,
    )
    row["source_intake"] = intake_state
    blockers.extend(intake_blockers)
    # An audit cannot safely be materialised if the underlying checked-in
    # intake is stale or invalid.  A newly materialised or exact intake is OK.
    if intake_state["status"] in {"materialised", "validated"}:
        audit_state, audit_blockers = _receipt_state(
            path=season_dir / AUDIT_NAME,
            expected=generated_audit,
            label="season source intake audit",
            seasons_root=seasons_root,
            write=write,
        )
        row["source_intake_audit"] = audit_state
        blockers.extend(audit_blockers)
    else:
        row["source_intake_audit"] = {
            "path": _relative_path(seasons_root=seasons_root, path=season_dir / AUDIT_NAME),
            "status": "not-evaluated",
        }
    return row


def discover_season_ids(*, seasons_root: Path, selected: list[str] | None = None) -> list[str]:
    """Return selected IDs, or the requested 2000/01--2025/26 batch scope.

    The repository retains 1999/00 research material, but the unattended
    batch default is deliberately the user's 26-season delivery scope.  A
    caller may still inspect 1999/00 explicitly with ``--season 1999-00``.
    """

    if selected:
        invalid = [value for value in selected if not SEASON_ID_RE.fullmatch(value)]
        if invalid:
            raise BatchError(f"invalid season ID(s): {', '.join(sorted(invalid))}")
        return sorted(set(selected))
    if not seasons_root.is_dir():
        raise BatchError(f"seasons root does not exist: {seasons_root}")
    # Keep a missing expected directory visible as a blocked row instead of
    # quietly shrinking a requested 26-season run to the folders that happen
    # to exist on one workstation.
    return [f"{year}-{str(year + 1)[-2:]}" for year in range(2000, 2026)]


def build_matrix(
    *,
    seasons_root: Path,
    selected: list[str] | None = None,
    assignment_name: str | None = None,
    write: bool = False,
) -> dict[str, Any]:
    """Build a canonical matrix; only ``write=True`` materialises receipts."""

    seasons_root = seasons_root.resolve()
    if (
        assignment_name is not None
        and (
            not isinstance(assignment_name, str)
            or not assignment_name
            or Path(assignment_name).name != assignment_name
            or assignment_name in {".", ".."}
        )
    ):
        raise BatchError("assignment_name must be a single filename")
    season_ids = discover_season_ids(seasons_root=seasons_root, selected=selected)
    rows = [
        _season_row(
            season_id=season_id,
            seasons_root=seasons_root,
            assignment_name=assignment_name,
            write=write,
        )
        for season_id in season_ids
    ]
    source_ready = sum(1 for row in rows if row["coverage"] is not None and not row["blockers"])
    materialised = sum(1 for row in rows if row["source_intake"]["status"] == "materialised")
    return {
        "schema_version": SCHEMA,
        "seasons_root": seasons_root.name,
        "rows": rows,
        "summary": {
            "season_count": len(rows),
            "source_intake_eligible_count": source_ready,
            "source_intake_materialised_count": materialised,
            "blocked_count": len(rows) - source_ready,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons-root", type=Path, default=ROOT / "seasons")
    parser.add_argument("--season", action="append", default=[], help="Season directory ID; repeat to select several")
    parser.add_argument(
        "--assignment-name",
        default=None,
        help=(
            "Override each season's active assignment filename. By default, a "
            "verified source-bundle.json selects its derived assignment; other "
            "seasons use foreign-carrier-assignment.json."
        ),
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Materialise only missing exact source-intake and audit receipts for eligible rows",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        matrix = build_matrix(
            seasons_root=args.seasons_root,
            selected=list(args.season) or None,
            assignment_name=args.assignment_name,
            write=bool(args.write),
        )
    except BatchError as exc:
        raise SystemExit(f"error: {exc}") from exc
    print(canonical_json_bytes(matrix).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
