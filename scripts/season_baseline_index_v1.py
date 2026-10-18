#!/usr/bin/env python3
"""Freeze a hash-pinned, non-playable baseline for forward season work.

The calendar batch has already performed package validation and written an
immutable matrix of package, calendar receipt and executable hashes.  This
tool does not rebuild, validate, or alter those packages.  It records that
matrix as one append-only baseline, so later authoring work can prove exactly
which season input it extends and rebuild only that season when an overlay
changes.
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

from scripts import season_package_v2 as package_v2  # noqa: E402


SCHEMA = "pm99-season-baseline-index-v1"
CALENDAR_BATCH_SCHEMA = "pm99-season-calendar-batch-bind-v1"


class BaselineIndexError(ValueError):
    """A purported calendar-bound batch cannot become a forward baseline."""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaselineIndexError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise BaselineIndexError(f"{label} must be a JSON object: {path}")
    return value


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not package_v2.SHA256_RE.fullmatch(value):
        raise BaselineIndexError(f"{label} must be a lowercase SHA-256")
    return value


def _season_from_package(package: Mapping[str, Any], *, expected: str) -> None:
    season = package.get("season")
    if not isinstance(season, Mapping):
        raise BaselineIndexError(f"{expected}: package has no season")
    start, end = season.get("start_year"), season.get("end_year")
    if not isinstance(start, int) or not isinstance(end, int) or end != start + 1:
        raise BaselineIndexError(f"{expected}: package season is malformed")
    if expected != f"{start:04d}-{end % 100:02d}":
        raise BaselineIndexError(f"{expected}: package season does not match its directory")


def build_index(*, calendar_bound_root: Path, baseline_id: str) -> dict[str, Any]:
    """Return a baseline index without recomputing its established hashes."""
    calendar_bound_root = calendar_bound_root.resolve()
    if not calendar_bound_root.is_dir() or calendar_bound_root.is_symlink():
        raise BaselineIndexError(f"calendar-bound root must be an ordinary directory: {calendar_bound_root}")
    if not package_v2.ID_RE.fullmatch(baseline_id):
        raise BaselineIndexError("baseline ID must be a stable lowercase identifier")

    matrix_path = calendar_bound_root / "calendar-binding-matrix.json"
    matrix = _read_json(matrix_path, "calendar batch matrix")
    if matrix.get("schema_version") != CALENDAR_BATCH_SCHEMA:
        raise BaselineIndexError("unsupported calendar batch matrix")
    summary = matrix.get("summary")
    rows = matrix.get("rows")
    if not isinstance(summary, Mapping) or not isinstance(rows, list):
        raise BaselineIndexError("calendar batch matrix has no summary or rows")
    if (
        summary.get("season_count") != len(rows)
        or summary.get("calendar_bound_draft_count") != len(rows)
        or summary.get("playable_count") != 0
    ):
        raise BaselineIndexError("calendar batch matrix does not describe only provisional drafts")

    seasons: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise BaselineIndexError("calendar batch matrix has a malformed row")
        season = row.get("season")
        if not isinstance(season, str) or season in seen:
            raise BaselineIndexError("calendar batch matrix has a blank or duplicate season")
        seen.add(season)
        if row.get("state") != "calendar-bound-provisional-draft" or row.get("release_eligible") is not False:
            raise BaselineIndexError(f"{season}: baseline may contain only provisional calendar-bound drafts")
        package_path = calendar_bound_root / season / "draft-season-package.calendar-bound.json"
        audit_path = calendar_bound_root / season / "calendar-binding-audit.json"
        if not package_path.is_file() or package_path.is_symlink() or not audit_path.is_file() or audit_path.is_symlink():
            raise BaselineIndexError(f"{season}: calendar-bound package or audit is missing")
        package = _read_json(package_path, f"{season} calendar-bound package")
        _season_from_package(package, expected=season)
        calendar = package.get("calendar")
        if not isinstance(calendar, Mapping) or calendar.get("target_year") != package["season"]["start_year"]:
            raise BaselineIndexError(f"{season}: package has an invalid calendar binding")
        seasons.append({
            "season": season,
            "base_draft": {
                "path": _relative(package_path),
                "sha256": _sha256(row.get("output_draft_sha256"), f"{season} output draft hash"),
            },
            "calendar_binding_audit": {
                "path": _relative(audit_path),
                "sha256": _sha256(row.get("calendar_binding_audit_sha256"), f"{season} calendar audit hash"),
            },
            "calendar_receipt_sha256": _sha256(row.get("calendar_receipt_sha256"), f"{season} calendar receipt hash"),
            "calendar_executable_sha256": _sha256(row.get("calendar_executable_sha256"), f"{season} calendar executable hash"),
            "state": "frozen-provisional-base",
            "playable": False,
        })
    seasons.sort(key=lambda row: str(row["season"]))
    return {
        "schema_version": SCHEMA,
        "baseline_id": baseline_id,
        "state": "frozen-provisional-base",
        "policy": {
            "input": "calendar batch matrix is already hash-verified; this index does not rerun its packages",
            "forward_work": "add hash-bound per-season overlays; rebuild only the changed season and dependants",
            "promotion": "strict package, clean compile, runtime receipt and screenshot remain required",
        },
        "calendar_batch_matrix": {
            "path": _relative(matrix_path),
            "sha256": _sha256_file(matrix_path),
        },
        "seasons": seasons,
        "summary": {
            "season_count": len(seasons),
            "frozen_provisional_base_count": len(seasons),
            "strict_release_count": 0,
            "playable_count": 0,
        },
    }


def write_index(*, calendar_bound_root: Path, baseline_id: str, output: Path) -> dict[str, Any]:
    """Create one index once; never overwrite a prior baseline selection."""
    output = output.resolve()
    if output.exists():
        raise BaselineIndexError(f"refusing to overwrite baseline index: {output}")
    index = build_index(calendar_bound_root=calendar_bound_root, baseline_id=baseline_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(package_v2.canonical_json_bytes(index))
    return index


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calendar-bound-root", type=Path, default=ROOT / ".local/season-calendar-bound-batch-v2")
    parser.add_argument("--baseline-id", default="calendar-bound-v2")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        index = write_index(
            calendar_bound_root=args.calendar_bound_root,
            baseline_id=args.baseline_id,
            output=args.output,
        )
    except (OSError, BaselineIndexError) as exc:
        parser.error(str(exc))
    print(json.dumps(index["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
