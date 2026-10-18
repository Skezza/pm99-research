#!/usr/bin/env python3
"""Resume-safe repair of proven current-compiler Handling readback drift."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
DIRECT_REPAIR = ROOT / "scripts" / "apply_compiled_handling_readback_repair_v1.py"
BASE_TREE = LOCAL / "season-pipeline-v2" / "pm99-base-clean"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.pm99_season_play_v1 import REVISIONS  # noqa: E402


SCHEMA = "pm99-season-direct-compiled-handling-readback-repair-batch-v1"


class BatchRepairError(ValueError):
    """A current game cannot receive the bounded readback repair."""


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BatchRepairError(f"cannot read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise BatchRepairError(f"JSON object required: {path}")
    return value


def _paths(season: str) -> dict[str, Path]:
    revision = REVISIONS.get(season)
    if revision is None:
        raise BatchRepairError(f"unsupported post-1999 season: {season}")
    ingress = LOCAL / "season-static-ingress-v1" / f"{season}-worldwide-source-backed-{revision}"
    return {
        "package": ingress / "season-package.reconciled.json",
        "runtime": LOCAL / "season-runtime-candidates-v1" / season / f"worldwide-source-backed-{revision}" / "game",
        "receipt": LOCAL / "season-direct-compiled-handling-readback-repairs-v1" / f"{season}.json",
    }


def _run_one(season: str, *, rerun: bool) -> dict[str, Any]:
    paths = _paths(season)
    missing = [name for name, path in paths.items() if name != "receipt" and not path.exists()]
    if missing:
        raise BatchRepairError(f"{season} lacks required current inputs: {', '.join(missing)}")
    if paths["receipt"].is_file() and not rerun:
        receipt = _read(paths["receipt"])
        return {
            "season": season,
            "status": "reused",
            "state": receipt.get("state"),
            "receipt": str(paths["receipt"].relative_to(ROOT)),
        }
    command = [
        sys.executable, str(DIRECT_REPAIR),
        "--package", str(paths["package"]),
        "--base-tree", str(BASE_TREE),
        "--runtime-game", str(paths["runtime"]),
        "--receipt", str(paths["receipt"]),
        "--apply",
    ]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if completed.returncode or not paths["receipt"].is_file():
        raise BatchRepairError(json.dumps({
            "season": season,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }, ensure_ascii=False, sort_keys=True))
    receipt = _read(paths["receipt"])
    state = receipt.get("state")
    if state not in {"applied-directly-to-alpha-game", "no-bounded-readback-repair-required"}:
        raise BatchRepairError(f"{season} has an unexpected direct readback receipt state: {state!r}")
    return {
        "season": season,
        "status": "applied" if state == "applied-directly-to-alpha-game" else "not-affected",
        "target_count": len(receipt.get("targets") or []),
        "remaining_compiled_handling_failure_count": receipt.get("remaining_compiled_handling_failure_count"),
        "receipt": str(paths["receipt"].relative_to(ROOT)),
    }


def batch(*, seasons: Sequence[str], rerun: bool, jobs: int) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    failures: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
        pending = {executor.submit(_run_one, season, rerun=rerun): season for season in seasons}
        for future in concurrent.futures.as_completed(pending):
            season = pending[future]
            try:
                event = future.result()
            except BatchRepairError as exc:
                failures.append(str(exc))
                print(json.dumps({"season": season, "status": "failed", "error": str(exc)}), flush=True)
                continue
            events.append(event)
            print(json.dumps(event, sort_keys=True), flush=True)
    if failures:
        raise BatchRepairError("; ".join(failures))
    events.sort(key=lambda row: str(row["season"]))
    return {
        "schema_version": SCHEMA,
        "state": "complete",
        "jobs": jobs,
        "events": events,
        "applied_count": sum(event["status"] == "applied" for event in events),
        "not_affected_count": sum(event["status"] == "not-affected" for event in events),
        "reused_count": sum(event["status"] == "reused" for event in events),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", action="append", choices=sorted(REVISIONS),
                        help="Repair one season; repeat. Defaults to all playable post-1999 seasons.")
    parser.add_argument("--rerun", action="store_true", help="Re-verify and rewrite an existing direct repair.")
    parser.add_argument("--jobs", type=int, default=2, help="Independent season checks to run at once (default: 2).")
    parser.add_argument("--output", type=Path,
                        default=LOCAL / "season-direct-compiled-handling-readback-repairs-v1" / "batch-receipt.json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.jobs < 1:
        raise SystemExit("--jobs must be at least 1")
    seasons = sorted(args.season or REVISIONS)
    try:
        result = batch(seasons=seasons, rerun=args.rerun, jobs=args.jobs)
    except BatchRepairError as exc:
        print(f"direct-compiled-handling-readback-repair-batch: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "state": result["state"],
        "applied_count": result["applied_count"],
        "not_affected_count": result["not_affected_count"],
        "reused_count": result["reused_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
