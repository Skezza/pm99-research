#!/usr/bin/env python3
"""Create and apply a verified cached-output replay stage for Season Pipeline V2.

This is a bridge for historical releases whose original compiler inputs were
not captured completely.  It deliberately replays approved *output bytes*;
it never claims to regenerate players, portraits or kits from web sources.

The cached bundle is local-only and content addressed.  Its canonical index
locks a verified base tree, a canonical season package and every byte it may
write.  The adapter refuses a different base or package and validates every
blob before touching the new materialisation tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_pipeline_v2 as pipeline


SCHEMA = "pm99-season-cached-replay-v1"
SHA256_LENGTH = 64


class CachedReplayError(ValueError):
    """A retained output bundle is incomplete, malformed or unsafe."""


def _canonical_bytes(value: Any) -> bytes:
    return pipeline.canonical_json_bytes(value) + b"\n"


def _safe_relative(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise CachedReplayError(f"{label} must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts or path.as_posix() != value:
        raise CachedReplayError(f"{label} must be a safe POSIX relative path: {value!r}")
    return value


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return pipeline.sha256_file(path)


def _put_blob(bundle_root: Path, payload: bytes) -> dict[str, Any]:
    digest = _sha256_bytes(payload)
    target = bundle_root / "blobs" / digest[:2] / digest
    if target.exists():
        if target.is_symlink() or not target.is_file() or _sha256_file(target) != digest:
            raise CachedReplayError(f"cached blob is corrupt: {target}")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_bytes(payload)
        temporary.replace(target)
    return {"path": f"blobs/{digest[:2]}/{digest}", "sha256": digest, "size": len(payload)}


def _normalise_include_paths(
    *, reference_tree: Path, include: Iterable[str], include_directories: Iterable[str]
) -> list[str]:
    paths: set[str] = set()
    for raw in include:
        relative = _safe_relative(raw, label="include")
        candidate = reference_tree / relative
        if candidate.is_symlink() or not candidate.is_file():
            raise CachedReplayError(f"included output is not a regular reference file: {relative}")
        paths.add(relative)
    for raw in include_directories:
        directory = _safe_relative(raw, label="include-directory")
        candidate = reference_tree / directory
        if candidate.is_symlink() or not candidate.is_dir():
            raise CachedReplayError(f"included output directory is not a regular directory: {directory}")
        for child in candidate.rglob("*"):
            if child.is_symlink():
                raise CachedReplayError(f"reference output contains a symlink: {child}")
            if child.is_file():
                paths.add(child.relative_to(reference_tree).as_posix())
    if not paths:
        raise CachedReplayError("cached replay needs at least one explicit output path")
    return sorted(paths)


def _bundle_index(
    *, base_tree: Path, season_package: Path, outputs: list[dict[str, Any]]
) -> dict[str, Any]:
    base = pipeline.build_tree_inventory(base_tree)
    package = pipeline.canonical_json_document_descriptor(season_package, document_id="season-package")
    return {
        "schema": SCHEMA,
        "base_inventory_fingerprint": base["files_fingerprint"],
        "season_package_canonical_sha256": package["canonical_sha256"],
        "outputs": outputs,
    }


def _load_index(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise CachedReplayError(f"bundle index must be a regular file: {path}")
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CachedReplayError(f"bundle index is not valid UTF-8 JSON: {path}") from exc
    if raw != _canonical_bytes(value):
        raise CachedReplayError("bundle index must be canonical JSON")
    if not isinstance(value, dict) or set(value) != {
        "schema", "base_inventory_fingerprint", "season_package_canonical_sha256", "outputs"
    }:
        raise CachedReplayError("bundle index has invalid keys")
    if value["schema"] != SCHEMA:
        raise CachedReplayError(f"unsupported cached replay schema: {value.get('schema')!r}")
    pipeline._require_sha256(value["base_inventory_fingerprint"], label="bundle base fingerprint")
    pipeline._require_sha256(value["season_package_canonical_sha256"], label="bundle package hash")
    outputs = value["outputs"]
    if not isinstance(outputs, list) or not outputs:
        raise CachedReplayError("bundle outputs must be a non-empty list")
    previous: str | None = None
    for row in outputs:
        if not isinstance(row, dict) or set(row) != {"path", "blob"}:
            raise CachedReplayError("bundle output has invalid keys")
        relative = _safe_relative(row["path"], label="bundle output path")
        if previous is not None and relative <= previous:
            raise CachedReplayError("bundle outputs must be sorted and unique")
        previous = relative
        blob = row["blob"]
        if not isinstance(blob, dict) or set(blob) != {"path", "sha256", "size"}:
            raise CachedReplayError("bundle output blob has invalid keys")
        blob_path = _safe_relative(blob["path"], label="bundle blob path")
        if not blob_path.startswith("blobs/"):
            raise CachedReplayError("bundle blob must live in blobs/")
        pipeline._require_sha256(blob["sha256"], label=f"bundle blob hash for {relative}")
        if not isinstance(blob["size"], int) or isinstance(blob["size"], bool) or blob["size"] < 0:
            raise CachedReplayError(f"bundle blob size is invalid for {relative}")
    return value


def create_bundle(
    *, base_tree: Path, reference_tree: Path, season_package: Path, bundle_root: Path,
    include: Iterable[str], include_directories: Iterable[str],
) -> dict[str, Any]:
    base_tree = base_tree.expanduser().resolve()
    reference_tree = reference_tree.expanduser().resolve()
    season_package = season_package.expanduser().resolve()
    bundle_root = bundle_root.expanduser().resolve()
    if bundle_root.exists():
        raise CachedReplayError(f"bundle root must not already exist: {bundle_root}")
    # This also rejects symlinks and gives a stable base lock before reading any
    # output.  The reference may be a historical run with other local state;
    # only explicitly selected regular files are retained.
    pipeline.build_tree_inventory(base_tree)
    pipeline.canonical_json_document_descriptor(season_package, document_id="season-package")
    selected = _normalise_include_paths(
        reference_tree=reference_tree, include=include, include_directories=include_directories
    )
    outputs: list[dict[str, Any]] = []
    for relative in selected:
        payload = (reference_tree / relative).read_bytes()
        outputs.append({"path": relative, "blob": _put_blob(bundle_root, payload)})
    index = _bundle_index(base_tree=base_tree, season_package=season_package, outputs=outputs)
    index_path = bundle_root / "index.json"
    index_path.write_bytes(_canonical_bytes(index))
    return {"index": index, "index_path": str(index_path)}


def prepare_clean_base(
    *, source_tree: Path, output_tree: Path, excluded_directories: Iterable[str], base_id: str
) -> dict[str, Any]:
    """Copy a known installation into a clean immutable-build base.

    This operation is deliberately narrow: it may remove named top-level
    runtime directories such as ``SAVE`` but does not normalise or alter game
    files.  Any symlink or special file is rejected instead of copied.
    """
    source_tree = source_tree.expanduser().resolve()
    output_tree = output_tree.expanduser().resolve()
    if output_tree.exists():
        raise CachedReplayError(f"clean base output must not already exist: {output_tree}")
    exclusions = {_safe_relative(item, label="exclude-directory") for item in excluded_directories}
    if any("/" in item for item in exclusions):
        raise CachedReplayError("only top-level runtime directories may be excluded from a base")
    if not exclusions:
        raise CachedReplayError("at least one explicitly reviewed runtime directory must be excluded")
    if source_tree.is_symlink() or not source_tree.is_dir():
        raise CachedReplayError("source base tree must be an existing non-symlink directory")
    for child in source_tree.rglob("*"):
        if child.is_symlink() or (not child.is_file() and not child.is_dir()):
            raise CachedReplayError(f"source base has unsafe filesystem entry: {child}")
    shutil.copytree(
        source_tree,
        output_tree,
        symlinks=False,
        copy_function=shutil.copyfile,
        ignore=shutil.ignore_patterns(*sorted(exclusions)),
    )
    descriptor = pipeline.make_verified_base_descriptor(base_id=base_id, tree=output_tree)
    return {"descriptor": descriptor, "output_tree": str(output_tree)}


def _expected_final_inventory(*, base_tree: Path, index: dict[str, Any]) -> dict[str, Any]:
    base = pipeline.build_tree_inventory(base_tree)
    files = {row["path"]: dict(row) for row in base["files"]}
    for row in index["outputs"]:
        blob = row["blob"]
        files[row["path"]] = {
            "path": row["path"], "sha256": blob["sha256"], "size": blob["size"],
        }
    ordered = [files[path] for path in sorted(files)]
    return pipeline.validate_inventory({
        "schema": pipeline.FILE_INVENTORY_SCHEMA,
        "file_count": len(ordered),
        "total_bytes": sum(row["size"] for row in ordered),
        "files_fingerprint": pipeline.canonical_json_sha256(ordered),
        "files": ordered,
    })


def apply_bundle(*, base_tree: Path, materialisation_tree: Path, season_package: Path, bundle_index: Path) -> None:
    base_tree = base_tree.expanduser().resolve()
    materialisation_tree = materialisation_tree.expanduser().resolve()
    season_package = season_package.expanduser().resolve()
    bundle_index = bundle_index.expanduser().resolve()
    index = _load_index(bundle_index)
    base = pipeline.build_tree_inventory(base_tree)
    package = pipeline.canonical_json_document_descriptor(season_package, document_id="season-package")
    if base["files_fingerprint"] != index["base_inventory_fingerprint"]:
        raise CachedReplayError("cached replay bundle was made from a different base tree")
    if package["canonical_sha256"] != index["season_package_canonical_sha256"]:
        raise CachedReplayError("cached replay bundle was made for a different season package")
    if not materialisation_tree.is_dir() or materialisation_tree.is_symlink():
        raise CachedReplayError("materialisation tree must be an existing non-symlink directory")
    bundle_root = bundle_index.parent
    for row in index["outputs"]:
        relative = row["path"]
        blob = row["blob"]
        source = bundle_root / blob["path"]
        if source.is_symlink() or not source.is_file() or source.stat().st_size != blob["size"]:
            raise CachedReplayError(f"cached output blob is missing or unsafe: {relative}")
        if _sha256_file(source) != blob["sha256"]:
            raise CachedReplayError(f"cached output blob hash mismatch: {relative}")
        target = materialisation_tree / relative
        if not target.parent.is_dir() and not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=False)
        if not target.parent.is_dir() or target.parent.is_symlink():
            raise CachedReplayError(f"cached output has unsafe parent: {relative}")
        temporary = target.with_name(target.name + ".tmp")
        shutil.copyfile(source, temporary)
        temporary.replace(target)


def _write_plan(*, base_id: str, base_tree: Path, season_package: Path, bundle_index: Path, adapter: Path, output: Path) -> dict[str, Any]:
    from scripts import season_pipeline_buildplan_v2 as buildplan

    index = _load_index(bundle_index)
    base = pipeline.make_verified_base_descriptor(base_id=base_id, tree=base_tree)
    package = pipeline.canonical_json_document_descriptor(season_package, document_id="season-package")
    if base["inventory"]["files_fingerprint"] != index["base_inventory_fingerprint"]:
        raise CachedReplayError("bundle base lock does not match supplied verified base")
    if package["canonical_sha256"] != index["season_package_canonical_sha256"]:
        raise CachedReplayError("bundle package lock does not match supplied season package")
    outputs = [row["path"] for row in index["outputs"]]
    output_inventory = {
        "schema": pipeline.FILE_INVENTORY_SCHEMA,
        "file_count": len(outputs),
        "total_bytes": sum(row["blob"]["size"] for row in index["outputs"]),
        "files_fingerprint": pipeline.canonical_json_sha256([
            {"path": row["path"], "sha256": row["blob"]["sha256"], "size": row["blob"]["size"]}
            for row in index["outputs"]
        ]),
        "files": [
            {"path": row["path"], "sha256": row["blob"]["sha256"], "size": row["blob"]["size"]}
            for row in index["outputs"]
        ],
    }
    output_inventory = pipeline.validate_inventory(output_inventory)
    bundle_artifact = pipeline.external_artifact_descriptor(
        artifact_id="cached-release-bundle", path=bundle_index, role="asset"
    )
    receipt = pipeline.make_stage_record(
        stage_id="cached-release-replay",
        implementation_path=adapter,
        input_fingerprints={
            "base-tree": base["inventory"]["files_fingerprint"],
            "season-package": package["canonical_sha256"],
        },
        parameters={"mode": "legacy-cached-output-replay", "outputs": outputs},
        external_artifacts=[bundle_artifact],
    )
    plan = {
        "schema": buildplan.BUILD_PLAN_SCHEMA,
        "season": str(json.loads(season_package.read_text(encoding="utf-8"))["season"]["label"]).replace("/", "-"),
        "base": {"base_id": base["base_id"], "inventory_fingerprint": base["inventory"]["files_fingerprint"]},
        "season_package": {
            "canonical_sha256": package["canonical_sha256"], "canonical_size": package["canonical_size"],
            "schema": package["schema"],
        },
        "external_artifacts": [bundle_artifact],
        "forbidden_runtime_state_directories": ["CACHE", "RUNTIME", "SAVE", "SAVEGAME", "SAVEGAMES", "SAVES", "TEMP", "TMP"],
        "stages": [{
            "id": "cached-release-replay", "order": 1,
            "command": {
                "id": "cached-replay-adapter", "sha256": pipeline.sha256_file(adapter),
                "args": ["apply", "--base-tree", "{base-tree}", "--materialisation-tree", "{materialisation-tree}", "--season-package", "{season-package}", "--bundle-index", "{external-artifact:cached-release-bundle}"],
                "timeout_seconds": 300,
            },
            "outputs": outputs,
            "expected_receipt": receipt,
            "expected_output_inventory": output_inventory,
        }],
        "expected_final_output_inventory": _expected_final_inventory(base_tree=base_tree, index=index),
    }
    buildplan.write_canonical_build_plan(output, plan)
    pipeline.write_canonical_json(output.with_name("verified-base.json"), base)
    return {"plan": plan, "verified_base": base}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    bundle = commands.add_parser("create-bundle", help="store reviewed output bytes as a local replay bundle")
    bundle.add_argument("--base-tree", required=True, type=Path)
    bundle.add_argument("--reference-tree", required=True, type=Path)
    bundle.add_argument("--season-package", required=True, type=Path)
    bundle.add_argument("--bundle-root", required=True, type=Path)
    bundle.add_argument("--include", action="append", default=[])
    bundle.add_argument("--include-directory", action="append", default=[])
    clean = commands.add_parser("prepare-clean-base", help="copy an installation without named runtime-state directories")
    clean.add_argument("--source-tree", required=True, type=Path)
    clean.add_argument("--output-tree", required=True, type=Path)
    clean.add_argument("--base-id", required=True)
    clean.add_argument("--exclude-directory", action="append", default=[])
    clean.add_argument("--verified-base-output", required=True, type=Path)
    apply = commands.add_parser("apply", help="apply one verified bundle to a fresh materialisation")
    apply.add_argument("--base-tree", required=True, type=Path)
    apply.add_argument("--materialisation-tree", required=True, type=Path)
    apply.add_argument("--season-package", required=True, type=Path)
    apply.add_argument("--bundle-index", required=True, type=Path)
    plan = commands.add_parser("write-plan", help="write a V2 plan for an already-created replay bundle")
    plan.add_argument("--base-id", required=True)
    plan.add_argument("--base-tree", required=True, type=Path)
    plan.add_argument("--season-package", required=True, type=Path)
    plan.add_argument("--bundle-index", required=True, type=Path)
    plan.add_argument("--adapter", required=True, type=Path)
    plan.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "create-bundle":
            result = create_bundle(
                base_tree=args.base_tree, reference_tree=args.reference_tree,
                season_package=args.season_package, bundle_root=args.bundle_root,
                include=args.include, include_directories=args.include_directory,
            )
            print(json.dumps({"index": result["index_path"], "outputs": len(result["index"]["outputs"])}, sort_keys=True))
        elif args.command == "prepare-clean-base":
            result = prepare_clean_base(
                source_tree=args.source_tree,
                output_tree=args.output_tree,
                excluded_directories=args.exclude_directory,
                base_id=args.base_id,
            )
            pipeline.write_canonical_json(args.verified_base_output, result["descriptor"])
        elif args.command == "apply":
            apply_bundle(
                base_tree=args.base_tree, materialisation_tree=args.materialisation_tree,
                season_package=args.season_package, bundle_index=args.bundle_index,
            )
        else:
            _write_plan(
                base_id=args.base_id, base_tree=args.base_tree, season_package=args.season_package,
                bundle_index=args.bundle_index, adapter=args.adapter, output=args.output,
            )
    except (CachedReplayError, pipeline.PipelineError, OSError, json.JSONDecodeError) as exc:
        print(f"cached replay error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
