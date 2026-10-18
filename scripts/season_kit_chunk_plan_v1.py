#!/usr/bin/env python3
"""Freeze one deterministic, allocation-bound seasonal kit work chunk.

The source capture tool works on an allocation-shaped input.  This helper
derives that deliberately small input from a complete, canonical carrier
allocation without changing the allocation itself.  Its separate plan receipt
records both hashes, the selection rule, and every carrier deliberately left
out, so a later chunk cannot silently reuse a stale capture.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.season_kit_catalogue_v1 import canonical_json_bytes


SCHEMA = "pm99-season-kit-source-chunk-plan-v1"
ALLOCATION_SCHEMA = "pm99-season-carrier-allocation-v1"


class ChunkPlanError(ValueError):
    """The frozen allocation cannot safely produce a source chunk."""


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_object(path: Path) -> tuple[Path, dict[str, Any], str]:
    try:
        if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
            raise ChunkPlanError(f"allocation must be a regular non-symlink file: {path}")
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ChunkPlanError(f"allocation is not valid JSON: {exc}") from exc
    if not isinstance(value, dict) or canonical_json_bytes(value) != payload:
        raise ChunkPlanError("allocation must be a canonical JSON object")
    return path.resolve(), value, _sha(payload)


def build_plan(*, allocation_path: Path, excluded_carrier_ids: list[int], limit: int) -> tuple[dict[str, Any], dict[str, Any]]:
    if not 1 <= limit <= 25:
        raise ChunkPlanError("limit must be between 1 and 25")
    if any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in excluded_carrier_ids):
        raise ChunkPlanError("excluded carrier IDs must be positive integers")
    if excluded_carrier_ids != sorted(set(excluded_carrier_ids)):
        raise ChunkPlanError("excluded carrier IDs must be sorted and unique")
    full_path, full, full_sha = _read_object(allocation_path)
    if full.get("schema_version") != ALLOCATION_SCHEMA:
        raise ChunkPlanError(f"allocation must use {ALLOCATION_SCHEMA}")
    assignments = full.get("assignments")
    if not isinstance(assignments, list):
        raise ChunkPlanError("allocation assignments must be a list")
    ordered: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in assignments:
        if not isinstance(row, Mapping):
            raise ChunkPlanError("allocation assignments must be objects")
        carrier = row.get("carrier_id")
        club = row.get("club_name")
        if isinstance(carrier, bool) or not isinstance(carrier, int) or carrier <= 0 or not isinstance(club, str) or not club.strip():
            raise ChunkPlanError("allocation assignment requires positive carrier_id and club_name")
        if carrier in seen:
            raise ChunkPlanError("allocation has duplicate carrier IDs")
        seen.add(carrier)
        ordered.append(dict(row))
    ordered.sort(key=lambda row: row["carrier_id"])
    missing = sorted(set(excluded_carrier_ids) - seen)
    if missing:
        raise ChunkPlanError(f"excluded carrier IDs absent from allocation: {missing}")
    selected = [row for row in ordered if row["carrier_id"] not in set(excluded_carrier_ids)][:limit]
    if len(selected) != limit:
        raise ChunkPlanError("allocation has too few non-excluded carriers for requested chunk")
    subset = {"season": full.get("season"), "assignments": selected}
    selected_ids = [row["carrier_id"] for row in selected]
    plan = {
        "schema_version": SCHEMA,
        "season": full.get("season"),
        "policy": {
            "selection": "ascending-carrier-id-after-explicit-exclusions",
            "source_capture": "fresh-cache-required; no stale capture reuse",
            "fallback": "no-native-fallback-for-continuing-clubs",
            "release": "source-and-asset-chunk-only; not-a-season-release",
        },
        "full_allocation": {"path": str(full_path), "sha256": full_sha},
        "subset_allocation": {"sha256": _sha(canonical_json_bytes(subset))},
        "selection": {
            "limit": limit,
            "excluded_carrier_ids": excluded_carrier_ids,
            "selected_carrier_ids": selected_ids,
            "selected_assignments_sha256": _sha(canonical_json_bytes(selected)),
            "selected_clubs": [{"carrier_id": row["carrier_id"], "club_name": row["club_name"]} for row in selected],
        },
    }
    return subset, plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-allocation", required=True, type=Path)
    parser.add_argument("--exclude-carrier", action="append", type=int, default=[])
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--output-dir", required=True, type=Path, help="new, nonexistent chunk directory")
    args = parser.parse_args()
    if args.output_dir.exists() or args.output_dir.is_symlink():
        parser.error(f"refusing to replace chunk directory: {args.output_dir}")
    excluded = sorted(args.exclude_carrier)
    try:
        subset, plan = build_plan(allocation_path=args.full_allocation, excluded_carrier_ids=excluded, limit=args.limit)
    except ChunkPlanError as exc:
        parser.error(str(exc))
    try:
        os.mkdir(args.output_dir)
        (args.output_dir / "chunk-allocation.json").write_bytes(canonical_json_bytes(subset))
        (args.output_dir / "kit-source-chunk-plan-v1.json").write_bytes(canonical_json_bytes(plan))
    except Exception:
        if args.output_dir.exists():
            for child in args.output_dir.iterdir():
                child.unlink()
            args.output_dir.rmdir()
        raise
    print(json.dumps({"selected_carrier_ids": plan["selection"]["selected_carrier_ids"], "subset_allocation_sha256": plan["subset_allocation"]["sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
