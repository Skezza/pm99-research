#!/usr/bin/env python3
"""Bind one proved PM99 calendar receipt to every replayed season draft.

This is a mechanical, resumable bridge between source-draft replay and the
canonical-workspace ingress.  It reads each canonical V2 draft below one
input root, checks the corresponding immutable calendar receipt and patched
``MANAGPRE.EXE``, then writes a new calendar-bound *draft* and receipt.

It never promotes a draft, compiles a game tree, creates a release manifest,
or records runtime/screenshot evidence.  A successful batch only proves that
each date patch is attached to the exact package bytes consumed downstream.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_calendar_package_overlay_v1 as overlay  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402


SCHEMA = "pm99-season-calendar-batch-bind-v1"


class CalendarBatchBindError(ValueError):
    """One replayed draft or its proved calendar input is unsafe."""


def _bytes(value: Mapping[str, Any]) -> bytes:
    return package_v2.canonical_json_bytes(dict(value))


def _sha256_file(path: Path) -> str:
    return package_v2.sha256_file(path)


def _season_id(package: Mapping[str, Any]) -> str:
    season = package.get("season")
    if not isinstance(season, Mapping):
        raise CalendarBatchBindError("package has no season object")
    start, end = season.get("start_year"), season.get("end_year")
    if not isinstance(start, int) or not isinstance(end, int) or end != start + 1:
        raise CalendarBatchBindError("package season must be one consecutive year")
    return f"{start:04d}-{end % 100:02d}"


def _read_receipt(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CalendarBatchBindError(f"cannot read calendar receipt: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CalendarBatchBindError(f"calendar receipt is not an object: {path}")
    return value, payload


def _bind_one(
    package_path: Path, *, calendar_root: Path, output_root: Path,
    receipt_root_relative: str,
) -> dict[str, Any]:
    """Bind one independent season directory, safe to call in a subprocess."""
    package = package_v2.read_canonical_package(package_path)
    # A source draft may retain unresolved same-person candidates and other
    # release gates.  Calendar proof can safely bind its structural package
    # now; strict release validation remains the later ingress gate, rather
    # than making date proof depend on unrelated editorial queues.
    package_v2.validate_package(package, strict=False)
    season_id = _season_id(package)
    if season_id != package_path.parent.name:
        raise CalendarBatchBindError(f"draft package path/season mismatch: {package_path}")
    calendar_dir = calendar_root / season_id
    receipt_path = calendar_dir / "calendar-receipt.json"
    executable_path = calendar_dir / "MANAGPRE.EXE"
    if not receipt_path.is_file() or receipt_path.is_symlink():
        raise CalendarBatchBindError(f"calendar receipt is missing: {receipt_path}")
    if not executable_path.is_file() or executable_path.is_symlink():
        raise CalendarBatchBindError(f"calendar executable is missing: {executable_path}")
    receipt, receipt_bytes = _read_receipt(receipt_path)
    package_out, audit = overlay.bind_calendar(
        package=package,
        receipt=receipt,
        receipt_relative_path=f"{receipt_root_relative}/{season_id}/calendar-receipt.json",
        receipt_sha256=hashlib.sha256(receipt_bytes).hexdigest(),
        executable_sha256=_sha256_file(executable_path),
    )
    destination = output_root / season_id
    package_output = destination / "draft-season-package.calendar-bound.json"
    audit_output = destination / "calendar-binding-audit.json"
    package_v2.write_canonical_package(package_output, package_out)
    actual_package_sha256 = _sha256_file(package_output)
    if audit["output_package_sha256"] != actual_package_sha256:
        raise CalendarBatchBindError(f"calendar overlay wrote a mismatched package receipt for {season_id}")
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.write_bytes(_bytes(audit))
    return {
        "season": season_id,
        "input_draft_sha256": _sha256_file(package_path),
        "calendar_receipt_sha256": audit["receipt_sha256"],
        "calendar_executable_sha256": audit["executable_sha256"],
        "output_draft_sha256": actual_package_sha256,
        "calendar_binding_audit_sha256": _sha256_file(audit_output),
        "state": "calendar-bound-provisional-draft",
        "release_eligible": False,
        "runtime_validation_pending": True,
    }


def bind_batch(*, input_root: Path, calendar_root: Path, output_root: Path,
               receipt_root_relative: str = ".local/calendar-v1", workers: int = 1) -> dict[str, Any]:
    """Write one new calendar-bound output directory per replayed draft.

    Inputs and outputs are intentionally separate and the output root must be
    absent.  That makes a retry either byte-identical in a fresh directory or
    visibly refused; it cannot mutate an earlier receipt beneath a handover.
    """
    input_root = input_root.resolve()
    calendar_root = calendar_root.resolve()
    output_root = output_root.resolve()
    if not input_root.is_dir() or input_root.is_symlink():
        raise CalendarBatchBindError(f"input root must be an ordinary directory: {input_root}")
    if not calendar_root.is_dir() or calendar_root.is_symlink():
        raise CalendarBatchBindError(f"calendar root must be an ordinary directory: {calendar_root}")
    if output_root.exists():
        raise CalendarBatchBindError(f"refusing to replace output root: {output_root}")
    if not receipt_root_relative.startswith(".local/") or ".." in Path(receipt_root_relative).parts:
        raise CalendarBatchBindError("receipt root relative path must be a safe .local path")
    if not isinstance(workers, int) or isinstance(workers, bool) or not 1 <= workers <= 8:
        raise CalendarBatchBindError("workers must be an integer from 1 to 8")

    package_paths = sorted(input_root.glob("*/draft-season-package.json"))
    if not package_paths:
        raise CalendarBatchBindError("input root has no draft-season-package.json files")
    seen: set[str] = set()
    for package_path in package_paths:
        package = package_v2.read_canonical_package(package_path)
        season_id = _season_id(package)
        if season_id != package_path.parent.name or season_id in seen:
            raise CalendarBatchBindError(f"draft package path/season mismatch: {package_path}")
        seen.add(season_id)
    if workers == 1:
        rows = [
            _bind_one(
                package_path, calendar_root=calendar_root, output_root=output_root,
                receipt_root_relative=receipt_root_relative,
            )
            for package_path in package_paths
        ]
    else:
        from functools import partial

        bind_one = partial(
            _bind_one, calendar_root=calendar_root, output_root=output_root,
            receipt_root_relative=receipt_root_relative,
        )
        with ProcessPoolExecutor(max_workers=workers) as executor:
            rows = list(executor.map(bind_one, package_paths))
    rows.sort(key=lambda row: str(row["season"]))
    result = {
        "schema_version": SCHEMA,
        "policy": "calendar-binding-only; no-promotion-compile-runtime-or-playable-claim",
        "rows": rows,
        "summary": {
            "season_count": len(rows),
            "calendar_bound_draft_count": len(rows),
            "playable_count": 0,
        },
    }
    matrix_path = output_root / "calendar-binding-matrix.json"
    matrix_path.write_bytes(_bytes(result))
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--calendar-root", type=Path, default=ROOT / ".local/calendar-v1")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-root-relative", default=".local/calendar-v1")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    try:
        result = bind_batch(
            input_root=args.input_root, calendar_root=args.calendar_root,
            output_root=args.output_root, receipt_root_relative=args.receipt_root_relative,
            workers=args.workers,
        )
    except (CalendarBatchBindError, OSError, package_v2.PackageValidationError,
            overlay.CalendarOverlayError) as exc:
        parser.error(str(exc))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
