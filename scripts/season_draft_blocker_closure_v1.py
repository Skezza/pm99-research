#!/usr/bin/env python3
"""Replay the current 25 source drafts with authorised opening-date closures.

This is an offline draft authoring tool.  It follows each immutable
``current.json`` pointer, verifies the selected intake/allocation bytes, then
replays the source-package builder with its hash-bound opening-squad
preallocation.  It writes draft packages and their blocker audits only; it
never writes a release package, compiles a database, or labels a draft
playable.

The only identity closure delegated to the builder is a unique, earlier,
dated opening-fixture owner.  Equal-date and undated claims remain explicit
hard blockers.  Opening-XI formation and manager-source integration are owned
by later authoring layers and are therefore not claimed as closed here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_source_package_builder_v1 as builder  # noqa: E402


SCHEMA = "pm99-season-draft-blocker-closure-v1"
CURRENT_SCHEMA = "pm99-historical-squad-backfill-current-v1"


class ClosureError(ValueError):
    """A current pointer or source input is malformed or stale."""


def _read(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClosureError(f"cannot read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ClosureError(f"JSON document must be an object: {path}")
    return value


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pointer_artifact(pointer_path: Path, pointer: Mapping[str, Any], name: str) -> Path:
    artifact = (pointer.get("artifacts") or {}).get(name)
    if not isinstance(artifact, Mapping):
        raise ClosureError(f"{pointer_path}: current pointer lacks {name!r} artifact")
    relative = artifact.get("path")
    expected = artifact.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected, str):
        raise ClosureError(f"{pointer_path}: {name!r} artifact is malformed")
    path = pointer_path.parent / relative
    if not path.is_file() or _sha256_file(path) != expected:
        raise ClosureError(f"{pointer_path}: {name!r} artifact does not verify")
    return path


def _audit_counts(document: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in document.get("hard_blockers", []):
        if not isinstance(row, Mapping) or not isinstance(row.get("code"), str):
            raise ClosureError("source package audit contains a malformed hard blocker")
        count = row.get("count", 1)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ClosureError("source package audit has an invalid blocker count")
        counts[str(row["code"])] = count
    return dict(sorted(counts.items()))


def _template_for_replay(
    *, template_path: Path, calendar_binding_audit: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], str]:
    """Read and validate one ordinary or calendar-bound replay template."""

    template = _read(template_path)
    template_sha256 = builder._sha256_document(template)
    if calendar_binding_audit is None:
        package_v2.validate_package(template, strict=True)
    else:
        # A calendar-bound source draft can correctly retain unrelated strict
        # release blockers (for example an unresolved target-season person
        # collision).  It is still safe to replay only when its structural V2
        # contract validates and the supplied overlay audit binds these exact
        # template bytes.  ``build_draft`` verifies the full calendar/artifact
        # contract again for the selected season before it may close the one
        # calendar blocker.
        package_v2.validate_package(template, strict=False)
        if calendar_binding_audit.get("output_package_sha256") != template_sha256:
            raise ClosureError(
                "calendar binding audit does not hash-bind the supplied template package"
            )
    return template, template_sha256


def _calendar_bound_template(
    *, calendar_binding_root: Path, season_id: str,
) -> tuple[Path, Mapping[str, Any]]:
    """Return the exact calendar-bound draft and overlay audit for one season."""

    season_root = calendar_binding_root / season_id
    template_path = season_root / "draft-season-package.calendar-bound.json"
    audit_path = season_root / "calendar-binding-audit.json"
    if not template_path.is_file() or template_path.is_symlink():
        raise ClosureError(f"{season_id}: calendar-bound template is missing: {template_path}")
    if not audit_path.is_file() or audit_path.is_symlink():
        raise ClosureError(f"{season_id}: calendar binding audit is missing: {audit_path}")
    audit = builder._read(audit_path, "calendar binding audit")
    season = audit.get("season")
    label = season.get("label") if isinstance(season, Mapping) else None
    if label != season_id.replace("-", "/"):
        raise ClosureError(f"{season_id}: calendar binding audit has a mismatched season label")
    return template_path, audit


def replay(
    *, current_root: Path, opening_root: Path, output_root: Path,
    template_path: Path, registry_root: Path, baseline_root: Path | None = None,
    calendar_binding_audit_path: Path | None = None,
    calendar_binding_root: Path | None = None,
    seasons: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build current source drafts and return a conservative closure matrix."""

    if calendar_binding_audit_path is not None and calendar_binding_root is not None:
        raise ClosureError("use either one calendar binding audit or a per-season calendar binding root")
    if calendar_binding_root is not None and (
        not calendar_binding_root.is_dir() or calendar_binding_root.is_symlink()
    ):
        raise ClosureError(f"calendar binding root must be an ordinary directory: {calendar_binding_root}")

    calendar_binding_audit = (
        builder._read(calendar_binding_audit_path, "calendar binding audit")
        if calendar_binding_audit_path is not None else None
    )
    wanted = set(seasons or ())
    pointer_paths = sorted(current_root.glob("*/current.json"))
    if wanted:
        pointer_paths = [path for path in pointer_paths if path.parent.name in wanted]
        missing = wanted - {path.parent.name for path in pointer_paths}
        if missing:
            raise ClosureError(f"missing current pointers: {', '.join(sorted(missing))}")
    if not pointer_paths:
        raise ClosureError("no current pointers selected")
    if calendar_binding_audit is not None:
        bound_season = calendar_binding_audit.get("season")
        if not isinstance(bound_season, Mapping) or not isinstance(bound_season.get("label"), str):
            raise ClosureError("calendar binding audit has no usable season label")
        bound_season_id = bound_season["label"].replace("/", "-")
        if len(pointer_paths) != 1 or pointer_paths[0].parent.name != bound_season_id:
            raise ClosureError(
                "a calendar binding audit may replay only its one matching current season; "
                f"expected {bound_season_id}"
            )

    rows: list[dict[str, Any]] = []
    for pointer_path in pointer_paths:
        season_id = pointer_path.parent.name
        row_calendar_binding_audit = calendar_binding_audit
        row_template_path = template_path
        if calendar_binding_root is not None:
            row_template_path, row_calendar_binding_audit = _calendar_bound_template(
                calendar_binding_root=calendar_binding_root, season_id=season_id
            )
        template, template_sha256 = _template_for_replay(
            template_path=row_template_path,
            calendar_binding_audit=row_calendar_binding_audit,
        )
        pointer = _read(pointer_path)
        if pointer.get("schema_version") != CURRENT_SCHEMA or pointer.get("season") != season_id:
            raise ClosureError(f"{pointer_path}: unsupported or mismatched current pointer")
        intake_path = _pointer_artifact(pointer_path, pointer, "intake")
        allocation_path = _pointer_artifact(pointer_path, pointer, "allocation")
        intake = _read(intake_path)
        allocation = _read(allocation_path)
        registry_path = registry_root / season_id / "fixed-carrier-registry.json"
        registry = _read(registry_path)
        registry_sha256 = builder._sha256_document(registry)
        if intake.get("registry_sha256") != registry_sha256:
            raise ClosureError(f"{season_id}: current intake targets a different fixed registry at {registry_path}")
        preallocation_path = opening_root / season_id / "opening-squad-preallocation.json"
        preallocation = _read(preallocation_path)
        draft, audit = builder.build_draft(
            template=template,
            source_intake=intake,
            registry=registry,
            carrier_allocation=allocation,
            opening_squad_preallocation=preallocation,
            calendar_binding_audit=row_calendar_binding_audit,
            template_prevalidated=True,
        )
        destination = output_root / season_id
        builder._write(destination / "draft-season-package.json", draft)
        builder._write(destination / "source-package-build-audit.json", audit)
        baseline_counts: dict[str, int] | None = None
        if baseline_root is not None:
            baseline_path = baseline_root / season_id / "preallocation-package-audit.json"
            if baseline_path.is_file():
                baseline_counts = _audit_counts(_read(baseline_path))
        current_counts = _audit_counts(audit)
        coverage = audit.get("coverage") or {}
        rows.append({
            "season_id": season_id,
            "status": "source-draft-blocked" if audit["release_eligible"] is not True else "source-draft-source-eligible",
            "inputs": {
                "current_pointer_sha256": _sha256_file(pointer_path),
                "intake_sha256": _sha256_file(intake_path),
                "allocation_sha256": _sha256_file(allocation_path),
                "opening_squad_preallocation_sha256": builder._sha256_document(preallocation),
                "template_package_sha256": template_sha256,
                "registry_sha256": registry_sha256,
                "calendar_binding_audit_sha256": (
                    builder._sha256_document(row_calendar_binding_audit)
                    if row_calendar_binding_audit is not None else None
                ),
            },
            "outputs": {
                "draft_package_sha256": audit["draft_package_sha256"],
                "audit_sha256": builder._sha256_document(audit),
            },
            "baseline_hard_blocker_counts": baseline_counts,
            "hard_blocker_counts": current_counts,
            "chronology_identity_resolution_count": coverage.get(
                "source_person_identity_unique_earliest_opening_fixture_resolution_count", 0
            ),
            "safe_opening_xi_shortfall_count": current_counts.get("safe-opening-xi-capacity-unavailable", 0),
            "release_eligible": False,
        })

    before_seasons = Counter()
    before_subjects = Counter()
    after_seasons = Counter()
    after_subjects = Counter()
    for row in rows:
        for code, count in (row["baseline_hard_blocker_counts"] or {}).items():
            before_seasons[code] += 1
            before_subjects[code] += count
        for code, count in row["hard_blocker_counts"].items():
            after_seasons[code] += 1
            after_subjects[code] += count
    result = {
        "schema_version": SCHEMA,
        "policy": {
            "duplicate_person": "unique-earliest-dated-opening-fixture-owner-only; equal-date-or-undated-remain-blocked",
            "formation": "not-integrated-here; later-layer-may-use-deterministic-source-position-inference",
            "manager": "not-integrated-here; sourced-opening-date-manager-string-required",
            "secondary_player_facts": "source-builder-preserve-existing-fallbacks-remain-nonblocking",
            "calendar": (
                "calendar-receipt-gate-may-close-only-with-an-exact-template-hash-bound-overlay-audit; "
                "runtime-validation-remains-owned-by-later-layer"
            ),
            "release": "drafts-only; no-release-package-compile-runtime-or-playable-claim",
        },
        "rows": rows,
        "summary": {
            "season_count": len(rows),
            "source_draft_source_eligible_count": sum(row["status"] == "source-draft-source-eligible" for row in rows),
            "playable_count": 0,
            "chronology_identity_resolution_count": sum(row["chronology_identity_resolution_count"] for row in rows),
            "safe_opening_xi_shortfall_count": sum(row["safe_opening_xi_shortfall_count"] for row in rows),
            "baseline_hard_blocker_season_counts": dict(sorted(before_seasons.items())),
            "baseline_hard_blocker_subject_counts": dict(sorted(before_subjects.items())),
            "current_hard_blocker_season_counts": dict(sorted(after_seasons.items())),
            "current_hard_blocker_subject_counts": dict(sorted(after_subjects.items())),
        },
    }
    builder._write(output_root / "closure-matrix.json", result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-root", type=Path, default=ROOT / ".local/season-historical-squad-backfill-v1")
    parser.add_argument("--opening-root", type=Path, default=ROOT / ".local/transfermarkt-opening-plans-current-v1")
    parser.add_argument("--baseline-root", type=Path, default=ROOT / ".local/transfermarkt-opening-plans-current-v1")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--template-package", type=Path, default=ROOT / "seasons/2015-16/season-package.json")
    parser.add_argument(
        "--registry-root", type=Path, default=ROOT / "seasons",
        help="season directories containing the registry hash-bound by each current intake",
    )
    parser.add_argument(
        "--calendar-binding-audit",
        type=Path,
        help=(
            "hash-bound calendar overlay audit for this exact template/season; "
            "use with one matching --season"
        ),
    )
    parser.add_argument(
        "--calendar-binding-root",
        type=Path,
        help=(
            "root containing one <season>/draft-season-package.calendar-bound.json "
            "and exact calendar-binding-audit.json pair per selected season"
        ),
    )
    parser.add_argument("--season", action="append", dest="seasons")
    args = parser.parse_args(argv)
    try:
        result = replay(
            current_root=args.current_root, opening_root=args.opening_root,
            output_root=args.output_root, template_path=args.template_package,
            registry_root=args.registry_root, baseline_root=args.baseline_root,
            calendar_binding_audit_path=args.calendar_binding_audit,
            calendar_binding_root=args.calendar_binding_root,
            seasons=args.seasons,
        )
    except (ClosureError, builder.SourcePackageBuildError, package_v2.PackageValidationError) as exc:
        parser.error(str(exc))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
