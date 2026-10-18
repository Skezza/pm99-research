#!/usr/bin/env python3
"""Install one hash-bound season calendar executable into a fresh game tree.

This is the deliberately narrow calendar lane for a historical V2 build.  It
accepts only the executable named by a strict package's calendar artifact and
the matching calendar-binding audit.  Before replacing ``MANAGPRE.EXE`` it
proves that the game tree still has the executable from the declared verified
clean base; afterwards it inventories the whole tree and proves that this
stage changed exactly that one file.

The receipt is package-, calendar-, base-, and output-bound.  It deliberately
retains ``runtime_validation_pending`` and ``release_eligible: false``: an
installed calendar is neither a runtime proof nor a playable-season claim.

With ``--build-plan-adapter`` the same checked write boundary emits its full
receipt on stdout and creates no receipt inside the game tree.  This makes it
a valid local adapter for ``season_pipeline_buildplan_v2.py``, whose own
external metadata records the reviewed stage receipt and output inventory.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_calendar_package_overlay_v1 as calendar_overlay  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_pipeline_v2 as pipeline_v2  # noqa: E402


RECEIPT_SCHEMA = "pm99-season-calendar-materialisation-v1"
CALENDAR_RECEIPT_SCHEMA = "pm99-calendar-patch-v1"
EXECUTABLE_NAME = "MANAGPRE.EXE"


class CalendarMaterialisationError(ValueError):
    """The requested calendar write lacks the required immutable bindings."""


def _regular_file(path: Path, *, label: str) -> Path:
    path = path.expanduser()
    if not path.is_file() or path.is_symlink():
        raise CalendarMaterialisationError(f"{label} must be a regular, non-symlink file: {path}")
    return path.resolve()


def _read_json(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    path = _regular_file(path, label=label)
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CalendarMaterialisationError(f"cannot read {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CalendarMaterialisationError(f"{label} must be a JSON object: {path}")
    return value, pipeline_v2.sha256_bytes(raw)


def _sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise CalendarMaterialisationError(f"{label} must be a SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise CalendarMaterialisationError(f"{label} must be a SHA-256 digest") from exc
    if value != value.lower():
        raise CalendarMaterialisationError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _inventory_hash(inventory: Mapping[str, Any], relative_path: str) -> str:
    files = inventory.get("files")
    if not isinstance(files, list):
        raise CalendarMaterialisationError("verified base has no file inventory")
    matching = [row for row in files if isinstance(row, Mapping) and row.get("path") == relative_path]
    if len(matching) != 1:
        raise CalendarMaterialisationError(
            f"verified base must contain exactly one {relative_path} inventory record"
        )
    return _sha256(matching[0].get("sha256"), label=f"verified base {relative_path} hash")


def _calendar_binding(
    *, package: Mapping[str, Any],
    audit: Mapping[str, Any], audit_sha256: str,
    calendar_receipt: Mapping[str, Any], calendar_receipt_sha256: str,
    calendar_executable_sha256: str,
) -> dict[str, Any]:
    """Verify the direct calendar-overlay contract for this exact package."""

    if audit.get("schema_version") != calendar_overlay.SCHEMA:
        raise CalendarMaterialisationError("calendar binding audit has an unsupported schema")
    audit_package_sha256 = _sha256(
        audit.get("output_package_sha256"), label="calendar binding audit output package hash"
    )
    if audit.get("receipt_sha256") != calendar_receipt_sha256:
        raise CalendarMaterialisationError("calendar binding audit does not bind this exact receipt")
    if audit.get("executable_sha256") != calendar_executable_sha256:
        raise CalendarMaterialisationError("calendar binding audit does not bind this exact executable")
    try:
        patch_count = calendar_overlay._validated_patch_count(calendar_receipt)
    except calendar_overlay.CalendarOverlayError as exc:
        raise CalendarMaterialisationError(str(exc)) from exc
    if audit.get("patch_count") != patch_count:
        raise CalendarMaterialisationError("calendar binding audit does not use the proved calendar profile")
    if audit.get("runtime_validation_pending") is not True:
        raise CalendarMaterialisationError("calendar binding audit must retain runtime validation as pending")

    season = package.get("season")
    calendar = package.get("calendar")
    artifacts = package.get("artifacts")
    if not isinstance(season, Mapping) or not isinstance(calendar, Mapping) or not isinstance(artifacts, list):
        raise CalendarMaterialisationError("strict package has no complete calendar contract")
    start_year, end_year = season.get("start_year"), season.get("end_year")
    if not isinstance(start_year, int) or not isinstance(end_year, int):
        raise CalendarMaterialisationError("package season has invalid years")
    if audit.get("season") != dict(season):
        raise CalendarMaterialisationError("calendar binding audit season does not match package")
    if (
        calendar.get("base_year") != 1998
        or calendar.get("target_year") != start_year
        or calendar.get("target_rollover_year") != end_year
    ):
        raise CalendarMaterialisationError("package calendar does not match package season")
    artifact_id = calendar.get("patch_artifact_id")
    artifact = next(
        (row for row in artifacts if isinstance(row, Mapping) and row.get("id") == artifact_id), None
    )
    if artifact is None or artifact.get("kind") != "calendar-patch":
        raise CalendarMaterialisationError("package calendar patch artifact is absent or has the wrong kind")
    if artifact.get("sha256") != calendar_receipt_sha256:
        raise CalendarMaterialisationError("package calendar artifact does not bind this exact receipt")

    if calendar_receipt.get("schema_version") != CALENDAR_RECEIPT_SCHEMA:
        raise CalendarMaterialisationError("calendar receipt has an unsupported schema")
    if (
        calendar_receipt.get("base_year") != 1998
        or calendar_receipt.get("target_year") != start_year
        or calendar_receipt.get("target_rollover_year") != end_year
        or calendar_receipt.get("patch_count") != patch_count
    ):
        raise CalendarMaterialisationError("calendar receipt does not match the package calendar contract")
    if calendar_receipt.get("after_sha256") != calendar_executable_sha256:
        raise CalendarMaterialisationError("calendar receipt does not bind this exact executable")
    before_sha256 = _sha256(calendar_receipt.get("before_sha256"), label="calendar receipt before hash")

    return {
        "calendar_binding_audit_sha256": audit_sha256,
        "calendar_binding_source_package_sha256": audit_package_sha256,
        "calendar_receipt_sha256": calendar_receipt_sha256,
        "calendar_executable_sha256": calendar_executable_sha256,
        "calendar_patch_artifact_id": artifact_id,
        "calendar_patch_count": patch_count,
        "base_executable_sha256": before_sha256,
        "target_year": start_year,
        "target_rollover_year": end_year,
    }


def _inventory_summary(inventory: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "files_fingerprint": inventory["files_fingerprint"],
        "file_count": inventory["file_count"],
        "total_bytes": inventory["total_bytes"],
    }


def _assert_only_calendar_changed(
    *, before: Mapping[str, Any], after: Mapping[str, Any],
    base_executable_sha256: str, calendar_executable_sha256: str,
) -> dict[str, Any]:
    difference = pipeline_v2.inventory_difference(before, after)
    if difference["only_left"] or difference["only_right"]:
        raise CalendarMaterialisationError("calendar materialisation added or removed game-tree files")
    changed = difference["changed"]
    if len(changed) != 1 or changed[0]["path"] != EXECUTABLE_NAME:
        paths = [row["path"] for row in changed]
        raise CalendarMaterialisationError(
            "calendar materialisation must change exactly MANAGPRE.EXE; changed paths: "
            + json.dumps(paths)
        )
    change = changed[0]
    if change["left"]["sha256"] != base_executable_sha256:
        raise CalendarMaterialisationError("pre-write MANAGPRE.EXE does not match the verified clean base")
    if change["right"]["sha256"] != calendar_executable_sha256:
        raise CalendarMaterialisationError("post-write MANAGPRE.EXE does not match the bound calendar executable")
    return difference


def materialise_calendar(
    *, package_path: Path, calendar_audit_path: Path, calendar_receipt_path: Path,
    calendar_executable_path: Path, verified_base_path: Path, game_tree: Path,
) -> dict[str, Any]:
    """Replace a fresh game tree's clean-base executable with a bound calendar.

    All checks run before the write.  The target must still hold the executable
    named by the verified base, which makes a repeated or cross-season write a
    hard failure rather than a silent overwrite.
    """

    package_path = _regular_file(package_path, label="package")
    package = package_v2.read_canonical_package(package_path)
    package_v2.validate_package(package, strict=True)
    package_sha256 = package_v2.sha256_file(package_path)
    audit, audit_sha256 = _read_json(calendar_audit_path, label="calendar binding audit")
    calendar_receipt, calendar_receipt_sha256 = _read_json(
        calendar_receipt_path, label="calendar receipt"
    )
    calendar_executable_path = _regular_file(calendar_executable_path, label="calendar executable")
    calendar_executable_sha256 = pipeline_v2.sha256_file(calendar_executable_path)
    base_descriptor, base_descriptor_sha256 = _read_json(
        verified_base_path, label="verified base descriptor"
    )
    try:
        base_descriptor = pipeline_v2.validate_verified_base_descriptor(base_descriptor)
    except pipeline_v2.PipelineError as exc:
        raise CalendarMaterialisationError(f"invalid verified base descriptor: {exc}") from exc

    binding = _calendar_binding(
        package=package,
        audit=audit,
        audit_sha256=audit_sha256,
        calendar_receipt=calendar_receipt,
        calendar_receipt_sha256=calendar_receipt_sha256,
        calendar_executable_sha256=calendar_executable_sha256,
    )
    base_executable_sha256 = _inventory_hash(base_descriptor["inventory"], EXECUTABLE_NAME)
    if binding["base_executable_sha256"] != base_executable_sha256:
        raise CalendarMaterialisationError(
            "calendar receipt input executable does not match the verified clean base"
        )

    game_tree = game_tree.expanduser()
    if game_tree.is_symlink() or not game_tree.is_dir():
        raise CalendarMaterialisationError(f"game tree must be an existing non-symlink directory: {game_tree}")
    game_tree = game_tree.resolve()
    target_executable = _regular_file(game_tree / EXECUTABLE_NAME, label="game-tree MANAGPRE.EXE")
    if target_executable.parent != game_tree:
        raise CalendarMaterialisationError("game-tree MANAGPRE.EXE resolved outside the game tree")
    if pipeline_v2.sha256_file(target_executable) != base_executable_sha256:
        raise CalendarMaterialisationError(
            "game tree MANAGPRE.EXE is not the verified clean-base executable; refusing overwrite"
        )

    before = pipeline_v2.build_tree_inventory(game_tree)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".calendar-materialise-", dir=target_executable.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            with calendar_executable_path.open("rb") as source:
                shutil.copyfileobj(source, handle)
            handle.flush()
            os.fsync(handle.fileno())
        shutil.copystat(calendar_executable_path, temporary)
        os.replace(temporary, target_executable)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

    after = pipeline_v2.build_tree_inventory(game_tree)
    difference = _assert_only_calendar_changed(
        before=before,
        after=after,
        base_executable_sha256=base_executable_sha256,
        calendar_executable_sha256=calendar_executable_sha256,
    )
    return {
        "schema_version": RECEIPT_SCHEMA,
        "season": f"{package['season']['start_year']:04d}-{package['season']['end_year'] % 100:02d}",
        "package_id": package["package_id"],
        "release_eligible": False,
        "runtime_validation_pending": True,
        "inputs": {
            "package_sha256": package_sha256,
            "calendar_binding_audit_sha256": binding["calendar_binding_audit_sha256"],
            "calendar_binding_source_package_sha256": binding["calendar_binding_source_package_sha256"],
            "calendar_receipt_sha256": binding["calendar_receipt_sha256"],
            "calendar_executable_sha256": binding["calendar_executable_sha256"],
            "verified_base_descriptor_sha256": base_descriptor_sha256,
        },
        "calendar": {
            "base_year": 1998,
            "target_year": binding["target_year"],
            "target_rollover_year": binding["target_rollover_year"],
            "patch_artifact_id": binding["calendar_patch_artifact_id"],
            "patch_count": binding["calendar_patch_count"],
        },
        "base": {
            "base_id": base_descriptor["base_id"],
            "inventory_fingerprint": base_descriptor["inventory"]["files_fingerprint"],
            "managpre_executable_sha256": base_executable_sha256,
        },
        "mutation": {
            "allowed_changed_paths": [EXECUTABLE_NAME],
            "added_paths": difference["only_right"],
            "removed_paths": difference["only_left"],
            "changed_paths": [row["path"] for row in difference["changed"]],
        },
        "game_tree_before": _inventory_summary(before),
        "game_tree_after": _inventory_summary(after),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--calendar-audit", required=True, type=Path)
    parser.add_argument("--calendar-receipt", required=True, type=Path)
    parser.add_argument("--calendar-executable", required=True, type=Path)
    parser.add_argument("--verified-base", required=True, type=Path)
    parser.add_argument("--game-tree", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--build-plan-adapter",
        action="store_true",
        help="emit the full receipt on stdout without writing a receipt file",
    )
    args = parser.parse_args(argv)
    try:
        if args.build_plan_adapter == (args.output is not None):
            raise CalendarMaterialisationError(
                "select exactly one receipt mode: --output or --build-plan-adapter"
            )
        if args.output is not None and (args.output.exists() or args.output.is_symlink()):
            raise CalendarMaterialisationError(f"refusing to overwrite calendar materialisation receipt: {args.output}")
        receipt = materialise_calendar(
            package_path=args.package,
            calendar_audit_path=args.calendar_audit,
            calendar_receipt_path=args.calendar_receipt,
            calendar_executable_path=args.calendar_executable,
            verified_base_path=args.verified_base,
            game_tree=args.game_tree,
        )
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(package_v2.canonical_json_bytes(receipt))
    except (
        CalendarMaterialisationError,
        OSError,
        package_v2.PackageValidationError,
        pipeline_v2.PipelineError,
    ) as exc:
        parser.error(str(exc))
    if args.build_plan_adapter:
        print(json.dumps(receipt, separators=(",", ":"), sort_keys=True))
    else:
        print(json.dumps({
            "season": receipt["season"],
            "package_id": receipt["package_id"],
            "release_eligible": receipt["release_eligible"],
            "runtime_validation_pending": receipt["runtime_validation_pending"],
            "changed_paths": receipt["mutation"]["changed_paths"],
            "output": str(args.output),
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
