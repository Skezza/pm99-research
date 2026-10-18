#!/usr/bin/env python3
"""Fail-closed local build-plan runner for PM99 Season Pipeline V2.

The V2 metadata module records a completed release.  This companion module
materialises one from a canonical, path-free plan:

* verify the declared pristine base and canonical season package;
* copy the base into a new, disposable materialisation directory;
* run only hashed, explicitly declared local adapter commands, without a shell;
* permit each stage to change only its declared non-overlapping file paths;
* verify every declared stage output inventory and the final tree inventory; and
* write the standard V2 release manifest plus a plan receipt outside the game.

It does not adapt or invoke the current 2015-specific compiler.  Each legacy
writer needs a small deterministic adapter first; see the companion document.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_pipeline_v2 as pipeline


BUILD_PLAN_SCHEMA = "pm99-season-build-plan-v2"
BUILD_PLAN_RECEIPT_SCHEMA = "pm99-season-build-plan-receipt-v2"

_COMMAND_SPEC_KEYS = {"id", "sha256", "args", "timeout_seconds"}
_STAGE_KEYS = {
    "id",
    "order",
    "command",
    "outputs",
    "expected_receipt",
    "expected_output_inventory",
}
_PLAN_KEYS = {
    "schema",
    "season",
    "base",
    "season_package",
    "external_artifacts",
    "forbidden_runtime_state_directories",
    "stages",
    "expected_final_output_inventory",
}
_FORBIDDEN_RUNTIME_DIRS = frozenset(
    {"cache", "runtime", "save", "savegame", "savegames", "saves", "temp", "tmp"}
)
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[a-zA-Z]:[\\/]")
_PLACEHOLDERS = {"{base-tree}", "{materialisation-tree}", "{season-package}"}
_EXTERNAL_ARTIFACT_PLACEHOLDER_RE = re.compile(
    r"^\{external-artifact:([a-z][a-z0-9_.-]{0,127})\}$"
)


class BuildPlanError(pipeline.PipelineError):
    """A build-plan-specific release invariant was not met."""


def _safe_relative_file(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise BuildPlanError(f"{label} must be a non-empty relative file path")
    if "\x00" in value or "\\" in value:
        raise BuildPlanError(f"{label} must use a safe POSIX relative path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts or value != pure.as_posix():
        raise BuildPlanError(f"{label} must use a safe POSIX relative path: {value!r}")
    if value.endswith("/"):
        raise BuildPlanError(f"{label} must name a file, not a directory: {value!r}")
    return value


def _safe_literal_argument(value: Any) -> str:
    """Reject path escapes in command arguments before substitution.

    Local adapters can receive normal flags and paths within the materialised
    tree.  The only absolute paths permitted are the three exact placeholders,
    expanded by this module after plan validation.  This is not a sandbox for a
    malicious tool; it prevents accidental output/path escape in a reviewed
    declarative plan.
    """

    if not isinstance(value, str) or not value or "\x00" in value or "\n" in value or "\r" in value:
        raise BuildPlanError("command arguments must be non-empty single-line strings")
    if value in _PLACEHOLDERS or _EXTERNAL_ARTIFACT_PLACEHOLDER_RE.fullmatch(value):
        return value
    fragments = re.split(r"[\\/]", value)
    if ".." in fragments:
        raise BuildPlanError(f"command argument contains a parent traversal: {value!r}")
    # Cover both bare paths and common --flag=/path / --flag=C:\\path forms.
    path_candidate = value.split("=", 1)[-1]
    if (
        value.startswith(("/", "\\"))
        or path_candidate.startswith(("/", "\\"))
        or _WINDOWS_ABSOLUTE_RE.match(value)
        or _WINDOWS_ABSOLUTE_RE.match(path_candidate)
    ):
        raise BuildPlanError(f"command argument contains an undeclared absolute path: {value!r}")
    return value


def _expand_argument(
    value: str,
    *,
    base_tree: Path,
    materialisation_tree: Path,
    season_package: Path,
    external_artifacts: Mapping[str, Path],
) -> str:
    replacements = {
        "{base-tree}": str(base_tree),
        "{materialisation-tree}": str(materialisation_tree),
        "{season-package}": str(season_package),
    }
    if value in replacements:
        return replacements[value]
    external_match = _EXTERNAL_ARTIFACT_PLACEHOLDER_RE.fullmatch(value)
    if external_match is not None:
        artifact_id = external_match.group(1)
        try:
            return str(external_artifacts[artifact_id])
        except KeyError as exc:
            raise BuildPlanError(
                f"command references undeclared external artifact: {artifact_id}"
            ) from exc
    return value


def _validate_runtime_directories(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise BuildPlanError("forbidden_runtime_state_directories must be a non-empty list")
    normalised: list[str] = []
    for item in value:
        if not isinstance(item, str) or not re.fullmatch(r"[A-Z0-9_.-]{1,64}", item):
            raise BuildPlanError("forbidden runtime directory names must be uppercase simple names")
        normalised.append(item)
    if normalised != sorted(set(normalised)):
        raise BuildPlanError("forbidden runtime directory names must be unique and sorted")
    actual = {item.casefold() for item in normalised}
    if not _FORBIDDEN_RUNTIME_DIRS.issubset(actual):
        missing = sorted(_FORBIDDEN_RUNTIME_DIRS - actual)
        raise BuildPlanError(f"plan cannot omit required runtime-state directory guards: {missing}")
    return normalised


def _validate_command_spec(value: Any, *, stage_id: str, receipt: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _COMMAND_SPEC_KEYS:
        raise BuildPlanError(f"stage {stage_id} command has invalid keys")
    command_id = pipeline._require_identifier(value["id"], label=f"stage {stage_id} command id")
    command_hash = pipeline._require_sha256(value["sha256"], label=f"stage {stage_id} command hash")
    if command_hash != receipt["implementation_sha256"]:
        raise BuildPlanError(
            f"stage {stage_id} command hash must match expected receipt implementation hash"
        )
    args = value["args"]
    if not isinstance(args, list):
        raise BuildPlanError(f"stage {stage_id} command args must be a list")
    normalised_args = [_safe_literal_argument(item) for item in args]
    timeout = value["timeout_seconds"]
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 3600:
        raise BuildPlanError(f"stage {stage_id} timeout_seconds must be an integer in 1..3600")
    return {
        "id": command_id,
        "sha256": command_hash,
        "args": normalised_args,
        "timeout_seconds": timeout,
    }


def _validate_declared_output_inventory(
    inventory: Any, *, outputs: Sequence[str], label: str
) -> dict[str, Any]:
    inventory = pipeline.validate_inventory(inventory)
    actual_paths = [entry["path"] for entry in inventory["files"]]
    if actual_paths != list(outputs):
        raise BuildPlanError(
            f"{label} paths must exactly equal its declared outputs; "
            f"expected {list(outputs)!r}, got {actual_paths!r}"
        )
    return inventory


def validate_build_plan(plan: Any) -> dict[str, Any]:
    """Validate a complete canonical plan before touching the game tree."""

    if not isinstance(plan, dict) or set(plan) != _PLAN_KEYS:
        raise BuildPlanError(
            f"build plan keys must be exactly {sorted(_PLAN_KEYS)}"
        )
    if plan["schema"] != BUILD_PLAN_SCHEMA:
        raise BuildPlanError(f"unsupported build plan schema: {plan['schema']!r}")
    season = pipeline.normalise_season_id(plan["season"])
    if season != plan["season"]:
        raise BuildPlanError("build plan season must already be canonical YYYY-YY")

    base = plan["base"]
    if not isinstance(base, dict) or set(base) != {"base_id", "inventory_fingerprint"}:
        raise BuildPlanError("build plan base must contain base_id and inventory_fingerprint")
    pipeline._require_identifier(base["base_id"], label="build plan base_id")
    pipeline._require_sha256(base["inventory_fingerprint"], label="build plan base fingerprint")

    package = plan["season_package"]
    package_keys = {"canonical_sha256", "canonical_size", "schema"}
    if not isinstance(package, dict) or set(package) != package_keys:
        raise BuildPlanError("build plan season_package has invalid keys")
    pipeline._require_sha256(package["canonical_sha256"], label="build plan package hash")
    if not isinstance(package["canonical_size"], int) or isinstance(package["canonical_size"], bool) or package["canonical_size"] < 2:
        raise BuildPlanError("build plan season_package canonical_size must be at least two")
    if package["schema"] is not None and not isinstance(package["schema"], str):
        raise BuildPlanError("build plan season_package schema must be a string or null")

    artifacts = pipeline.normalise_external_artifacts(plan["external_artifacts"])
    if plan["external_artifacts"] != artifacts:
        raise BuildPlanError("build plan external artifacts must be ID-sorted and canonical")
    forbidden_dirs = _validate_runtime_directories(plan["forbidden_runtime_state_directories"])

    stages = plan["stages"]
    if not isinstance(stages, list) or not stages:
        raise BuildPlanError("build plan must declare at least one ordered stage")
    normalised_stages: list[dict[str, Any]] = []
    declared_outputs: list[str] = []
    stage_ids: set[str] = set()
    for expected_order, stage in enumerate(stages, start=1):
        if not isinstance(stage, dict) or set(stage) != _STAGE_KEYS:
            raise BuildPlanError(f"stage {expected_order} has invalid keys")
        stage_id = pipeline._require_identifier(stage["id"], label=f"stage {expected_order} id")
        if stage_id in stage_ids:
            raise BuildPlanError(f"duplicate stage id: {stage_id}")
        stage_ids.add(stage_id)
        if stage["order"] != expected_order:
            raise BuildPlanError(
                f"stage {stage_id} order must be contiguous and match list order ({expected_order})"
            )
        receipt = pipeline.validate_stage_record(stage["expected_receipt"])
        if receipt["id"] != stage_id:
            raise BuildPlanError(f"stage {stage_id} receipt id does not match stage id")
        expected_inputs = receipt["input_fingerprints"]
        if expected_inputs.get("base-tree") != base["inventory_fingerprint"]:
            raise BuildPlanError(f"stage {stage_id} receipt must lock the build-plan base-tree fingerprint")
        if expected_inputs.get("season-package") != package["canonical_sha256"]:
            raise BuildPlanError(f"stage {stage_id} receipt must lock the build-plan season-package hash")
        outputs = stage["outputs"]
        if not isinstance(outputs, list) or not outputs:
            raise BuildPlanError(f"stage {stage_id} must declare at least one output file")
        normalised_outputs = [_safe_relative_file(item, label=f"stage {stage_id} output") for item in outputs]
        if normalised_outputs != sorted(set(normalised_outputs)):
            raise BuildPlanError(f"stage {stage_id} outputs must be unique and path-sorted")
        for output in normalised_outputs:
            for existing in declared_outputs:
                if output == existing or output.startswith(existing + "/") or existing.startswith(output + "/"):
                    raise BuildPlanError(
                        f"stage output paths overlap: {existing!r} and {output!r}"
                    )
        declared_outputs.extend(normalised_outputs)
        expected_output_inventory = _validate_declared_output_inventory(
            stage["expected_output_inventory"], outputs=normalised_outputs,
            label=f"stage {stage_id} expected_output_inventory",
        )
        command = _validate_command_spec(stage["command"], stage_id=stage_id, receipt=receipt)
        normalised_stages.append(
            {
                "id": stage_id,
                "order": expected_order,
                "command": command,
                "outputs": normalised_outputs,
                "expected_receipt": receipt,
                "expected_output_inventory": expected_output_inventory,
            }
        )

    final_inventory = pipeline.validate_inventory(plan["expected_final_output_inventory"])
    final_paths = {entry["path"] for entry in final_inventory["files"]}
    missing_outputs = set(declared_outputs) - final_paths
    if missing_outputs:
        raise BuildPlanError(
            "expected final output inventory omits declared stage output(s): "
            f"{sorted(missing_outputs)}"
        )
    for path in final_paths:
        if any(component.casefold() in {item.casefold() for item in forbidden_dirs} for component in PurePosixPath(path).parts[:-1]):
            raise BuildPlanError(f"expected final inventory contains a runtime-state directory: {path}")

    return {
        "schema": BUILD_PLAN_SCHEMA,
        "season": season,
        "base": {"base_id": base["base_id"], "inventory_fingerprint": base["inventory_fingerprint"]},
        "season_package": package,
        "external_artifacts": artifacts,
        "forbidden_runtime_state_directories": forbidden_dirs,
        "stages": normalised_stages,
        "expected_final_output_inventory": final_inventory,
    }


def load_canonical_build_plan(path: Path) -> tuple[dict[str, Any], str]:
    """Load a strictly canonical JSON plan and return it with its content hash."""

    path = path.expanduser()
    if not path.is_file() or path.is_symlink():
        raise BuildPlanError(f"build plan must be a regular non-symlink file: {path}")
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildPlanError(f"build plan is not valid UTF-8 JSON: {path}") from exc
    canonical = pipeline.canonical_json_bytes(value) + b"\n"
    if raw != canonical:
        raise BuildPlanError(
            "build plan must be stored as canonical JSON (sorted keys, compact separators, trailing newline)"
        )
    validated = validate_build_plan(value)
    return validated, pipeline.canonical_json_sha256(validated)


def write_canonical_build_plan(path: Path, plan: Mapping[str, Any]) -> str:
    """Validate and write a new canonical plan; useful for plan generators/tests."""

    validated = validate_build_plan(dict(plan))
    return pipeline.write_canonical_json(path, validated)


def _directory_set(root: Path) -> set[str]:
    if root.is_symlink():
        raise BuildPlanError(f"tree root must not be a symlink: {root}")
    directories = {""}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise BuildPlanError(f"materialisation tree contains a symlink: {path}")
        if path.is_dir():
            directories.add(path.relative_to(root).as_posix())
    return directories


def _assert_no_runtime_state_directories(root: Path, forbidden: Sequence[str]) -> None:
    forbidden_folded = {name.casefold() for name in forbidden}
    for relative in _directory_set(root):
        if not relative:
            continue
        for component in PurePosixPath(relative).parts:
            if component.casefold() in forbidden_folded:
                raise BuildPlanError(
                    f"runtime-state directory is forbidden in a materialisation: {relative}"
                )


def _assert_directories_are_declared(
    root: Path, *, initial_directories: set[str], declared_outputs: Sequence[str]
) -> None:
    allowed = set(initial_directories)
    for output in declared_outputs:
        pure = PurePosixPath(output)
        for index in range(1, len(pure.parts)):
            allowed.add(PurePosixPath(*pure.parts[:index]).as_posix())
    unexpected = sorted(_directory_set(root) - allowed)
    if unexpected:
        raise BuildPlanError(
            "materialisation created undeclared directory/directories: " + ", ".join(unexpected)
        )


def _build_declared_output_inventory(root: Path, outputs: Sequence[str]) -> dict[str, Any]:
    """Build an inventory for exactly a stage's reviewed files."""

    files: list[dict[str, Any]] = []
    total_bytes = 0
    for relative in outputs:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise BuildPlanError(f"declared stage output is missing or unsafe: {relative}")
        size = path.stat().st_size
        files.append({"path": relative, "sha256": pipeline.sha256_file(path), "size": size})
        total_bytes += size
    inventory = {
        "schema": pipeline.FILE_INVENTORY_SCHEMA,
        "file_count": len(files),
        "total_bytes": total_bytes,
        "files_fingerprint": pipeline.canonical_json_sha256(files),
        "files": files,
    }
    return pipeline.validate_inventory(inventory)


def _assert_inventory_equal(*, actual: Mapping[str, Any], expected: Mapping[str, Any], label: str) -> None:
    difference = pipeline.inventory_difference(actual, expected)
    if not difference["equal"]:
        raise BuildPlanError(f"{label} does not match its expected inventory: {json.dumps(difference, sort_keys=True)}")


def _command_mapping(specifications: Sequence[str], *, required_ids: set[str]) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    for specification in specifications:
        if "=" not in specification:
            raise BuildPlanError("local command must use ID=PATH")
        command_id, raw_path = specification.split("=", 1)
        pipeline._require_identifier(command_id, label="local command id")
        if not raw_path:
            raise BuildPlanError("local command path is empty")
        if command_id in mapping:
            raise BuildPlanError(f"duplicate local command mapping: {command_id}")
        path = Path(raw_path).expanduser()
        if path.is_symlink() or not path.is_file():
            raise BuildPlanError(f"local command must be a regular non-symlink file: {path}")
        path = path.resolve()
        if not os.access(path, os.X_OK):
            raise BuildPlanError(f"local command is not directly executable: {path}")
        mapping[command_id] = path
    if set(mapping) != required_ids:
        raise BuildPlanError(
            "local command mappings must exactly match plan command IDs; "
            f"required {sorted(required_ids)}, got {sorted(mapping)}"
        )
    return mapping


def _artifact_mapping(
    specifications: Sequence[str], *, expected: Sequence[Mapping[str, Any]]
) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    for specification in specifications:
        if "=" not in specification:
            raise BuildPlanError("external artifact must use ID=PATH")
        artifact_id, raw_path = specification.split("=", 1)
        pipeline._require_identifier(artifact_id, label="external artifact id")
        if not raw_path or artifact_id in mapping:
            raise BuildPlanError(f"invalid or duplicate external artifact mapping: {artifact_id!r}")
        mapping[artifact_id] = Path(raw_path).expanduser().resolve()
    expected_by_id = {descriptor["id"]: descriptor for descriptor in expected}
    if set(mapping) != set(expected_by_id):
        raise BuildPlanError(
            "external artifact mappings must exactly match plan artifact IDs; "
            f"required {sorted(expected_by_id)}, got {sorted(mapping)}"
        )
    for artifact_id, path in mapping.items():
        pipeline.verify_external_artifact(path=path, descriptor=expected_by_id[artifact_id])
    return mapping


def _prepare_clean_materialisation(*, base_tree: Path, materialisation_tree: Path, forbidden: Sequence[str]) -> set[str]:
    base_tree = base_tree.expanduser().resolve()
    materialisation_tree = materialisation_tree.expanduser()
    if materialisation_tree.exists() or materialisation_tree.is_symlink():
        raise BuildPlanError(
            f"materialisation tree must not already exist; use a fresh disposable directory: {materialisation_tree}"
        )
    if not materialisation_tree.parent.is_dir() or materialisation_tree.parent.is_symlink():
        raise BuildPlanError("materialisation tree parent must be an existing non-symlink directory")
    _assert_no_runtime_state_directories(base_tree, forbidden)
    shutil.copytree(base_tree, materialisation_tree, symlinks=False, copy_function=shutil.copyfile)
    _assert_no_runtime_state_directories(materialisation_tree, forbidden)
    return _directory_set(materialisation_tree)


def _run_stage(
    *,
    stage: Mapping[str, Any],
    command_path: Path,
    base_tree: Path,
    materialisation_tree: Path,
    season_package: Path,
    external_artifacts: Mapping[str, Path],
    initial_directories: set[str],
    allowed_output_paths: Sequence[str],
    forbidden_dirs: Sequence[str],
) -> dict[str, Any]:
    before = pipeline.build_tree_inventory(materialisation_tree)
    command = stage["command"]
    argv = [
        str(command_path),
        *[
            _expand_argument(
                item,
                base_tree=base_tree,
                materialisation_tree=materialisation_tree,
                season_package=season_package,
                external_artifacts=external_artifacts,
            )
            for item in command["args"]
        ],
    ]
    try:
        completed = subprocess.run(
            argv,
            cwd=materialisation_tree,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
            check=False,
            timeout=command["timeout_seconds"],
        )
    except subprocess.TimeoutExpired as exc:
        raise BuildPlanError(f"stage {stage['id']} exceeded {command['timeout_seconds']} seconds") from exc
    if completed.returncode != 0:
        stdout = completed.stdout[-2000:]
        stderr = completed.stderr[-2000:]
        raise BuildPlanError(
            f"stage {stage['id']} failed with exit {completed.returncode}; "
            f"stdout={stdout!r}; stderr={stderr!r}"
        )

    _assert_no_runtime_state_directories(materialisation_tree, forbidden_dirs)
    _assert_directories_are_declared(
        materialisation_tree,
        initial_directories=initial_directories,
        declared_outputs=allowed_output_paths,
    )
    after = pipeline.build_tree_inventory(materialisation_tree)
    difference = pipeline.inventory_difference(before, after)
    touched = set(difference["only_left"]) | set(difference["only_right"]) | {
        item["path"] for item in difference["changed"]
    }
    undeclared = sorted(touched - set(stage["outputs"]))
    if undeclared:
        raise BuildPlanError(
            f"stage {stage['id']} changed undeclared file(s): {undeclared}"
        )
    actual_outputs = _build_declared_output_inventory(materialisation_tree, stage["outputs"])
    _assert_inventory_equal(
        actual=actual_outputs,
        expected=stage["expected_output_inventory"],
        label=f"stage {stage['id']} output",
    )
    return {
        "id": stage["id"],
        "receipt_sha256": pipeline.canonical_json_sha256(stage["expected_receipt"]),
        "output_inventory_fingerprint": actual_outputs["files_fingerprint"],
        "output_file_count": actual_outputs["file_count"],
    }


def execute_build_plan(
    *,
    plan: Mapping[str, Any],
    plan_sha256: str,
    verified_base: Mapping[str, Any],
    base_tree: Path,
    season_package: Path,
    materialisation_tree: Path,
    metadata_dir: Path,
    local_commands: Mapping[str, Path],
    external_artifacts: Mapping[str, Path],
) -> dict[str, Any]:
    """Materialise and fully verify one release plan.

    The caller normally uses :func:`run_build_plan_from_paths`, which validates
    all file-based arguments first.  This public form makes the policy easy to
    test without a shell or a legacy compiler dependency.
    """

    plan = validate_build_plan(dict(plan))
    pipeline._require_sha256(plan_sha256, label="build plan hash")
    if pipeline.canonical_json_sha256(plan) != plan_sha256:
        raise BuildPlanError("build plan hash does not match canonical plan content")
    verified_base = pipeline.validate_verified_base_descriptor(dict(verified_base))
    for label, raw_path in (
        ("base tree", base_tree),
        ("season package", season_package),
        ("materialisation tree", materialisation_tree),
        ("metadata directory", metadata_dir),
    ):
        if raw_path.expanduser().is_symlink():
            raise BuildPlanError(f"{label} must not be a symlink: {raw_path}")
    base_tree = base_tree.expanduser().resolve()
    season_package = season_package.expanduser().resolve()
    materialisation_tree = materialisation_tree.expanduser().resolve()
    metadata_dir = metadata_dir.expanduser().resolve()
    pipeline._ensure_disjoint_directories(base_tree, materialisation_tree, metadata_dir)

    if verified_base["base_id"] != plan["base"]["base_id"]:
        raise BuildPlanError("verified base ID does not match build plan")
    if verified_base["inventory"]["files_fingerprint"] != plan["base"]["inventory_fingerprint"]:
        raise BuildPlanError("verified base inventory fingerprint does not match build plan")
    pipeline.verify_base_tree(tree=base_tree, verified_base=verified_base)
    package_descriptor = pipeline.canonical_json_document_descriptor(
        season_package, document_id="season-package"
    )
    expected_package = plan["season_package"]
    if {
        "canonical_sha256": package_descriptor["canonical_sha256"],
        "canonical_size": package_descriptor["canonical_size"],
        "schema": package_descriptor["schema"],
    } != expected_package:
        raise BuildPlanError("season package does not match the canonical hash declared by build plan")

    required_command_ids = {stage["command"]["id"] for stage in plan["stages"]}
    if set(local_commands) != required_command_ids:
        raise BuildPlanError("validated local command mapping does not match build plan")
    for stage in plan["stages"]:
        command_path = local_commands[stage["command"]["id"]]
        if command_path.is_symlink() or not command_path.is_file() or not os.access(command_path, os.X_OK):
            raise BuildPlanError(f"local command is not directly executable: {command_path}")
        if pipeline.sha256_file(command_path) != stage["command"]["sha256"]:
            raise BuildPlanError(f"local command hash changed after validation: {stage['command']['id']}")
    expected_artifact_ids = {item["id"] for item in plan["external_artifacts"]}
    if set(external_artifacts) != expected_artifact_ids:
        raise BuildPlanError("validated external artifact mapping does not match build plan")
    for descriptor in plan["external_artifacts"]:
        pipeline.verify_external_artifact(path=external_artifacts[descriptor["id"]], descriptor=descriptor)

    initial_directories = _prepare_clean_materialisation(
        base_tree=base_tree,
        materialisation_tree=materialisation_tree,
        forbidden=plan["forbidden_runtime_state_directories"],
    )
    _assert_inventory_equal(
        actual=pipeline.build_tree_inventory(materialisation_tree),
        expected=verified_base["inventory"],
        label="fresh materialisation base copy",
    )
    stage_results: list[dict[str, Any]] = []
    allowed_output_paths: list[str] = []
    for stage in plan["stages"]:
        allowed_output_paths.extend(stage["outputs"])
        stage_results.append(
            _run_stage(
                stage=stage,
                command_path=local_commands[stage["command"]["id"]],
                base_tree=base_tree,
                materialisation_tree=materialisation_tree,
                season_package=season_package,
                external_artifacts=external_artifacts,
                initial_directories=initial_directories,
                allowed_output_paths=allowed_output_paths,
                forbidden_dirs=plan["forbidden_runtime_state_directories"],
            )
        )
    final_inventory = pipeline.build_tree_inventory(materialisation_tree)
    _assert_inventory_equal(
        actual=final_inventory,
        expected=plan["expected_final_output_inventory"],
        label="final materialisation",
    )

    # This writes the standard path-free Season Pipeline V2 manifest.  The
    # metadata directory remains outside both game trees by contract.
    release = pipeline.write_release_metadata(
        season=plan["season"],
        base_tree=base_tree,
        verified_base=verified_base,
        season_package=season_package,
        output_tree=materialisation_tree,
        metadata_dir=metadata_dir,
        external_artifacts=plan["external_artifacts"],
        stages=[stage["expected_receipt"] for stage in plan["stages"]],
    )
    plan_receipt = {
        "schema": BUILD_PLAN_RECEIPT_SCHEMA,
        "plan_sha256": plan_sha256,
        "season": plan["season"],
        "base_inventory_fingerprint": verified_base["inventory"]["files_fingerprint"],
        "season_package_canonical_sha256": package_descriptor["canonical_sha256"],
        "stages": stage_results,
        "final_output_inventory_fingerprint": final_inventory["files_fingerprint"],
        "release_manifest_sha256": pipeline.canonical_json_sha256(release["manifest"]),
    }
    plan_receipt_path = metadata_dir / "build-plan-receipt.json"
    pipeline.write_canonical_json(plan_receipt_path, plan_receipt)
    return {
        "materialisation_tree": str(materialisation_tree),
        "metadata": release["paths"],
        "build_plan_receipt": str(plan_receipt_path),
        "final_inventory": final_inventory,
        "manifest": release["manifest"],
    }


def run_build_plan_from_paths(
    *,
    plan_path: Path,
    verified_base_path: Path,
    base_tree: Path,
    season_package: Path,
    materialisation_tree: Path,
    metadata_dir: Path,
    local_command_specs: Sequence[str],
    external_artifact_specs: Sequence[str],
) -> dict[str, Any]:
    """Load all path-backed inputs and execute a plan with strict mappings."""

    plan, plan_sha256 = load_canonical_build_plan(plan_path)
    verified_base = pipeline.validate_verified_base_descriptor(
        pipeline.read_json_file(verified_base_path)
    )
    required_command_ids = {stage["command"]["id"] for stage in plan["stages"]}
    commands = _command_mapping(local_command_specs, required_ids=required_command_ids)
    artifacts = _artifact_mapping(
        external_artifact_specs, expected=plan["external_artifacts"]
    )
    return execute_build_plan(
        plan=plan,
        plan_sha256=plan_sha256,
        verified_base=verified_base,
        base_tree=base_tree,
        season_package=season_package,
        materialisation_tree=materialisation_tree,
        metadata_dir=metadata_dir,
        local_commands=commands,
        external_artifacts=artifacts,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--verified-base", required=True, type=Path)
    parser.add_argument("--base-tree", required=True, type=Path)
    parser.add_argument("--season-package", required=True, type=Path)
    parser.add_argument("--materialisation-tree", required=True, type=Path)
    parser.add_argument("--metadata-dir", required=True, type=Path)
    parser.add_argument("--local-command", action="append", default=[], metavar="ID=PATH")
    parser.add_argument("--external-artifact", action="append", default=[], metavar="ID=PATH")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_build_plan_from_paths(
            plan_path=args.plan,
            verified_base_path=args.verified_base,
            base_tree=args.base_tree,
            season_package=args.season_package,
            materialisation_tree=args.materialisation_tree,
            metadata_dir=args.metadata_dir,
            local_command_specs=args.local_command,
            external_artifact_specs=args.external_artifact,
        )
    except pipeline.PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "ok": True,
                "materialisation_tree": result["materialisation_tree"],
                "final_inventory": result["final_inventory"]["files_fingerprint"],
                "manifest": result["metadata"]["manifest"],
                "build_plan_receipt": result["build_plan_receipt"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
