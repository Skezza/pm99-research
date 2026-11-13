#!/usr/bin/env python3
"""Dry-run or convert an explicit, hash-locked list of inactive local JSON files.

This is not a recursive cleanup command. Apply requires a reviewed manifest;
each converted file gets a durable completion record. Rollback uses that same
manifest's original byte hashes. Current registered input paths are excluded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import json_storage_v1 as storage


def _raw_sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def registered_references(root: Path) -> set[Path]:
    paths = set()
    for locator in (root / ".local/season-release-registry-v1/releases").glob("*/*/locator.json"):
        value = json.loads(locator.read_text())
        for candidate in value.values():
            if isinstance(candidate, str) and candidate.startswith(".local/"):
                paths.add(root / candidate)
    return paths


def checked_rows(manifest: dict, root: Path) -> list[tuple[Path, dict]]:
    if manifest.get("schema") != "pm99-json-storage-migration-v1":
        raise ValueError("unsupported migration manifest")
    rows = manifest.get("files")
    if not isinstance(rows, list) or not rows:
        raise ValueError("manifest requires explicit files")
    refs = registered_references(root)
    selected = []
    seen = set()
    for row in rows:
        relative = Path(row["path"])
        path = root / relative
        if (relative.is_absolute() or ".." in relative.parts
                or relative.parts[:1] != (".local",) or relative.suffix != ".json"
                or "game" in relative.parts
                or relative.parts[:2] == (".local", "season-release-registry-v1")
                or path.resolve() != path or path in seen):
            raise ValueError(f"unsafe or duplicate migration path: {relative}")
        if path in refs:
            raise ValueError(f"registered input is outside this inactive-file pilot: {relative}")
        if (type(row.get("logical_bytes")) is not int
                or not 0 < row["logical_bytes"] <= storage.MAX_DECODED_BYTES):
            raise ValueError("manifest JSON size is outside the pilot limit")
        if storage.sha256_file(path) != row["sha256"] or storage.size(path) != row["logical_bytes"]:
            raise ValueError(f"original byte binding changed: {relative}")
        json.loads(storage.read_bytes(path).decode("utf-8"))
        seen.add(path)
        selected.append((path, row))
    return selected


def run(manifest_path: Path, *, root: Path = ROOT, apply: bool = False,
        restore: bool = False, receipt_path: Path | None = None) -> dict:
    root = root.resolve()
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    rows = checked_rows(manifest, root)
    catalog = root / "data/preferred-season-releases-v1.json"
    catalog_hash = _raw_sha(catalog)
    expected_catalog = manifest.get("preferred_catalog_sha256")
    if catalog_hash != expected_catalog:
        raise ValueError("preferred catalogue differs from the reviewed manifest")
    prepared = {"utc": datetime.now(timezone.utc).isoformat(), "machine": socket.gethostname(),
                "source_session": os.environ.get("CODEX_THREAD_ID"),
                "manifest": str(manifest_path), "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
                "preferred_catalog_sha256": catalog_hash, "restore": restore,
                "apply": apply, "files": len(rows)}
    if not apply:
        return prepared
    if receipt_path is None or receipt_path.exists():
        raise ValueError("apply requires a new receipt path")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    # The header survives interruption and distinguishes partial from complete work.
    with receipt_path.open("x") as handle:
        handle.write(json.dumps({"event": "prepared", **prepared}) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        total = 0
        for path, row in rows:
            if _raw_sha(catalog) != catalog_hash:
                raise ValueError("preferred catalogue changed; stop after the recorded subset")
            if storage.sha256_file(path) != row["sha256"]:
                raise ValueError("source changed after preflight")
            already = storage.physical_path(path) == (path if restore else storage.compressed_path(path))
            if already:
                handle.write(json.dumps({"event": "already-converted", "path": row["path"]}) + "\n")
            else:
                result = (storage.restore_file(path, expected_sha256=row['sha256']) if restore
                          else storage.compress_file(path, expected_sha256=row['sha256']))
                if storage.sha256_file(path) != row["sha256"]:
                    raise ValueError("post-conversion original byte hash differs")
                total += result["allocated_released"]
                handle.write(json.dumps({"event": "converted", **result}) + "\n")
                print(json.dumps(result), flush=True)
            handle.flush()
            os.fsync(handle.fileno())
        if _raw_sha(catalog) != catalog_hash:
            raise ValueError("catalogue changed; do not mark batch complete")
        summary = {"event": "complete", "files": len(rows), "allocated_released": total,
                   "preferred_catalog_unchanged": True}
        handle.write(json.dumps(summary) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--restore", action="store_true")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.manifest, apply=args.apply, restore=args.restore,
                         receipt_path=args.receipt), indent=2))


if __name__ == "__main__":
    main()
