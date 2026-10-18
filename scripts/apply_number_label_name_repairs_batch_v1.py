#!/usr/bin/env python3
"""Resume-safe direct application of proven rendered-squad-number name fixes.

This is a deliberately small alpha-maintenance batch: it discovers the one
current playable recipe for each post-1999 season, invokes the bounded direct
repair command, and treats the per-season repair receipt as its terminal
marker.  It never rebuilds a season whose direct repair receipt already
exists, and it never re-runs source acquisition, kit rendering, or manager
authoring.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
DIRECT_REPAIR = ROOT / "scripts" / "apply_number_label_name_repairs_v1.py"
BASE_TREE = LOCAL / "season-pipeline-v2" / "pm99-base-clean"
VERIFIED_BASE = LOCAL / "season-pipeline-v2" / "verified-base.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.pm99_season_play_v1 import REVISIONS  # noqa: E402


SCHEMA = "pm99-season-number-label-name-direct-repair-batch-v1"


class BatchRepairError(ValueError):
    """A current playable recipe cannot receive the bounded direct repair."""


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BatchRepairError(f"cannot read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise BatchRepairError(f"JSON object required: {path}")
    return value


def _candidate_count(provenance_path: Path) -> int:
    sidecar = _read(provenance_path)
    return sum(
        1
        for row in sidecar.get("players", [])
        if isinstance(row, dict)
        and row.get("status") == "source-row-linked"
        and isinstance(row.get("component_candidate"), dict)
        and row["component_candidate"].get("source_number_label_stripped") is True
    )


def _paths(season: str) -> dict[str, Path]:
    revision = REVISIONS.get(season)
    if revision is None:
        raise BatchRepairError(f"unsupported post-1999 season: {season}")
    ingress = LOCAL / "season-static-ingress-v1" / f"{season}-worldwide-source-backed-{revision}"
    return {
        "provenance": LOCAL / "season-name-provenance-v1" / f"{season}.json",
        "strict": LOCAL / "season-worldwide-merged-v1" / season / revision / "strict-season-package.json",
        "source": ingress / "season-package.source-writable.json",
        "alias": ingress / "season-package.alias-bound.json",
        "reconciled": ingress / "season-package.reconciled.json",
        "runtime": LOCAL / "season-runtime-candidates-v1" / season / f"worldwide-source-backed-{revision}" / "game",
        "receipt": LOCAL / "season-direct-name-repairs-v1" / f"{season}.json",
    }


def _command(season: str, paths: dict[str, Path]) -> list[str]:
    return [
        sys.executable, str(DIRECT_REPAIR),
        "--provenance", str(paths["provenance"]),
        "--package", str(paths["strict"]),
        "--package", str(paths["source"]),
        "--compile-package", str(paths["source"]),
        "--alias-package", str(paths["alias"]),
        "--reconciled-package", str(paths["reconciled"]),
        "--base-tree", str(BASE_TREE),
        "--verified-base", str(VERIFIED_BASE),
        "--runtime-game", str(paths["runtime"]),
        "--receipt", str(paths["receipt"]),
        "--apply",
    ]


def batch(*, seasons: Sequence[str], rerun: bool) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for season in seasons:
        paths = _paths(season)
        count = _candidate_count(paths["provenance"])
        if not count:
            events.append({"season": season, "status": "not-affected", "candidate_count": 0})
            continue
        missing = [name for name, path in paths.items() if name != "receipt" and not path.exists()]
        if missing:
            raise BatchRepairError(f"{season} lacks required current inputs: {', '.join(missing)}")
        if paths["receipt"].is_file() and not rerun:
            events.append({"season": season, "status": "reused", "candidate_count": count,
                           "receipt": str(paths["receipt"].relative_to(ROOT))})
            continue
        print(json.dumps({"season": season, "status": "running", "candidate_count": count}), flush=True)
        completed = subprocess.run(_command(season, paths), cwd=ROOT, text=True, capture_output=True)
        if completed.returncode or not paths["receipt"].is_file():
            raise BatchRepairError(json.dumps({
                "season": season,
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            }, ensure_ascii=False, sort_keys=True))
        receipt = _read(paths["receipt"])
        events.append({
            "season": season,
            "status": "applied",
            "candidate_count": count,
            "changed_carrier_count": receipt.get("runtime_refresh", {}).get("jug_delta", {}).get("changed_carrier_count"),
            "receipt": str(paths["receipt"].relative_to(ROOT)),
        })
        print(json.dumps(events[-1], sort_keys=True), flush=True)
    return {
        "schema_version": SCHEMA,
        "state": "complete",
        "events": events,
        "applied_count": sum(event["status"] == "applied" for event in events),
        "reused_count": sum(event["status"] == "reused" for event in events),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", action="append", choices=sorted(REVISIONS),
                        help="Repair one season; repeat. Defaults to all playable post-1999 seasons.")
    parser.add_argument("--rerun", action="store_true", help="Re-verify and rewrite an existing direct repair.")
    parser.add_argument("--list", action="store_true", help="List direct-repair candidate counts without changing files.")
    parser.add_argument("--output", type=Path,
                        default=LOCAL / "season-direct-name-repairs-v1" / "batch-receipt.json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    seasons = sorted(args.season or REVISIONS)
    if args.list:
        print(json.dumps([
            {"season": season, "candidate_count": _candidate_count(_paths(season)["provenance"])}
            for season in seasons
        ], sort_keys=True))
        return 0
    try:
        result = batch(seasons=seasons, rerun=args.rerun)
    except BatchRepairError as exc:
        print(f"direct-number-label-repair-batch: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"state": result["state"], "applied_count": result["applied_count"],
                      "reused_count": result["reused_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
