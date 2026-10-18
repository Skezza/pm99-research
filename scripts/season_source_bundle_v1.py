#!/usr/bin/env python3
"""Compose a hash-locked multi-capture season source without PM99 writes.

A season may need both split-year and calendar-year squad captures.  This
tool consumes a small data-only bundle recipe, verifies every retained input,
creates one canonical combined capture, and derives a fresh carrier-assignment
ledger bound to that new capture.  It never chooses a capture by filename,
reconciles an identity, or writes a PM99 game file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import foreign_carrier_assignment_v1 as assignment_lib  # noqa: E402
from scripts import merge_footballsquads_captures as merge_lib  # noqa: E402
from scripts import world_fixed_carrier_ledger_v2 as registry_lib  # noqa: E402


SCHEMA = "pm99-season-source-bundle-v1"
ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,79}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SourceBundleError(ValueError):
    """A source bundle is stale, malformed, or unsafe to materialise."""


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return assignment_lib.canonical_json_bytes(value)


def _sha256_file(path: Path) -> str:
    return assignment_lib.sha256_file(path)


def _require_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise SourceBundleError(f"{label} must be a stable lower-case ID")
    return value


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise SourceBundleError(f"{label} must be a lowercase SHA-256")
    return value


def _safe_relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise SourceBundleError(f"{label} must be a non-empty POSIX relative path")
    candidate = Path(value)
    if candidate.is_absolute() or "." in candidate.parts or ".." in candidate.parts or candidate.as_posix() != value:
        raise SourceBundleError(f"{label} must be a safe relative path")
    return value


def _resolve(bundle_path: Path, relative_path: str, label: str) -> Path:
    root = bundle_path.parent.resolve()
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise SourceBundleError(f"{label} escapes the bundle directory") from exc
    return path


def _read_canonical(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        return assignment_lib.read_canonical_json(path, label=label)
    except assignment_lib.AssignmentError as exc:
        raise SourceBundleError(str(exc)) from exc


def read_bundle(path: Path) -> dict[str, Any]:
    payload, _ = _read_canonical(path, "source bundle")
    validate_bundle(payload)
    return payload


def validate_bundle(bundle: Mapping[str, Any]) -> None:
    expected = {"schema_version", "bundle_id", "season", "registry", "captures", "output", "assignment_rebinding"}
    if not isinstance(bundle, Mapping) or set(bundle) != expected:
        raise SourceBundleError(f"source bundle keys must exactly equal {sorted(expected)}")
    if bundle.get("schema_version") != SCHEMA:
        raise SourceBundleError(f"source bundle schema_version must be {SCHEMA!r}")
    _require_id(bundle.get("bundle_id"), "bundle_id")
    season = bundle.get("season")
    if not isinstance(season, Mapping) or set(season) != {"catalog", "label"}:
        raise SourceBundleError("season must contain only catalog and label")
    if not isinstance(season.get("catalog"), str) or not season["catalog"].strip():
        raise SourceBundleError("season.catalog must be non-blank")
    if not isinstance(season.get("label"), str) or not season["label"].strip():
        raise SourceBundleError("season.label must be non-blank")

    registry = bundle.get("registry")
    if not isinstance(registry, Mapping) or set(registry) != {"relative_path", "sha256"}:
        raise SourceBundleError("registry must contain relative_path and sha256")
    _safe_relative_path(registry.get("relative_path"), "registry.relative_path")
    _require_sha256(registry.get("sha256"), "registry.sha256")

    captures = bundle.get("captures")
    if not isinstance(captures, list) or len(captures) < 2:
        raise SourceBundleError("captures must be a list of at least two rows")
    previous_path: str | None = None
    seen_paths: set[str] = set()
    seen_names: set[str] = set()
    for index, capture in enumerate(captures):
        if not isinstance(capture, Mapping) or set(capture) != {"relative_path", "sha256"}:
            raise SourceBundleError(f"captures[{index}] must contain relative_path and sha256")
        relative_path = _safe_relative_path(capture.get("relative_path"), f"captures[{index}].relative_path")
        _require_sha256(capture.get("sha256"), f"captures[{index}].sha256")
        if relative_path in seen_paths or (previous_path is not None and relative_path <= previous_path):
            raise SourceBundleError("captures must be path-sorted and unique")
        if Path(relative_path).name in seen_names:
            raise SourceBundleError("captures must have unique filenames")
        seen_paths.add(relative_path)
        seen_names.add(Path(relative_path).name)
        previous_path = relative_path

    output = bundle.get("output")
    if not isinstance(output, Mapping) or set(output) != {"relative_path"}:
        raise SourceBundleError("output must contain only relative_path")
    output_path = _safe_relative_path(output.get("relative_path"), "output.relative_path")
    if output_path in seen_paths:
        raise SourceBundleError("output.relative_path must not replace a source capture")

    rebinding = bundle.get("assignment_rebinding")
    rebinding_keys = {"input_relative_path", "input_sha256", "previous_capture_relative_path", "output_relative_path", "assignment_id"}
    if not isinstance(rebinding, Mapping) or set(rebinding) != rebinding_keys:
        raise SourceBundleError(f"assignment_rebinding must contain exactly {sorted(rebinding_keys)}")
    _safe_relative_path(rebinding.get("input_relative_path"), "assignment_rebinding.input_relative_path")
    _require_sha256(rebinding.get("input_sha256"), "assignment_rebinding.input_sha256")
    previous_capture = _safe_relative_path(
        rebinding.get("previous_capture_relative_path"), "assignment_rebinding.previous_capture_relative_path"
    )
    if previous_capture not in seen_paths:
        raise SourceBundleError("assignment_rebinding.previous_capture_relative_path must name one bundled capture")
    rebinding_output = _safe_relative_path(
        rebinding.get("output_relative_path"), "assignment_rebinding.output_relative_path"
    )
    if rebinding_output in seen_paths or rebinding_output == output_path:
        raise SourceBundleError("assignment rebinding output must be distinct from capture inputs and output")
    _require_id(rebinding.get("assignment_id"), "assignment_rebinding.assignment_id")


def compose_bundle(*, bundle_path: Path, bundle: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Recompute exactly the composed capture and rebound assignment."""

    validate_bundle(bundle)
    registry_spec = bundle["registry"]
    registry_path = _resolve(bundle_path, str(registry_spec["relative_path"]), "registry.relative_path")
    registry, registry_digest = _read_canonical(registry_path, "fixed-carrier registry")
    if registry_digest != registry_spec["sha256"]:
        raise SourceBundleError("fixed-carrier registry hash does not match bundle")
    try:
        registry_lib.validate_registry(registry)
    except registry_lib.WorldLedgerError as exc:
        raise SourceBundleError(str(exc)) from exc

    source_rows: list[tuple[str, Mapping[str, Any], str]] = []
    captures_by_relative_path: dict[str, dict[str, Any]] = {}
    for spec in bundle["captures"]:
        relative_path = str(spec["relative_path"])
        path = _resolve(bundle_path, relative_path, f"capture {relative_path}")
        capture, digest = _read_canonical(path, f"capture {relative_path}")
        if digest != spec["sha256"]:
            raise SourceBundleError(f"capture hash does not match bundle: {relative_path}")
        # The merger's own validator checks source/club structure before it
        # accepts this document.
        source_rows.append((path.name, capture, digest))
        captures_by_relative_path[relative_path] = capture
    try:
        composed = merge_lib.merge_captures(
            captures=source_rows,
            merged_catalog=str(bundle["season"]["catalog"]),
            merged_label=str(bundle["season"]["label"]),
        )
    except merge_lib.MergeError as exc:
        raise SourceBundleError(str(exc)) from exc

    rebinding = bundle["assignment_rebinding"]
    assignment_path = _resolve(bundle_path, str(rebinding["input_relative_path"]), "assignment input")
    assignment, assignment_digest = _read_canonical(assignment_path, "carrier assignment")
    if assignment_digest != rebinding["input_sha256"]:
        raise SourceBundleError("carrier assignment hash does not match bundle")
    previous = captures_by_relative_path[str(rebinding["previous_capture_relative_path"])]
    try:
        rebound = assignment_lib.rebind_assignment_to_capture(
            assignment=assignment,
            registry=registry,
            previous_source_capture=previous,
            source_capture=composed,
            assignment_id=str(rebinding["assignment_id"]),
        )
    except assignment_lib.AssignmentError as exc:
        raise SourceBundleError(str(exc)) from exc
    return composed, rebound


def _output_paths(bundle_path: Path, bundle: Mapping[str, Any]) -> tuple[Path, Path]:
    return (
        _resolve(bundle_path, str(bundle["output"]["relative_path"]), "output.relative_path"),
        _resolve(
            bundle_path,
            str(bundle["assignment_rebinding"]["output_relative_path"]),
            "assignment_rebinding.output_relative_path",
        ),
    )


def build_bundle(*, bundle_path: Path, bundle: Mapping[str, Any]) -> dict[str, Any]:
    composed, rebound = compose_bundle(bundle_path=bundle_path, bundle=bundle)
    capture_output, assignment_output = _output_paths(bundle_path, bundle)
    if capture_output.exists() or assignment_output.exists():
        raise SourceBundleError("bundle outputs already exist; use verify instead of replacing them")
    assignment_lib.write_canonical_json(capture_output, composed)
    try:
        assignment_lib.write_canonical_json(assignment_output, rebound)
    except OSError:
        # Avoid claiming a partial completed bundle.  The capture is a known,
        # resolved exact target rather than an arbitrary directory.
        capture_output.unlink(missing_ok=True)
        raise
    return receipt(bundle_path=bundle_path, bundle=bundle, composed=composed, rebound=rebound)


def receipt(
    *, bundle_path: Path, bundle: Mapping[str, Any], composed: Mapping[str, Any], rebound: Mapping[str, Any]
) -> dict[str, Any]:
    capture_output, assignment_output = _output_paths(bundle_path, bundle)
    return {
        "schema_version": "pm99-season-source-bundle-receipt-v1",
        "bundle_id": bundle["bundle_id"],
        "season": dict(bundle["season"]),
        "capture_output": {
            "relative_path": str(bundle["output"]["relative_path"]),
            "sha256": hashlib.sha256(canonical_json_bytes(composed)).hexdigest(),
        },
        "assignment_output": {
            "relative_path": str(bundle["assignment_rebinding"]["output_relative_path"]),
            "sha256": hashlib.sha256(canonical_json_bytes(rebound)).hexdigest(),
        },
        "output_paths": {
            "capture": capture_output.name,
            "assignment": assignment_output.name,
        },
    }


def verify_bundle(*, bundle_path: Path, bundle: Mapping[str, Any]) -> dict[str, Any]:
    composed, rebound = compose_bundle(bundle_path=bundle_path, bundle=bundle)
    capture_output, assignment_output = _output_paths(bundle_path, bundle)
    actual_capture, _ = _read_canonical(capture_output, "composed source capture")
    actual_assignment, _ = _read_canonical(assignment_output, "composed carrier assignment")
    if actual_capture != composed:
        raise SourceBundleError("composed source capture does not exactly match bundle inputs")
    if actual_assignment != rebound:
        raise SourceBundleError("composed carrier assignment does not exactly match bundle inputs")
    return receipt(bundle_path=bundle_path, bundle=bundle, composed=composed, rebound=rebound)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--bundle", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        bundle_path = args.bundle.resolve()
        bundle = read_bundle(bundle_path)
        output = build_bundle(bundle_path=bundle_path, bundle=bundle) if args.command == "build" else verify_bundle(
            bundle_path=bundle_path, bundle=bundle
        )
    except (SourceBundleError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
