#!/usr/bin/env python3
"""Audit position-aware rating remediation from package through compiled DB.

This is a focused clean-static gate, not a playable-release claim.  It checks
the new immutable quality revisions while leaving calendar, kits and runtime
evidence attached to the existing preferred gameplay candidates.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.pm99_season_play_v1 import REVISIONS  # noqa: E402
from scripts.pm99_season_qa_v1 import (  # noqa: E402
    audit_compiled_handling,
    audit_compiled_managers,
    audit_recipe,
)
from scripts.season_package_v2 import canonical_json_bytes, validate_package  # noqa: E402


SCHEMA = "pm99-season-quality-remediation-audit-v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _paths(season: str) -> tuple[Path, Path]:
    if season == "2017-18":
        root = ROOT / ".local/season-static-ingress-v1/2017-18-worldwide-source-backed-qa2"
    else:
        root = ROOT / ".local/season-quality-ingress-v1" / season / "qa1"
    return root / "season-package.reconciled.json", root


def audit_season(season: str) -> dict[str, Any]:
    package_path, root = _paths(season)
    package = json.loads(package_path.read_text(encoding="utf-8"))
    if not isinstance(package, dict):
        raise ValueError(f"package is not an object: {package_path}")
    validate_package(package, strict=True)
    recipe = audit_recipe(package, season=season)
    handling = audit_compiled_handling(package, game=root / "game")
    managers = audit_compiled_managers(package, game=root / "game", season=season)
    receipt_path = root / "compiler-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    mismatches = []
    for row in receipt.get("outputs", []):
        if not isinstance(row, Mapping):
            continue
        path = root / "game" / str(row.get("path") or "")
        expected = str(row.get("sha256") or "")
        actual = _sha256(path) if path.is_file() else None
        if actual != expected:
            mismatches.append({"path": str(row.get("path") or ""), "expected": expected, "actual": actual})
    failures = {
        "recipe_rating": int(recipe["rating_failure_count"]),
        "compiled_handling": int(handling["failure_count"]),
        "compiled_managers": int(managers["failure_count"]),
        "compiler_hash": len(mismatches),
    }
    return {
        "season": season,
        "result": "pass" if not any(failures.values()) else "fail",
        "inputs": {
            "package": str(package_path.relative_to(ROOT)),
            "package_sha256": _sha256(package_path),
            "compiler_receipt": str(receipt_path.relative_to(ROOT)),
            "compiler_receipt_sha256": _sha256(receipt_path),
        },
        "failures": failures,
        "recipe": {
            "player_count": recipe["player_count"],
            "rating_failure_count": recipe["rating_failure_count"],
            "date_queue_count": recipe["date_failure_count"],
            "lineup_queue_count": recipe["lineup_failure_count"],
        },
        "compiled": {
            "handling_failure_count": handling["failure_count"],
            "manager_failure_count": managers["failure_count"],
            "unverified_preserve_position_count": handling["unverified_position_player_count"],
            "output_hash_mismatch_count": len(mismatches),
            "output_hash_mismatches": mismatches,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--season", action="append")
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args(argv)
    seasons = sorted(set(args.season or REVISIONS))
    unknown = sorted(set(seasons) - set(REVISIONS))
    if unknown:
        parser.error("unsupported seasons: " + ", ".join(unknown))
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")
    with concurrent.futures.ProcessPoolExecutor(max_workers=min(args.jobs, len(seasons))) as pool:
        rows = list(pool.map(audit_season, seasons))
    result = {
        "schema_version": SCHEMA,
        "classification": "clean-static-quality-remediation-not-playable-release",
        "summary": {
            "season_count": len(rows),
            "pass_count": sum(row["result"] == "pass" for row in rows),
            "fail_count": sum(row["result"] != "pass" for row in rows),
            "remaining_date_queue_count": sum(row["recipe"]["date_queue_count"] for row in rows),
            "remaining_lineup_queue_count": sum(row["recipe"]["lineup_queue_count"] for row in rows),
        },
        "seasons": rows,
    }
    output = args.output.resolve()
    if output.exists() or output.is_symlink():
        parser.error(f"refusing to replace output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0 if result["summary"]["fail_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
