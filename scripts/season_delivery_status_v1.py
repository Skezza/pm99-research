#!/usr/bin/env python3
"""Report the evidence-backed delivery state of every PM99 season.

This is an operations *reader*.  It deliberately does not prepare, compile,
copy, archive, or delete anything.  A watcher can run it repeatedly while
workers update their local receipts and write the Markdown/JSON outputs below.

The report has one intentionally conservative rule: a source intake, a draft
package, a calendar receipt, or an unbound screenshot can never make a season
``playable``.  That label needs a static release audit, a successful runtime
route, and at least one screenshot from that route.  The currently documented
2015/16 world release is recognised by its explicit final-build and guarded
runtime receipt. Registered provisional runtime proofs are also reported, but
remain provisional until they create the equivalent canonical release
evidence.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


SCHEMA = "pm99-season-delivery-status-v1"
BASELINE_INDEX_SCHEMA = "pm99-season-baseline-index-v1"
SEASON_RE = re.compile(r"^(?:19|20)\d{2}-\d{2}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TARGET_START = "2000-01"
TARGET_END = "2025-26"
STATIC_INGRESS_SCHEMA = "pm99-season-static-ingress-receipt-v1"
STATIC_INGRESS_STATE = "clean-static-ingress-complete-not-playable"
STATIC_INGRESS_PREFLIGHT_SCHEMA = "pm99-season-static-ingress-preflight-blocked-v1"
STATIC_INGRESS_PREFLIGHT_STATE = "blocked-before-static-compilation"
STALE_CANDIDATE_SCHEMA = "pm99-stale-mode1-source-candidate-reconciliation-v1"
STALE_CANDIDATE_STATE = "stale-mode1-source-candidates-reconciled-static-candidate-only"
STALE_CANDIDATE_POLICY = "replace-only-exact-one-current-source-versus-one-legacy-non-source-mode1-candidate"
STATIC_INGRESS_DATABASE_FILES = {
    "DBDAT/ENT98030.FDI",
    "DBDAT/EQ98030.FDI",
    "DBDAT/JUG98030.FDI",
}
CANONICAL_PROMOTION_SCHEMA = "pm99-season-canonical-promotion-factory-v1"
CANONICAL_PROMOTION_STATE = "canonical-workspace-candidate-only"
BUILD_PLAN_SCHEMA = "pm99-season-build-plan-v2"
BUILD_PLAN_RECEIPT_SCHEMA = "pm99-season-build-plan-receipt-v2"
RELEASE_MANIFEST_SCHEMA = "pm99-season-release-manifest-v2"
RUNTIME_ATTESTATION_SCHEMA = "pm99-season-release-attestation-v2"
STATIC_INGRESS_RUNTIME_ATTESTATION_SCHEMA = "pm99-season-static-ingress-runtime-attestation-v1"
KNOWN_RUNTIME_PROOF = {
    "2000-01": {
        "kind": "stoke-route",
        "expected_phase": "return_from_line_up",
        "path": Path(
            "upstream/pm99-runner/docs/artifacts/pm99_runner/"
            "post1999_2000_01_stoke_lineup_20260907_r2/summary.json"
        ),
    },
    "2001-02": {
        "kind": "stoke-route",
        "expected_phase": "return_from_line_up",
        "path": Path(
            "upstream/pm99-runner/docs/artifacts/pm99_runner/"
            "post1999_2001_02_stoke_lineup_20260907_r3/summary.json"
        ),
    },
    "2005-06": {
        "kind": "stoke-route",
        "expected_phase": "return_from_line_up",
        "path": Path(
            ".local/season-runtime-evidence-v1/"
            "post1999_2005_06_target_calendar_runtime_20260909_r2/summary.json"
        ),
        "attestation_path": Path(
            ".local/season-runtime-evidence-v1/"
            "post1999_2005_06_target_calendar_runtime_20260909_r2/runtime-attestation.json"
        ),
        "static_game_root": Path(
            ".local/season-static-qualification-v1/"
            "2005-06-carrier-12-reconciled-20260908/game"
        ),
    },
    "2007-08": {
        "kind": "stoke-route",
        "expected_phase": "return_from_line_up",
        "path": Path(
            ".local/season-runtime-evidence-v1/"
            "post1999_2007_08_target_calendar_runtime_20260908_r1/summary.json"
        ),
        "attestation_path": Path(
            ".local/season-runtime-evidence-v1/"
            "post1999_2007_08_target_calendar_runtime_20260908_r1/runtime-attestation.json"
        ),
        "static_game_root": Path(
            ".local/season-static-qualification-v1/"
            "2007-08-alias-roster-carrier10-20260908-r2/game"
        ),
    },
    "2008-09": {
        "kind": "selector-discovery",
        "path": Path(
            "upstream/pm99-runner/docs/artifacts/pm99_runner/"
            "post1999_2008_09_exact_plan_runtime_20260907_r1/selector_discovery_summary.json"
        ),
    },
    "2015-16": {
        "kind": "stoke-route",
        "path": Path(
            "upstream/pm99-runner/docs/artifacts/pm99_runner/"
            "world2015_clean_final_guarded_stoke_20260831/summary.json"
        ),
    },
}
KNOWN_RUNTIME_SCREEN = "return_from_squad"
BENTLEY_SOURCE = Path("/home/joe/Bentley/SD")
BENTLEY_REMOTE = "/srv/hdd/pm99-archive/backups/bentley-sd-20260902"
BENTLEY_RECEIPTS = "/srv/hdd/pm99-archive/receipts/bentley-sd-20260902"


class StatusError(ValueError):
    """A report input is malformed, rather than merely absent."""


def sha256_file(path: Path) -> str:
    """Return a file SHA-256 without loading a game asset into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> Mapping[str, Any] | None:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, Mapping) else None


def _read_json_value(path: Path) -> Any | None:
    """Read JSON when an evidence sidecar is deliberately an array."""

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _canonical_json_bytes(value: Any) -> bytes:
    """Return the pipeline's content-addressed JSON encoding, sans file newline."""

    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _read_canonical_json(path: Path) -> tuple[Any, str] | None:
    """Read a regular canonical JSON file and return its semantic SHA-256.

    Pipeline V2 hashes canonical JSON without its on-disk trailing newline.
    Checking both the byte encoding and this semantic hash is necessary when a
    promotion receipt uses package file hashes while a build plan uses document
    descriptors.
    """

    try:
        if not path.is_file() or path.is_symlink():
            return None
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
        canonical = _canonical_json_bytes(value)
    except (OSError, UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if raw != canonical + b"\n":
        return None
    return value, hashlib.sha256(canonical).hexdigest()


def _relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _hash_record(root: Path, path: Path) -> dict[str, Any]:
    """Return an exact, current fingerprint or a clear missing state."""

    record: dict[str, Any] = {"path": _relative(root, path), "exists": path.is_file()}
    if path.is_file():
        record.update({"sha256": sha256_file(path), "bytes": path.stat().st_size})
    return record


def _current_artifact(root: Path, pointer_path: Path, artifact: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(artifact, Mapping):
        return {"state": "missing"}
    relative = artifact.get("path")
    expected = artifact.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected, str):
        return {"state": "invalid-pointer"}
    resolved = pointer_path.parent / relative
    record = _hash_record(root, resolved)
    record["declared_sha256"] = expected
    record["state"] = "bound" if record.get("sha256") == expected else "hash-mismatch"
    return record


def source_status(root: Path, season: str) -> dict[str, Any]:
    """Read a current historical-source pointer without changing it."""

    pointer = root / ".local/season-historical-squad-backfill-v1" / season / "current.json"
    if pointer.is_file():
        document = _read_json(pointer)
        if document is None:
            return {"state": "invalid-current-pointer", "pointer": _hash_record(root, pointer)}
        artifacts = document.get("artifacts")
        artifacts = artifacts if isinstance(artifacts, Mapping) else {}
        source = _current_artifact(root, pointer, artifacts.get("source"))
        intake = _current_artifact(root, pointer, artifacts.get("intake"))
        state = "bound" if source.get("state") == intake.get("state") == "bound" else "pointer-incomplete"
        return {
            "state": state,
            "pointer": _hash_record(root, pointer),
            "revision_id": document.get("revision_id"),
            "source": source,
            "intake": intake,
        }

    source_dir = root / "seasons" / season / "sources"
    source_files = sorted(path for path in source_dir.glob("*.json") if path.is_file()) if source_dir.is_dir() else []
    return {
        "state": "season-source-files-only" if source_files else "missing",
        "source_files": [_hash_record(root, path) for path in source_files],
    }


def _newest(paths: Iterable[Path]) -> Path | None:
    candidates = [path for path in paths if path.is_file()]
    return max(candidates, key=lambda path: path.stat().st_mtime_ns) if candidates else None


def _safe_index_path(root: Path, value: Any) -> Path | None:
    """Resolve a baseline-index path only when it remains beneath the repo."""
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        return None
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _safe_child_path(parent: Path, value: Any) -> Path | None:
    """Resolve a receipt-relative artifact only when it stays under its receipt."""

    if not isinstance(value, str) or not value or Path(value).is_absolute():
        return None
    candidate = (parent / value).resolve()
    try:
        candidate.relative_to(parent.resolve())
    except ValueError:
        return None
    return candidate


def _frozen_baseline_draft(root: Path, season: str) -> tuple[Path, Path, Mapping[str, Any]] | None:
    """Find a current hash-verified frozen baseline entry for one season.

    The index itself is a selection record, not a release package.  It is used
    here only to surface the correct current provisional base and to reject a
    stale or mutated package before a later overlay can extend it.
    """
    index_root = root / ".local/season-baselines-v1"
    candidates: list[tuple[Path, Path, Mapping[str, Any]]] = []
    if not index_root.is_dir():
        return None
    for index_path in sorted(index_root.glob("*.json")):
        index = _read_json(index_path)
        if index is None or index.get("schema_version") != BASELINE_INDEX_SCHEMA:
            continue
        if index.get("state") != "frozen-provisional-base":
            continue
        entries = index.get("seasons")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, Mapping) or entry.get("season") != season:
                continue
            base = entry.get("base_draft")
            audit = entry.get("calendar_binding_audit")
            if not isinstance(base, Mapping) or not isinstance(audit, Mapping):
                continue
            package_path = _safe_index_path(root, base.get("path"))
            audit_path = _safe_index_path(root, audit.get("path"))
            expected_package = base.get("sha256")
            expected_audit = audit.get("sha256")
            if (
                package_path is None or audit_path is None
                or not package_path.is_file() or not audit_path.is_file()
                or _hash_record(root, package_path).get("sha256") != expected_package
                or _hash_record(root, audit_path).get("sha256") != expected_audit
            ):
                continue
            candidates.append((package_path, index_path, entry))
    if not candidates:
        return None
    return max(candidates, key=lambda row: row[1].stat().st_mtime_ns)


def _frozen_baseline_seasons(root: Path) -> set[str]:
    """Return season labels named by syntactically valid frozen indexes."""
    index_root = root / ".local/season-baselines-v1"
    result: set[str] = set()
    if not index_root.is_dir():
        return result
    for path in index_root.glob("*.json"):
        document = _read_json(path)
        if document is None or document.get("schema_version") != BASELINE_INDEX_SCHEMA:
            continue
        if document.get("state") != "frozen-provisional-base":
            continue
        for row in document.get("seasons", []):
            season = row.get("season") if isinstance(row, Mapping) else None
            if isinstance(season, str) and SEASON_RE.fullmatch(season):
                result.add(season)
    return result


def _calendar_bound_source_draft(root: Path, season: str) -> tuple[Path, Path, Mapping[str, Any]] | None:
    """Find a current, hash-verified post-calendar source draft.

    These are still drafts, not canonical release packages.  The additional
    state only makes a source-package audit's proven calendar closure visible
    to operations, instead of falling back to an older pre-calendar shard.
    """

    candidates = _matching_source_build_audits(root, season)
    if not candidates:
        return None
    return max(candidates, key=lambda row: row[1].stat().st_mtime_ns)


def _matching_source_build_audits(
    root: Path,
    season: str,
    *,
    package_sha256: str | None = None,
    calendar_audit_sha256: str | None = None,
) -> list[tuple[Path, Path, Mapping[str, Any]]]:
    """Find current source-build audits that bind an exact draft when requested.

    Frozen baseline indexes select a calendar-bound draft directly, whereas
    source-build audits additionally record current intake and hard-blocker
    evidence.  Requiring all three bindings prevents an older ingress
    candidate from being presented as current merely because its season name
    happens to match.
    """

    candidates: list[tuple[Path, Path, Mapping[str, Any]]] = []
    pattern = f"season-authoring-post-calendar-binding-*/{season}/source-package-build-audit.json"
    source = source_status(root, season)
    intake = source.get("intake") if isinstance(source, Mapping) else None
    if not isinstance(intake, Mapping):
        return candidates
    for audit_path in root.glob(f".local/{pattern}"):
        audit = _read_json(audit_path)
        package_path = audit_path.with_name("draft-season-package.json")
        if audit is None or not package_path.is_file():
            continue
        package = _hash_record(root, package_path)
        hard_blockers = audit.get("hard_blockers")
        calendar_binding = audit.get("calendar_binding")
        coverage = audit.get("coverage")
        if (
            audit.get("schema_version") != "pm99-season-source-package-build-audit-v1"
            or audit.get("draft_package_sha256") != package.get("sha256")
            or not isinstance(hard_blockers, list)
            or not isinstance(calendar_binding, Mapping)
            or calendar_binding.get("template_package_sha256") != audit.get("template_package_sha256")
            or not isinstance(calendar_binding.get("audit_sha256"), str)
            or not isinstance(coverage, Mapping)
            or coverage.get("calendar_binding_verified_count") != 1
        ):
            continue
        if package_sha256 is not None and package.get("sha256") != package_sha256:
            continue
        if (
            calendar_audit_sha256 is not None
            and calendar_binding.get("audit_sha256") != calendar_audit_sha256
        ):
            continue
        # Reject a receipt for stale source intake even though it remains a
        # useful historical artifact.  Operations should report only the
        # source-package audit that still binds the current intake pointer.
        if audit.get("source_intake_sha256") != intake.get("sha256"):
            continue
        candidates.append((package_path, audit_path, audit))
    return candidates


def _candidate_output_record(
    root: Path, candidate_root: Path, outputs: Mapping[str, Any], key: str,
) -> dict[str, Any] | None:
    """Return a hash-verified canonical-candidate output record.

    The promotion factory intentionally writes a candidate rather than a
    release package.  Its audit pins each output, so do not surface a partial
    or later-mutated candidate in the operations report.
    """

    declared = outputs.get(key)
    if not isinstance(declared, Mapping):
        return None
    relative = declared.get("relative_path")
    expected = declared.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected, str):
        return None
    record = _hash_record(root, candidate_root / relative)
    if record.get("sha256") != expected:
        return None
    return record


def _canonical_workspace_candidates(
    root: Path,
    season: str,
    *,
    draft_sha256: str,
    source_audit_sha256: str,
) -> list[dict[str, Any]]:
    """Find complete ingress candidates that still bind the current draft.

    A candidate proves strict V2, calendar, base, workspace, and prepare
    ingress only.  It is deliberately never a canonical release package:
    source-editorial blockers, binary compilation, runtime, and screenshots
    remain separate gates. Matching both current draft and source-audit
    hashes prevents a historical candidate from being reported as current.
    """

    candidates: list[dict[str, Any]] = []
    candidate_root = root / ".local/season-canonical-candidate-v1"
    if not candidate_root.is_dir():
        return candidates
    required_contracts = {
        "season_package_v2_strict",
        "calendar_binding",
        "verified_base_descriptor",
        "workspace_contract",
        "workspace_prepare",
    }
    required_outputs = {
        "package",
        "prepared_effective_package",
        "timeline",
        "workspace",
        "build_plan_candidate",
    }
    for audit_path in sorted(candidate_root.glob("*/promotion-audit.json")):
        audit = _read_json(audit_path)
        if audit is None:
            continue
        candidate = audit_path.parent
        inputs = audit.get("input")
        outputs = audit.get("outputs")
        contracts = audit.get("static_contracts")
        if not isinstance(inputs, Mapping) or not isinstance(outputs, Mapping) or not isinstance(contracts, Mapping):
            continue
        if (
            audit.get("schema_version") != "pm99-season-canonical-promotion-factory-v1"
            or audit.get("season") != season
            or audit.get("state") != "canonical-workspace-candidate-only"
            or audit.get("release_eligible") is not False
            or inputs.get("calendar_bound_package_sha256") != draft_sha256
            or inputs.get("calendar_binding_audit_sha256") != source_audit_sha256
            or not required_contracts.issubset(contracts)
            or any(contracts.get(name) != "passed" for name in required_contracts)
        ):
            continue
        base_sha256 = inputs.get("verified_base_descriptor_sha256")
        base_record = _hash_record(root, candidate / "verified-base.json")
        if not isinstance(base_sha256, str) or base_record.get("sha256") != base_sha256:
            continue
        output_records = {
            key: _candidate_output_record(root, candidate, outputs, key)
            for key in required_outputs
        }
        if any(record is None for record in output_records.values()):
            continue
        package_record = output_records["package"]
        if package_record is None:
            continue
        package_sha256 = package_record.get("sha256")
        alias_binding = inputs.get("display_alias_binding")
        if alias_binding is None:
            # A direct ingress candidate must remain byte-identical to the
            # calendar-bound draft.  Do not let a changed package masquerade
            # as one merely because the other workspace receipts are valid.
            if (
                package_sha256 != draft_sha256
                or "display_alias_binding" in contracts
            ):
                continue
            package_binding = {"state": "byte-identical-calendar-bound"}
        else:
            # The promotion factory permits one narrowly-scoped derivative:
            # an independently audited, display-name-only alias package.  It
            # is still an ingress candidate, never a release package.  Bind
            # both ends and the immutable alias receipt before surfacing it.
            if not isinstance(alias_binding, Mapping):
                continue
            source_package_sha256 = alias_binding.get("source_package_sha256")
            alias_package_sha256 = alias_binding.get("alias_package_sha256")
            alias_audit_sha256 = alias_binding.get("display_alias_audit_sha256")
            changed_display_name_count = alias_binding.get("changed_display_name_count")
            if (
                contracts.get("display_alias_binding") != "passed"
                or source_package_sha256 != draft_sha256
                or alias_package_sha256 != package_sha256
                or not isinstance(alias_audit_sha256, str)
                or SHA256_RE.fullmatch(alias_audit_sha256) is None
                or not isinstance(changed_display_name_count, int)
                or isinstance(changed_display_name_count, bool)
                or changed_display_name_count < 1
            ):
                continue
            package_binding = {
                "state": "verified-display-alias-derivative",
                "source_package_sha256": source_package_sha256,
                "display_alias_audit_sha256": alias_audit_sha256,
                "changed_display_name_count": changed_display_name_count,
            }
        candidates.append({
            "path": _relative(root, candidate),
            "promotion_audit": _hash_record(root, audit_path),
            "package_binding": package_binding,
            "static_contracts": {name: contracts[name] for name in sorted(required_contracts)},
            "verified_base": base_record,
            "outputs": output_records,
            "not_performed": audit.get("not_performed"),
        })
    return candidates


def _add_current_source_audit(
    root: Path,
    season: str,
    result: dict[str, Any],
    audit_path: Path,
    audit: Mapping[str, Any],
) -> None:
    """Attach current source-audit and ingress facts without release promotion."""

    blockers = audit.get("hard_blockers")
    source_audit = _hash_record(root, audit_path)
    result["source_package_audit"] = source_audit
    result["release_eligible"] = audit.get("release_eligible") is True
    result["hard_blocker_count"] = len(blockers) if isinstance(blockers, list) else None

    calendar_binding = audit.get("calendar_binding")
    if not isinstance(calendar_binding, Mapping):
        return
    result["calendar_binding"] = {
        "state": "hash-bound-source-audit",
        "audit_sha256": calendar_binding.get("audit_sha256"),
        "receipt_sha256": calendar_binding.get("receipt_sha256"),
        "executable_sha256": calendar_binding.get("executable_sha256"),
        "runtime_validation_pending": calendar_binding.get("runtime_validation_pending"),
    }
    package = result.get("package")
    if not isinstance(package, Mapping) or not isinstance(package.get("sha256"), str):
        return
    candidates = _canonical_workspace_candidates(
        root,
        season,
        draft_sha256=package["sha256"],
        source_audit_sha256=source_audit["sha256"],
    )
    if candidates:
        result["canonical_workspace_candidates"] = {
            "state": "verified-ingress-only-not-release",
            "count": len(candidates),
            "release_eligible": False,
            "candidates": candidates,
        }


def package_status(root: Path, season: str) -> dict[str, Any]:
    """Locate a canonical package first, otherwise the current draft package."""

    canonical = root / "seasons" / season / "season-package.json"
    if canonical.is_file():
        package_path, state = canonical, "canonical-package"
    else:
        frozen = _frozen_baseline_draft(root, season)
        if frozen is not None:
            package_path, baseline_index_path, baseline_entry = frozen
            document = _read_json(package_path)
            result: dict[str, Any] = {
                "state": "frozen-provisional-base",
                "package": _hash_record(root, package_path),
                "package_id": document.get("package_id") if document is not None else None,
                "schema_version": document.get("schema_version") if document is not None else None,
                "migration_status": (
                    (document.get("migration") or {}).get("status")
                    if isinstance(document, Mapping) and isinstance(document.get("migration"), Mapping)
                    else None
                ),
                "baseline": {
                    "state": "hash-verified-frozen-provisional-base",
                    "index": _hash_record(root, baseline_index_path),
                    "calendar_binding_audit": baseline_entry.get("calendar_binding_audit"),
                    "calendar_receipt_sha256": baseline_entry.get("calendar_receipt_sha256"),
                    "calendar_executable_sha256": baseline_entry.get("calendar_executable_sha256"),
                },
                "release_eligible": False,
                "hard_blocker_count": None,
            }
            calendar_audit = baseline_entry.get("calendar_binding_audit")
            calendar_audit_sha256 = (
                calendar_audit.get("sha256") if isinstance(calendar_audit, Mapping) else None
            )
            audits = _matching_source_build_audits(
                root,
                season,
                package_sha256=result["package"]["sha256"],
                calendar_audit_sha256=calendar_audit_sha256,
            )
            if audits:
                _package, audit_path, audit = max(audits, key=lambda row: row[1].stat().st_mtime_ns)
                _add_current_source_audit(root, season, result, audit_path, audit)
            return result
        bound = _calendar_bound_source_draft(root, season)
        if bound is not None:
            package_path, bound_audit_path, bound_audit = bound
            state = "calendar-bound-source-draft"
        else:
            package_path = _newest(
                (root / ".local/season-authoring-final-shards-v1").glob(f"*/{season}/draft-season-package.json")
            )
            state = "draft-package" if package_path else "missing"
    if package_path is None:
        return {"state": state}

    document = _read_json(package_path)
    result: dict[str, Any] = {
        "state": state,
        "package": _hash_record(root, package_path),
    }
    if document is not None:
        result.update({
            "package_id": document.get("package_id"),
            "schema_version": document.get("schema_version"),
            "migration_status": (document.get("migration") or {}).get("status")
            if isinstance(document.get("migration"), Mapping) else None,
        })

    audit_path = (
        bound_audit_path if state == "calendar-bound-source-draft"
        else root / ".local/transfermarkt-opening-plans-current-v1" / season / "preallocation-package-audit.json"
    )
    if audit_path.is_file():
        audit = bound_audit if state == "calendar-bound-source-draft" else (_read_json(audit_path) or {})
        if state == "calendar-bound-source-draft":
            _add_current_source_audit(root, season, result, audit_path, audit)
        else:
            blockers = audit.get("hard_blockers")
            result["draft_audit"] = _hash_record(root, audit_path)
            result["release_eligible"] = audit.get("release_eligible") is True
            result["hard_blocker_count"] = len(blockers) if isinstance(blockers, list) else None
    return result


def _static_ingress_candidates(
    root: Path, season: str, *, input_package_sha256: str | None,
) -> list[dict[str, Any]]:
    """Return only complete static-ingress evidence bound to the current draft.

    Static ingress intentionally produces a reconciled derivative of a strict
    source draft.  It is useful evidence that the database writer and
    fixed-tail audit passed, but it is not a canonical package or release.
    Every receipt edge, including the three materialised database files, is
    verified here so an old or later-mutated ingress tree cannot advance the
    operations surface.
    """

    if not isinstance(input_package_sha256, str) or SHA256_RE.fullmatch(input_package_sha256) is None:
        return []

    receipt_paths = [
        *sorted((root / ".local/season-static-ingress-v1").glob("*/static-ingress-receipt.json")),
        *sorted((root / ".local/season-static-ingress-batch-v1").glob("*/*/static-ingress-receipt.json")),
        *sorted((root / ".local/season-static-qualification-v1").glob("*/static-ingress-receipt.json")),
    ]
    expected_label = season.replace("-", "/", 1)
    candidates: list[dict[str, Any]] = []
    for receipt_path in receipt_paths:
        receipt = _read_json(receipt_path)
        if receipt is None:
            continue
        receipt_season = receipt.get("season")
        inputs = receipt.get("input")
        outputs = receipt.get("outputs")
        if (
            receipt.get("schema_version") != STATIC_INGRESS_SCHEMA
            or receipt.get("state") != STATIC_INGRESS_STATE
            or receipt.get("release_eligible") is not False
            or not isinstance(receipt_season, Mapping)
            or receipt_season.get("label") != expected_label
            or not isinstance(inputs, Mapping)
            or not isinstance(outputs, Mapping)
        ):
            continue

        receipt_input_sha256 = inputs.get("package_sha256")
        preparation: dict[str, Any] | None = None
        package_binding = "current-package-bound"
        canonical_repair_chain: dict[str, Any] | None = None
        if (
            receipt_input_sha256 != input_package_sha256
            and outputs.get("package_sha256") == input_package_sha256
            and receipt_path.parent.parent.name == "season-static-qualification-v1"
        ):
            stage_specs = (
                ("source-write-policy-lift", "source-write-policy-lift-audit.json", "pm99-mode1-source-write-policy-lift-v1"),
                ("display-alias-repair", "display-alias-repair-audit.json", "pm99-season-package-display-alias-repair-v1"),
                ("mode1-roster-reconciliation", "mode1-roster-reconciliation-audit.json", "pm99-mode1-roster-base-reconciliation-batch-v1"),
            )
            prior_sha256 = receipt_input_sha256
            chain_records: list[dict[str, Any]] = []
            chain_valid = True
            for stage_name, filename, schema in stage_specs:
                stage_path = receipt_path.parent / filename
                stage = _read_json(stage_path)
                stage_input = stage.get("input") if isinstance(stage, Mapping) else None
                stage_output = stage.get("output") if isinstance(stage, Mapping) else None
                if (
                    stage is None or stage.get("schema_version") != schema
                    or not isinstance(stage_input, Mapping) or not isinstance(stage_output, Mapping)
                    or stage_input.get("package_sha256") != prior_sha256
                    or stage_input.get("verified_base_sha256") != inputs.get("verified_base_sha256")
                    or not isinstance(stage_output.get("package_sha256"), str)
                ):
                    chain_valid = False
                    break
                stage_package = Path(str(stage_output.get("package_path", "")))
                if not stage_package.is_absolute():
                    stage_package = receipt_path.parent / stage_package
                try:
                    stage_package.resolve().relative_to(receipt_path.parent.resolve())
                except ValueError:
                    chain_valid = False
                    break
                if _hash_record(root, stage_package).get("sha256") != stage_output["package_sha256"]:
                    chain_valid = False
                    break
                prior_sha256 = stage_output["package_sha256"]
                chain_records.append({"name": stage_name, "audit": _hash_record(root, stage_path)})
            if chain_valid and prior_sha256 == input_package_sha256:
                package_binding = "canonical-package-bound-static-repair-chain"
                canonical_repair_chain = {
                    "state": "verified-canonical-package-repair-chain", "stages": chain_records,
                }
            else:
                continue
        elif receipt_input_sha256 != input_package_sha256:
            preparation_root = root / ".local/season-provisional-compile-packages-v1"
            preparation_candidates: list[tuple[int, str, Path, Path, dict[str, Any]]] = []
            for preparation_path in sorted(
                preparation_root.glob(f"{season}*/provisional-preparation-audit.json")
            ):
                if not (
                    preparation_path.parent.name == season
                    or preparation_path.parent.name.startswith(f"{season}-")
                ):
                    continue
                prepared_package_path = preparation_path.parent / "draft-season-package.json"
                preparation_document = _read_json(preparation_path)
                preparation_input = preparation_document.get("input") if preparation_document else None
                preparation_output = preparation_document.get("output") if preparation_document else None
                preparation_season = preparation_document.get("season") if preparation_document else None
                duplicate_ownership = (
                    preparation_document.get("duplicate_ownership") if preparation_document else None
                )
                outfield_handling = (
                    preparation_document.get("outfield_handling") if preparation_document else None
                )
                state = preparation_document.get("state") if preparation_document else None
                if (
                    preparation_document is None
                    or preparation_document.get("schema_version")
                    != "pm99-provisional-compile-package-preparation-v1"
                    or state not in {
                        "strict-package-ready-provisional",
                        "strict-package-ready-provisional-editorial-gaps-retained",
                    }
                    or preparation_document.get("release_eligible") is not False
                    or not isinstance(preparation_input, Mapping)
                    or not isinstance(preparation_output, Mapping)
                    or preparation_output.get("package_sha256") != receipt_input_sha256
                    or not isinstance(preparation_season, Mapping)
                    or preparation_season.get("label") != expected_label
                    or not prepared_package_path.is_file()
                    or sha256_file(prepared_package_path) != receipt_input_sha256
                    or not isinstance(duplicate_ownership, Mapping)
                    or not isinstance(outfield_handling, Mapping)
                    or not isinstance(duplicate_ownership.get("editorial_review_required_count"), int)
                ):
                    continue
                preparation_candidates.append((
                    duplicate_ownership["editorial_review_required_count"],
                    str(preparation_path), preparation_path, prepared_package_path,
                    preparation_document,
                ))
            if not preparation_candidates:
                continue
            _, _, preparation_path, prepared_package_path, preparation_document = min(
                preparation_candidates
            )
            preparation_input = preparation_document["input"]
            duplicate_ownership = preparation_document["duplicate_ownership"]
            outfield_handling = preparation_document["outfield_handling"]
            package_binding = "provisional-derivative-unbound-current-package"
            preparation = {
                "audit": _hash_record(root, preparation_path),
                "prepared_package": _hash_record(root, prepared_package_path),
                "source_package_sha256": preparation_input.get("package_sha256"),
                "state": preparation_document.get("state"),
                "editorial_ownership_gap_count": duplicate_ownership.get(
                    "editorial_review_required_count"
                ),
                "source_evidence_resolved_count": duplicate_ownership.get(
                    "source_evidence_resolved_count", 0
                ),
                "outfield_handling_correction_count": outfield_handling.get(
                    "changed_player_count"
                ),
            }

        package_path = _safe_child_path(receipt_path.parent, outputs.get("package_path"))
        compiler_path = _safe_child_path(receipt_path.parent, outputs.get("compiler_receipt"))
        audit_path = _safe_child_path(receipt_path.parent, outputs.get("clean_static_audit"))
        game_tree = _safe_child_path(receipt_path.parent, outputs.get("game_tree"))
        if (
            package_path is None or compiler_path is None or audit_path is None or game_tree is None
            or not game_tree.is_dir() or game_tree.is_symlink()
            or not isinstance(outputs.get("package_sha256"), str)
            or not isinstance(outputs.get("compiler_receipt_sha256"), str)
            or not isinstance(outputs.get("clean_static_audit_sha256"), str)
        ):
            continue
        package_record = _hash_record(root, package_path)
        compiler_record = _hash_record(root, compiler_path)
        audit_record = _hash_record(root, audit_path)
        if (
            package_record.get("sha256") != outputs["package_sha256"]
            or compiler_record.get("sha256") != outputs["compiler_receipt_sha256"]
            or audit_record.get("sha256") != outputs["clean_static_audit_sha256"]
        ):
            continue

        compiler = _read_json(compiler_path)
        audit = _read_json(audit_path)
        if (
            compiler is None or audit is None
            or compiler.get("schema") != "pm99-season-package-compiler-receipt-v1"
            or compiler.get("season_package_sha256") != package_record.get("sha256")
            or compiler.get("source_season_package_sha256") != package_record.get("sha256")
            or audit.get("schema_version") != "pm99-season-clean-base-audit-v1"
            or audit.get("result") != "pass"
            or audit.get("package_canonical_sha256") != package_record.get("sha256")
            or audit.get("append_or_recycle_count") != 0
            or audit.get("fixed_roster_tail_mismatch_count") != 0
            or not isinstance(audit.get("fixed_roster_tail_count"), int)
            or audit["fixed_roster_tail_count"] < 1
        ):
            continue

        compiler_outputs = compiler.get("outputs")
        audit_outputs = audit.get("output_database_sha256")
        if not isinstance(compiler_outputs, list) or not isinstance(audit_outputs, Mapping):
            continue
        output_entries: dict[str, Mapping[str, Any]] = {}
        for entry in compiler_outputs:
            if not isinstance(entry, Mapping):
                continue
            path = entry.get("path")
            sha256 = entry.get("sha256")
            if isinstance(path, str) and isinstance(sha256, str) and SHA256_RE.fullmatch(sha256):
                output_entries[path] = entry
        if set(output_entries) != STATIC_INGRESS_DATABASE_FILES or set(audit_outputs) != STATIC_INGRESS_DATABASE_FILES:
            continue
        database_files: list[dict[str, Any]] = []
        valid_files = True
        for relative in sorted(STATIC_INGRESS_DATABASE_FILES):
            path = _safe_child_path(game_tree, relative)
            entry = output_entries[relative]
            record = _hash_record(root, path) if path is not None else {"exists": False}
            if record.get("sha256") != entry["sha256"] or audit_outputs.get(relative) != entry["sha256"]:
                valid_files = False
                break
            database_files.append(record)
        if not valid_files:
            continue

        remaining_gates = receipt.get("remaining_release_gates")
        calendar_path = game_tree / "MANAGPRE.EXE"
        expected_calendar_path = root / ".local/calendar-v1" / season / "MANAGPRE.EXE"
        calendar_record = _hash_record(root, calendar_path)
        expected_calendar_record = _hash_record(root, expected_calendar_path)
        calendar_record["state"] = (
            "target-calendar-bound"
            if calendar_record.get("sha256") == expected_calendar_record.get("sha256")
            and calendar_record.get("sha256") is not None
            else "target-calendar-missing-or-mismatched"
        )
        calendar_record["expected"] = expected_calendar_record
        candidate = {
            "path": _relative(root, receipt_path.parent),
            "receipt": _hash_record(root, receipt_path),
            "input_package_sha256": input_package_sha256,
            "package_binding": package_binding,
            "reconciled_package": package_record,
            "compiler_receipt": compiler_record,
            "audit": audit_record,
            "database_files": database_files,
            "calendar": calendar_record,
            "remaining_release_gates": remaining_gates if isinstance(remaining_gates, list) else [],
        }
        if preparation is not None:
            candidate["provisional_preparation"] = preparation
        if canonical_repair_chain is not None:
            candidate["canonical_repair_chain"] = canonical_repair_chain
        candidates.append(candidate)
    return sorted(candidates, key=lambda candidate: candidate["receipt"]["path"])


def _static_ingress_preflight_candidates(
    root: Path, season: str, *, input_package_sha256: str | None,
) -> list[dict[str, Any]]:
    """Return hash-verified safe source repairs stopped before static compilation.

    A blocked ingress is useful operational evidence only when the immutable
    draft hash, source-only reconciliation audit, and repaired derivative all
    still agree.  It must never be mistaken for a compiler or runtime result.
    """

    if not isinstance(input_package_sha256, str) or SHA256_RE.fullmatch(input_package_sha256) is None:
        return []

    expected_label = season.replace("-", "/", 1)
    candidates: list[dict[str, Any]] = []
    for receipt_path in sorted(
        (root / ".local/season-static-ingress-v1").glob("*/static-ingress-preflight-blocked.json")
    ):
        receipt = _read_json(receipt_path)
        if receipt is None:
            continue
        receipt_season = receipt.get("season")
        inputs = receipt.get("input")
        stages = receipt.get("completed_source_only_stages")
        error = receipt.get("remaining_strict_validation_error")
        if (
            receipt.get("schema_version") != STATIC_INGRESS_PREFLIGHT_SCHEMA
            or receipt.get("state") != STATIC_INGRESS_PREFLIGHT_STATE
            or receipt.get("release_eligible") is not False
            or not isinstance(receipt_season, Mapping)
            or receipt_season.get("label") != expected_label
            or not isinstance(inputs, Mapping)
            or inputs.get("package_sha256") != input_package_sha256
            or not isinstance(stages, list)
            or not isinstance(error, str)
            or not error.strip()
        ):
            continue
        stage = next(
            (
                row for row in stages
                if isinstance(row, Mapping) and row.get("name") == "stale-source-candidate-reconciliation"
            ),
            None,
        )
        if not isinstance(stage, Mapping):
            continue
        audit_path = _safe_child_path(receipt_path.parent, stage.get("audit"))
        package_path = _safe_child_path(receipt_path.parent, stage.get("package"))
        repaired_pair_count = stage.get("repaired_pair_count")
        if (
            audit_path is None or package_path is None
            or not isinstance(repaired_pair_count, int) or isinstance(repaired_pair_count, bool)
            or repaired_pair_count < 1
        ):
            continue
        audit_record = _hash_record(root, audit_path)
        package_record = _hash_record(root, package_path)
        audit = _read_json(audit_path)
        if audit is None:
            continue
        audit_season = audit.get("season")
        audit_input = audit.get("input")
        audit_output = audit.get("output")
        reconciliation = audit.get("reconciliation")
        if (
            audit.get("schema_version") != STALE_CANDIDATE_SCHEMA
            or audit.get("state") != STALE_CANDIDATE_STATE
            or audit.get("release_eligible") is not False
            or not isinstance(audit_season, Mapping)
            or audit_season.get("label") != expected_label
            or not isinstance(audit_input, Mapping)
            or audit_input.get("package_sha256") != input_package_sha256
            or not isinstance(audit_output, Mapping)
            or audit_output.get("package_sha256") != package_record.get("sha256")
            or not isinstance(reconciliation, Mapping)
            or reconciliation.get("policy") != STALE_CANDIDATE_POLICY
            or reconciliation.get("repaired_pair_count") != repaired_pair_count
            or not isinstance(reconciliation.get("repaired"), list)
            or len(reconciliation["repaired"]) != repaired_pair_count
        ):
            continue
        remaining_groups = reconciliation.get("remaining_current_source_duplicate_group_count")
        if (
            not isinstance(remaining_groups, int)
            or isinstance(remaining_groups, bool)
            or remaining_groups < 1
        ):
            continue
        candidates.append({
            "path": _relative(root, receipt_path.parent),
            "receipt": _hash_record(root, receipt_path),
            "input_package_sha256": input_package_sha256,
            "reconciled_package": package_record,
            "source_reconciliation_audit": audit_record,
            "repaired_pair_count": repaired_pair_count,
            "remaining_current_source_duplicate_group_count": remaining_groups,
        })
    return sorted(candidates, key=lambda candidate: candidate["receipt"]["path"])


def _canonical_document_descriptor(path: Path) -> tuple[dict[str, Any], str] | None:
    """Return the V2 document descriptor and its file SHA-256 when canonical."""

    parsed = _read_canonical_json(path)
    if parsed is None:
        return None
    document, semantic_sha256 = parsed
    if not isinstance(document, Mapping):
        return None
    file_sha256 = sha256_file(path)
    return {
        "id": "season-package",
        "canonical_sha256": semantic_sha256,
        "canonical_size": len(_canonical_json_bytes(document)),
        "schema": document.get("schema"),
    }, file_sha256


def _inventory_summary(value: Any) -> dict[str, Any] | None:
    """Return the three manifest inventory fields only when they are usable."""

    if not isinstance(value, Mapping):
        return None
    fingerprint = value.get("files_fingerprint")
    file_count = value.get("file_count")
    total_bytes = value.get("total_bytes")
    if (
        not isinstance(fingerprint, str) or SHA256_RE.fullmatch(fingerprint) is None
        or not isinstance(file_count, int) or isinstance(file_count, bool) or file_count < 0
        or not isinstance(total_bytes, int) or isinstance(total_bytes, bool) or total_bytes < 0
    ):
        return None
    return {
        "files_fingerprint": fingerprint,
        "file_count": file_count,
        "total_bytes": total_bytes,
    }


def _current_candidate_output(
    root: Path, candidate_root: Path, outputs: Mapping[str, Any], key: str,
) -> tuple[Path, dict[str, Any]] | None:
    """Resolve one promotion output only when its declared file hash still holds."""

    declared = outputs.get(key)
    if not isinstance(declared, Mapping):
        return None
    relative = declared.get("relative_path")
    expected = declared.get("sha256")
    path = _safe_child_path(candidate_root, relative)
    if path is None or not isinstance(expected, str) or SHA256_RE.fullmatch(expected) is None:
        return None
    record = _hash_record(root, path)
    if record.get("sha256") != expected:
        return None
    return path, record


def _database_output_hashes(plan: Mapping[str, Any]) -> dict[str, str] | None:
    """Read the exact database output hashes declared by the V2 compiler stage."""

    stages = plan.get("stages")
    if not isinstance(stages, list):
        return None
    stage = next(
        (row for row in stages if isinstance(row, Mapping) and row.get("id") == "database-compiler"),
        None,
    )
    inventory = stage.get("expected_output_inventory") if isinstance(stage, Mapping) else None
    files = inventory.get("files") if isinstance(inventory, Mapping) else None
    if not isinstance(files, list):
        return None
    hashes: dict[str, str] = {}
    for row in files:
        if not isinstance(row, Mapping):
            return None
        path, digest = row.get("path"), row.get("sha256")
        if path in STATIC_INGRESS_DATABASE_FILES and isinstance(digest, str) and SHA256_RE.fullmatch(digest):
            hashes[path] = digest
    return hashes if set(hashes) == STATIC_INGRESS_DATABASE_FILES else None


def _matching_bound_runtime(
    root: Path,
    season: str,
    *,
    attestation: Mapping[str, Any],
    release_manifest_record: Mapping[str, Any],
    output_inventory_fingerprint: str,
) -> dict[str, Any] | None:
    """Verify one registered runner receipt and its screenshot against an attestation."""

    proof = KNOWN_RUNTIME_PROOF.get(season)
    if proof is None:
        return None
    receipts = attestation.get("runtime_receipts")
    if not isinstance(receipts, list):
        return None
    expected_summary = _relative(root, root / proof["path"])
    for receipt in receipts:
        if not isinstance(receipt, Mapping):
            continue
        if receipt.get("route_kind") != proof["kind"]:
            continue
        input_binding = receipt.get("input_binding")
        result = receipt.get("result")
        summary = receipt.get("summary")
        screenshot = receipt.get("screenshot")
        if (
            not isinstance(input_binding, Mapping) or not isinstance(result, Mapping)
            or not isinstance(summary, Mapping) or not isinstance(screenshot, Mapping)
            or input_binding.get("output_inventory_fingerprint") != output_inventory_fingerprint
            or input_binding.get("release_manifest_file_sha256") != release_manifest_record.get("sha256")
            or summary.get("path") != expected_summary
        ):
            continue
        if proof["kind"] == "selector-discovery":
            completed = (
                result.get("success") is True
                and result.get("wine_debugger_detected") is False
                and result.get("division_count") == 4
                and result.get("observation_count") == 80
            )
        else:
            completed = (
                result.get("success") is True
                and result.get("crash_detected") is False
                and result.get("phase_reached") == proof.get("expected_phase", KNOWN_RUNTIME_SCREEN)
            )
        if not completed:
            continue
        summary_path = _safe_index_path(root, summary.get("path"))
        screenshot_path = _safe_index_path(root, screenshot.get("path"))
        if summary_path is None or screenshot_path is None:
            continue
        summary_record = _hash_record(root, summary_path)
        screenshot_record = _hash_record(root, screenshot_path)
        if (
            summary_record.get("sha256") != summary.get("sha256")
            or summary_record.get("bytes") != summary.get("bytes")
            or screenshot_record.get("sha256") != screenshot.get("sha256")
            or screenshot_record.get("bytes") != screenshot.get("bytes")
        ):
            continue
        return {"summary": summary_record, "screenshot": screenshot_record, "route_kind": proof["kind"]}
    return None


def _canonical_package_build_evidence(
    root: Path, season: str, package_sha256: str,
) -> dict[str, Any] | None:
    """Find one complete, hash-bound canonical-package build chain.

    A promotion candidate records package *file* hashes.  Pipeline V2 then
    records the same effective package as a canonical-content descriptor.
    This reader bridges those deliberately different hash domains, requiring
    every intermediate receipt, clean audit, registered runtime result, and
    bound screenshot to remain current. It never creates a release link.
    """

    candidate_root = root / ".local/season-canonical-candidate-v1"
    plan_root = root / ".local/season-build-plans-v2"
    required_contracts = {
        "season_package_v2_strict",
        "calendar_binding",
        "verified_base_descriptor",
        "workspace_contract",
        "workspace_prepare",
    }
    if not candidate_root.is_dir() or not plan_root.is_dir():
        return None

    for promotion_path in sorted(candidate_root.glob("*/promotion-audit.json")):
        promotion = _read_json(promotion_path)
        if promotion is None:
            continue
        candidate = promotion_path.parent
        inputs = promotion.get("input")
        outputs = promotion.get("outputs")
        contracts = promotion.get("static_contracts")
        if (
            promotion.get("schema_version") != CANONICAL_PROMOTION_SCHEMA
            or promotion.get("season") != season
            or promotion.get("state") != CANONICAL_PROMOTION_STATE
            or promotion.get("release_eligible") is not False
            or not isinstance(inputs, Mapping) or not isinstance(outputs, Mapping)
            or not isinstance(contracts, Mapping)
            or any(contracts.get(name) != "passed" for name in required_contracts)
        ):
            continue
        package_output = _current_candidate_output(root, candidate, outputs, "package")
        effective_output = _current_candidate_output(root, candidate, outputs, "prepared_effective_package")
        candidate_plan_output = _current_candidate_output(root, candidate, outputs, "build_plan_candidate")
        if package_output is None or effective_output is None or candidate_plan_output is None:
            continue
        candidate_package_path, candidate_package = package_output
        effective_path, effective_record = effective_output
        candidate_plan_path, candidate_plan_record = candidate_plan_output
        if candidate_package.get("sha256") != package_sha256:
            continue
        base_path = candidate / "verified-base.json"
        base_record = _hash_record(root, base_path)
        if base_record.get("sha256") != inputs.get("verified_base_descriptor_sha256"):
            continue
        base = _read_json(base_path)
        base_inventory = base.get("inventory") if isinstance(base, Mapping) else None
        base_fingerprint = (
            base_inventory.get("files_fingerprint") if isinstance(base_inventory, Mapping) else None
        )
        base_id = base.get("base_id") if isinstance(base, Mapping) else None
        effective_descriptor = _canonical_document_descriptor(effective_path)
        candidate_plan = _read_json(candidate_plan_path)
        if (
            effective_descriptor is None or not isinstance(candidate_plan, Mapping)
            or candidate_plan.get("schema_version") != "pm99-season-build-plan-candidate-v1"
            or candidate_plan.get("season") != season
            or candidate_plan.get("state") != "blocked-before-binary-compile"
            or candidate_plan.get("release_eligible") is not False
            or candidate_plan.get("base") != {
                "base_id": base_id, "inventory_fingerprint": base_fingerprint,
            }
        ):
            continue
        effective_document, effective_file_sha256 = effective_descriptor
        effective_plan_document = {
            key: value for key, value in effective_document.items() if key != "id"
        }
        candidate_effective = candidate_plan.get("effective_package")
        if (
            not isinstance(candidate_effective, Mapping)
            or candidate_effective.get("relative_path") != "prepared/season-package.effective.json"
            or candidate_effective.get("sha256") != effective_file_sha256
            or candidate_effective.get("size") != effective_record.get("bytes")
        ):
            continue

        for plan_path in sorted(plan_root.glob("*/build-plan.json")):
            parsed_plan = _read_canonical_json(plan_path)
            if parsed_plan is None:
                continue
            plan, plan_semantic_sha256 = parsed_plan
            if (
                not isinstance(plan, Mapping)
                or plan.get("schema") != BUILD_PLAN_SCHEMA
                or plan.get("season") != season
                or plan.get("base") != candidate_plan.get("base")
                or plan.get("season_package") != effective_plan_document
                or _inventory_summary(plan.get("expected_final_output_inventory")) is None
                or _database_output_hashes(plan) is None
            ):
                continue
            final_inventory = _inventory_summary(plan["expected_final_output_inventory"])
            database_hashes = _database_output_hashes(plan)
            if final_inventory is None or database_hashes is None:
                continue
            manifest_output = {
                "inventory_fingerprint": final_inventory["files_fingerprint"],
                "file_count": final_inventory["file_count"],
                "total_bytes": final_inventory["total_bytes"],
            }

            for metadata_path in sorted(plan_root.glob("*/build-plan-receipt.json")):
                receipt = _read_json(metadata_path)
                if receipt is None:
                    continue
                metadata = metadata_path.parent
                if (
                    receipt.get("schema") != BUILD_PLAN_RECEIPT_SCHEMA
                    or receipt.get("plan_sha256") != plan_semantic_sha256
                    or receipt.get("season") != season
                    or receipt.get("base_inventory_fingerprint") != base_fingerprint
                    or receipt.get("season_package_canonical_sha256") != effective_document["canonical_sha256"]
                    or receipt.get("final_output_inventory_fingerprint") != final_inventory["files_fingerprint"]
                ):
                    continue
                manifest_path = metadata / "season-manifest.json"
                output_inventory_path = metadata / "output.inventory.json"
                manifest_parsed = _read_canonical_json(manifest_path)
                inventory_parsed = _read_canonical_json(output_inventory_path)
                if manifest_parsed is None or inventory_parsed is None:
                    continue
                manifest, manifest_semantic_sha256 = manifest_parsed
                output_inventory, _output_inventory_semantic_sha256 = inventory_parsed
                if (
                    not isinstance(manifest, Mapping) or not isinstance(output_inventory, Mapping)
                    or manifest.get("schema") != RELEASE_MANIFEST_SCHEMA
                    or manifest.get("season") != season
                    or manifest.get("base") != {
                        "base_id": base_id,
                        "inventory_fingerprint": base_fingerprint,
                        "file_count": base_inventory.get("file_count") if isinstance(base_inventory, Mapping) else None,
                        "total_bytes": base_inventory.get("total_bytes") if isinstance(base_inventory, Mapping) else None,
                    }
                    or manifest.get("season_document") != effective_document
                    or manifest.get("output") != manifest_output
                    or _inventory_summary(output_inventory) != final_inventory
                    or receipt.get("release_manifest_sha256") != manifest_semantic_sha256
                ):
                    continue
                manifest_record = _hash_record(root, manifest_path)
                audit_path = metadata / "clean-base-audit.json"
                audit = _read_json(audit_path)
                if (
                    audit is None
                    or audit.get("schema_version") != "pm99-season-clean-base-audit-v1"
                    or audit.get("result") != "pass"
                    or audit.get("package_canonical_sha256") != effective_file_sha256
                    or audit.get("base_inventory_fingerprint") != base_fingerprint
                    or audit.get("append_or_recycle_count") != 0
                    or audit.get("fixed_roster_tail_mismatch_count") != 0
                    or audit.get("output_database_sha256") != database_hashes
                ):
                    continue
                attestation_path = metadata / "runtime-attestation.json"
                runtime_receipts_path = metadata / "runtime-receipts.json"
                attestation_parsed = _read_canonical_json(attestation_path)
                runtime_receipts = _read_json_value(runtime_receipts_path)
                if attestation_parsed is None or runtime_receipts is None:
                    continue
                attestation, _attestation_semantic_sha256 = attestation_parsed
                if (
                    not isinstance(attestation, Mapping) or not isinstance(runtime_receipts, list)
                    or attestation.get("schema") != RUNTIME_ATTESTATION_SCHEMA
                    or attestation.get("output_inventory_fingerprint") != final_inventory["files_fingerprint"]
                    or attestation.get("release_manifest_sha256") != manifest_semantic_sha256
                    or attestation.get("runtime_receipts") != runtime_receipts
                ):
                    continue
                runtime = _matching_bound_runtime(
                    root,
                    season,
                    attestation=attestation,
                    release_manifest_record=manifest_record,
                    output_inventory_fingerprint=final_inventory["files_fingerprint"],
                )
                if runtime is None:
                    continue
                return {
                    "state": "verified-canonical-package-bound-static-runtime-attested",
                    "promotion_audit": _hash_record(root, promotion_path),
                    "candidate_package": candidate_package,
                    "effective_package": effective_record,
                    "candidate_build_plan": candidate_plan_record,
                    "verified_base": base_record,
                    "build_plan": _hash_record(root, plan_path),
                    "build_plan_semantic_sha256": plan_semantic_sha256,
                    "build_plan_receipt": _hash_record(root, metadata_path),
                    "release_manifest": manifest_record,
                    "output_inventory": _hash_record(root, output_inventory_path),
                    "clean_base_audit": _hash_record(root, audit_path),
                    "runtime_attestation": _hash_record(root, attestation_path),
                    "runtime_receipts": _hash_record(root, runtime_receipts_path),
                    "runtime": runtime,
                }
    return None


def compilation_status(root: Path, season: str, package: Mapping[str, Any]) -> dict[str, Any]:
    """Recognise an audited release, never a calendar-only copy as a compile."""

    receipts = root / ".local/season-workspace-v1" / f"{season}-final-build"
    release_link = root / ".local/releases" / f"pm99-{season}-world"
    release_root = release_link.resolve() if release_link.exists() else None
    audit_path = receipts / "clean-base-audit.json"
    compiler_path = receipts / "database-compiler-receipt.json"
    effective_path = receipts / "season-package.effective.json"
    result: dict[str, Any] = {
        "state": "not-compiled",
        "release_link": _relative(root, release_link) if release_link.exists() else None,
        "release_root": _relative(root, release_root) if release_root and release_root.exists() else None,
        "audit": _hash_record(root, audit_path),
        "compiler_receipt": _hash_record(root, compiler_path),
        "effective_package": _hash_record(root, effective_path),
    }
    if not (release_root and release_root.is_dir() and audit_path.is_file() and compiler_path.is_file()):
        package_record = package.get("package")
        input_package_sha256 = package_record.get("sha256") if isinstance(package_record, Mapping) else None
        if package.get("state") == "canonical-package" and isinstance(input_package_sha256, str):
            evidence = _canonical_package_build_evidence(root, season, input_package_sha256)
            if evidence is not None:
                result.update({
                    "state": "static-audited-canonical-package",
                    "canonical_package_evidence": evidence,
                })
                return result
        candidates = _static_ingress_candidates(root, season, input_package_sha256=input_package_sha256)
        if candidates:
            canonical_candidates = [
                candidate for candidate in candidates
                if candidate.get("package_binding") == "canonical-package-bound-static-repair-chain"
            ]
            if package.get("state") == "canonical-package" and canonical_candidates:
                result.update({
                    "state": "static-audited-canonical-package",
                    "canonical_package_evidence": {
                        "state": "verified-canonical-package-bound-static-repair-chain",
                        "candidate": canonical_candidates[-1],
                    },
                })
                return result
            result.update({
                "state": "static-audited-ingress-only",
                "static_ingress": {
                    "state": "hash-verified-clean-static-ingress-not-release",
                    "count": len(candidates),
                    "candidates": candidates,
                },
            })
        else:
            preflight_candidates = _static_ingress_preflight_candidates(
                root, season, input_package_sha256=input_package_sha256,
            )
            if preflight_candidates:
                result.update({
                    "state": "static-ingress-preflight-blocked",
                    "static_ingress_preflight": {
                        "state": "hash-verified-source-repair-blocked-before-static-compilation",
                        "count": len(preflight_candidates),
                        "candidates": preflight_candidates,
                    },
                })
        return result

    audit = _read_json(audit_path) or {}
    files = [
        release_root / "MANAGPRE.EXE",
        release_root / "DBDAT/JUG98030.FDI",
        release_root / "DBDAT/EQ98030.FDI",
        release_root / "DBDAT/ENT98030.FDI",
        release_root / "DBDAT/MINIFOTO.PKF",
    ]
    result.update({
        "state": "static-audited" if audit.get("append_or_recycle_count") == 0 else "static-audit-failed",
        "append_or_recycle_count": audit.get("append_or_recycle_count"),
        "base_inventory_fingerprint": audit.get("base_inventory_fingerprint"),
        "release_files": [_hash_record(root, path) for path in files],
    })
    return result


def _attested_file(root: Path, value: Any) -> tuple[Path, dict[str, Any]] | None:
    """Resolve and re-hash one file named by a runtime attestation."""

    if not isinstance(value, Mapping):
        return None
    path = _safe_index_path(root, value.get("path"))
    if path is None:
        return None
    record = _hash_record(root, path)
    if (
        record.get("sha256") != value.get("sha256")
        or record.get("bytes") != value.get("bytes")
    ):
        return None
    return path, record


def _verify_static_ingress_runtime_binding(
    root: Path, season: str, proof: Mapping[str, Any], summary_path: Path,
) -> dict[str, Any] | None:
    """Verify one registered target-calendar runtime proof against static ingress."""

    raw_attestation_path = proof.get("attestation_path")
    raw_game_root = proof.get("static_game_root")
    if not isinstance(raw_attestation_path, Path) or not isinstance(raw_game_root, Path):
        return None
    attestation_path = (root / raw_attestation_path).resolve()
    game_root = (root / raw_game_root).resolve()
    try:
        attestation_path.relative_to(root.resolve())
        game_root.relative_to(root.resolve())
    except ValueError:
        return None
    parsed = _read_canonical_json(attestation_path)
    if parsed is None:
        return None
    attestation, _semantic_sha256 = parsed
    if (
        not isinstance(attestation, Mapping)
        or attestation.get("schema") != STATIC_INGRESS_RUNTIME_ATTESTATION_SCHEMA
        or attestation.get("season") != season
        or attestation.get("state") != "target-calendar-bound-runtime-screenshot-attested"
        or attestation.get("release_eligible") is not False
    ):
        return None

    package = attestation.get("package")
    package_file = _attested_file(root, package)
    if package_file is None or package_file[0] != (root / "seasons" / season / "season-package.json").resolve():
        return None
    package_document = _read_json(package_file[0])
    if not isinstance(package_document, Mapping):
        return None

    static = attestation.get("static")
    if not isinstance(static, Mapping):
        return None
    receipt_file = _attested_file(root, static.get("receipt"))
    compiler_file = _attested_file(root, static.get("compiler_receipt"))
    audit_file = _attested_file(root, static.get("audit"))
    if receipt_file is None or compiler_file is None or audit_file is None:
        return None
    receipt = _read_json(receipt_file[0])
    compiler = _read_json(compiler_file[0])
    audit = _read_json(audit_file[0])
    if not isinstance(receipt, Mapping) or not isinstance(compiler, Mapping) or not isinstance(audit, Mapping):
        return None
    package_sha256 = package_file[1].get("sha256")
    if (
        receipt.get("outputs", {}).get("package_sha256") != package_sha256
        or compiler.get("season_package_sha256") != package_sha256
        or audit.get("package_canonical_sha256") != package_sha256
        or audit.get("result") != "pass"
        or audit.get("base_inventory_fingerprint") != static.get("base_inventory_fingerprint")
    ):
        return None

    compiler_outputs = {
        row.get("path"): row.get("sha256")
        for row in compiler.get("outputs", [])
        if isinstance(row, Mapping)
    }
    audit_outputs = audit.get("output_database_sha256")
    database_files = static.get("database_files")
    if not isinstance(audit_outputs, Mapping) or not isinstance(database_files, list):
        return None
    for entry in database_files:
        if not isinstance(entry, Mapping):
            return None
        database_file = _attested_file(root, entry)
        if database_file is None:
            return None
        try:
            database_relative = database_file[0].relative_to(game_root).as_posix()
        except ValueError:
            return None
        if database_relative not in compiler_outputs:
            if database_relative == "DBDAT/MINIFOTO.PKF":
                continue
            return None
        if compiler_outputs[database_relative] != entry.get("sha256"):
            return None
        audit_relative = database_relative
        if audit_outputs.get(audit_relative) != entry.get("sha256"):
            return None

    calendar_file = _attested_file(root, attestation.get("calendar"))
    expected_calendar = (root / ".local" / "calendar-v1" / season / "MANAGPRE.EXE").resolve()
    if calendar_file is None or calendar_file[0] != expected_calendar:
        return None

    runtime = attestation.get("runtime")
    if not isinstance(runtime, Mapping) or runtime.get("route_kind") != proof.get("kind"):
        return None
    control_file = _attested_file(root, runtime.get("control_launch"))
    summary_file = _attested_file(root, runtime.get("summary"))
    screenshot_file = _attested_file(root, runtime.get("screenshot"))
    if (
        control_file is None or summary_file is None or screenshot_file is None
        or summary_file[0] != summary_path.resolve()
        or not screenshot_file[0].as_posix().startswith(summary_path.parent.as_posix() + "/screens/")
    ):
        return None
    control = _read_json(control_file[0])
    runtime_summary = _read_json(summary_file[0])
    if not isinstance(control, Mapping) or not isinstance(runtime_summary, Mapping):
        return None
    child_command = control.get("child_command")
    expected_game_db = _relative(root, game_root / "DBDAT")
    expected_exe = _relative(root, expected_calendar)
    if (
        control.get("run_tag") != runtime.get("run_tag")
        or not isinstance(child_command, list)
        or "--dbdat-dir" not in child_command
        or child_command[child_command.index("--dbdat-dir") + 1] != expected_game_db
        or "--exe-file" not in child_command
        or child_command[child_command.index("--exe-file") + 1] != expected_exe
        or runtime_summary.get("success") is not True
        or runtime_summary.get("crash_detected") is not False
        or runtime_summary.get("wine_debugger_detected") is not False
        or runtime_summary.get("phase_reached") != proof.get("expected_phase")
    ):
        return None
    squad_route = runtime_summary.get("route_summaries", {}).get("squad")
    if (
        not isinstance(squad_route, Mapping)
        or squad_route.get("expected_screen_matched") is not True
        or squad_route.get("route_signal_matched") is not True
    ):
        return None
    return {
        "attestation": _hash_record(root, attestation_path),
        "screenshot": screenshot_file[1],
        "calendar": calendar_file[1],
    }


def runtime_status(root: Path, season: str) -> dict[str, Any]:
    """Accept only the deliberately registered, finished release route."""

    proof = KNOWN_RUNTIME_PROOF.get(season)
    if proof is None:
        return {"state": "no-attested-runtime-proof", "screenshots": {"state": "missing", "count": 0}}
    summary_path = root / proof["path"]
    summary = _read_json(summary_path)
    if summary is None:
        return {"state": "runtime-proof-missing", "summary": _hash_record(root, summary_path), "screenshots": {"state": "missing", "count": 0}}
    runtime_binding = None
    if proof.get("attestation_path") is not None:
        runtime_binding = _verify_static_ingress_runtime_binding(
            root, season, proof, summary_path,
        )
        if runtime_binding is None:
            return {
                "state": "runtime-proof-unbound-or-invalid",
                "summary": _hash_record(root, summary_path),
                "screenshots": {"state": "missing", "count": 0},
            }
    screen_paths = sorted(path for path in (summary_path.parent / "screens").glob("*") if path.is_file())
    if proof["kind"] == "selector-discovery":
        completed = (
            summary.get("success") is True
            and summary.get("wine_debugger_detected") is False
            and summary.get("division_count") == 4
            and summary.get("observation_count") == 80
        )
    else:
        completed = (
            summary.get("success") is True
            and summary.get("crash_detected") is False
            and summary.get("phase_reached") == proof.get("expected_phase", KNOWN_RUNTIME_SCREEN)
        )
    screenshot_records = (
        [runtime_binding["screenshot"]]
        if runtime_binding is not None else [_hash_record(root, path) for path in screen_paths]
    )
    result = {
        "state": "runtime-passed" if completed else "runtime-failed-or-incomplete",
        "route_kind": proof["kind"],
        "summary": _hash_record(root, summary_path),
        "phase_reached": summary.get("phase_reached"),
        "success": summary.get("success"),
        "crash_detected": summary.get("crash_detected"),
        "screenshots": {
            "state": "present" if screenshot_records else "missing",
            "count": len(screenshot_records),
            "sample": screenshot_records[-1] if screenshot_records else None,
            "artifacts": screenshot_records,
        },
    }
    if runtime_binding is not None:
        result["binding"] = runtime_binding
    return result


def _directory_size(path: Path) -> tuple[int, int] | None:
    if not path.is_dir():
        return None
    total, files = 0, 0
    for current, _dirs, names in os.walk(path):
        for name in names:
            candidate = Path(current) / name
            try:
                total += candidate.stat().st_size
                files += 1
            except OSError:
                continue
    return total, files


def _running_bentley_rsync() -> list[dict[str, Any]]:
    completed = subprocess.run(
        ["ps", "-eo", "pid=,etimes=,args="], text=True, capture_output=True, check=False,
    )
    found: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        if str(BENTLEY_SOURCE) not in line or BENTLEY_REMOTE not in line or "rsync" not in line:
            continue
        fields = line.strip().split(maxsplit=2)
        if len(fields) == 3 and fields[0].isdigit() and fields[1].isdigit():
            found.append({"pid": int(fields[0]), "elapsed_seconds": int(fields[1]), "command": fields[2]})
    return found


def _remote_archive_status(host: str, timeout_seconds: int) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", host):
        raise StatusError(f"unsafe archive host {host!r}")
    command = (
        "target='/srv/hdd/pm99-archive/backups/bentley-sd-20260902'; "
        "if test -d \"$target\"; then "
        "find \"$target\" -type f -printf '%s\\n' | awk '{n += 1; b += $1} END {printf \"files=%d\\nbytes=%d\\n\", n, b}'; "
        "else printf 'files=0\\nbytes=0\\n'; fi; "
        "df -B1 /srv/hdd | awk 'NR == 2 {printf \"free_bytes=%s\\n\", $4}'; "
        f"for marker in TRANSFER_COMPLETE VERIFIED VERIFY_FAILED; do if test -f '{BENTLEY_RECEIPTS}/'\"$marker\"; then printf '%s=true\\n' \"$marker\"; else printf '%s=false\\n' \"$marker\"; fi; done"
    )
    try:
        completed = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={timeout_seconds}", host, command],
            text=True,
            capture_output=True,
            timeout=timeout_seconds + 2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"state": "unreachable", "error": str(error)}
    if completed.returncode != 0:
        return {"state": "unreachable", "error": completed.stderr.strip() or f"ssh exit {completed.returncode}"}
    values: dict[str, Any] = {}
    for line in completed.stdout.splitlines():
        key, separator, value = line.partition("=")
        if not separator:
            continue
        if value.isdigit():
            values[key] = int(value)
        elif value in {"true", "false"}:
            values[key] = value == "true"
    return {"state": "reachable", **values}


def archive_status(*, remote_host: str | None, remote_timeout_seconds: int) -> dict[str, Any]:
    """Show copy/verification facts, never infer a safe local deletion."""

    source_size = _directory_size(BENTLEY_SOURCE)
    local: dict[str, Any] = {
        "path": str(BENTLEY_SOURCE),
        "exists": source_size is not None,
    }
    if source_size is not None:
        local.update({"bytes": source_size[0], "files": source_size[1]})
    running = _running_bentley_rsync()
    result: dict[str, Any] = {
        "bentley_sd": {
            "source": local,
            "remote_path": BENTLEY_REMOTE,
            "rsync": {"state": "running" if running else "not-observed", "processes": running},
            "verification": {
                "state": "pending",
                "rule": "Do not delete the local directory until a complete checksum comparison has passed.",
            },
        },
    }
    if remote_host is not None:
        remote = _remote_archive_status(remote_host, remote_timeout_seconds)
        result["remote"] = remote
        if remote.get("state") == "reachable":
            verification = result["bentley_sd"]["verification"]
            if remote.get("VERIFIED"):
                verification["state"] = "verified-local-removed" if not local["exists"] else "verified-local-retained"
            elif remote.get("VERIFY_FAILED"):
                verification["state"] = "failed"
            elif remote.get("TRANSFER_COMPLETE"):
                verification["state"] = "awaiting-checksum"
    else:
        result["remote"] = {"state": "not-queried"}
    return result


def delivery_status(source: Mapping[str, Any], package: Mapping[str, Any], compilation: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the public labels, keeping every non-release state conservative."""

    runtime_ok = runtime.get("state") == "runtime-passed"
    screenshots = runtime.get("screenshots")
    screenshot_ok = isinstance(screenshots, Mapping) and screenshots.get("state") == "present"
    static_ok = compilation.get("state") in {
        "static-audited", "static-audited-canonical-package",
    }
    static_ingress_only = compilation.get("state") == "static-audited-ingress-only"
    if static_ok and runtime_ok and screenshot_ok:
        return {"classification": "playable-known-good", "gates_missing": []}

    missing: list[str] = []
    if source.get("state") not in {"bound", "season-source-files-only"}:
        missing.append("hash-bound source intake")
    if package.get("state") != "canonical-package":
        missing.append("canonical release package (draft packages are not releases)")
    if not static_ok:
        missing.append(
            "canonical package-bound clean static compile/audit"
            if static_ingress_only else "clean static compile/audit"
        )
    if not runtime_ok:
        missing.append("successful runtime route")
    if not screenshot_ok:
        missing.append("runtime screenshot")
    return {"classification": "provisional-not-playable", "gates_missing": missing}


def build_report(root: Path, *, remote_host: str | None = None, remote_timeout_seconds: int = 5) -> dict[str, Any]:
    root = root.resolve()
    season_root = root / "seasons"
    seasons = _frozen_baseline_seasons(root)
    if season_root.is_dir():
        seasons.update(path.name for path in season_root.iterdir() if path.is_dir() and SEASON_RE.fullmatch(path.name))
    seasons = sorted(seasons)
    rows: list[dict[str, Any]] = []
    for season in seasons:
        source = source_status(root, season)
        package = package_status(root, season)
        compilation = compilation_status(root, season, package)
        runtime = runtime_status(root, season)
        rows.append({
            "season": season,
            "programme_target": TARGET_START <= season <= TARGET_END,
            "source": source,
            "package": package,
            "compilation": compilation,
            "runtime": runtime,
            "delivery": delivery_status(source, package, compilation, runtime),
        })
    playable = [row["season"] for row in rows if row["delivery"]["classification"] == "playable-known-good"]
    targets = [row for row in rows if row["programme_target"]]
    normalized_calendar_bound = 0
    for row in targets:
        ingress = row["compilation"].get("static_ingress")
        candidates = ingress.get("candidates", []) if isinstance(ingress, Mapping) else []
        if any(
            isinstance(candidate, Mapping)
            and isinstance(candidate.get("provisional_preparation"), Mapping)
            and isinstance(candidate.get("calendar"), Mapping)
            and candidate["calendar"].get("state") == "target-calendar-bound"
            for candidate in candidates
        ):
            normalized_calendar_bound += 1
    return {
        "schema_version": SCHEMA,
        "generated_at": dt.datetime.now(tz=dt.timezone.utc).isoformat(timespec="seconds"),
        "repository": str(root),
        "summary": {
            "seasons_observed": len(rows),
            "programme_target_seasons": len(targets),
            "playable_known_good": playable,
            "playable_target_season_count": sum(
                row["season"] != "2015-16" and row["delivery"]["classification"] == "playable-known-good"
                for row in targets
            ),
            "normalized_static_target_calendar_bound_count": normalized_calendar_bound,
            "provisional_or_incomplete_count": sum(
                row["delivery"]["classification"] != "playable-known-good" for row in rows
            ),
        },
        "playable_gate": {
            "required": [
                "clean static compile/audit",
                "successful runtime route",
                "at least one screenshot produced by that route",
            ],
            "not_sufficient": [
                "source intake", "draft package", "calendar receipt", "unbound screenshot",
            ],
        },
        "archive": archive_status(remote_host=remote_host, remote_timeout_seconds=remote_timeout_seconds),
        "seasons": rows,
    }


def _short(value: Any) -> str:
    return value[:12] if isinstance(value, str) and len(value) > 12 else (value or "—")


def render_markdown(report: Mapping[str, Any]) -> str:
    """Make a compact human report; the companion JSON retains every full hash."""

    summary = report["summary"]
    archive = report["archive"]
    lines = [
        "# PM99 season delivery status",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "This report is evidence-led: **playable** requires a clean static audit, a successful runtime route, and a screenshot from that route. Draft packages, calendar-only builds, and unbound screenshots remain **provisional**.",
        "",
        f"Observed `{summary['seasons_observed']}` season directories. Proven playable seasons: `{', '.join(summary['playable_known_good']) or 'none'}`. Proven target-season playable seasons other than the 2015/16 baseline: `{summary['playable_target_season_count']}`. Normalized provisional static candidates with target calendars: `{summary['normalized_static_target_calendar_bound_count']}`.",
        "",
        "## Per-season gates",
        "",
        "| Season | Source | Package | Static compile | Calendar | Ownership gaps | Runtime | Screens | Delivery |",
        "| --- | --- | --- | --- | --- | ---: | --- | ---: | --- |",
    ]
    for row in report["seasons"]:
        source = row["source"]
        package = row["package"]
        compilation = row["compilation"]
        runtime = row["runtime"]
        screenshots = runtime.get("screenshots") if isinstance(runtime, Mapping) else {}
        count = screenshots.get("count", 0) if isinstance(screenshots, Mapping) else 0
        candidates = package.get("canonical_workspace_candidates")
        candidate_note = (
            f"; verified ingress candidate ×{candidates['count']} (not release)"
            if isinstance(candidates, Mapping) else ""
        )
        ingress = compilation.get("static_ingress") if isinstance(compilation, Mapping) else None
        ingress_candidates = ingress.get("candidates", []) if isinstance(ingress, Mapping) else []
        normalized = [
            candidate for candidate in ingress_candidates
            if isinstance(candidate, Mapping)
            and isinstance(candidate.get("provisional_preparation"), Mapping)
        ]
        normalized_candidate = normalized[-1] if normalized else None
        calendar = normalized_candidate.get("calendar") if isinstance(normalized_candidate, Mapping) else None
        preparation = (
            normalized_candidate.get("provisional_preparation")
            if isinstance(normalized_candidate, Mapping) else None
        )
        calendar_state = calendar.get("state") if isinstance(calendar, Mapping) else "—"
        ownership_gaps = (
            preparation.get("editorial_ownership_gap_count")
            if isinstance(preparation, Mapping) else "—"
        )
        lines.append(
            f"| {row['season']} | {source.get('state', '—')} `{_short((source.get('pointer') or {}).get('sha256'))}` | "
            f"{package.get('state', '—')}{candidate_note} `{_short((package.get('package') or {}).get('sha256'))}` | "
            f"{compilation.get('state', '—')} | {calendar_state} | {ownership_gaps} | "
            f"{runtime.get('state', '—')} | {count} | {row['delivery']['classification']} |"
        )
    lines.extend([
        "",
        "## Archive state",
        "",
        f"Bentley SD local source: `{archive['bentley_sd']['source']['path']}`; rsync: `{archive['bentley_sd']['rsync']['state']}`; checksum verification: `{archive['bentley_sd']['verification']['state']}`.",
        "",
        "The local Bentley data must not be deleted until the watcher records a complete checksum comparison. A completed file copy or matching byte total is not that verification.",
        "",
        "## Exact evidence",
        "",
        "The companion JSON generated alongside this document contains the full SHA-256 values for every current source pointer, source/intake artifact, draft or canonical package, audit receipt, runtime summary, runtime screenshot, and installed release file. It is the machine-readable handover record; hashes abbreviated in the table are only navigation aids.",
        "",
    ])
    remote = archive.get("remote")
    if isinstance(remote, Mapping):
        if remote.get("state") == "reachable":
            lines.extend([
                f"Pi archive query: `{remote.get('files', 0)}` files / `{remote.get('bytes', 0)}` bytes at the Bentley target; `{remote.get('free_bytes', 0)}` bytes free on `/srv/hdd`.",
                "",
            ])
        else:
            lines.extend([f"Pi archive query: `{remote.get('state')}` ({remote.get('error', 'not requested')}).", ""])
    return "\n".join(lines)


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    temporary.replace(path)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="PM99RE root (default: repository containing this script)")
    parser.add_argument("--output", type=Path, help="write Markdown report atomically")
    parser.add_argument("--json-output", type=Path, help="write full JSON report atomically")
    parser.add_argument("--archive-host", default="192.168.1.133", help="Pi address; use --no-remote for a local-only read")
    parser.add_argument("--archive-timeout", type=int, default=5, help="maximum SSH connection time in seconds")
    parser.add_argument("--no-remote", action="store_true", help="do not make the read-only Pi archive query")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    report = build_report(
        args.root,
        remote_host=None if args.no_remote else args.archive_host,
        remote_timeout_seconds=args.archive_timeout,
    )
    markdown = render_markdown(report)
    if args.output:
        _atomic_write(args.output, markdown)
    else:
        print(markdown)
    if args.json_output:
        _atomic_write(args.json_output, json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
