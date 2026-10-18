#!/usr/bin/env python3
"""Capture and immutably promote declared Soccerbase August season scopes."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.capture_ntf_historical_carrier_squads_v1 import Cache
from scripts.capture_soccerbase_august_squads_v1 import capture
from scripts.capture_transfermarkt_historical_squads_v1 import canonical_bytes
from scripts.promote_soccerbase_august_squads_v1 import promote


def _scope(path: Path, requested: set[str]) -> list[dict[str, Any]]:
    value = json.loads(path.read_text())
    if value.get("schema_version") != "pm99-soccerbase-august-scope-v1":
        raise ValueError("unsupported Soccerbase scope schema")
    rows = value.get("seasons")
    if not isinstance(rows, list):
        raise ValueError("scope seasons must be a list")
    selected = [row for row in rows if not requested or row.get("season") in requested]
    if requested - {str(row.get("season")) for row in selected}:
        raise ValueError("requested season absent from scope")
    return sorted(selected, key=lambda row: row["season"])


def _capture(row: dict[str, Any], *, offline: bool, delay: float) -> tuple[str, Path, Path, dict[str, Any]]:
    season = str(row["season"])
    local = ROOT / ".local" / f"season-{season}"
    output = local / "soccerbase-august-english-nonleague-v1.json"
    gaps_output = local / "soccerbase-august-english-nonleague-gaps-v1.json"
    result, gaps = capture(
        tournament_id=int(row["tournament_id"]), season_id=int(row["season_id"]),
        start_year=int(season[:4]), competition=str(row["competition"]),
        cache=Cache(local / "soccerbase-august-cache-v1", offline=offline, delay=delay),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_bytes(result))
    gaps_output.write_bytes(canonical_bytes(gaps))
    return season, output, gaps_output, result["summary"]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", type=Path, default=ROOT / "scripts/data/soccerbase-national-league-august-scope-v1.json")
    parser.add_argument("--season", action="append", default=[])
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--delay", type=float, default=.2)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output-root", type=Path, default=ROOT / ".local/season-historical-squad-backfill-v1")
    parser.add_argument("--matrix-output", type=Path)
    args = parser.parse_args(argv)
    rows = _scope(args.scope, set(args.season))
    captures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(_capture, row, offline=args.offline, delay=args.delay) for row in rows]
        for future in concurrent.futures.as_completed(futures):
            captures.append(future.result())
    results = []
    for season, output, gaps, summary in sorted(captures):
        promoted = promote(season=season, capture_path=output, gaps_path=gaps, output_root=args.output_root)
        results.append({**promoted, "capture_summary": summary})
    matrix = {"schema_version": "pm99-soccerbase-august-backfill-batch-v1", "seasons": results}
    matrix_output = args.matrix_output or args.output_root / "soccerbase-august-matrix.json"
    matrix_output.write_bytes(canonical_bytes(matrix))
    print(json.dumps(results, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
