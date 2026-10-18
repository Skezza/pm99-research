#!/usr/bin/env python3
"""Prove a kit application did not mutate compiler or portrait payloads."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

KIT_ARCHIVES = {"DBDAT/BIGCAMP.PKF", "DBDAT/BIGESC.PKF", "DBDAT/MINIESC.PKF", "DBDAT/NANOESC.PKF", "DBDAT/RIDIESC.PKF"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-tree", type=Path, required=True)
    parser.add_argument("--compiler-receipt", type=Path, required=True)
    parser.add_argument("--post-portrait-audit", type=Path, required=True)
    parser.add_argument("--kit-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    compiler = json.loads(args.compiler_receipt.read_text(encoding="utf-8"))
    portraits = json.loads(args.post_portrait_audit.read_text(encoding="utf-8"))
    kits = json.loads(args.kit_receipt.read_text(encoding="utf-8"))
    expected = {str(row["path"]): str(row["sha256"]) for row in compiler["outputs"]}
    expected.update({str(path): str(value) for path, value in portraits["critical_file_sha256"].items() if path not in KIT_ARCHIVES})
    files = {path: {"expected_sha256": value, "actual_sha256": digest(args.game_tree / path)} for path, value in sorted(expected.items())}
    if any(row["expected_sha256"] != row["actual_sha256"] for row in files.values()):
        parser.error("a non-kit compiler/portrait payload changed")
    if int(kits["coverage"]["foreign_patched_record_count"]) != len(kits["foreign_events"]):
        parser.error("kit event count does not match receipt coverage")
    result = {"schema_version": "pm99-world-2015-kit-postwrite-audit-v1", "result": "pass", "game_tree": str(args.game_tree.resolve()), "non_kit_files": files, "kit_application_receipt_sha256": digest(args.kit_receipt), "foreign_event_readback_count": len(kits["foreign_events"]), "native_fallback_count": len(kits["native_fallbacks"])}
    args.output.write_text(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"result": "pass", "non_kit_file_count": len(files), "foreign_event_readback_count": len(kits["foreign_events"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
