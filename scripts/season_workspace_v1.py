#!/usr/bin/env python3
"""One year-neutral entry point for preparing and compiling a PM99 season.

The workspace binds a strict season package to the permanent editorial
timeline and the fail-open portrait policy.  Preparation derives a package
from applicable corrections and always writes machine-readable coverage and
missing-photo reports.  Compilation delegates the proven PM99 binary writes
to Season-Package Compiler V2; it never modifies the canonical source package
or an earlier release tree.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_editorial_timeline_v1 as editorial
from scripts import season_package_compiler_v2 as binary_compiler
from scripts import season_package_v2 as package_v2
from scripts import season_pipeline_v2 as pipeline_v2
from scripts import season_review_v2 as review_v2


SCHEMA = "pm99-season-workspace-v1"
PRECEDENCE = [
    "reviewed-editorial",
    "nearby-season-editorial",
    "fifa-nearest-edition",
    "deterministic-context",
    "preserve-native",
]
SCHEMA_PATH = ROOT / "schemas" / "pm99-season-workspace-v1.schema.json"


class WorkspaceError(ValueError):
    """A season workspace is unsafe, stale, or incomplete."""


def _canonical_bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def _read_canonical(path: Path, *, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkspaceError(f"cannot read {label}: {path}: {exc}") from exc
    if not isinstance(value, dict) or raw != _canonical_bytes(value):
        raise WorkspaceError(f"{label} must be canonical UTF-8 JSON")
    return value


def _schema_errors(value: dict[str, Any]) -> list[str]:
    try:
        import jsonschema  # type: ignore[import-not-found]
    except ImportError:
        return []
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(value),
        key=lambda error: list(error.absolute_path),
    )
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in errors
    ]


def _resolve_file(workspace_path: Path, descriptor: dict[str, Any], *, label: str) -> Path:
    relative = descriptor.get("relative_path")
    digest = descriptor.get("sha256")
    if not isinstance(relative, str) or not isinstance(digest, str):
        raise WorkspaceError(f"{label} has no relative_path/sha256")
    path = (workspace_path.parent / relative).resolve()
    if not path.is_file() or path.is_symlink():
        raise WorkspaceError(f"{label} is not a regular file: {path}")
    actual = package_v2.sha256_file(path)
    if actual != digest:
        raise WorkspaceError(f"{label} hash mismatch: expected {digest}, found {actual}")
    return path


def validate_workspace(value: dict[str, Any], *, workspace_path: Path) -> dict[str, Path]:
    errors = _schema_errors(value)
    package_v2._check_portable_strings(value, errors)
    if value.get("schema_version") != SCHEMA:
        errors.append(f"schema_version must be {SCHEMA!r}")
    if value.get("ratings", {}).get("precedence") != PRECEDENCE:
        errors.append("ratings.precedence must use the published five-tier order")
    if value.get("portraits", {}).get("failure_policy") != "native-no-photo":
        errors.append("portraits.failure_policy must be native-no-photo")
    if value.get("portraits", {}).get("record_missing") is not True:
        errors.append("portraits.record_missing must be true")
    if errors:
        raise WorkspaceError("Season workspace validation failed:\n- " + "\n- ".join(errors))

    package_path = _resolve_file(workspace_path, value["package"], label="season package")
    base_descriptor_path = _resolve_file(
        workspace_path, value["base"]["descriptor"], label="verified base descriptor"
    )
    base_descriptor = pipeline_v2.validate_verified_base_descriptor(
        pipeline_v2.read_json_file(base_descriptor_path)
    )
    timeline_path = _resolve_file(workspace_path, value["editorial"]["timeline"], label="editorial timeline")
    package = package_v2.read_canonical_package(package_path)
    package_v2.validate_package(package, strict=True)
    season = editorial._season_key(package)
    if value["season"] != season:
        raise WorkspaceError(f"workspace season {value['season']!r} does not match package {season!r}")
    timeline = editorial._read(timeline_path, label="editorial timeline")
    editorial.validate_timeline_against_package(timeline, package)
    paths = {
        "package": package_path,
        "timeline": timeline_path,
        "base_descriptor": base_descriptor_path,
    }
    results = value["portraits"].get("results")
    if results is not None:
        paths["portrait_results"] = _resolve_file(workspace_path, results, label="portrait results")
    return paths


def _rating_tier(method: str) -> str:
    text = method.casefold()
    if "review" in text or "editorial" in text and "deterministic" not in text:
        return "reviewed-editorial"
    if "nearby" in text or "continuity" in text:
        return "nearby-season-editorial"
    if "fifa" in text:
        return "fifa-nearest-edition"
    if "deterministic" in text or "fallback" in text:
        return "deterministic-context"
    return "preserve-native"


def build_coverage_report(package: dict[str, Any]) -> dict[str, Any]:
    ratings = Counter(_rating_tier(row["ratings"]["provenance"]["method"]) for row in package["players"])
    portraits = Counter(row["status"] for row in package["assets"]["portraits"])
    preserve_managers = sum(row.get("policy") == "preserve-existing-mode1" for row in package["managers"])
    preserve_clubs = sum(row["opening"].get("policy") == "preserve-existing-mode1" for row in package["clubs"])
    return {
        "schema_version": "pm99-season-coverage-report-v1",
        "package_id": package["package_id"],
        "season": editorial._season_key(package),
        "counts": {
            "clubs": len(package["clubs"]),
            "players": len(package["players"]),
            "managers": len(package["managers"]),
            "preserve_only_foreign_clubs": preserve_clubs,
            "preserve_only_manager_carriers": preserve_managers,
        },
        "rating_precedence": PRECEDENCE,
        "rating_tier_counts": dict(sorted(ratings.items())),
        "portrait_declaration_counts": dict(sorted(portraits.items())),
    }


def _portrait_outcomes(package: dict[str, Any], results_path: Path | None) -> dict[str, dict[str, Any]]:
    if results_path is None:
        return {
            row["player_id"]: {
                "player_id": row["player_id"],
                "status": "applied" if row["status"] == "applied" else "native-no-photo",
                "reason_code": "package-applied" if row["status"] == "applied" else "package-unresolved",
                "reason": row.get("review_reason", "package declares native no-photo"),
            }
            for row in package["assets"]["portraits"]
        }
    value = review_v2.read_portrait_results(results_path, package)
    return {row["player_id"]: row for row in value["results"]}


def build_missing_portrait_report(
    package: dict[str, Any], results_path: Path | None = None,
    *, results_package: dict[str, Any] | None = None,
) -> dict[str, Any]:
    outcomes = _portrait_outcomes(results_package or package, results_path)
    players = {row["id"]: row for row in package["players"]}
    clubs = {row["id"]: row for row in package["clubs"]}
    missing = []
    for player_id, outcome in sorted(outcomes.items()):
        state = outcome.get("resulting_state", outcome.get("status"))
        if state == "applied":
            continue
        player = players[player_id]
        missing.append({
            "player_id": player_id,
            "person_id": player.get("person_id"),
            "player_name": player.get("source_name", player["name"]),
            "club_id": player["club_id"],
            "club_name": clubs[player["club_id"]]["name"],
            "carrier_id": player["carrier_id"],
            "resulting_state": "native-no-photo",
            "reason_code": outcome.get("reason_code", "unspecified"),
            "reason": outcome.get("reason", "portrait unavailable"),
        })
    return {
        "schema_version": "pm99-season-missing-portraits-v1",
        "package_id": package["package_id"],
        "season": editorial._season_key(package),
        "fail_open_policy": "native-no-photo",
        "missing_count": len(missing),
        "players": missing,
    }


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))


def prepare_workspace(*, workspace_path: Path, output_dir: Path) -> dict[str, Any]:
    workspace = _read_canonical(workspace_path, label="season workspace")
    paths = validate_workspace(workspace, workspace_path=workspace_path)
    package = package_v2.read_canonical_package(paths["package"])
    timeline = editorial._read(paths["timeline"], label="editorial timeline")
    overlay = editorial.build_review_overlay(
        package=package,
        timeline=timeline,
        override_id=workspace["editorial"]["override_id"],
    )
    derived, review_receipt = review_v2.apply_overrides(
        package,
        overlay,
        derived_package_id=workspace["editorial"]["derived_package_id"],
    )
    package_v2.validate_package(derived, strict=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "effective_package": output_dir / "season-package.effective.json",
        "editorial_overlay": output_dir / "editorial-overrides.json",
        "editorial_receipt": output_dir / "editorial-application-receipt.json",
        "coverage": output_dir / "coverage-report.json",
        "missing_portraits": output_dir / "missing-portraits.json",
    }
    package_v2.write_canonical_package(outputs["effective_package"], derived)
    _write(outputs["editorial_overlay"], overlay)
    _write(outputs["editorial_receipt"], review_receipt)
    _write(outputs["coverage"], build_coverage_report(derived))
    _write(
        outputs["missing_portraits"],
        build_missing_portrait_report(
            derived,
            paths.get("portrait_results"),
            results_package=package,
        ),
    )
    return {
        "workspace_id": workspace["workspace_id"],
        "season": workspace["season"],
        "effective_package_sha256": package_v2.sha256_file(outputs["effective_package"]),
        "editorial_patch_count": len(overlay["data_patches"]),
        "missing_portrait_count": json.loads(outputs["missing_portraits"].read_text())["missing_count"],
        "outputs": {key: str(value) for key, value in outputs.items()},
    }


def materialise_base_tree(
    *, base_tree: Path, materialisation_tree: Path, link_unchanged: bool
) -> None:
    """Copy a base while never hard-linking files touched by season stages."""

    if materialisation_tree.exists():
        raise WorkspaceError(f"refusing to replace materialisation tree: {materialisation_tree}")
    base_tree = base_tree.resolve()

    def copy_file(source: str, destination: str) -> str:
        source_path = Path(source).resolve()
        relative = source_path.relative_to(base_tree)
        writable = (
            relative.parts[0].casefold() == "dbdat"
            or relative.name.casefold() == "managpre.exe"
        )
        if writable or not link_unchanged:
            return shutil.copy2(source, destination)
        os.link(source, destination)
        return destination

    shutil.copytree(
        base_tree, materialisation_tree, copy_function=copy_file, symlinks=True
    )


def compile_workspace(
    *, workspace_path: Path, base_tree: Path, materialisation_tree: Path,
    output_dir: Path, copy_base: bool, link_unchanged: bool = False,
) -> dict[str, Any]:
    prepared = prepare_workspace(workspace_path=workspace_path, output_dir=output_dir)
    workspace = _read_canonical(workspace_path, label="season workspace")
    paths = validate_workspace(workspace, workspace_path=workspace_path)
    verified_base = pipeline_v2.validate_verified_base_descriptor(
        pipeline_v2.read_json_file(paths["base_descriptor"])
    )
    pipeline_v2.verify_base_tree(tree=base_tree, verified_base=verified_base)
    effective = Path(prepared["outputs"]["effective_package"])
    if copy_base or link_unchanged:
        materialise_base_tree(
            base_tree=base_tree,
            materialisation_tree=materialisation_tree,
            link_unchanged=link_unchanged,
        )
    receipt = binary_compiler.compile_package_to_tree(
        package_path=effective,
        base_tree=base_tree,
        materialisation_tree=materialisation_tree,
    )
    receipt_path = output_dir / "database-compiler-receipt.json"
    binary_compiler.write_canonical_receipt(receipt_path, receipt)
    prepared["database_compiler_receipt"] = str(receipt_path)
    prepared["database_output_hashes"] = {row["path"]: row["sha256"] for row in receipt["outputs"]}
    return prepared


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="verify every hash and contract in a season workspace")
    check.add_argument("--workspace", required=True, type=Path)
    prepare = commands.add_parser("prepare", help="derive the effective package and review reports")
    prepare.add_argument("--workspace", required=True, type=Path)
    prepare.add_argument("--output-dir", required=True, type=Path)
    compile_parser = commands.add_parser("compile", help="prepare and compile a clean game materialisation")
    compile_parser.add_argument("--workspace", required=True, type=Path)
    compile_parser.add_argument("--base-tree", required=True, type=Path)
    compile_parser.add_argument("--materialisation-tree", required=True, type=Path)
    compile_parser.add_argument("--output-dir", required=True, type=Path)
    copy_mode = compile_parser.add_mutually_exclusive_group()
    copy_mode.add_argument("--copy-base", action="store_true")
    copy_mode.add_argument(
        "--link-unchanged",
        action="store_true",
        help="Hard-link read-only assets but physically copy DBDAT and MANAGPRE.EXE",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        workspace_path = args.workspace.resolve()
        if args.command == "check":
            workspace = _read_canonical(workspace_path, label="season workspace")
            paths = validate_workspace(workspace, workspace_path=workspace_path)
            result = {"ok": True, "workspace_id": workspace["workspace_id"], "season": workspace["season"], "inputs": {key: str(value) for key, value in paths.items()}}
        elif args.command == "prepare":
            result = prepare_workspace(workspace_path=workspace_path, output_dir=args.output_dir.resolve())
        else:
            result = compile_workspace(
                workspace_path=workspace_path,
                base_tree=args.base_tree.resolve(),
                materialisation_tree=args.materialisation_tree.resolve(),
                output_dir=args.output_dir.resolve(),
                copy_base=args.copy_base,
                link_unchanged=args.link_unchanged,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    except (WorkspaceError, editorial.TimelineError, package_v2.PackageValidationError, review_v2.SeasonReviewError, binary_compiler.SeasonCompilerError, OSError) as exc:
        print(f"season workspace error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
