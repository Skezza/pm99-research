#!/usr/bin/env python3
"""Resume-safe batch application of bounded playable-recipe quality repairs.

The command intentionally does not rebuild, recrawl, or replace a whole
season.  It applies the direct source/base/cited-DOB repair only to seasons
with an outstanding date plausibility gate, then applies the coordinate-based
opening-XI goalkeeper repair only to seasons with that gate.  A completed
per-season receipt is the resume marker.
"""

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
BASE_TREE = LOCAL / "season-pipeline-v2/pm99-base-clean"
DATE_REPAIR = ROOT / "scripts/apply_birth_date_plausibility_repairs_v1.py"
POSITION_REPAIR = ROOT / "scripts/apply_opening_lineup_position_repairs_v1.py"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.pm99_season_play_v1 import REVISIONS  # noqa: E402


SCHEMA = "pm99-season-recipe-quality-repair-batch-v1"
DATE_DEFAULTS = (
    "2000-01", "2001-02", "2002-03", "2003-04", "2004-05", "2005-06",
    "2006-07", "2007-08", "2008-09", "2009-10", "2010-11", "2011-12",
    "2020-21", "2023-24", "2024-25", "2025-26",
)
POSITION_DEFAULTS = (
    "2001-02", "2002-03", "2003-04", "2004-05", "2005-06", "2006-07",
    "2007-08", "2009-10", "2010-11", "2011-12", "2012-13", "2013-14",
    "2014-15", "2016-17", "2018-19", "2019-20", "2021-22", "2025-26",
)


class BatchRepairError(ValueError):
    pass


def _paths(season: str) -> dict[str, Path]:
    revision = REVISIONS.get(season)
    if revision is None:
        raise BatchRepairError(f"unsupported playable season: {season}")
    ingress = LOCAL / "season-static-ingress-v1" / f"{season}-worldwide-source-backed-{revision}"
    return {
        "strict": LOCAL / "season-worldwide-merged-v1" / season / revision / "strict-season-package.json",
        "source": ingress / "season-package.source-writable.json",
        "alias": ingress / "season-package.alias-bound.json",
        "reconciled": ingress / "season-package.reconciled.json",
        "runtime": LOCAL / "season-runtime-candidates-v1" / season / f"worldwide-source-backed-{revision}" / "game",
        "intake": ROOT / "seasons" / season / "source-intake.json",
    }


def _packages(paths: dict[str, Path]) -> list[str]:
    result: list[str] = []
    for key in ("strict", "source", "alias", "reconciled"):
        if paths[key].is_file():
            result.extend(("--package", str(paths[key])))
    if str(paths["reconciled"]) not in result:
        raise BatchRepairError("reconciled recipe snapshot is unavailable")
    return result


def _command(*, kind: str, season: str, paths: dict[str, Path]) -> tuple[list[str], Path]:
    common = _packages(paths) + [
        "--compile-package", str(paths["reconciled"]), "--base-tree", str(BASE_TREE),
        "--runtime-game", str(paths["runtime"]), "--apply",
    ]
    if kind == "date":
        receipt = LOCAL / "season-direct-birth-date-plausibility-repairs-v1" / f"{season}.json"
        return [sys.executable, str(DATE_REPAIR), *common,
                "--source-intake", str(paths["intake"]), "--receipt", str(receipt)], receipt
    if kind == "position":
        receipt = LOCAL / "season-direct-opening-lineup-position-repairs-v1" / f"{season}.json"
        return [sys.executable, str(POSITION_REPAIR), *common, "--receipt", str(receipt)], receipt
    raise BatchRepairError(f"unknown repair kind: {kind}")


def _run_one(kind: str, season: str) -> dict[str, Any]:
    paths = _paths(season)
    required = ("source", "alias", "reconciled", "runtime")
    missing = [key for key in required if not paths[key].exists()]
    if kind == "date" and not paths["intake"].is_file():
        missing.append("intake")
    if missing:
        raise BatchRepairError(f"{season} lacks required inputs: {', '.join(missing)}")
    command, receipt = _command(kind=kind, season=season, paths=paths)
    if receipt.is_file():
        value = json.loads(receipt.read_text(encoding="utf-8"))
        if value.get("state") == "applied-directly-to-alpha-game":
            return {"season": season, "kind": kind, "status": "reused", "receipt": str(receipt.relative_to(ROOT))}
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    # The default queue is deliberately broad.  A source-package revision may
    # already have resolved a season's dates, in which case the direct repair
    # correctly declines to manufacture a zero-change receipt.  That is a
    # completed, QA-verifiable no-op, not a batch failure.
    if (
        kind == "date"
        and completed.returncode == 2
        and "no implausible player birth dates require repair" in completed.stderr
    ):
        return {"season": season, "kind": kind, "status": "not-required"}
    if completed.returncode or not receipt.is_file():
        raise BatchRepairError(json.dumps({
            "season": season, "kind": kind, "returncode": completed.returncode,
            "stdout": completed.stdout.strip(), "stderr": completed.stderr.strip(),
        }, ensure_ascii=False, sort_keys=True))
    value = json.loads(receipt.read_text(encoding="utf-8"))
    return {
        "season": season, "kind": kind, "status": "applied",
        "target_player_count": value.get("target_player_count"), "actions": value.get("actions"),
        "receipt": str(receipt.relative_to(ROOT)),
    }


def _phase(*, kind: str, seasons: Sequence[str], jobs: int) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    failures: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = {executor.submit(_run_one, kind, season): season for season in sorted(set(seasons))}
        for future in concurrent.futures.as_completed(futures):
            season = futures[future]
            try:
                event = future.result()
            except (BatchRepairError, OSError, ValueError) as exc:
                failures.append(str(exc))
                print(json.dumps({"season": season, "kind": kind, "status": "failed", "error": str(exc)}), flush=True)
            else:
                events.append(event)
                print(json.dumps(event, sort_keys=True), flush=True)
    return sorted(events, key=lambda row: (str(row["kind"]), str(row["season"]))), failures


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-season", action="append", choices=sorted(REVISIONS))
    parser.add_argument("--position-season", action="append", choices=sorted(REVISIONS))
    parser.add_argument("--skip-date", action="store_true",
                        help="do not run the DOB-plausibility phase")
    parser.add_argument("--skip-position", action="store_true",
                        help="do not run the opening-lineup position phase")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--output", type=Path,
                        default=LOCAL / "season-recipe-quality-repairs-v1/batch-receipt.json")
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")
    if args.skip_date and args.skip_position:
        parser.error("at least one repair phase must be selected")
    date_events, date_failures = _phase(
        kind="date", seasons=() if args.skip_date else args.date_season or DATE_DEFAULTS, jobs=args.jobs,
    )
    position_events, position_failures = _phase(
        kind="position", seasons=() if args.skip_position else args.position_season or POSITION_DEFAULTS, jobs=args.jobs,
    )
    result = {
        "schema_version": SCHEMA,
        "state": "complete" if not date_failures and not position_failures else "completed-with-failures",
        "jobs": args.jobs, "date_events": date_events, "position_events": position_events,
        "failures": [*date_failures, *position_failures],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "state": result["state"], "date_applied": sum(row["status"] == "applied" for row in date_events),
        "position_applied": sum(row["status"] == "applied" for row in position_events),
        "failure_count": len(result["failures"]),
    }, sort_keys=True))
    return 0 if not result["failures"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
