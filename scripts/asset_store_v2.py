#!/usr/bin/env python3
"""Import retained PM99 season artwork into a local content-addressed store.

The importer captures byte-exact material already available locally.  It never
downloads a URL, guesses a crop, or reports a rendered asset as source
regenerable when its historical recipe/provenance was not retained.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "pm99-asset-store-import-v1.schema.json"
SCHEMA_VERSION = "pm99-asset-store-import-v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LOOSE_NAME_RE = re.compile(r"^J96\d{5}\.BMP$")


class AssetStoreError(ValueError):
    """The retained assets/receipts cannot safely establish a cache entry."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssetStoreError(f"cannot read {path}: {exc}") from exc


def _safe_blob_path(store_root: Path, digest: str) -> Path:
    if not SHA256_RE.fullmatch(digest):
        raise AssetStoreError(f"invalid SHA-256 {digest!r}")
    return store_root / "blobs" / digest[:2] / digest


def _put_bytes(store_root: Path, payload: bytes) -> dict[str, str]:
    digest = sha256_bytes(payload)
    destination = _safe_blob_path(store_root, digest)
    if destination.exists():
        if sha256_file(destination) != digest:
            raise AssetStoreError(f"existing blob is corrupt: {destination}")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        temporary.write_bytes(payload)
        temporary.replace(destination)
    return {"sha256": digest, "blob": f"blobs/{digest[:2]}/{digest}"}


def _put_file(store_root: Path, path: Path) -> dict[str, str]:
    if not path.is_file():
        raise AssetStoreError(f"expected retained asset is missing: {path}")
    return _put_bytes(store_root, path.read_bytes())


def _receipt(path: Path, identity: str) -> dict[str, str]:
    if not path.is_file():
        raise AssetStoreError(f"missing receipt: {path}")
    return {"id": identity, "sha256": sha256_file(path)}


def _require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise AssetStoreError(f"{label}: expected lowercase SHA-256")
    return value


def _legacy_reason(kind: str) -> list[str]:
    if kind == "portrait":
        return [
            "legacy receipt has no per-player crop recipe",
            "legacy converter/palette input identity was not retained as a source build contract",
            "web-page/evidence content hashes were not captured with the source image",
        ]
    return [
        "legacy kit receipt has no captured source-artwork content hash",
        "legacy kit receipt has no pinned renderer and palette input contract",
        "the retained style description is not evidence of the source web-page content",
    ]


def _read_slice(payload: bytes, offset: Any, length: Any, label: str) -> tuple[int, int, bytes]:
    if not isinstance(offset, int) or not isinstance(length, int) or offset < 0 or length <= 0:
        raise AssetStoreError(f"{label}: invalid offset/length")
    end = offset + length
    if end > len(payload):
        raise AssetStoreError(f"{label}: range exceeds retained container")
    return offset, length, payload[offset:end]


def _portrait_index(
    *,
    receipt: dict[str, Any],
    game_root: Path,
    store_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    archive = game_root / "DBDAT" / "MINIFOTO.PKF"
    if not archive.is_file():
        raise AssetStoreError(f"missing MINIFOTO.PKF: {archive}")
    archive_bytes = archive.read_bytes()
    after_hash = _require_sha(receipt.get("minifoto_sha256_after"), "face receipt after hash")
    if sha256_bytes(archive_bytes) != after_hash:
        raise AssetStoreError("MINIFOTO.PKF does not match face receipt minifoto_sha256_after")
    before_hash = _require_sha(receipt.get("minifoto_sha256_before"), "face receipt before hash")
    loose_dir = game_root / "DBDAT" / "MINIFOTO"
    rows = receipt.get("rows")
    if not isinstance(rows, list):
        raise AssetStoreError("face receipt rows must be a list")

    portraits: list[dict[str, Any]] = []
    referenced_loose_names: set[str] = set()
    counts = {"cached_output": 0, "unresolved": 0, "native_no_photo": 0, "missing_source": 0, "missing_preview": 0}
    for row in sorted((item for item in rows if isinstance(item, dict)), key=lambda item: int(item.get("record_id", 0))):
        record_id = row.get("record_id")
        if not isinstance(record_id, int) or record_id < 1:
            raise AssetStoreError("face receipt has invalid record_id")
        status = row.get("status")
        if status == "intentionally-no-photo":
            portraits.append({
                "record_id": record_id,
                "status": "native-no-photo",
                "regeneration": {"state": "source-regenerable", "reasons": ["PM99 native no-photo state is explicit in the receipt"]},
            })
            counts["native_no_photo"] += 1
            continue
        if status != "applied":
            portraits.append({
                "record_id": record_id,
                "status": "unresolved",
                "regeneration": {"state": "non-regenerable-legacy", "reasons": [f"legacy receipt status: {status}"]},
            })
            counts["unresolved"] += 1
            continue

        entry: dict[str, Any] = {
            "record_id": record_id,
            "status": "cached-output",
            "regeneration": {"state": "non-regenerable-legacy", "reasons": _legacy_reason("portrait")},
        }
        source_path = Path(row["source_image_path"]) if isinstance(row.get("source_image_path"), str) else None
        preview_path = Path(row["preview_path"]) if isinstance(row.get("preview_path"), str) else None
        if source_path is not None and source_path.is_file():
            entry["source"] = _put_file(store_root, source_path)
        else:
            counts["missing_source"] += 1
        if preview_path is not None and preview_path.is_file():
            entry["preview"] = _put_file(store_root, preview_path)
        else:
            counts["missing_preview"] += 1

        storage = row.get("storage")
        if storage == "MINIFOTO.PKF":
            result = row.get("replace_result")
            if not isinstance(result, dict):
                raise AssetStoreError(f"portrait {record_id}: archive result is missing")
            offset, length, raw_bitmap = _read_slice(
                archive_bytes, result.get("bitmap_offset"), result.get("bitmap_length"), f"portrait {record_id}",
            )
            entry["output"] = {
                "storage": storage,
                "blob": _put_bytes(store_root, raw_bitmap),
                "offset": offset,
                "length": length,
                "container_before_sha256": before_hash,
                "container_after_sha256": after_hash,
            }
        elif storage == "loose-DBDAT/MINIFOTO":
            expected = f"J96{record_id:05d}.BMP"
            loose_path = loose_dir / expected
            if not loose_path.is_file():
                raise AssetStoreError(f"portrait {record_id}: expected loose output missing: {loose_path}")
            referenced_loose_names.add(expected)
            entry["output"] = {
                "storage": storage,
                "blob": _put_file(store_root, loose_path),
                "target_filename": expected,
            }
        else:
            raise AssetStoreError(f"portrait {record_id}: unsupported applied storage {storage!r}")
        portraits.append(entry)
        counts["cached_output"] += 1

    unlinked_loose: list[dict[str, Any]] = []
    if loose_dir.is_dir():
        for path in sorted(loose_dir.iterdir(), key=lambda item: item.name):
            if path.is_file() and LOOSE_NAME_RE.fullmatch(path.name) and path.name not in referenced_loose_names:
                unlinked_loose.append({"filename": path.name, "blob": _put_file(store_root, path)})
    return portraits, unlinked_loose, counts


def _kit_index(
    *,
    receipt: dict[str, Any],
    game_root: Path,
    store_root: Path,
) -> list[dict[str, Any]]:
    rows = receipt.get("patched")
    if not isinstance(rows, list):
        raise AssetStoreError("kit receipt patched must be a list")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("archive_name"), str):
            raise AssetStoreError("kit receipt contains invalid patch row")
        grouped.setdefault(row["archive_name"], []).append(row)
    kits: list[dict[str, Any]] = []
    for archive_name, patches in sorted(grouped.items()):
        archive_path = game_root / "DBDAT" / archive_name
        if not archive_path.is_file():
            raise AssetStoreError(f"missing kit archive: {archive_path}")
        archive_bytes = archive_path.read_bytes()
        before_hashes = {str(row.get("archive_sha256_before")) for row in patches}
        after_hashes = {str(row.get("archive_sha256_after")) for row in patches}
        if len(before_hashes) != 1 or len(after_hashes) != 1:
            raise AssetStoreError(f"{archive_name}: kit receipt does not declare one whole-archive base/output hash")
        before_hash = _require_sha(next(iter(before_hashes)), f"{archive_name} before hash")
        after_hash = _require_sha(next(iter(after_hashes)), f"{archive_name} after hash")
        if sha256_bytes(archive_bytes) != after_hash:
            raise AssetStoreError(f"{archive_name}: retained archive does not match receipt output hash")
        index_patches: list[dict[str, Any]] = []
        seen_ranges: set[tuple[int, int]] = set()
        for row in sorted(patches, key=lambda item: (int(item.get("team_id", 0)), int(item.get("slot", 0)))):
            offset, length, raw_bitmap = _read_slice(
                archive_bytes, row.get("bitmap_offset"), row.get("bitmap_length"),
                f"{archive_name} team {row.get('team_id')}",
            )
            if (offset, length) in seen_ranges:
                raise AssetStoreError(f"{archive_name}: duplicate patch range")
            seen_ranges.add((offset, length))
            expected = _require_sha(row.get("bitmap_sha256_after"), f"{archive_name} team {row.get('team_id')} bitmap hash")
            if sha256_bytes(raw_bitmap) != expected:
                raise AssetStoreError(f"{archive_name} team {row.get('team_id')}: raw bitmap does not match receipt")
            index_patches.append({
                "team_id": int(row["team_id"]),
                "slot": int(row["slot"]),
                "offset": offset,
                "length": length,
                "blob": _put_bytes(store_root, raw_bitmap),
            })
        kits.append({
            "archive_name": archive_name,
            "before_sha256": before_hash,
            "after_sha256": after_hash,
            "patches": index_patches,
            "regeneration": {"state": "non-regenerable-legacy", "reasons": _legacy_reason("kit")},
        })
    return kits


def build_2015_index(*, face_receipt_path: Path, kit_receipt_path: Path, game_root: Path, store_root: Path) -> dict[str, Any]:
    """Import exact retained artwork and return a canonical metadata index."""
    face_receipt = _load_json(face_receipt_path)
    kit_receipt = _load_json(kit_receipt_path)
    if not isinstance(face_receipt, dict) or not isinstance(kit_receipt, dict):
        raise AssetStoreError("receipts must be JSON objects")
    portraits, unlinked_loose, portrait_counts = _portrait_index(
        receipt=face_receipt, game_root=game_root, store_root=store_root,
    )
    kits = _kit_index(receipt=kit_receipt, game_root=game_root, store_root=store_root)
    cached_reasons = [
        "all indexed portrait and kit output bytes are stored by SHA-256",
        "replay requires each named PM99 container to match its declared before SHA-256",
        "unlinked loose outputs are retained separately so a replay cannot silently discard existing output files",
    ]
    if portrait_counts["unresolved"]:
        cached_reasons.append(f"{portrait_counts['unresolved']} portrait rows remain unresolved and are not fabricated")
    if portrait_counts["missing_source"] or portrait_counts["missing_preview"]:
        cached_reasons.append("some retained source/preview files were absent, but their byte-exact PM99 output cache remains indexed")
    known_limits = [
        "This is a local cache contract; it does not grant redistribution rights for third-party portrait sources.",
        "Exact output replay requires a verified matching pre-patch PM99 container and does not resize or repack archives.",
        "Legacy source URLs are evidence labels, not captured web-page content hashes.",
        "Legacy portraits and kits are intentionally marked non-regenerable until source/crop/renderer/palette contracts are captured.",
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "store_layout": {"blob_algorithm": "sha256", "blob_path_template": "blobs/{sha256[0:2]}/{sha256}"},
        "input_receipts": [
            _receipt(face_receipt_path, "legacy-face-stage-receipt"),
            _receipt(kit_receipt_path, "legacy-kit-stage-receipt"),
        ],
        "portraits": portraits,
        "kits": kits,
        "unlinked_loose_outputs": unlinked_loose,
        "build_modes": {
            "cached_output": {"status": "qualified-with-matching-base", "reasons": cached_reasons},
            "strict_source_provenance": {
                "status": "blocked",
                "reasons": sorted(set(_legacy_reason("portrait") + _legacy_reason("kit"))),
            },
        },
        "known_limits": known_limits,
    }


def write_index(store_root: Path, index: dict[str, Any]) -> Path:
    path = store_root / "index.json"
    path.write_bytes(canonical_json_bytes(index))
    return path


def read_index(store_root: Path) -> dict[str, Any]:
    path = store_root / "index.json"
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssetStoreError(f"invalid asset-store index: {exc}") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise AssetStoreError("asset-store index is not canonically encoded")
    return value


def _schema_errors(index: dict[str, Any]) -> list[str]:
    try:
        import jsonschema  # type: ignore[import-not-found]
    except ImportError:
        return []
    schema = _load_json(SCHEMA_PATH)
    errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(index), key=lambda item: list(item.absolute_path))
    return [f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}" for error in errors]


def validate_index(store_root: Path, *, verify_blobs: bool = False) -> dict[str, int]:
    index = read_index(store_root)
    errors = _schema_errors(index)
    if index.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version mismatch")
    if index.get("build_modes", {}).get("cached_output", {}).get("status") != "qualified-with-matching-base":
        errors.append("cached output mode must state matching-base qualification")
    if index.get("build_modes", {}).get("strict_source_provenance", {}).get("status") != "blocked":
        errors.append("legacy import must not claim strict source provenance")
    records = index.get("portraits", [])
    if not isinstance(records, list) or [row.get("record_id") for row in records if isinstance(row, dict)] != sorted(row.get("record_id") for row in records if isinstance(row, dict)):
        errors.append("portraits must be sorted by record_id")
    blobs: list[dict[str, str]] = []
    for portrait in records if isinstance(records, list) else []:
        if not isinstance(portrait, dict):
            continue
        for key in ("source", "preview"):
            if isinstance(portrait.get(key), dict):
                blobs.append(portrait[key])
        output = portrait.get("output")
        if isinstance(output, dict) and isinstance(output.get("blob"), dict):
            blobs.append(output["blob"])
    for kit in index.get("kits", []) if isinstance(index.get("kits"), list) else []:
        if isinstance(kit, dict):
            for patch in kit.get("patches", []):
                if isinstance(patch, dict) and isinstance(patch.get("blob"), dict):
                    blobs.append(patch["blob"])
    for loose in index.get("unlinked_loose_outputs", []) if isinstance(index.get("unlinked_loose_outputs"), list) else []:
        if isinstance(loose, dict) and isinstance(loose.get("blob"), dict):
            blobs.append(loose["blob"])
    unique: dict[str, str] = {}
    for blob in blobs:
        digest, relative = blob.get("sha256"), blob.get("blob")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            errors.append("blob reference has invalid SHA-256")
            continue
        expected = f"blobs/{digest[:2]}/{digest}"
        if relative != expected:
            errors.append(f"blob path does not match digest: {relative!r}")
            continue
        unique[digest] = relative
    if verify_blobs:
        for digest, relative in unique.items():
            blob_path = store_root / relative
            if not blob_path.is_file() or sha256_file(blob_path) != digest:
                errors.append(f"blob is missing or corrupt: {relative}")
    if errors:
        raise AssetStoreError("Asset store validation failed:\n- " + "\n- ".join(errors))
    return {"portrait_rows": len(records), "kit_archives": len(index.get("kits", [])), "unique_blobs": len(unique)}


def _command_import(args: argparse.Namespace) -> int:
    store = Path(args.store_root)
    index = build_2015_index(
        face_receipt_path=Path(args.face_receipt),
        kit_receipt_path=Path(args.kit_receipt),
        game_root=Path(args.game_root),
        store_root=store,
    )
    path = write_index(store, index)
    summary = validate_index(store, verify_blobs=True)
    print(json.dumps({"ok": True, "index": str(path), **summary}, sort_keys=True))
    return 0


def _command_validate(args: argparse.Namespace) -> int:
    summary = validate_index(Path(args.store_root), verify_blobs=args.verify_blobs)
    print(json.dumps({"ok": True, **summary}, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    importer = commands.add_parser("import-2015", help="import retained 2015 portrait/kit outputs")
    importer.add_argument("--face-receipt", required=True)
    importer.add_argument("--kit-receipt", required=True)
    importer.add_argument("--game-root", required=True)
    importer.add_argument("--store-root", required=True)
    importer.set_defaults(handler=_command_import)
    validate = commands.add_parser("validate", help="validate an existing local asset store")
    validate.add_argument("--store-root", required=True)
    validate.add_argument("--verify-blobs", action="store_true")
    validate.set_defaults(handler=_command_validate)
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except AssetStoreError as exc:
        print(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
