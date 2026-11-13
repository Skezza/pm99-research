#!/usr/bin/env python3
"""Prove a versioned game-tree variant differs from its baseline only in kits."""

from __future__ import annotations

try:
    from scripts import json_storage_io_v1 as storage_io
except ModuleNotFoundError:
    import sys as _storage_sys
    from pathlib import Path as _StoragePath
    _storage_sys.path.insert(0, str(next(p for p in _StoragePath(__file__).resolve().parents if (p / 'scripts/json_storage_io_v1.py').is_file())))
    from scripts import json_storage_io_v1 as storage_io

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


KIT_PATHS = {
    Path("DBDAT/BIGCAMP.PKF"),
    Path("DBDAT/BIGESC.PKF"),
    Path("DBDAT/MINIESC.PKF"),
    Path("DBDAT/NANOESC.PKF"),
    Path("DBDAT/RIDIESC.PKF"),
}
SCHEMA = "pm99-kit-only-game-tree-audit-v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with storage_io.open_file(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def files(root: Path) -> set[Path]:
    return {path.relative_to(root) for path in storage_io.glob(root, '*', recursive=True) if storage_io.is_file(path)}


def audit(*, baseline: Path, target: Path, kit_receipt: dict[str, Any]) -> dict[str, Any]:
    baseline_files, target_files = files(baseline), files(target)
    errors: list[dict[str, str]] = []
    if baseline_files != target_files:
        for path in sorted(baseline_files ^ target_files):
            errors.append({"code": "file-set-mismatch", "path": str(path)})
    checked_nonkit = 0
    for path in sorted((baseline_files & target_files) - KIT_PATHS):
        checked_nonkit += 1
        if sha256(baseline / path) != sha256(target / path):
            errors.append({"code": "non-kit-file-changed", "path": str(path)})
    expected_archives = ((kit_receipt.get("target") or {}).get("archive_sha256_after") or {})
    for path in sorted(KIT_PATHS):
        expected = expected_archives.get(path.name)
        actual = sha256(target / path) if storage_io.is_file(target / path) else None
        if not expected or actual != expected:
            errors.append({"code": "kit-archive-readback-mismatch", "path": str(path)})
    event_count = len(kit_receipt.get("foreign_events") or [])
    expected_events = int((kit_receipt.get("coverage") or {}).get("foreign_patched_record_count") or 0)
    if event_count != expected_events:
        errors.append({"code": "kit-event-count-mismatch", "path": "foreign_events"})
    return {
        "schema_version": SCHEMA,
        "result": "pass" if not errors else "fail",
        "baseline_game_tree": str(storage_io.resolve(baseline)),
        "target_game_tree": str(storage_io.resolve(target)),
        "coverage": {"checked_nonkit_file_count": checked_nonkit, "checked_kit_archive_count": len(KIT_PATHS), "foreign_event_readback_count": event_count, "error_count": len(errors)},
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-game-tree", type=Path, required=True)
    parser.add_argument("--target-game-tree", type=Path, required=True)
    parser.add_argument("--kit-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(
        baseline=args.baseline_game_tree,
        target=args.target_game_tree,
        kit_receipt=json.loads(storage_io.read_text(args.kit_receipt, encoding='utf-8')),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    storage_io.write_text(args.output, json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({"result": result["result"], **result["coverage"]}, sort_keys=True))
    return 0 if result["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
