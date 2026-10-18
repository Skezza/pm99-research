#!/usr/bin/env python3
"""Resume-safe batch for exact target-season manager promotion."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
DIRECT = ROOT / "scripts/apply_target_season_manager_repair_v1.py"
BASE = LOCAL / "season-pipeline-v2/pm99-base-clean"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.pm99_season_play_v1 import REVISIONS  # noqa: E402


SCHEMA = "pm99-season-direct-target-manager-repair-batch-v1"


class BatchError(ValueError):
    """One season cannot complete the bounded manager repair."""


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BatchError(f"cannot read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise BatchError(f"JSON object required: {path}")
    return value


def _ledger(season: str) -> Path:
    candidates = []
    for path in (LOCAL / "season-overlays-v1" / season).glob("manager-v*/opening-manager-ledger.json"):
        match = re.fullmatch(r"manager-v([1-9][0-9]*)", path.parent.name)
        if match:
            candidates.append((int(match.group(1)), path))
    if not candidates:
        raise BatchError(f"{season}: no versioned manager ledger exists")
    return max(candidates, key=lambda row: row[0])[1]


def _paths(season: str) -> dict[str, Path]:
    revision = REVISIONS[season]
    ingress = LOCAL / "season-static-ingress-v1" / f"{season}-worldwide-source-backed-{revision}"
    return {
        "strict": LOCAL / "season-worldwide-merged-v1" / season / revision / "strict-season-package.json",
        "source": ingress / "season-package.source-writable.json",
        "alias": ingress / "season-package.alias-bound.json",
        "reconciled": ingress / "season-package.reconciled.json",
        "runtime": LOCAL / "season-runtime-candidates-v1" / season / f"worldwide-source-backed-{revision}" / "game",
        "receipt": LOCAL / "season-direct-target-manager-repairs-v1" / f"{season}.json",
    }


def _run_one(season: str) -> dict[str, Any]:
    paths = _paths(season)
    if paths["receipt"].is_file():
        receipt = _read(paths["receipt"])
        if receipt.get("schema_version") != "pm99-season-direct-target-manager-repair-v1" or receipt.get("state") != "applied-directly-to-alpha-game":
            raise BatchError(f"{season}: existing receipt is not a completed manager repair")
        return {"season": season, "status": "reused", "coverage": receipt.get("coverage"),
                "receipt": paths["receipt"].relative_to(ROOT).as_posix()}
    required = [paths[key] for key in ("source", "alias", "reconciled", "runtime")]
    if not all(path.exists() for path in required):
        raise BatchError(f"{season}: current recipe or runtime input is missing")
    command = [sys.executable, str(DIRECT)]
    for key in ("strict", "source", "alias", "reconciled"):
        if paths[key].is_file():
            command.extend(("--package", str(paths[key])))
    command.extend((
        "--compile-package", str(paths["reconciled"]),
        "--ledger", str(_ledger(season)),
        "--base-tree", str(BASE),
        "--runtime-game", str(paths["runtime"]),
        "--receipt", str(paths["receipt"]),
        "--apply",
    ))
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if completed.returncode or not paths["receipt"].is_file():
        raise BatchError(json.dumps({
            "season": season, "returncode": completed.returncode,
            "stdout": completed.stdout.strip(), "stderr": completed.stderr.strip(),
        }, ensure_ascii=False, sort_keys=True))
    receipt = _read(paths["receipt"])
    return {"season": season, "status": "applied", "coverage": receipt.get("coverage"),
            "receipt": paths["receipt"].relative_to(ROOT).as_posix()}


def batch(*, seasons: Sequence[str], jobs: int) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
        pending = {executor.submit(_run_one, season): season for season in seasons}
        for future in concurrent.futures.as_completed(pending):
            season = pending[future]
            try:
                event = future.result()
            except BatchError as exc:
                failures.append({"season": season, "error": str(exc)})
                print(json.dumps({"season": season, "status": "failed", "error": str(exc)}), flush=True)
            else:
                events.append(event)
                print(json.dumps(event, sort_keys=True), flush=True)
    events.sort(key=lambda row: str(row["season"]))
    return {
        "schema_version": SCHEMA,
        "state": "complete" if not failures else "incomplete",
        "jobs": jobs, "events": events, "failures": failures,
        "summary": {
            "season_count": len(seasons), "completed_count": len(events),
            "failed_count": len(failures),
            "evidence_bound_count": sum(int((row.get("coverage") or {}).get("evidence_bound_count") or 0) for row in events),
            "remaining_gap_count": sum(int((row.get("coverage") or {}).get("gap_count") or 0) for row in events),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", action="append", choices=sorted(REVISIONS))
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--output", type=Path, default=LOCAL / "season-direct-target-manager-repairs-v1/batch-receipt.json")
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")
    result = batch(seasons=sorted(args.season or REVISIONS), jobs=args.jobs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], sort_keys=True))
    return 0 if not result["failures"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
