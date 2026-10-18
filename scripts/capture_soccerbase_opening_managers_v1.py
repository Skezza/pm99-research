#!/usr/bin/env python3
"""Capture dated Soccerbase manager-history supplements for composed XI gaps."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.supplement_soccerbase_opening_lineups_v1 import BASE_URL, Cache, canonical_json_bytes  # noqa: E402


SCHEMA = "pm99-opening-manager-supplement-v1"


def _date(value: str) -> date:
    return datetime.strptime(value.strip(), "%d %b, %Y").date()


def _manager_at(payload: bytes, fixture_date: str) -> str:
    page = BeautifulSoup(payload, "html.parser")
    target = date.fromisoformat(fixture_date)
    candidates = []
    for row in page.select("table tr"):
        cells = row.select("td")
        link = row.select_one('a[href*="/managers/manager.sd?manager_id="]')
        if len(cells) < 3 or link is None:
            continue
        try:
            start = _date(cells[1].get_text(" ", strip=True))
            end_text = cells[2].get_text(" ", strip=True)
            end = date.max if end_text.casefold() == "present" else _date(end_text)
        except ValueError:
            continue
        if start <= target <= end:
            name = link.get_text(" ", strip=True)
            if name:
                candidates.append((start, end, name))
    candidates = sorted(set(candidates))
    if len(candidates) > 1:
        # Soccerbase retains a few legacy rows with implausibly broad end
        # dates that overlap a later, precisely dated appointment. The tenure
        # with the unique latest start is the manager appointed most recently
        # before the fixture and is therefore the opening-date incumbent.
        latest_start = max(row[0] for row in candidates)
        candidates = [row for row in candidates if row[0] == latest_start]
    if len(candidates) != 1:
        raise ValueError(f"manager history has {len(candidates)} tenures covering {fixture_date}")
    return candidates[0][2]


def capture(*, lineups: dict[str, Any], source_capture_sha256: str, cache: Cache) -> dict[str, Any]:
    managers, gaps = [], []
    for row in lineups.get("clubs") or []:
        selector = row.get("source_selector") or {}
        team_id = selector.get("soccerbase_team_id")
        if not isinstance(team_id, int):
            continue
        fixture_date = str(row.get("first_league_fixture_date") or "")
        url = f"{BASE_URL}/teams/team.sd?team_id={team_id}&teamTabs=managers"
        try:
            payload = cache.get(url, f"manager/{team_id}.html")
            manager = _manager_at(payload, fixture_date)
            managers.append({"source_selector": {key: selector[key] for key in ("country_catalog", "competition_catalog", "club_name")}, "opening_fixture_date": fixture_date, "manager_name": manager, "source_name": "Soccerbase dated club manager history", "source_url": url, "source_snapshot_sha256": hashlib.sha256(payload).hexdigest(), "reason": "unique published manager tenure covers the first league fixture date"})
        except (OSError, ValueError) as exc:
            gaps.append({"source_selector": {key: selector[key] for key in ("country_catalog", "competition_catalog", "club_name")}, "reason": str(exc)})
    return {"schema_version": SCHEMA, "season_start_year": lineups["season_start_year"], "sources": {"source_capture_sha256": source_capture_sha256, "opening_lineup_sha256": hashlib.sha256(canonical_json_bytes(lineups)).hexdigest(), "cache_files": [cache.used[key] for key in sorted(cache.used)], "credit": "Soccerbase"}, "summary": {"supplemented_manager_count": len(managers), "unresolved_manager_count": len(gaps)}, "managers": managers, "gaps": gaps}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opening-lineups", type=Path, required=True)
    parser.add_argument("--source-capture-sha256", required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    lineups = json.loads(args.opening_lineups.read_text(encoding="utf-8"))
    result = capture(lineups=lineups, source_capture_sha256=args.source_capture_sha256, cache=Cache(args.cache_dir, offline=args.offline, delay=args.delay))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 1 if args.strict and result["gaps"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
