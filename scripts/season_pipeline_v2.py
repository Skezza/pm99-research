#!/usr/bin/env python3
"""Reproducible, fail-closed release metadata for PM99 season packages.

This is deliberately a *pipeline foundation*, not another season-specific
binary writer.  A season compiler supplies the actual database, portrait and
kit stages; this module makes their inputs and outputs reproducible:

* a verified, immutable base tree is fingerprinted before a build starts;
* a season package is represented by canonical JSON, not a machine path;
* every external asset is identified by content hash;
* each deterministic stage has a content-addressed cache key; and
* finished trees can be compared bit-for-bit through complete inventories.

The canonical release manifest intentionally contains no timestamps, host
names, absolute paths, or run IDs.  Runtime/environment evidence belongs in a
separate attestation because it is useful proof but must never influence a
rebuild.  This is the durable release boundary for 1999/00 through 2025/26.

No PM99 game data is bundled, copied, or written by this module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import socket
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any


FILE_INVENTORY_SCHEMA = "pm99-file-inventory-v2"
VERIFIED_BASE_SCHEMA = "pm99-verified-base-v2"
SEASON_MANIFEST_SCHEMA = "pm99-season-release-manifest-v2"
ATTESTATION_SCHEMA = "pm99-season-release-attestation-v2"
EXTERNAL_ARTIFACT_SCHEMA = "pm99-external-artifact-v2"
STAGE_RECORD_SCHEMA = "pm99-stage-record-v2"
STAGE_KEY_SCHEMA = "pm99-stage-key-v2"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_SEASON_RE = re.compile(r"^((?:19[0-9]{2}|20(?:0[0-9]|1[0-9]|2[0-5])))[-/]([0-9]{2})$")


class PipelineError(ValueError):
    """A release invariant was not met.

    The CLI reports this as a normal, non-zero failure.  Callers should not
    catch it and continue with a partial package.
    """


def _require_identifier(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise PipelineError(
            f"{label} must match {_IDENTIFIER_RE.pattern!r}; got {value!r}"
        )
    return value


def _require_sha256(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise PipelineError(f"{label} must be a lowercase SHA-256 hex digest")
    return value


def normalise_season_id(value: str) -> str:
    """Return ``YYYY-YY`` for a supported historical PM99 season.

    Both ``2015-16`` and ``2015/16`` are accepted at the CLI boundary.  The
    canonical manifest always uses the former form.
    """

    match = _SEASON_RE.fullmatch(str(value or ""))
    if not match:
        raise PipelineError(
            "season must be YYYY-YY or YYYY/YY between 1900/01 and 2025/26"
        )
    start_year = int(match.group(1))
    ending = int(match.group(2))
    if ending != (start_year + 1) % 100:
        raise PipelineError(f"season ending year is not consecutive: {value!r}")
    return f"{start_year:04d}-{ending:02d}"


def canonical_json_bytes(value: Any) -> bytes:
    """Encode semantic JSON canonically for hashes and release inputs.

    Python's standard JSON serialiser is sufficient here because the allowed
    release data is JSON only.  Reject NaN/Infinity instead of giving them
    implementation-specific spellings.
    """

    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise PipelineError(f"value is not canonical JSON: {exc}") from exc
    return text.encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def sha256_file(path: Path) -> str:
    """Hash one regular file without loading large asset archives at once."""

    if not path.is_file() or path.is_symlink():
        raise PipelineError(f"expected a regular, non-symlink file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sorted_regular_files(tree: Path) -> list[Path]:
    """Return every regular file under ``tree`` or reject unsafe trees.

    Symlinks make a release's content depend on outside state; special files
    make the output impossible to reproduce on Windows.  Treat both as hard
    errors instead of silently skipping them.
    """

    tree = tree.expanduser()
    if tree.is_symlink():
        raise PipelineError(f"tree root must not be a symlink: {tree}")
    if not tree.exists() or not tree.is_dir():
        raise PipelineError(f"tree must be an existing directory: {tree}")

    files: list[Path] = []
    for path in tree.rglob("*"):
        if path.is_symlink():
            raise PipelineError(f"release trees must not contain symlinks: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise PipelineError(f"release tree contains a non-regular entry: {path}")
        files.append(path)
    return sorted(files, key=lambda path: path.relative_to(tree).as_posix())


def build_tree_inventory(tree: Path) -> dict[str, Any]:
    """Create a complete, path-independent byte inventory for ``tree``."""

    if tree.expanduser().is_symlink():
        raise PipelineError(f"tree root must not be a symlink: {tree}")
    tree = tree.expanduser().resolve()
    files: list[dict[str, Any]] = []
    total_bytes = 0
    for path in _sorted_regular_files(tree):
        relative = path.relative_to(tree).as_posix()
        # ``relative_to`` cannot yield an absolute path.  Retain this explicit
        # guard because inventory paths are a release/security boundary.
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or relative in {"", "."}:
            raise PipelineError(f"unsafe inventory path: {relative!r}")
        size = path.stat().st_size
        files.append({"path": relative, "sha256": sha256_file(path), "size": size})
        total_bytes += size

    files_fingerprint = canonical_json_sha256(files)
    return {
        "schema": FILE_INVENTORY_SCHEMA,
        "file_count": len(files),
        "total_bytes": total_bytes,
        "files_fingerprint": files_fingerprint,
        "files": files,
    }


def validate_inventory(inventory: Any) -> dict[str, Any]:
    """Validate an inventory's own claims before trusting it as a base lock."""

    if not isinstance(inventory, dict):
        raise PipelineError("inventory must be a JSON object")
    expected_keys = {
        "schema",
        "file_count",
        "total_bytes",
        "files_fingerprint",
        "files",
    }
    if set(inventory) != expected_keys:
        raise PipelineError(
            "inventory keys must be exactly "
            f"{sorted(expected_keys)}; got {sorted(inventory)}"
        )
    if inventory["schema"] != FILE_INVENTORY_SCHEMA:
        raise PipelineError(f"unsupported inventory schema: {inventory['schema']!r}")
    files = inventory["files"]
    if not isinstance(files, list):
        raise PipelineError("inventory files must be a list")
    previous_path: str | None = None
    total_bytes = 0
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size"}:
            raise PipelineError("each inventory file must have path, sha256 and size")
        path = entry["path"]
        if not isinstance(path, str):
            raise PipelineError("inventory file path must be a string")
        pure = PurePosixPath(path)
        if not path or pure.is_absolute() or ".." in pure.parts or path != pure.as_posix():
            raise PipelineError(f"unsafe inventory path: {path!r}")
        if previous_path is not None and path <= previous_path:
            raise PipelineError("inventory files must be strictly path-sorted")
        previous_path = path
        _require_sha256(entry["sha256"], label=f"inventory hash for {path}")
        size = entry["size"]
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise PipelineError(f"inventory size for {path} must be a non-negative integer")
        total_bytes += size
    if inventory["file_count"] != len(files):
        raise PipelineError("inventory file_count does not match files")
    if inventory["total_bytes"] != total_bytes:
        raise PipelineError("inventory total_bytes does not match files")
    computed = canonical_json_sha256(files)
    if inventory["files_fingerprint"] != computed:
        raise PipelineError("inventory files_fingerprint does not match files")
    return inventory


def inventory_difference(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    """Describe exactly why two validated inventory trees differ."""

    left = validate_inventory(dict(left))
    right = validate_inventory(dict(right))
    left_files = {entry["path"]: entry for entry in left["files"]}
    right_files = {entry["path"]: entry for entry in right["files"]}
    left_paths = set(left_files)
    right_paths = set(right_files)
    changed = [
        {
            "path": path,
            "left": left_files[path],
            "right": right_files[path],
        }
        for path in sorted(left_paths & right_paths)
        if left_files[path] != right_files[path]
    ]
    return {
        "equal": left["files_fingerprint"] == right["files_fingerprint"],
        "left_fingerprint": left["files_fingerprint"],
        "right_fingerprint": right["files_fingerprint"],
        "only_left": sorted(left_paths - right_paths),
        "only_right": sorted(right_paths - left_paths),
        "changed": changed,
    }


def assert_tree_matches_inventory(tree: Path, expected: Mapping[str, Any]) -> dict[str, Any]:
    """Fail if an input/output tree differs by even one byte or filename."""

    expected = validate_inventory(dict(expected))
    actual = build_tree_inventory(tree)
    difference = inventory_difference(expected, actual)
    if not difference["equal"]:
        raise PipelineError(
            "tree does not match locked inventory: "
            + json.dumps(difference, ensure_ascii=False, sort_keys=True)
        )
    return actual


def _ensure_disjoint_directories(*paths: Path) -> None:
    resolved = [path.expanduser().resolve() for path in paths]
    for index, left in enumerate(resolved):
        for right in resolved[index + 1 :]:
            if left == right or left.is_relative_to(right) or right.is_relative_to(left):
                raise PipelineError(
                    "base tree, output tree and release metadata directory must be "
                    f"disjoint; conflict: {left} / {right}"
                )


def make_verified_base_descriptor(*, base_id: str, tree: Path) -> dict[str, Any]:
    """Lock an independently verified pristine PM99 installation by content."""

    return {
        "schema": VERIFIED_BASE_SCHEMA,
        "base_id": _require_identifier(base_id, label="base_id"),
        "inventory": build_tree_inventory(tree),
    }


def validate_verified_base_descriptor(descriptor: Any) -> dict[str, Any]:
    if not isinstance(descriptor, dict) or set(descriptor) != {"schema", "base_id", "inventory"}:
        raise PipelineError("verified base descriptor must contain schema, base_id and inventory")
    if descriptor["schema"] != VERIFIED_BASE_SCHEMA:
        raise PipelineError(f"unsupported verified base schema: {descriptor.get('schema')!r}")
    _require_identifier(descriptor["base_id"], label="base_id")
    validate_inventory(descriptor["inventory"])
    return descriptor


def verify_base_tree(*, tree: Path, verified_base: Mapping[str, Any]) -> dict[str, Any]:
    """Verify that a build began from the declared immutable base, not rN."""

    verified_base = validate_verified_base_descriptor(dict(verified_base))
    return assert_tree_matches_inventory(tree, verified_base["inventory"])


def external_artifact_descriptor(*, artifact_id: str, path: Path, role: str = "input") -> dict[str, Any]:
    """Hash a source asset without leaking its local path into a manifest."""

    if role not in {"input", "tool", "asset", "runtime-proof"}:
        raise PipelineError(f"unsupported external artifact role: {role!r}")
    path = path.expanduser().resolve()
    return {
        "schema": EXTERNAL_ARTIFACT_SCHEMA,
        "id": _require_identifier(artifact_id, label="artifact_id"),
        "role": role,
        "sha256": sha256_file(path),
        "size": path.stat().st_size,
    }


def validate_external_artifact_descriptor(descriptor: Any) -> dict[str, Any]:
    keys = {"schema", "id", "role", "sha256", "size"}
    if not isinstance(descriptor, dict) or set(descriptor) != keys:
        raise PipelineError("external artifact descriptor has invalid keys")
    if descriptor["schema"] != EXTERNAL_ARTIFACT_SCHEMA:
        raise PipelineError("unsupported external artifact schema")
    _require_identifier(descriptor["id"], label="artifact_id")
    if descriptor["role"] not in {"input", "tool", "asset", "runtime-proof"}:
        raise PipelineError("external artifact has invalid role")
    _require_sha256(descriptor["sha256"], label=f"artifact hash for {descriptor['id']}")
    if not isinstance(descriptor["size"], int) or isinstance(descriptor["size"], bool) or descriptor["size"] < 0:
        raise PipelineError("external artifact size must be a non-negative integer")
    return descriptor


def normalise_external_artifacts(descriptors: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Validate and deterministically order a non-duplicated asset list."""

    normalised = [validate_external_artifact_descriptor(dict(item)) for item in descriptors]
    ids = [item["id"] for item in normalised]
    if len(ids) != len(set(ids)):
        raise PipelineError("external artifact IDs must be unique")
    return sorted(normalised, key=lambda item: item["id"])


def verify_external_artifact(*, path: Path, descriptor: Mapping[str, Any]) -> None:
    descriptor = validate_external_artifact_descriptor(dict(descriptor))
    actual = external_artifact_descriptor(
        artifact_id=descriptor["id"], path=path, role=descriptor["role"]
    )
    if actual != descriptor:
        raise PipelineError(
            "external artifact differs from its locked descriptor: "
            f"{descriptor['id']}"
        )


def canonical_json_document_descriptor(path: Path, *, document_id: str) -> dict[str, Any]:
    """Read a JSON object and describe its semantic, canonical content."""

    path = path.expanduser().resolve()
    if not path.is_file() or path.is_symlink():
        raise PipelineError(f"season document must be a regular file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"season document is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise PipelineError("season document must be a JSON object")
    canonical = canonical_json_bytes(payload)
    schema = payload.get("schema")
    if schema is not None and not isinstance(schema, str):
        raise PipelineError("season document schema must be a string when present")
    return {
        "id": _require_identifier(document_id, label="document_id"),
        "canonical_sha256": sha256_bytes(canonical),
        "canonical_size": len(canonical),
        "schema": schema,
    }


def _validate_hash_mapping(value: Mapping[str, Any], *, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise PipelineError(f"{label} must be a mapping of IDs to SHA-256 hashes")
    output: dict[str, str] = {}
    for key, digest in value.items():
        output[_require_identifier(str(key), label=f"{label} ID")] = _require_sha256(
            digest, label=f"{label} hash for {key}"
        )
    if not output:
        raise PipelineError(f"{label} must not be empty")
    return dict(sorted(output.items()))


def content_addressed_stage_key(
    *,
    stage_id: str,
    implementation_sha256: str,
    input_fingerprints: Mapping[str, str],
    parameters: Any,
    external_artifacts: Sequence[Mapping[str, Any]] = (),
) -> str:
    """Return a stable cache key for a deterministic compiler stage.

    ``implementation_sha256`` is deliberately a content hash, not a version
    label.  A code edit must invalidate a cached database/face/kit stage.
    """

    payload = {
        "schema": STAGE_KEY_SCHEMA,
        "stage_id": _require_identifier(stage_id, label="stage_id"),
        "implementation_sha256": _require_sha256(
            implementation_sha256, label="implementation_sha256"
        ),
        "input_fingerprints": _validate_hash_mapping(
            input_fingerprints, label="stage input_fingerprints"
        ),
        "parameters": json.loads(canonical_json_bytes(parameters)),
        "external_artifacts": normalise_external_artifacts(external_artifacts),
    }
    return canonical_json_sha256(payload)


def make_stage_record(
    *,
    stage_id: str,
    implementation_path: Path,
    input_fingerprints: Mapping[str, str],
    parameters: Any,
    external_artifacts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Create a serialisable stage receipt from a compiler script/tool file."""

    implementation_path = implementation_path.expanduser().resolve()
    implementation_sha256 = sha256_file(implementation_path)
    normalised_artifacts = normalise_external_artifacts(external_artifacts)
    normalised_inputs = _validate_hash_mapping(input_fingerprints, label="stage input_fingerprints")
    canonical_parameters = json.loads(canonical_json_bytes(parameters))
    return {
        "schema": STAGE_RECORD_SCHEMA,
        "id": _require_identifier(stage_id, label="stage_id"),
        "implementation_sha256": implementation_sha256,
        "input_fingerprints": normalised_inputs,
        "parameters": canonical_parameters,
        "external_artifacts": normalised_artifacts,
        "cache_key": content_addressed_stage_key(
            stage_id=stage_id,
            implementation_sha256=implementation_sha256,
            input_fingerprints=normalised_inputs,
            parameters=canonical_parameters,
            external_artifacts=normalised_artifacts,
        ),
    }


def validate_stage_record(record: Any) -> dict[str, Any]:
    required = {
        "schema",
        "id",
        "implementation_sha256",
        "input_fingerprints",
        "parameters",
        "external_artifacts",
        "cache_key",
    }
    if not isinstance(record, dict) or set(record) != required:
        raise PipelineError("stage record has invalid keys")
    if record["schema"] != STAGE_RECORD_SCHEMA:
        raise PipelineError("unsupported stage record schema")
    stage_id = _require_identifier(record["id"], label="stage_id")
    implementation = _require_sha256(record["implementation_sha256"], label="implementation_sha256")
    inputs = _validate_hash_mapping(record["input_fingerprints"], label="stage input_fingerprints")
    parameters = json.loads(canonical_json_bytes(record["parameters"]))
    artifacts = normalise_external_artifacts(record["external_artifacts"])
    expected_key = content_addressed_stage_key(
        stage_id=stage_id,
        implementation_sha256=implementation,
        input_fingerprints=inputs,
        parameters=parameters,
        external_artifacts=artifacts,
    )
    if record["cache_key"] != expected_key:
        raise PipelineError(f"stage cache key does not match stage content: {stage_id}")
    return {
        "schema": STAGE_RECORD_SCHEMA,
        "id": stage_id,
        "implementation_sha256": implementation,
        "input_fingerprints": inputs,
        "parameters": parameters,
        "external_artifacts": artifacts,
        "cache_key": expected_key,
    }


def normalise_stage_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalised = [validate_stage_record(dict(record)) for record in records]
    ids = [record["id"] for record in normalised]
    if len(ids) != len(set(ids)):
        raise PipelineError("stage record IDs must be unique")
    return sorted(normalised, key=lambda record: record["id"])


def create_release_manifest(
    *,
    season: str,
    verified_base: Mapping[str, Any],
    season_document: Mapping[str, Any],
    output_inventory: Mapping[str, Any],
    external_artifacts: Sequence[Mapping[str, Any]] = (),
    stages: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Create path-free canonical release provenance for an already-built tree."""

    verified_base = validate_verified_base_descriptor(dict(verified_base))
    output_inventory = validate_inventory(dict(output_inventory))
    expected_document_keys = {"id", "canonical_sha256", "canonical_size", "schema"}
    if not isinstance(season_document, dict) or set(season_document) != expected_document_keys:
        raise PipelineError("season document descriptor has invalid keys")
    document_id = _require_identifier(season_document["id"], label="document_id")
    canonical_sha256 = _require_sha256(
        season_document["canonical_sha256"], label="season document canonical_sha256"
    )
    if not isinstance(season_document["canonical_size"], int) or season_document["canonical_size"] < 2:
        raise PipelineError("season document canonical_size must be a positive integer")
    if season_document["schema"] is not None and not isinstance(season_document["schema"], str):
        raise PipelineError("season document schema must be a string or null")
    return {
        "schema": SEASON_MANIFEST_SCHEMA,
        "season": normalise_season_id(season),
        "base": {
            "base_id": verified_base["base_id"],
            "inventory_fingerprint": verified_base["inventory"]["files_fingerprint"],
            "file_count": verified_base["inventory"]["file_count"],
            "total_bytes": verified_base["inventory"]["total_bytes"],
        },
        "season_document": {
            "id": document_id,
            "canonical_sha256": canonical_sha256,
            "canonical_size": season_document["canonical_size"],
            "schema": season_document["schema"],
        },
        "external_artifacts": normalise_external_artifacts(external_artifacts),
        "stages": normalise_stage_records(stages),
        "output": {
            "inventory_fingerprint": output_inventory["files_fingerprint"],
            "file_count": output_inventory["file_count"],
            "total_bytes": output_inventory["total_bytes"],
        },
    }


def validate_release_manifest(manifest: Any) -> dict[str, Any]:
    """Validate manifest fields whose full inventories live in sibling files."""

    keys = {
        "schema", "season", "base", "season_document", "external_artifacts", "stages", "output"
    }
    if not isinstance(manifest, dict) or set(manifest) != keys:
        raise PipelineError("release manifest has invalid keys")
    if manifest["schema"] != SEASON_MANIFEST_SCHEMA:
        raise PipelineError("unsupported release manifest schema")
    normalise_season_id(manifest["season"])
    for label, expected_keys in (
        ("base", {"base_id", "inventory_fingerprint", "file_count", "total_bytes"}),
        ("output", {"inventory_fingerprint", "file_count", "total_bytes"}),
    ):
        value = manifest[label]
        if not isinstance(value, dict) or set(value) != expected_keys:
            raise PipelineError(f"release manifest {label} has invalid keys")
        if label == "base":
            _require_identifier(value["base_id"], label="base_id")
        _require_sha256(value["inventory_fingerprint"], label=f"{label} inventory fingerprint")
        for field in ("file_count", "total_bytes"):
            if not isinstance(value[field], int) or isinstance(value[field], bool) or value[field] < 0:
                raise PipelineError(f"release manifest {label}.{field} must be non-negative")
    document = manifest["season_document"]
    if not isinstance(document, dict) or set(document) != {"id", "canonical_sha256", "canonical_size", "schema"}:
        raise PipelineError("release manifest season_document has invalid keys")
    _require_identifier(document["id"], label="document_id")
    _require_sha256(document["canonical_sha256"], label="season document canonical_sha256")
    if not isinstance(document["canonical_size"], int) or isinstance(document["canonical_size"], bool) or document["canonical_size"] < 2:
        raise PipelineError("season document canonical_size must be at least two bytes")
    if document["schema"] is not None and not isinstance(document["schema"], str):
        raise PipelineError("season document schema must be a string or null")
    artifacts = normalise_external_artifacts(manifest["external_artifacts"])
    if manifest["external_artifacts"] != artifacts:
        raise PipelineError("release manifest external artifacts must be ID-sorted")
    stages = normalise_stage_records(manifest["stages"])
    if manifest["stages"] != stages:
        raise PipelineError("release manifest stage records must be ID-sorted and canonical")
    return manifest


def write_canonical_json(path: Path, payload: Any) -> str:
    """Write a new canonical JSON file; never silently overwrite evidence."""

    path = path.expanduser()
    if path.exists() or path.is_symlink():
        raise PipelineError(f"refusing to overwrite existing release evidence: {path}")
    path = path.resolve()
    if not path.parent.is_dir():
        raise PipelineError(f"output parent must already exist: {path.parent}")
    encoded = canonical_json_bytes(payload) + b"\n"
    try:
        with path.open("xb") as handle:
            handle.write(encoded)
    except FileExistsError as exc:
        raise PipelineError(f"refusing to overwrite existing release evidence: {path}") from exc
    return sha256_bytes(encoded)


def read_json_file(path: Path) -> Any:
    path = path.expanduser().resolve()
    if not path.is_file() or path.is_symlink():
        raise PipelineError(f"expected a regular JSON file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"invalid JSON file: {path}") from exc


def write_release_metadata(
    *,
    season: str,
    base_tree: Path,
    verified_base: Mapping[str, Any],
    season_package: Path,
    output_tree: Path,
    metadata_dir: Path,
    external_artifacts: Sequence[Mapping[str, Any]] = (),
    stages: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Verify inputs and write the three reproducible release metadata files.

    This is normally called immediately after a compiler has written its output
    tree.  It does not mutate either game tree.  ``metadata_dir`` must be a new
    empty directory outside both trees, preventing metadata from accidentally
    changing the output fingerprint it describes.
    """

    base_tree = base_tree.expanduser().resolve()
    output_tree = output_tree.expanduser().resolve()
    metadata_dir = metadata_dir.expanduser().resolve()
    _ensure_disjoint_directories(base_tree, output_tree, metadata_dir)
    if metadata_dir.exists():
        if not metadata_dir.is_dir() or any(metadata_dir.iterdir()):
            raise PipelineError(f"metadata directory must be new or empty: {metadata_dir}")
    else:
        metadata_dir.mkdir(parents=True)

    verified_base = validate_verified_base_descriptor(dict(verified_base))
    base_inventory = verify_base_tree(tree=base_tree, verified_base=verified_base)
    output_inventory = build_tree_inventory(output_tree)
    season_document = canonical_json_document_descriptor(
        season_package, document_id="season-package"
    )
    manifest = create_release_manifest(
        season=season,
        verified_base=verified_base,
        season_document=season_document,
        output_inventory=output_inventory,
        external_artifacts=external_artifacts,
        stages=stages,
    )
    # The input descriptor itself must match the base we just verified.  This
    # redundant guard makes it impossible for a caller to lock one base and
    # build from another directory with coincidentally plausible filenames.
    if base_inventory["files_fingerprint"] != verified_base["inventory"]["files_fingerprint"]:
        raise PipelineError("verified base changed while release metadata was being written")

    base_path = metadata_dir / "base.inventory.json"
    output_path = metadata_dir / "output.inventory.json"
    manifest_path = metadata_dir / "season-manifest.json"
    write_canonical_json(base_path, verified_base["inventory"])
    write_canonical_json(output_path, output_inventory)
    write_canonical_json(manifest_path, manifest)
    return {
        "base_inventory": base_inventory,
        "output_inventory": output_inventory,
        "manifest": manifest,
        "paths": {
            "base_inventory": str(base_path),
            "output_inventory": str(output_path),
            "manifest": str(manifest_path),
        },
    }


def verify_release_output(*, manifest: Mapping[str, Any], output_tree: Path) -> dict[str, Any]:
    """Verify an output tree against the canonical release manifest."""

    manifest = validate_release_manifest(dict(manifest))
    inventory = build_tree_inventory(output_tree)
    expected = manifest["output"]
    if (
        inventory["files_fingerprint"] != expected["inventory_fingerprint"]
        or inventory["file_count"] != expected["file_count"]
        or inventory["total_bytes"] != expected["total_bytes"]
    ):
        raise PipelineError("output tree does not match release manifest inventory fingerprint")
    return inventory


def create_attestation(
    *,
    release_manifest: Mapping[str, Any],
    output_tree: Path,
    run_id: str | None = None,
    note: str | None = None,
    runtime_receipts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Create non-reproducible environment/runtime evidence for one release.

    This payload is intentionally excluded from the canonical release
    manifest.  It answers *where and when did we validate it?*, not *what
    bytes should a clean rebuild create?*.
    """

    release_manifest = validate_release_manifest(
        dict(release_manifest)
    )
    output_inventory = verify_release_output(manifest=release_manifest, output_tree=output_tree)
    receipts = json.loads(canonical_json_bytes(list(runtime_receipts)))
    if not isinstance(receipts, list):  # Defensive: canonical JSON preserves list.
        raise PipelineError("runtime_receipts must be a list")
    if run_id is not None:
        _require_identifier(run_id, label="run_id")
    if note is not None and not isinstance(note, str):
        raise PipelineError("attestation note must be a string")
    return {
        "schema": ATTESTATION_SCHEMA,
        "created_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "run_id": run_id,
        "note": note,
        "release_manifest_sha256": canonical_json_sha256(release_manifest),
        "output_inventory_fingerprint": output_inventory["files_fingerprint"],
        "runtime_receipts": receipts,
    }


def _parse_artifact_spec(spec: str) -> tuple[str, Path]:
    if "=" not in spec:
        raise PipelineError("external artifact must use ID=PATH")
    artifact_id, raw_path = spec.split("=", 1)
    _require_identifier(artifact_id, label="artifact_id")
    if not raw_path:
        raise PipelineError("external artifact path is empty")
    return artifact_id, Path(raw_path)


def _load_stage_records(paths: Sequence[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw_path in paths:
        records.append(validate_stage_record(read_json_file(Path(raw_path))))
    return normalise_stage_records(records)


def _load_json_argument(path: str, *, expected_type: type[Any], label: str) -> Any:
    value = read_json_file(Path(path))
    if not isinstance(value, expected_type):
        raise PipelineError(f"{label} must contain a JSON {expected_type.__name__}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    inventory = commands.add_parser("inventory", help="write a full tree inventory")
    inventory.add_argument("--tree", required=True, type=Path)
    inventory.add_argument("--output", required=True, type=Path)

    base = commands.add_parser("verified-base", help="lock a verified pristine base tree")
    base.add_argument("--base-id", required=True)
    base.add_argument("--tree", required=True, type=Path)
    base.add_argument("--output", required=True, type=Path)

    check_base = commands.add_parser("verify-base", help="verify a tree against a locked base")
    check_base.add_argument("--tree", required=True, type=Path)
    check_base.add_argument("--verified-base", required=True, type=Path)

    artifact = commands.add_parser("external-artifact", help="hash a source asset")
    artifact.add_argument("--id", required=True)
    artifact.add_argument("--file", required=True, type=Path)
    artifact.add_argument("--role", default="input", choices=("input", "tool", "asset", "runtime-proof"))
    artifact.add_argument("--output", required=True, type=Path)

    stage = commands.add_parser("stage-key", help="create a content-addressed stage record")
    stage.add_argument("--id", required=True)
    stage.add_argument("--implementation", required=True, type=Path)
    stage.add_argument("--inputs-json", required=True)
    stage.add_argument("--parameters-json", required=True)
    stage.add_argument("--external-artifact", action="append", default=[], metavar="ID=PATH")
    stage.add_argument("--output", required=True, type=Path)

    release = commands.add_parser("release-metadata", help="write canonical release metadata")
    release.add_argument("--season", required=True)
    release.add_argument("--base-tree", required=True, type=Path)
    release.add_argument("--verified-base", required=True, type=Path)
    release.add_argument("--season-package", required=True, type=Path)
    release.add_argument("--output-tree", required=True, type=Path)
    release.add_argument("--metadata-dir", required=True, type=Path)
    release.add_argument("--external-artifact", action="append", default=[], metavar="ID=PATH")
    release.add_argument("--stage-record", action="append", default=[], type=Path)

    compare = commands.add_parser("double-build", help="compare two finished output trees")
    compare.add_argument("--first-tree", required=True, type=Path)
    compare.add_argument("--second-tree", required=True, type=Path)

    attest = commands.add_parser("attest", help="write non-reproducible runtime/environment evidence")
    attest.add_argument("--release-manifest", required=True, type=Path)
    attest.add_argument("--output-tree", required=True, type=Path)
    attest.add_argument("--run-id")
    attest.add_argument("--note")
    attest.add_argument("--runtime-receipts-json")
    attest.add_argument("--output", required=True, type=Path)
    return parser


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inventory":
            inventory = build_tree_inventory(args.tree)
            write_canonical_json(args.output, inventory)
            _print_json({"ok": True, "inventory": inventory["files_fingerprint"], "output": str(args.output)})
            return 0
        if args.command == "verified-base":
            descriptor = make_verified_base_descriptor(base_id=args.base_id, tree=args.tree)
            write_canonical_json(args.output, descriptor)
            _print_json({"ok": True, "base_id": descriptor["base_id"], "output": str(args.output)})
            return 0
        if args.command == "verify-base":
            descriptor = validate_verified_base_descriptor(read_json_file(args.verified_base))
            inventory = verify_base_tree(tree=args.tree, verified_base=descriptor)
            _print_json({"ok": True, "base_id": descriptor["base_id"], "inventory": inventory["files_fingerprint"]})
            return 0
        if args.command == "external-artifact":
            descriptor = external_artifact_descriptor(artifact_id=args.id, path=args.file, role=args.role)
            write_canonical_json(args.output, descriptor)
            _print_json({"ok": True, "id": descriptor["id"], "sha256": descriptor["sha256"]})
            return 0
        if args.command == "stage-key":
            inputs = _load_json_argument(args.inputs_json, expected_type=dict, label="inputs-json")
            parameters = read_json_file(Path(args.parameters_json))
            artifacts = [
                external_artifact_descriptor(artifact_id=artifact_id, path=path)
                for artifact_id, path in (_parse_artifact_spec(item) for item in args.external_artifact)
            ]
            record = make_stage_record(
                stage_id=args.id,
                implementation_path=args.implementation,
                input_fingerprints=inputs,
                parameters=parameters,
                external_artifacts=artifacts,
            )
            write_canonical_json(args.output, record)
            _print_json({"ok": True, "id": record["id"], "cache_key": record["cache_key"]})
            return 0
        if args.command == "release-metadata":
            verified_base = validate_verified_base_descriptor(read_json_file(args.verified_base))
            artifacts = [
                external_artifact_descriptor(artifact_id=artifact_id, path=path)
                for artifact_id, path in (_parse_artifact_spec(item) for item in args.external_artifact)
            ]
            result = write_release_metadata(
                season=args.season,
                base_tree=args.base_tree,
                verified_base=verified_base,
                season_package=args.season_package,
                output_tree=args.output_tree,
                metadata_dir=args.metadata_dir,
                external_artifacts=artifacts,
                stages=_load_stage_records([str(path) for path in args.stage_record]),
            )
            _print_json({"ok": True, "paths": result["paths"], "output": result["output_inventory"]["files_fingerprint"]})
            return 0
        if args.command == "double-build":
            result = inventory_difference(
                build_tree_inventory(args.first_tree), build_tree_inventory(args.second_tree)
            )
            _print_json(result)
            return 0 if result["equal"] else 1
        if args.command == "attest":
            manifest = validate_release_manifest(
                read_json_file(args.release_manifest)
            )
            receipts: list[Any] = []
            if args.runtime_receipts_json:
                receipts = _load_json_argument(
                    args.runtime_receipts_json, expected_type=list, label="runtime-receipts-json"
                )
            attestation = create_attestation(
                release_manifest=manifest,
                output_tree=args.output_tree,
                run_id=args.run_id,
                note=args.note,
                runtime_receipts=receipts,
            )
            write_canonical_json(args.output, attestation)
            _print_json({"ok": True, "output": str(args.output), "release_manifest_sha256": attestation["release_manifest_sha256"]})
            return 0
        raise AssertionError(f"unhandled command: {args.command}")
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
