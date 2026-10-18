#!/usr/bin/env python3
"""Create and verify isolated, calendar-only PM99 playtest variants.

This is a deliberately narrow provisional release profile.  It copies one
known-good game tree, regenerates *only* MANAGPRE.EXE for the requested
opening season from the fingerprinted pristine calendar executable, and proves
with full-tree inventories that every database and asset file is byte-for-byte
identical to the selected baseline.

It is useful for playtesting the game/runtime and calendar in parallel while
historical season packages are still being authored.  It must not be described
as a historical database for its target season: player, club, kit, portrait and
manager content remain those of the declared content baseline.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_pipeline_v2 as pipeline  # noqa: E402
from scripts.assert_pm99_isolated_input import resolve_game_root  # noqa: E402
from tools import pm99_calendar_patcher as calendar  # noqa: E402


SCHEMA = "pm99-provisional-playtest-calendar-variant-v1"
RELEASE_CLASS = "provisional-calendar-only-playtest"
MANIFEST_NAME = "provisional-playtest-manifest.json"
MATRIX_SCHEMA = "pm99-provisional-playtest-matrix-v1"
RECEIPT_NAMES = {
    "base_inventory": "base-tree.inventory.json",
    "output_inventory": "output-tree.inventory.json",
    "tree_difference": "tree-difference.json",
    "baseline_calendar": "baseline-calendar-patch.json",
    "target_calendar": "target-calendar-patch.json",
}
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
TARGET_26_SEASONS = tuple(f"{year:04d}-{(year + 1) % 100:02d}" for year in range(2000, 2026))


class PlaytestVariantError(ValueError):
    """The requested provisional variant is not safe or reproducible."""


def _identifier(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise PlaytestVariantError(f"{label} must match {_IDENTIFIER.pattern!r}: {value!r}")
    return value


def _sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise PlaytestVariantError(f"{label} must be a lowercase SHA-256 hex digest")
    return value


def _normalise_season(value: str) -> str:
    try:
        return pipeline.normalise_season_id(value)
    except pipeline.PipelineError as exc:
        raise PlaytestVariantError(str(exc)) from exc


def _start_year(season: str) -> int:
    return int(season.split("-", 1)[0])


def _canonical_read(path: Path, *, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlaytestVariantError(f"cannot read {label}: {path}: {exc}") from exc
    if not isinstance(value, dict) or raw != pipeline.canonical_json_bytes(value) + b"\n":
        raise PlaytestVariantError(f"{label} must be canonical JSON written by the release pipeline")
    return value


def _copy_game_tree(source_game_root: Path, target_game_root: Path) -> None:
    """Copy a fresh, isolated output tree without using hard links.

    ``--reflink=auto`` may save space on a supporting filesystem.  Its fallback
    is a regular copy, so later writes to the target can never mutate the
    known-good source tree through shared inode links.
    """

    if target_game_root.exists() or target_game_root.is_symlink():
        raise PlaytestVariantError(f"refusing to replace target game tree: {target_game_root}")
    target_game_root.parent.mkdir(parents=True, exist_ok=True)
    target_game_root.mkdir()
    subprocess.run(
        ["cp", "-a", "--reflink=auto", f"{source_game_root}/.", str(target_game_root)],
        check=True,
    )


def _normalise_calendar_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Retain calendar evidence without machine-specific input/output paths."""

    raw_expected = {
        "schema_version",
        "profile",
        "input",
        "output",
        "base_year",
        "rollover_year",
        "target_year",
        "target_rollover_year",
        "before_sha256",
        "after_sha256",
        "patch_count",
        "source_operand_counts",
        "patches",
    }
    canonical_expected = raw_expected - {"input", "output"}
    if set(receipt) == canonical_expected:
        return dict(receipt)
    if set(receipt) != raw_expected:
        raise PlaytestVariantError("calendar patcher returned an unexpected receipt shape")
    return {
        "schema_version": receipt["schema_version"],
        "profile": receipt["profile"],
        "base_year": receipt["base_year"],
        "rollover_year": receipt["rollover_year"],
        "target_year": receipt["target_year"],
        "target_rollover_year": receipt["target_rollover_year"],
        "before_sha256": receipt["before_sha256"],
        "after_sha256": receipt["after_sha256"],
        "patch_count": receipt["patch_count"],
        "source_operand_counts": receipt["source_operand_counts"],
        "patches": receipt["patches"],
    }


def _calendar_contract(receipt: Mapping[str, Any], *, expected_start_year: int) -> dict[str, Any]:
    value = _normalise_calendar_receipt(receipt)
    if value["schema_version"] != "pm99-calendar-patch-v1":
        raise PlaytestVariantError("calendar receipt has an unsupported schema")
    if value["target_year"] != expected_start_year:
        raise PlaytestVariantError("calendar receipt target year does not match its requested season")
    if value["target_rollover_year"] != expected_start_year + 1:
        raise PlaytestVariantError("calendar receipt rollover year is not consecutive")
    _sha256(value["before_sha256"], label="calendar input hash")
    _sha256(value["after_sha256"], label="calendar output hash")
    if not isinstance(value["patch_count"], int) or value["patch_count"] <= 0:
        raise PlaytestVariantError("calendar receipt patch_count must be positive")
    return value


def _assert_calendar_only_difference(
    *, base_inventory: Mapping[str, Any], output_inventory: Mapping[str, Any],
    baseline_exe_sha256: str, target_exe_sha256: str,
) -> dict[str, Any]:
    difference = pipeline.inventory_difference(base_inventory, output_inventory)
    if difference["only_left"] or difference["only_right"]:
        raise PlaytestVariantError("calendar-only output added or removed game-tree files")
    changed = difference["changed"]
    if len(changed) != 1 or changed[0]["path"] != "MANAGPRE.EXE":
        paths = [row["path"] for row in changed]
        raise PlaytestVariantError(
            "calendar-only output must change exactly MANAGPRE.EXE; changed paths: "
            + json.dumps(paths)
        )
    change = changed[0]
    if change["left"]["sha256"] != baseline_exe_sha256:
        raise PlaytestVariantError("baseline inventory MANAGPRE.EXE hash does not match calendar baseline")
    if change["right"]["sha256"] != target_exe_sha256:
        raise PlaytestVariantError("output inventory MANAGPRE.EXE hash does not match target calendar")
    return difference


def _run_database_validation(game_root: Path) -> dict[str, Any]:
    command = [
        "./scripts/dev_editor.sh",
        "python3",
        "-m",
        "app.cli",
        "validate-database",
        "--players",
        str(game_root / "DBDAT" / "JUG98030.FDI"),
        "--teams",
        str(game_root / "DBDAT" / "EQ98030.FDI"),
        "--coaches",
        str(game_root / "DBDAT" / "ENT98030.FDI"),
        "--json",
    ]
    completed = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, check=False)
    return {
        "command": command,
        "returncode": int(completed.returncode),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _write_validation(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise PlaytestVariantError(f"refusing to overwrite validation attestation: {path}")
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_receipt(receipts_dir: Path, key: str, value: Mapping[str, Any]) -> tuple[Path, str]:
    path = receipts_dir / RECEIPT_NAMES[key]
    digest = pipeline.write_canonical_json(path, value)
    return path, digest


def _manifest(
    *, variant_id: str, target_season: str, baseline_id: str, baseline_season: str,
    base_inventory: Mapping[str, Any], output_inventory: Mapping[str, Any],
    receipts: Mapping[str, str], baseline_calendar: Mapping[str, Any],
    target_calendar: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "release_class": RELEASE_CLASS,
        "variant_id": variant_id,
        "target_season": target_season,
        "content_baseline": {
            "release_id": baseline_id,
            "season": baseline_season,
            "database_content": "byte-identical-except-calendar-executable",
            "historical_status": "not-historically-authored-for-target-season",
            "limitations": [
                "Player, club, manager, kit and portrait content remain the declared baseline season.",
                "A playable calendar clone is not evidence of a historically authored season database.",
                "No opening-lineup screenshot or runtime qualification is implied by this build receipt.",
            ],
        },
        "calendar": {
            "profile": target_calendar["profile"],
            "pristine_input_sha256": target_calendar["before_sha256"],
            "baseline_start_year": baseline_calendar["target_year"],
            "baseline_executable_sha256": baseline_calendar["after_sha256"],
            "target_start_year": target_calendar["target_year"],
            "target_rollover_year": target_calendar["target_rollover_year"],
            "target_executable_sha256": target_calendar["after_sha256"],
            "patch_count": target_calendar["patch_count"],
        },
        "mutation_contract": {
            "allowed_changed_paths": ["MANAGPRE.EXE"],
            "database_asset_paths_must_match_baseline": True,
        },
        "base_tree": {
            "inventory_fingerprint": base_inventory["files_fingerprint"],
            "file_count": base_inventory["file_count"],
            "total_bytes": base_inventory["total_bytes"],
        },
        "output_tree": {
            "inventory_fingerprint": output_inventory["files_fingerprint"],
            "file_count": output_inventory["file_count"],
            "total_bytes": output_inventory["total_bytes"],
        },
        "builder": {
            "variant_builder_sha256": pipeline.sha256_file(Path(__file__).resolve()),
            "calendar_patcher_sha256": pipeline.sha256_file(ROOT / "tools" / "pm99_calendar_patcher.py"),
        },
        "receipts": dict(sorted(receipts.items())),
    }


def validate_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version", "release_class", "variant_id", "target_season", "content_baseline",
        "calendar", "mutation_contract", "base_tree", "output_tree", "builder", "receipts",
    }
    if set(value) != expected:
        raise PlaytestVariantError("provisional manifest has an invalid key set")
    if value["schema_version"] != SCHEMA or value["release_class"] != RELEASE_CLASS:
        raise PlaytestVariantError("provisional manifest has an unsupported schema or release class")
    _identifier(value["variant_id"], label="variant_id")
    target_season = _normalise_season(value["target_season"])
    if target_season != value["target_season"]:
        raise PlaytestVariantError("target_season must be canonical YYYY-YY")

    baseline = value["content_baseline"]
    if not isinstance(baseline, dict) or set(baseline) != {
        "release_id", "season", "database_content", "historical_status", "limitations"
    }:
        raise PlaytestVariantError("content_baseline has an invalid key set")
    _identifier(baseline["release_id"], label="content_baseline.release_id")
    if _normalise_season(baseline["season"]) != baseline["season"]:
        raise PlaytestVariantError("content_baseline.season must be canonical YYYY-YY")
    if baseline["database_content"] != "byte-identical-except-calendar-executable":
        raise PlaytestVariantError("content_baseline.database_content is invalid")
    if baseline["historical_status"] != "not-historically-authored-for-target-season":
        raise PlaytestVariantError("content_baseline.historical_status is invalid")
    if not isinstance(baseline["limitations"], list) or not all(
        isinstance(item, str) and item for item in baseline["limitations"]
    ):
        raise PlaytestVariantError("content_baseline.limitations must be a non-empty string list")

    calendar_value = value["calendar"]
    if not isinstance(calendar_value, dict) or set(calendar_value) != {
        "profile", "pristine_input_sha256", "baseline_start_year", "baseline_executable_sha256",
        "target_start_year", "target_rollover_year", "target_executable_sha256", "patch_count",
    }:
        raise PlaytestVariantError("calendar has an invalid key set")
    if calendar_value["profile"] != "managpre-calendar-1998-99-to-target-v1":
        raise PlaytestVariantError("calendar profile is unsupported")
    for label in ("pristine_input_sha256", "baseline_executable_sha256", "target_executable_sha256"):
        _sha256(calendar_value[label], label=f"calendar.{label}")
    if calendar_value["baseline_start_year"] != _start_year(baseline["season"]):
        raise PlaytestVariantError("calendar baseline year does not match content baseline season")
    if calendar_value["target_start_year"] != _start_year(target_season):
        raise PlaytestVariantError("calendar target year does not match target season")
    if calendar_value["target_rollover_year"] != calendar_value["target_start_year"] + 1:
        raise PlaytestVariantError("calendar target rollover year is not consecutive")
    if not isinstance(calendar_value["patch_count"], int) or calendar_value["patch_count"] <= 0:
        raise PlaytestVariantError("calendar patch_count must be positive")

    mutation = value["mutation_contract"]
    if mutation != {
        "allowed_changed_paths": ["MANAGPRE.EXE"],
        "database_asset_paths_must_match_baseline": True,
    }:
        raise PlaytestVariantError("mutation_contract must permit only MANAGPRE.EXE")
    for label in ("base_tree", "output_tree"):
        tree = value[label]
        if not isinstance(tree, dict) or set(tree) != {"inventory_fingerprint", "file_count", "total_bytes"}:
            raise PlaytestVariantError(f"{label} has an invalid key set")
        _sha256(tree["inventory_fingerprint"], label=f"{label}.inventory_fingerprint")
        if not isinstance(tree["file_count"], int) or tree["file_count"] <= 0:
            raise PlaytestVariantError(f"{label}.file_count must be positive")
        if not isinstance(tree["total_bytes"], int) or tree["total_bytes"] <= 0:
            raise PlaytestVariantError(f"{label}.total_bytes must be positive")
    builder = value["builder"]
    if not isinstance(builder, dict) or set(builder) != {"variant_builder_sha256", "calendar_patcher_sha256"}:
        raise PlaytestVariantError("builder has an invalid key set")
    for label, digest in builder.items():
        _sha256(digest, label=f"builder.{label}")
    receipts = value["receipts"]
    if not isinstance(receipts, dict) or set(receipts) != set(RECEIPT_NAMES):
        raise PlaytestVariantError("receipts must name every canonical provisional receipt")
    for label, digest in receipts.items():
        _sha256(digest, label=f"receipts.{label}")
    return dict(value)


def create_variant(
    *, source_game_root: Path, calendar_source_exe: Path, output_root: Path,
    variant_id: str, baseline_id: str, baseline_season: str, target_season: str,
    skip_database_validation: bool = False,
) -> dict[str, Any]:
    """Materialise one fresh provisional calendar-only variant."""

    variant_id = _identifier(variant_id, label="variant_id")
    baseline_id = _identifier(baseline_id, label="baseline_id")
    baseline_season = _normalise_season(baseline_season)
    target_season = _normalise_season(target_season)
    source_game_root = resolve_game_root(source_game_root, require_writable=False)
    if source_game_root is None:  # Defensive; required=True is the default.
        raise PlaytestVariantError("source game root is required")
    calendar_source_exe = calendar_source_exe.expanduser().resolve()
    calendar_source_sha256 = pipeline.sha256_file(calendar_source_exe)
    output_root = output_root.expanduser().resolve()
    variant_root = output_root / variant_id
    if variant_root.exists() or variant_root.is_symlink():
        raise PlaytestVariantError(f"refusing to replace existing variant root: {variant_root}")
    if variant_root == source_game_root or source_game_root.is_relative_to(variant_root):
        raise PlaytestVariantError("variant root must not contain the source game root")

    base_inventory = pipeline.build_tree_inventory(source_game_root)
    source_exe_sha256 = pipeline.sha256_file(source_game_root / "MANAGPRE.EXE")
    variant_root.mkdir(parents=True)
    game_root = variant_root / "game"
    receipts_dir = variant_root / "receipts"
    receipts_dir.mkdir()
    _copy_game_tree(source_game_root, game_root)

    baseline_preview = receipts_dir / "baseline-calendar.exe"
    baseline_calendar = _calendar_contract(
        calendar.patch_calendar(calendar_source_exe, baseline_preview, _start_year(baseline_season)),
        expected_start_year=_start_year(baseline_season),
    )
    if baseline_calendar["before_sha256"] != calendar_source_sha256:
        raise PlaytestVariantError("calendar patcher used an unexpected pristine executable")
    if baseline_calendar["after_sha256"] != source_exe_sha256:
        raise PlaytestVariantError(
            "source game executable is not the verified calendar output for its declared baseline season"
        )

    target_exe = game_root / "MANAGPRE.EXE"
    # The just-created copy is the only file removed.  The source tree was
    # independently inventoried before copying and is checked again below.
    target_exe.unlink()
    target_calendar = _calendar_contract(
        calendar.patch_calendar(calendar_source_exe, target_exe, _start_year(target_season)),
        expected_start_year=_start_year(target_season),
    )
    if target_calendar["before_sha256"] != calendar_source_sha256:
        raise PlaytestVariantError("calendar patcher used an unexpected pristine executable")

    source_after = pipeline.build_tree_inventory(source_game_root)
    if source_after["files_fingerprint"] != base_inventory["files_fingerprint"]:
        raise PlaytestVariantError("source game tree changed while creating the variant")
    output_inventory = pipeline.build_tree_inventory(game_root)
    difference = _assert_calendar_only_difference(
        base_inventory=base_inventory,
        output_inventory=output_inventory,
        baseline_exe_sha256=source_exe_sha256,
        target_exe_sha256=target_calendar["after_sha256"],
    )

    validation_path = receipts_dir / "database-validation.json"
    if not skip_database_validation:
        validation = _run_database_validation(game_root)
        _write_validation(validation_path, validation)
        if validation["returncode"] != 0:
            raise PlaytestVariantError("validate-database failed; partial variant evidence was retained")

    receipt_hashes: dict[str, str] = {}
    _, receipt_hashes["base_inventory"] = _write_receipt(receipts_dir, "base_inventory", base_inventory)
    _, receipt_hashes["output_inventory"] = _write_receipt(receipts_dir, "output_inventory", output_inventory)
    _, receipt_hashes["tree_difference"] = _write_receipt(receipts_dir, "tree_difference", difference)
    _, receipt_hashes["baseline_calendar"] = _write_receipt(receipts_dir, "baseline_calendar", baseline_calendar)
    _, receipt_hashes["target_calendar"] = _write_receipt(receipts_dir, "target_calendar", target_calendar)
    manifest = _manifest(
        variant_id=variant_id,
        target_season=target_season,
        baseline_id=baseline_id,
        baseline_season=baseline_season,
        base_inventory=base_inventory,
        output_inventory=output_inventory,
        receipts=receipt_hashes,
        baseline_calendar=baseline_calendar,
        target_calendar=target_calendar,
    )
    validate_manifest(manifest)
    manifest_path = variant_root / MANIFEST_NAME
    manifest_sha256 = pipeline.write_canonical_json(manifest_path, manifest)
    return {
        "ok": True,
        "variant_id": variant_id,
        "target_season": target_season,
        "release_class": RELEASE_CLASS,
        "variant_root": str(variant_root),
        "game_root": str(game_root),
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha256,
        "changed_paths": [row["path"] for row in difference["changed"]],
        "database_validation": "skipped" if skip_database_validation else str(validation_path),
    }


def verify_variant(*, variant_root: Path, run_database_validation: bool = False) -> dict[str, Any]:
    """Verify a created variant without modifying its game tree."""

    variant_root = variant_root.expanduser().resolve()
    manifest_path = variant_root / MANIFEST_NAME
    manifest = validate_manifest(_canonical_read(manifest_path, label="provisional manifest"))
    receipts_dir = variant_root / "receipts"
    receipt_values: dict[str, dict[str, Any]] = {}
    for key, filename in RECEIPT_NAMES.items():
        receipt_path = receipts_dir / filename
        actual_sha256 = pipeline.sha256_file(receipt_path)
        if actual_sha256 != manifest["receipts"][key]:
            raise PlaytestVariantError(f"receipt hash mismatch for {key}")
        receipt_values[key] = _canonical_read(receipt_path, label=f"{key} receipt")

    base_inventory = pipeline.validate_inventory(receipt_values["base_inventory"])
    expected_output = pipeline.validate_inventory(receipt_values["output_inventory"])
    actual_output = pipeline.build_tree_inventory(variant_root / "game")
    if actual_output["files_fingerprint"] != expected_output["files_fingerprint"]:
        raise PlaytestVariantError("variant game tree does not match its locked output inventory")
    baseline_calendar = _calendar_contract(
        receipt_values["baseline_calendar"], expected_start_year=manifest["calendar"]["baseline_start_year"]
    )
    target_calendar = _calendar_contract(
        receipt_values["target_calendar"], expected_start_year=manifest["calendar"]["target_start_year"]
    )
    if baseline_calendar["after_sha256"] != manifest["calendar"]["baseline_executable_sha256"]:
        raise PlaytestVariantError("baseline calendar receipt does not match manifest")
    if target_calendar["after_sha256"] != manifest["calendar"]["target_executable_sha256"]:
        raise PlaytestVariantError("target calendar receipt does not match manifest")
    calculated_difference = _assert_calendar_only_difference(
        base_inventory=base_inventory,
        output_inventory=actual_output,
        baseline_exe_sha256=baseline_calendar["after_sha256"],
        target_exe_sha256=target_calendar["after_sha256"],
    )
    locked_difference = receipt_values["tree_difference"]
    if pipeline.canonical_json_bytes(calculated_difference) != pipeline.canonical_json_bytes(locked_difference):
        raise PlaytestVariantError("locked tree difference does not match the game tree")
    for label, inventory in (("base_tree", base_inventory), ("output_tree", actual_output)):
        expected = manifest[label]
        if (
            expected["inventory_fingerprint"] != inventory["files_fingerprint"]
            or expected["file_count"] != inventory["file_count"]
            or expected["total_bytes"] != inventory["total_bytes"]
        ):
            raise PlaytestVariantError(f"manifest {label} does not match its inventory")

    validation_result: str | None = None
    if run_database_validation:
        validation = _run_database_validation(variant_root / "game")
        if validation["returncode"] != 0:
            raise PlaytestVariantError("validate-database failed during verification")
        validation_result = "passed"
    return {
        "ok": True,
        "variant_id": manifest["variant_id"],
        "target_season": manifest["target_season"],
        "game_root": str(variant_root / "game"),
        "manifest_path": str(manifest_path),
        "changed_paths": [row["path"] for row in calculated_difference["changed"]],
        "database_validation": validation_result or "not-rerun",
    }


def _matrix_variant_row(manifest: Mapping[str, Any], *, manifest_sha256: str) -> dict[str, Any]:
    baseline = manifest["content_baseline"]
    calendar_value = manifest["calendar"]
    return {
        "season": manifest["target_season"],
        "variant_id": manifest["variant_id"],
        "kind": "calendar-only-provisional",
        "status": "provisional-playtest",
        "manifest_sha256": manifest_sha256,
        "baseline_release_id": baseline["release_id"],
        "baseline_season": baseline["season"],
        "calendar_start_year": calendar_value["target_start_year"],
        "calendar_rollover_year": calendar_value["target_rollover_year"],
        "output_inventory_fingerprint": manifest["output_tree"]["inventory_fingerprint"],
        "allowed_changed_paths": manifest["mutation_contract"]["allowed_changed_paths"],
        "historical_status": baseline["historical_status"],
        "limitations": baseline["limitations"],
    }


def create_matrix(
    *, output_root: Path, baseline_game_root: Path, baseline_id: str,
    baseline_season: str, matrix_id: str, require_target_26: bool,
) -> dict[str, Any]:
    """Write one reviewable matrix index for independently built variants.

    The baseline fills its own target season rather than making a misleading
    zero-delta clone.  Every other row must be an immutable provisional
    manifest built by :func:`create_variant`.
    """

    baseline_id = _identifier(baseline_id, label="baseline_id")
    baseline_season = _normalise_season(baseline_season)
    matrix_id = _identifier(matrix_id, label="matrix_id")
    output_root = output_root.expanduser().resolve()
    if not output_root.is_dir() or output_root.is_symlink():
        raise PlaytestVariantError(f"output_root must be an existing ordinary directory: {output_root}")
    baseline_game_root = resolve_game_root(baseline_game_root, require_writable=False)
    if baseline_game_root is None:
        raise PlaytestVariantError("baseline game root is required")
    baseline_inventory = pipeline.build_tree_inventory(baseline_game_root)

    rows: list[dict[str, Any]] = [
        {
            "season": baseline_season,
            "variant_id": baseline_id,
            "kind": "known-good-baseline",
            "status": "known-good",
            "manifest_sha256": None,
            "baseline_release_id": baseline_id,
            "baseline_season": baseline_season,
            "calendar_start_year": _start_year(baseline_season),
            "calendar_rollover_year": _start_year(baseline_season) + 1,
            "output_inventory_fingerprint": baseline_inventory["files_fingerprint"],
            "allowed_changed_paths": [],
            "historical_status": "historically-authored-known-good-baseline",
            "limitations": [],
        }
    ]
    for directory in sorted(output_root.iterdir(), key=lambda path: path.name):
        if not directory.is_dir() or directory.is_symlink():
            continue
        manifest_path = directory / MANIFEST_NAME
        if not manifest_path.is_file() or manifest_path.is_symlink():
            continue
        raw_manifest = _canonical_read(manifest_path, label=f"variant manifest {directory.name}")
        manifest = validate_manifest(raw_manifest)
        if manifest["content_baseline"]["release_id"] != baseline_id:
            raise PlaytestVariantError(f"variant {directory.name} uses a different baseline release")
        if manifest["content_baseline"]["season"] != baseline_season:
            raise PlaytestVariantError(f"variant {directory.name} uses a different baseline season")
        rows.append(
            _matrix_variant_row(
                manifest,
                manifest_sha256=pipeline.sha256_file(manifest_path),
            )
        )
    rows.sort(key=lambda row: row["season"])
    seasons = [row["season"] for row in rows]
    if len(seasons) != len(set(seasons)):
        raise PlaytestVariantError("matrix has duplicate target seasons")
    if require_target_26 and tuple(seasons) != TARGET_26_SEASONS:
        missing = [season for season in TARGET_26_SEASONS if season not in seasons]
        extra = [season for season in seasons if season not in TARGET_26_SEASONS]
        raise PlaytestVariantError(
            "target 26 matrix is incomplete or out of scope: "
            + json.dumps({"missing": missing, "extra": extra}, sort_keys=True)
        )
    matrix = {
        "schema_version": MATRIX_SCHEMA,
        "matrix_id": matrix_id,
        "purpose": "Mass review and launch selection only; variant rows are not historical target-season database claims.",
        "baseline": {
            "release_id": baseline_id,
            "season": baseline_season,
            "inventory_fingerprint": baseline_inventory["files_fingerprint"],
            "file_count": baseline_inventory["file_count"],
            "total_bytes": baseline_inventory["total_bytes"],
        },
        "target_seasons": list(TARGET_26_SEASONS),
        "variants": rows,
    }
    matrix_path = output_root / f"{matrix_id}.json"
    matrix_sha256 = pipeline.write_canonical_json(matrix_path, matrix)
    return {
        "ok": True,
        "matrix_path": str(matrix_path),
        "matrix_sha256": matrix_sha256,
        "variant_count": len(rows),
        "seasons": seasons,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="create one fresh calendar-only provisional variant")
    create.add_argument("--source-game-root", required=True, type=Path)
    create.add_argument("--calendar-source-exe", required=True, type=Path)
    create.add_argument("--output-root", required=True, type=Path)
    create.add_argument("--variant-id", required=True)
    create.add_argument("--baseline-id", required=True)
    create.add_argument("--baseline-season", required=True)
    create.add_argument("--target-season", required=True)
    create.add_argument("--skip-database-validation", action="store_true")
    verify = commands.add_parser("verify", help="verify an existing provisional variant without changing it")
    verify.add_argument("--variant-root", required=True, type=Path)
    verify.add_argument("--run-database-validation", action="store_true")
    matrix = commands.add_parser("matrix", help="write one mass-review index for existing provisional variants")
    matrix.add_argument("--output-root", required=True, type=Path)
    matrix.add_argument("--baseline-game-root", required=True, type=Path)
    matrix.add_argument("--baseline-id", required=True)
    matrix.add_argument("--baseline-season", required=True)
    matrix.add_argument("--matrix-id", default="pm99-2000-2025-provisional-playtest-r0")
    matrix.add_argument("--require-target-26", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "create":
            result = create_variant(
                source_game_root=args.source_game_root,
                calendar_source_exe=args.calendar_source_exe,
                output_root=args.output_root,
                variant_id=args.variant_id,
                baseline_id=args.baseline_id,
                baseline_season=args.baseline_season,
                target_season=args.target_season,
                skip_database_validation=bool(args.skip_database_validation),
            )
        elif args.command == "verify":
            result = verify_variant(
                variant_root=args.variant_root,
                run_database_validation=bool(args.run_database_validation),
            )
        else:
            result = create_matrix(
                output_root=args.output_root,
                baseline_game_root=args.baseline_game_root,
                baseline_id=args.baseline_id,
                baseline_season=args.baseline_season,
                matrix_id=args.matrix_id,
                require_target_26=bool(args.require_target_26),
            )
    except (OSError, subprocess.CalledProcessError, calendar.PatchError, pipeline.PipelineError, PlaytestVariantError) as exc:
        print(f"provisional playtest variant error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
