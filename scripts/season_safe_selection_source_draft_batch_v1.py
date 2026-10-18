#!/usr/bin/env python3
"""Materialise source-only drafts from the 25 safe club-selection manifests.

This batch is deliberately one layer below a release.  For each requested
season it verifies the immutable current source pointer, applies the explicit
safe source-club selection, regenerates the selection-bound opening-squad
preallocation, and replays the source-package builder against the matching
calendar-bound template.

The operation is fail-closed and transactional at the batch-root level:

* no raw capture, current pointer, allocation, manifest, registry, template,
  calendar receipt, or existing draft is changed;
* every content-addressed input is verified before that season receives a new
  revision directory;
* a missing selection manifest or stale/missing dependency is a recorded
  ``skipped`` row, never a fallback to a different season or stale input;
* the requested output root must not already exist, and is created only after
  all per-season rows have been evaluated in a sibling staging directory; and
* it emits source drafts, audits and receipts only.  It never compiles a
  database, creates a release package, runs PM99, or calls a draft playable.

The generated selection is an auditable projection of the immutable intake.
The accompanying preallocation is regenerated from that exact projection, so
an opening-date alias cannot return as a second carrier allocation.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import materialise_opening_squad_preallocation_v1 as preallocation_v1  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_source_club_selection_v1 as selection_v1  # noqa: E402
from scripts import season_source_package_builder_v1 as source_builder_v1  # noqa: E402


SCHEMA = "pm99-season-safe-selection-source-draft-batch-v1"
SEASON_RECEIPT_SCHEMA = "pm99-season-safe-selection-source-draft-receipt-v1"
CURRENT_SCHEMA = "pm99-historical-squad-backfill-current-v1"
SEASON_ID_RE = re.compile(r"^(19|20)[0-9]{2}-[0-9]{2}$")
DEFAULT_CURRENT_ROOT = ROOT / ".local" / "season-historical-squad-backfill-v1"
DEFAULT_SELECTION_MANIFEST_ROOT = (
    ROOT / ".local" / "season-safe-source-club-selection-v1" / "20260904-r2"
)
DEFAULT_OPENING_ROOT = ROOT / ".local" / "transfermarkt-opening-plans-current-v1"
DEFAULT_TEMPLATE_ROOT = ROOT / ".local" / "season-calendar-bound-batch-v4"
DEFAULT_REGISTRY_ROOT = ROOT / "seasons"


class SourceDraftBatchError(ValueError):
    """The batch contract cannot be safely evaluated."""


def _canonical_bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_document(value: Mapping[str, Any]) -> str:
    return _sha_bytes(_canonical_bytes(dict(value)))


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _require_regular_file(path: Path, label: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise SourceDraftBatchError(f"{label} must be an ordinary file: {path}")


def _read_json(path: Path, label: str, *, canonical: bool = False) -> tuple[dict[str, Any], str]:
    _require_regular_file(path, label)
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceDraftBatchError(f"cannot read {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SourceDraftBatchError(f"{label} must be a JSON object: {path}")
    if canonical and raw != _canonical_bytes(value):
        raise SourceDraftBatchError(f"{label} must be canonical UTF-8 JSON: {path}")
    return value, _sha_bytes(raw)


def _write_new(path: Path, value: Mapping[str, Any]) -> str:
    if path.exists() or path.is_symlink():
        raise SourceDraftBatchError(f"refusing to overwrite output: {path}")
    payload = _canonical_bytes(value)
    path.write_bytes(payload)
    return _sha_bytes(payload)


def _season_label(season_id: str) -> str:
    if not SEASON_ID_RE.fullmatch(season_id):
        raise SourceDraftBatchError(f"invalid season id: {season_id!r}")
    return f"{season_id[:4]}/{season_id[5:]}"


def _within(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _current_artifact(
    *, pointer_path: Path, pointer: Mapping[str, Any], name: str, canonical: bool,
) -> tuple[Path, dict[str, Any], str]:
    artifacts = pointer.get("artifacts")
    artifact = artifacts.get(name) if isinstance(artifacts, Mapping) else None
    if not isinstance(artifact, Mapping):
        raise SourceDraftBatchError(f"current pointer lacks {name!r} artifact")
    relative = artifact.get("path")
    expected_sha256 = artifact.get("sha256")
    if not isinstance(relative, str) or not relative or not isinstance(expected_sha256, str):
        raise SourceDraftBatchError(f"current pointer {name!r} artifact is malformed")
    candidate = (pointer_path.parent / relative).resolve()
    if not _within(pointer_path.parent, candidate):
        raise SourceDraftBatchError(f"current pointer {name!r} escapes its revision root")
    value, actual_sha256 = _read_json(candidate, f"current {name} artifact", canonical=canonical)
    if actual_sha256 != expected_sha256:
        raise SourceDraftBatchError(
            f"current {name!r} artifact hash mismatch: expected {expected_sha256}, got {actual_sha256}"
        )
    return candidate, value, actual_sha256


def _require_same_season(value: Mapping[str, Any], *, season_id: str, label: str) -> None:
    expected_label = _season_label(season_id)
    season = value.get("season")
    if not isinstance(season, Mapping) or season.get("label") != expected_label:
        raise SourceDraftBatchError(f"{label} does not target {expected_label}")


def _manifest_path(selection_manifest_root: Path, season_id: str) -> Path:
    return selection_manifest_root / season_id / "selection-manifest.json"


def _revision_id(
    *, season_id: str, input_hashes: Mapping[str, str],
) -> str:
    identity = _sha_document({"season_id": season_id, "inputs": dict(sorted(input_hashes.items()))})
    return f"safe-selection-source-draft-{season_id}-{identity[:20]}"


def _blocker_counts(audit: Mapping[str, Any]) -> dict[str, int]:
    rows = audit.get("hard_blockers")
    if not isinstance(rows, list):
        raise SourceDraftBatchError("source-package build audit has malformed hard_blockers")
    counts: dict[str, int] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise SourceDraftBatchError(f"source-package build audit blocker {index} is malformed")
        code = row.get("code")
        count = row.get("count", 1)
        if not isinstance(code, str) or not code or not isinstance(count, int) or isinstance(count, bool):
            raise SourceDraftBatchError(f"source-package build audit blocker {index} is invalid")
        counts[code] = counts.get(code, 0) + count
    return dict(sorted(counts.items()))


def _skipped_receipt(
    *, season_id: str, state: str, reason: str, inputs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if state not in {"skipped-no-safe-selection-manifest", "skipped-unresolved-dependency"}:
        raise SourceDraftBatchError(f"unsupported skipped receipt state: {state}")
    return {
        "schema_version": SEASON_RECEIPT_SCHEMA,
        "season_id": season_id,
        "season_label": _season_label(season_id),
        "state": state,
        "reason": reason,
        "inputs": dict(inputs or {}),
        "outputs": {},
        "hard_blocker_counts": {},
        "release_eligible": False,
        "not_performed": [
            "release package creation",
            "database compilation",
            "PM99 runtime validation",
            "playable claim",
        ],
    }


def _load_season_inputs(
    *, season_id: str, current_root: Path, selection_manifest_root: Path,
    opening_root: Path, template_root: Path, registry_root: Path,
) -> dict[str, Any]:
    """Read and cross-check every immutable input used by a source draft."""

    pointer_path = current_root / season_id / "current.json"
    pointer, pointer_sha256 = _read_json(pointer_path, "current pointer", canonical=True)
    if pointer.get("schema_version") != CURRENT_SCHEMA or pointer.get("season") != season_id:
        raise SourceDraftBatchError("current pointer schema or season is unsupported")
    source_path, _source, source_sha256 = _current_artifact(
        pointer_path=pointer_path, pointer=pointer, name="source", canonical=True,
    )
    intake_path, intake, intake_sha256 = _current_artifact(
        pointer_path=pointer_path, pointer=pointer, name="intake", canonical=True,
    )
    allocation_path, allocation, allocation_sha256 = _current_artifact(
        pointer_path=pointer_path, pointer=pointer, name="allocation", canonical=True,
    )
    _require_same_season(intake, season_id=season_id, label="source intake")
    if intake.get("source_capture_sha256") != source_sha256:
        raise SourceDraftBatchError("source intake does not bind the current source capture")

    manifest_path = _manifest_path(selection_manifest_root, season_id)
    manifest, manifest_sha256 = _read_json(manifest_path, "safe selection manifest", canonical=True)
    if manifest.get("schema_version") != selection_v1.MANIFEST_SCHEMA:
        raise SourceDraftBatchError("safe selection manifest schema is unsupported")
    _require_same_season(manifest, season_id=season_id, label="safe selection manifest")

    registry_path = registry_root / season_id / "fixed-carrier-registry.json"
    registry, registry_sha256 = _read_json(registry_path, "fixed-carrier registry", canonical=True)
    if intake.get("registry_sha256") != _sha_document(registry):
        raise SourceDraftBatchError("source intake targets a different fixed-carrier registry")

    opening_dir = opening_root / season_id
    lineup_path = opening_dir / "opening-lineups.json"
    reconciliation_path = opening_dir / "opening-lineup-reconciliation.json"
    additions_path = opening_dir / "opening-fixture-player-additions.json"
    lineup, lineup_sha256 = _read_json(lineup_path, "opening lineup capture")
    reconciliation, reconciliation_sha256 = _read_json(
        reconciliation_path, "opening lineup reconciliation"
    )
    additions, additions_sha256 = _read_json(additions_path, "opening fixture additions")

    template_dir = template_root / season_id
    template_path = template_dir / "draft-season-package.calendar-bound.json"
    calendar_audit_path = template_dir / "calendar-binding-audit.json"
    template, template_sha256 = _read_json(template_path, "calendar-bound template", canonical=True)
    calendar_audit, calendar_audit_sha256 = _read_json(
        calendar_audit_path, "calendar binding audit", canonical=True
    )
    _require_same_season(template, season_id=season_id, label="calendar-bound template")
    _require_same_season(calendar_audit, season_id=season_id, label="calendar binding audit")
    if calendar_audit.get("output_package_sha256") != _sha_document(template):
        raise SourceDraftBatchError("calendar binding audit does not bind the calendar-bound template")

    return {
        "paths": {
            "current_pointer": pointer_path,
            "source_capture": source_path,
            "source_intake": intake_path,
            "carrier_allocation": allocation_path,
            "safe_selection_manifest": manifest_path,
            "registry": registry_path,
            "opening_lineup_capture": lineup_path,
            "opening_reconciliation": reconciliation_path,
            "opening_additions": additions_path,
            "calendar_bound_template": template_path,
            "calendar_binding_audit": calendar_audit_path,
        },
        "hashes": {
            "current_pointer_sha256": pointer_sha256,
            "source_capture_sha256": source_sha256,
            "source_intake_sha256": intake_sha256,
            "carrier_allocation_sha256": allocation_sha256,
            "safe_selection_manifest_sha256": manifest_sha256,
            "registry_sha256": registry_sha256,
            "opening_lineup_capture_sha256": lineup_sha256,
            "opening_reconciliation_sha256": reconciliation_sha256,
            "opening_additions_sha256": additions_sha256,
            "calendar_bound_template_sha256": template_sha256,
            "calendar_binding_audit_sha256": calendar_audit_sha256,
        },
        "pointer": pointer,
        "intake": intake,
        "allocation": allocation,
        "manifest": manifest,
        "registry": registry,
        "lineup": lineup,
        "reconciliation": reconciliation,
        "additions": additions,
        "template": template,
        "calendar_audit": calendar_audit,
    }


def _build_season_draft(
    *, season_id: str, inputs: Mapping[str, Any],
) -> dict[str, Any]:
    """Build one complete in-memory draft before the output root is touched."""

    intake = inputs["intake"]
    manifest = inputs["manifest"]
    selection, selection_audit = selection_v1.build_selection(
        source_intake=intake, manifest=manifest
    )
    selection_sha256 = _sha_document(selection)
    preallocation = preallocation_v1.materialise(
        source_intake=intake,
        source_intake_sha256=_sha_document(intake),
        lineup=inputs["lineup"],
        lineup_sha256=inputs["hashes"]["opening_lineup_capture_sha256"],
        reconciliation=inputs["reconciliation"],
        reconciliation_sha256=inputs["hashes"]["opening_reconciliation_sha256"],
        additions=inputs["additions"],
        additions_sha256=inputs["hashes"]["opening_additions_sha256"],
        source_club_selection=selection,
        source_club_selection_sha256=selection_sha256,
    )
    preallocation_v1.validate_selection_bound_preallocation(
        preallocation=preallocation, source_intake=intake, source_club_selection=selection,
    )
    preallocation_sha256 = _sha_document(preallocation)
    draft, build_audit = source_builder_v1.build_draft(
        template=inputs["template"],
        source_intake=intake,
        registry=inputs["registry"],
        carrier_allocation=inputs["allocation"],
        source_club_selection=selection,
        opening_squad_preallocation=preallocation,
        calendar_binding_audit=inputs["calendar_audit"],
    )
    if build_audit.get("draft_package_sha256") != _sha_document(draft):
        raise SourceDraftBatchError("source-package build audit does not bind its draft package")
    if build_audit.get("source_club_selection_sha256") != selection_sha256:
        raise SourceDraftBatchError("source-package build audit does not bind its source-club selection")
    if build_audit.get("opening_squad_preallocation_sha256") != preallocation_sha256:
        raise SourceDraftBatchError("source-package build audit does not bind its opening preallocation")

    hashes = dict(inputs["hashes"])
    hashes.update({
        "source_club_selection_sha256": selection_sha256,
        "source_club_selection_audit_sha256": _sha_document(selection_audit),
        "opening_squad_preallocation_sha256": preallocation_sha256,
        "draft_package_sha256": _sha_document(draft),
        "source_package_build_audit_sha256": _sha_document(build_audit),
    })
    return {
        "revision_id": _revision_id(season_id=season_id, input_hashes=hashes),
        "selection": selection,
        "selection_audit": selection_audit,
        "preallocation": preallocation,
        "draft": draft,
        "build_audit": build_audit,
        "hashes": hashes,
        "inputs": inputs,
    }


def _receipt_for_draft(*, season_id: str, result: Mapping[str, Any]) -> dict[str, Any]:
    build_audit = result["build_audit"]
    blocker_counts = _blocker_counts(build_audit)
    draft_hashes = result["hashes"]
    paths = result["inputs"]["paths"]
    return {
        "schema_version": SEASON_RECEIPT_SCHEMA,
        "season_id": season_id,
        "season_label": _season_label(season_id),
        "revision_id": result["revision_id"],
        "state": "source-draft-blocked-no-release" if blocker_counts else "source-draft-unreleased",
        "inputs": {
            **{
                name: {
                    "path": _relative(path),
                    "sha256": draft_hashes["%s_sha256" % name]
                    if "%s_sha256" % name in draft_hashes else None,
                }
                for name, path in paths.items()
            },
            "safe_selection_manifest": {
                "path": _relative(paths["safe_selection_manifest"]),
                "sha256": draft_hashes["safe_selection_manifest_sha256"],
            },
        },
        "outputs": {
            "source_club_selection_sha256": draft_hashes["source_club_selection_sha256"],
            "source_club_selection_audit_sha256": draft_hashes[
                "source_club_selection_audit_sha256"
            ],
            "opening_squad_preallocation_sha256": draft_hashes[
                "opening_squad_preallocation_sha256"
            ],
            "draft_package_sha256": draft_hashes["draft_package_sha256"],
            "source_package_build_audit_sha256": draft_hashes[
                "source_package_build_audit_sha256"
            ],
        },
        "hard_blocker_counts": blocker_counts,
        "release_eligible": False,
        "builder_reported_release_eligible": build_audit.get("release_eligible") is True,
        "not_performed": [
            "release package creation",
            "database compilation",
            "PM99 runtime validation",
            "playable claim",
        ],
    }


def _write_draft_result(*, root: Path, season_id: str, result: Mapping[str, Any]) -> dict[str, Any]:
    revision_root = root / season_id / "revisions" / str(result["revision_id"])
    revision_root.mkdir(parents=True, exist_ok=False)
    output_hashes = {
        "source_club_selection_sha256": _write_new(
            revision_root / "source-club-selection.json", result["selection"]
        ),
        "source_club_selection_audit_sha256": _write_new(
            revision_root / "source-club-selection-audit.json", result["selection_audit"]
        ),
        "opening_squad_preallocation_sha256": _write_new(
            revision_root / "opening-squad-preallocation.json", result["preallocation"]
        ),
        "draft_package_sha256": _write_new(
            revision_root / "draft-season-package.json", result["draft"]
        ),
        "source_package_build_audit_sha256": _write_new(
            revision_root / "source-package-build-audit.json", result["build_audit"]
        ),
    }
    receipt = _receipt_for_draft(season_id=season_id, result=result)
    if receipt["outputs"] != {
        key: output_hashes[key] for key in receipt["outputs"]
    }:
        raise SourceDraftBatchError("written source-draft outputs differ from their in-memory receipt")
    receipt_sha256 = _write_new(revision_root / "source-draft-receipt.json", receipt)
    return {
        "season_id": season_id,
        "state": receipt["state"],
        "revision_id": result["revision_id"],
        "revision_relative_path": revision_root.relative_to(root).as_posix(),
        "source_draft_receipt_sha256": receipt_sha256,
        "hard_blocker_counts": receipt["hard_blocker_counts"],
        "release_eligible": False,
    }


def _write_skipped_result(*, root: Path, receipt: Mapping[str, Any]) -> dict[str, Any]:
    season_id = str(receipt["season_id"])
    season_root = root / season_id
    season_root.mkdir(parents=True, exist_ok=False)
    receipt_sha256 = _write_new(season_root / "source-draft-receipt.json", receipt)
    return {
        "season_id": season_id,
        "state": receipt["state"],
        "reason": receipt["reason"],
        "revision_id": None,
        "revision_relative_path": None,
        "source_draft_receipt_sha256": receipt_sha256,
        "hard_blocker_counts": {},
        "release_eligible": False,
    }


def _target_seasons(*, current_root: Path, seasons: Sequence[str] | None) -> list[str]:
    if seasons:
        result = sorted(set(seasons))
    else:
        result = sorted(path.parent.name for path in current_root.glob("*/current.json"))
    if not result:
        raise SourceDraftBatchError("no target seasons selected")
    for season_id in result:
        _season_label(season_id)
    return result


def run_batch(
    *, current_root: Path, selection_manifest_root: Path, opening_root: Path,
    template_root: Path, registry_root: Path, output_root: Path,
    seasons: Sequence[str] | None = None, expected_season_count: int | None = None,
) -> dict[str, Any]:
    """Evaluate all target seasons and atomically publish one new batch root."""

    target_seasons = _target_seasons(current_root=current_root, seasons=seasons)
    if expected_season_count is not None and len(target_seasons) != expected_season_count:
        raise SourceDraftBatchError(
            f"expected {expected_season_count} target seasons, found {len(target_seasons)}"
        )
    output_root = output_root.resolve()
    if output_root.exists() or output_root.is_symlink():
        raise SourceDraftBatchError(f"refusing to overwrite batch output root: {output_root}")
    staging_root = output_root.parent / f".{output_root.name}.staging"
    if staging_root.exists() or staging_root.is_symlink():
        raise SourceDraftBatchError(
            f"refusing to reuse an existing incomplete staging root: {staging_root}"
        )
    output_root.parent.mkdir(parents=True, exist_ok=True)

    evaluated: list[tuple[str, Mapping[str, Any]]] = []
    for season_id in target_seasons:
        manifest_path = _manifest_path(selection_manifest_root, season_id)
        if not manifest_path.is_file() or manifest_path.is_symlink():
            evaluated.append(("skipped", _skipped_receipt(
                season_id=season_id,
                state="skipped-no-safe-selection-manifest",
                reason=f"safe selection manifest is absent: {_relative(manifest_path)}",
            )))
            continue
        try:
            inputs = _load_season_inputs(
                season_id=season_id,
                current_root=current_root,
                selection_manifest_root=selection_manifest_root,
                opening_root=opening_root,
                template_root=template_root,
                registry_root=registry_root,
            )
            result = _build_season_draft(season_id=season_id, inputs=inputs)
        except (
            OSError,
            SourceDraftBatchError,
            selection_v1.SourceClubSelectionError,
            preallocation_v1.PreallocationError,
            source_builder_v1.SourcePackageBuildError,
            package_v2.PackageValidationError,
        ) as exc:
            evaluated.append(("skipped", _skipped_receipt(
                season_id=season_id,
                state="skipped-unresolved-dependency",
                reason=str(exc),
                inputs={"safe_selection_manifest_path": _relative(manifest_path)},
            )))
            continue
        evaluated.append(("draft", result))

    staging_root.mkdir(parents=False, exist_ok=False)
    try:
        rows: list[dict[str, Any]] = []
        for kind, value in evaluated:
            if kind == "draft":
                rows.append(_write_draft_result(
                    root=staging_root,
                    season_id=_season_from_result(value),
                    result=value,
                ))
            else:
                rows.append(_write_skipped_result(root=staging_root, receipt=value))
        rows.sort(key=lambda row: str(row["season_id"]))
        blockers = Counter()
        for row in rows:
            blockers.update(row["hard_blocker_counts"])
        receipt = {
            "schema_version": SCHEMA,
            "policy": {
                "source_club_selection": "only explicit hash-bound safe manifests; raw intake remains immutable",
                "opening_squad": "selection-bound preallocation regenerated before carrier allocation",
                "dependency_failure": "recorded per season; no fallback or substitution",
                "output": "new immutable source-draft revisions only",
                "release": "no-release-package-compile-runtime-or-playable-claim",
            },
            "inputs": {
                "current_root": _relative(current_root),
                "selection_manifest_root": _relative(selection_manifest_root),
                "opening_root": _relative(opening_root),
                "template_root": _relative(template_root),
                "registry_root": _relative(registry_root),
            },
            "rows": rows,
            "summary": {
                "target_season_count": len(target_seasons),
                "source_draft_revision_count": sum(row["revision_id"] is not None for row in rows),
                "source_draft_blocked_count": sum(
                    row["state"] == "source-draft-blocked-no-release" for row in rows
                ),
                "source_draft_unreleased_count": sum(
                    row["state"] == "source-draft-unreleased" for row in rows
                ),
                "skipped_no_safe_selection_manifest_count": sum(
                    row["state"] == "skipped-no-safe-selection-manifest" for row in rows
                ),
                "skipped_unresolved_dependency_count": sum(
                    row["state"] == "skipped-unresolved-dependency" for row in rows
                ),
                "hard_blocker_subject_counts": dict(sorted(blockers.items())),
                "release_count": 0,
                "playable_count": 0,
            },
        }
        _write_new(staging_root / "batch-receipt.json", receipt)
        os.rename(staging_root, output_root)
    except BaseException:
        # Keep the uniquely named staging root for forensic inspection.  It is
        # deliberately never reused on a later invocation.
        raise
    return receipt


def _season_from_result(result: Mapping[str, Any]) -> str:
    """Recover the season from the source input instead of parsing a revision id."""

    season = result["inputs"]["intake"].get("season")
    if not isinstance(season, Mapping) or not isinstance(season.get("label"), str):
        raise SourceDraftBatchError("draft result has no season label")
    return season["label"].replace("/", "-")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-root", type=Path, default=DEFAULT_CURRENT_ROOT)
    parser.add_argument(
        "--selection-manifest-root", type=Path, default=DEFAULT_SELECTION_MANIFEST_ROOT,
    )
    parser.add_argument("--opening-root", type=Path, default=DEFAULT_OPENING_ROOT)
    parser.add_argument("--template-root", type=Path, default=DEFAULT_TEMPLATE_ROOT)
    parser.add_argument("--registry-root", type=Path, default=DEFAULT_REGISTRY_ROOT)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--season", action="append", dest="seasons",
        help="season id to include (repeatable); default is every current pointer",
    )
    parser.add_argument(
        "--expected-season-count", type=int,
        help="fail before writing if the selected target count differs",
    )
    args = parser.parse_args(argv)
    try:
        result = run_batch(
            current_root=args.current_root,
            selection_manifest_root=args.selection_manifest_root,
            opening_root=args.opening_root,
            template_root=args.template_root,
            registry_root=args.registry_root,
            output_root=args.output_root,
            seasons=args.seasons,
            expected_season_count=args.expected_season_count,
        )
    except (OSError, SourceDraftBatchError) as exc:
        parser.error(str(exc))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
