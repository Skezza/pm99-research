"""Hash-bound editorial amendments for immutable PM99 season manifests.

This is intentionally a small source-editing layer, not a PM99 binary editor.
An amendment names one allowlisted manifest, records the value seen by the
reviewer, and replaces only that value when materialised.  If the selected
source manifest changes, materialisation refuses rather than guessing.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


SCHEMA = "pm99-season-manifest-amendments-v1"
RECEIPT_SCHEMA = "pm99-season-manifest-amendment-receipt-v1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SEASON = re.compile(r"^(?:1999|20[0-2][0-9])-[0-9]{2}$")


class AmendmentError(ValueError):
    """An amendment is malformed, stale, or unsafe to materialise."""


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return (json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AmendmentError(f"amendment must be JSON-compatible: {exc}") from exc


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def empty_document(season: str) -> dict[str, Any]:
    if not SEASON.fullmatch(season):
        raise AmendmentError(f"invalid season: {season!r}")
    return {
        "schema_version": SCHEMA,
        "season": season,
        "revision_id": "working",
        "changes": [],
    }


def _require_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AmendmentError(f"{label} must be a non-empty string")
    return value.strip()


def _pointer_parts(pointer: Any) -> list[str]:
    if not isinstance(pointer, str) or not pointer.startswith("/") or pointer == "/":
        raise AmendmentError("json_pointer must identify an existing nested field")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def _resolve_parent(value: Any, pointer: str) -> tuple[dict[str, Any] | list[Any], str]:
    parts = _pointer_parts(pointer)
    current = value
    for part in parts[:-1]:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdecimal() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise AmendmentError(f"json_pointer does not exist in the selected manifest: {pointer}")
    if not isinstance(current, (dict, list)):
        raise AmendmentError(f"json_pointer parent is not editable: {pointer}")
    return current, parts[-1]


def value_at(value: Any, pointer: str) -> Any:
    parent, final = _resolve_parent(value, pointer)
    if isinstance(parent, dict) and final in parent:
        return copy.deepcopy(parent[final])
    if isinstance(parent, list) and final.isdecimal() and int(final) < len(parent):
        return copy.deepcopy(parent[int(final)])
    raise AmendmentError(f"json_pointer does not exist in the selected manifest: {pointer}")


def replace_at(value: Any, pointer: str, replacement: Any) -> None:
    parent, final = _resolve_parent(value, pointer)
    if isinstance(parent, dict) and final in parent:
        parent[final] = copy.deepcopy(replacement)
        return
    if isinstance(parent, list) and final.isdecimal() and int(final) < len(parent):
        parent[int(final)] = copy.deepcopy(replacement)
        return
    raise AmendmentError(f"json_pointer does not exist in the selected manifest: {pointer}")


def validate_document(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"schema_version", "season", "revision_id", "changes"}:
        raise AmendmentError("amendment document has unsupported or missing fields")
    if value["schema_version"] != SCHEMA:
        raise AmendmentError(f"amendment document must use {SCHEMA}")
    if not isinstance(value["season"], str) or not SEASON.fullmatch(value["season"]):
        raise AmendmentError("amendment document has an invalid season")
    _require_string(value["revision_id"], label="revision_id")
    if not isinstance(value["changes"], list):
        raise AmendmentError("amendment changes must be a list")
    seen_ids: set[str] = set()
    seen_targets: set[tuple[str, str]] = set()
    previous_id = ""
    for row in value["changes"]:
        if not isinstance(row, dict) or set(row) != {
            "id", "manifest_id", "manifest_sha256", "json_pointer", "expected", "set", "reason", "evidence"
        }:
            raise AmendmentError("each amendment change has unsupported or missing fields")
        change_id = _require_string(row["id"], label="change id")
        if not re.fullmatch(r"change-[0-9]{4,}", change_id):
            raise AmendmentError("change id must use change-0001 style")
        if change_id <= previous_id or change_id in seen_ids:
            raise AmendmentError("changes must be uniquely sorted by id")
        previous_id = change_id
        seen_ids.add(change_id)
        manifest_id = _require_string(row["manifest_id"], label=f"{change_id}.manifest_id")
        if not isinstance(row["manifest_sha256"], str) or not SHA256.fullmatch(row["manifest_sha256"]):
            raise AmendmentError(f"{change_id}.manifest_sha256 must be a SHA-256")
        pointer = row["json_pointer"]
        _pointer_parts(pointer)
        target = (manifest_id, pointer)
        if target in seen_targets:
            raise AmendmentError(f"duplicate amendment target: {manifest_id} {pointer}")
        seen_targets.add(target)
        _require_string(row["reason"], label=f"{change_id}.reason")
        if row["evidence"] is not None and not isinstance(row["evidence"], str):
            raise AmendmentError(f"{change_id}.evidence must be a string or null")
    return value


def load_or_empty(path: Path, *, season: str) -> dict[str, Any]:
    if not path.exists():
        return empty_document(season)
    if path.is_symlink() or not path.is_file():
        raise AmendmentError(f"amendment path is not a regular file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AmendmentError(f"cannot read amendment document: {exc}") from exc
    document = validate_document(value)
    if document["season"] != season:
        raise AmendmentError("amendment document targets a different season")
    return document


def write_document(path: Path, document: Mapping[str, Any]) -> None:
    value = validate_document(copy.deepcopy(dict(document)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def stage_change(
    document: Mapping[str, Any], *, manifest_id: str, manifest_sha256: str,
    json_pointer: str, expected: Any, replacement: Any, reason: str,
    evidence: str | None,
) -> dict[str, Any]:
    value = validate_document(copy.deepcopy(dict(document)))
    if not SHA256.fullmatch(manifest_sha256):
        raise AmendmentError("selected manifest does not have a valid SHA-256")
    _pointer_parts(json_pointer)
    next_number = len(value["changes"]) + 1
    candidate = {
        "id": f"change-{next_number:04d}",
        "manifest_id": _require_string(manifest_id, label="manifest_id"),
        "manifest_sha256": manifest_sha256,
        "json_pointer": json_pointer,
        "expected": copy.deepcopy(expected),
        "set": copy.deepcopy(replacement),
        "reason": _require_string(reason, label="reason"),
        "evidence": evidence.strip() if isinstance(evidence, str) and evidence.strip() else None,
    }
    value["changes"].append(candidate)
    value["changes"].sort(key=lambda row: row["id"])
    return validate_document(value)


def remove_change(document: Mapping[str, Any], *, change_id: str) -> dict[str, Any]:
    value = validate_document(copy.deepcopy(dict(document)))
    original = len(value["changes"])
    value["changes"] = [row for row in value["changes"] if row["id"] != change_id]
    if len(value["changes"]) == original:
        raise AmendmentError("amendment change was not found")
    for index, row in enumerate(value["changes"], start=1):
        row["id"] = f"change-{index:04d}"
    return validate_document(value)


Resolver = Callable[[str], tuple[Path, str]]


def materialise(
    document: Mapping[str, Any], *, resolve_manifest: Resolver, output_root: Path,
) -> dict[str, Any]:
    """Write amended copies and a receipt; never change the selected source files."""

    value = validate_document(copy.deepcopy(dict(document)))
    document_hash = sha256_bytes(canonical_json_bytes(value))
    destination = output_root / value["season"] / document_hash
    if destination.exists():
        raise AmendmentError(f"refusing to overwrite existing amendment materialisation: {destination}")
    destination.mkdir(parents=True)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for change in value["changes"]:
        grouped.setdefault(change["manifest_id"], []).append(change)
    outputs: list[dict[str, Any]] = []
    for manifest_id, changes in sorted(grouped.items()):
        path, locked_sha256 = resolve_manifest(manifest_id)
        actual_sha256 = sha256_file(path)
        if actual_sha256 != locked_sha256:
            raise AmendmentError(f"selected manifest changed after it was catalogued: {manifest_id}")
        if any(change["manifest_sha256"] != actual_sha256 for change in changes):
            raise AmendmentError(f"amendments target a different source revision: {manifest_id}")
        try:
            source = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AmendmentError(f"cannot read selected manifest {manifest_id}: {exc}") from exc
        amended = copy.deepcopy(source)
        for change in changes:
            actual = value_at(amended, change["json_pointer"])
            if actual != change["expected"]:
                raise AmendmentError(
                    f"stale amendment {change['id']}: expected value differs at {change['json_pointer']}"
                )
            replace_at(amended, change["json_pointer"], change["set"])
        filename = f"{len(outputs) + 1:02d}-{hashlib.sha256(manifest_id.encode('utf-8')).hexdigest()[:12]}.json"
        output_path = destination / "manifests" / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(canonical_json_bytes(amended))
        outputs.append({
            "manifest_id": manifest_id,
            "source_sha256": actual_sha256,
            "output_path": str(output_path),
            "output_sha256": sha256_file(output_path),
            "change_ids": [change["id"] for change in changes],
        })
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "season": value["season"],
        "amendment_sha256": document_hash,
        "amendment_path": "season editorial amendments/working.json",
        "change_count": len(value["changes"]),
        "outputs": outputs,
        "state": "materialised-source-copies-not-promoted",
    }
    (destination / "amendment-receipt.json").write_bytes(canonical_json_bytes(receipt))
    return receipt
