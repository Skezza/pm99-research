#!/usr/bin/env python3
"""Build the 25-season Stoke opening-lineup screenshot preflight matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "pm99-stoke-opening-evidence-matrix-v1"


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _selector(row: Mapping[str, Any]) -> bool:
    selector = row.get("source_selector") or row.get("selector") or {}
    return str(selector.get("country_catalog") or "") == "eng" and str(selector.get("club_name") or "").casefold() == "stoke city"


def _inferred_formation(xi: list[Mapping[str, Any]]) -> str | None:
    positions = []
    for row in xi:
        value = str(row.get("source_position") or row.get("source_position_group") or "").casefold()
        if value in {"g", "goalkeeper", "goalkeepers"}: positions.append("G")
        elif value == "d" or "defen" in value: positions.append("D")
        elif value == "m" or "mid" in value: positions.append("M")
        elif value == "f" or "forward" in value or "attack" in value: positions.append("F")
        else: return None
    if len(positions) != 11 or positions.count("G") != 1:
        return None
    counts = [positions.count(value) for value in "DMF"]
    return "-".join(map(str, counts)) if sum(counts) == 10 and all(counts) else None


def _expected_seasons() -> list[str]:
    return [f"{year:04d}-{(year + 1) % 100:02d}" for year in range(2000, 2026) if year != 2015]


def build_matrix(roots: list[Path], *, historical_current_root: Path | None = None) -> dict[str, Any]:
    directories: dict[str, Path] = {}
    for root in roots:
        for season in _expected_seasons():
            candidate = root / season
            if not (candidate / "opening-lineups.json").is_file():
                continue
            if season in directories and _digest(directories[season] / "opening-lineups.json") != _digest(candidate / "opening-lineups.json"):
                raise ValueError(f"{season}: multiple different lineup receipts; select one immutable revision root")
            directories[season] = candidate
    rows = []
    for season in _expected_seasons():
        directory = directories.get(season)
        if directory is None:
            rows.append({"season": season, "status": "opening-evidence-not-yet-materialised", "screenshot_preflight_ready": False})
            continue
        current_revision = None
        current_intake_sha = None
        if historical_current_root is not None:
            current_path = historical_current_root / season / "current.json"
            plan_path = directory / "plan.json"
            if not current_path.is_file() or not plan_path.is_file():
                rows.append({"season": season, "status": "historical-current-binding-missing", "screenshot_preflight_ready": False})
                continue
            current = json.loads(current_path.read_text(encoding="utf-8"))
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            current_revision = str(current.get("revision_id") or "")
            current_intake_sha = str(((current.get("artifacts") or {}).get("intake") or {}).get("sha256") or "")
            if not current_revision or not current_intake_sha or (plan.get("source_intake") or {}).get("sha256") != current_intake_sha:
                rows.append({
                    "season": season,
                    "status": "historical-current-binding-stale",
                    "historical_current_revision": current_revision or None,
                    "screenshot_preflight_ready": False,
                })
                continue
        lineup_path = directory / "opening-lineups.json"
        lineup = json.loads(lineup_path.read_text(encoding="utf-8"))
        candidates = [row for row in lineup.get("clubs") or [] if _selector(row)]
        if len(candidates) != 1:
            rows.append({"season": season, "status": "stoke-opening-lineup-unresolved", "candidate_count": len(candidates), "opening_lineups_sha256": _digest(lineup_path), "screenshot_preflight_ready": False})
            continue
        source = candidates[0]
        xi = list(source.get("starting_xi") or [])
        formation = str(source.get("formation") or "") or _inferred_formation(xi)
        formation_method = "source" if source.get("formation") else "deterministic-inference-from-sourced-xi"
        manager_path = directory / "opening-manager-ledger.json"
        preallocation_path = directory / "opening-squad-preallocation.json"
        manager = None
        if manager_path.is_file():
            ledger = json.loads(manager_path.read_text(encoding="utf-8"))
            matches = [row for row in ledger.get("managers") or [] if _selector(row)]
            manager = matches[0] if len(matches) == 1 else None
        preallocated = False
        if preallocation_path.is_file():
            preallocation = json.loads(preallocation_path.read_text(encoding="utf-8"))
            matches = [row for row in preallocation.get("source_clubs") or [] if _selector(row)]
            intake_bound = historical_current_root is None or (preallocation.get("sources") or {}).get("source_intake_sha256") == current_intake_sha
            preallocated = intake_bound and len(matches) == 1 and matches[0].get("opening_xi_complete") is True
        ready = len(xi) == 11 and bool(formation) and manager is not None and preallocated
        rows.append({
            "season": season, "status": "screenshot-preflight-ready" if ready else "screenshot-preflight-blocked",
            "screenshot_preflight_ready": ready, "fixture_date": source.get("first_league_fixture_date"),
            "source_match_id": source.get("source_match_id"), "source_url": source.get("lineup_source_url"),
            "first_xi": [str(row.get("display_name") or "") for row in xi],
            "formation": formation, "formation_method": formation_method if formation else None,
            "manager_name": manager.get("manager_name") if manager else None,
            "manager_source_url": (manager.get("evidence") or {}).get("source_url") if manager else None,
            "opening_xi_preallocated": preallocated,
            "opening_lineups_sha256": _digest(lineup_path),
            "opening_manager_ledger_sha256": _digest(manager_path) if manager_path.is_file() else None,
            "opening_squad_preallocation_sha256": _digest(preallocation_path) if preallocation_path.is_file() else None,
            "historical_current_revision": current_revision,
        })
    return {"schema_version": SCHEMA, "coverage": {"season_count": len(rows), "screenshot_preflight_ready_count": sum(row["screenshot_preflight_ready"] for row in rows), "blocked_count": sum(not row["screenshot_preflight_ready"] for row in rows)}, "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, action="append", required=True)
    parser.add_argument("--historical-current-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_matrix(args.root, historical_current_root=args.historical_current_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps(result["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
