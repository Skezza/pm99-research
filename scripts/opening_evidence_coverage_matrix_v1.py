#!/usr/bin/env python3
"""Summarise hash-bound opening-XI and manager evidence by season."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "pm99-opening-evidence-coverage-matrix-v1"


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path, schema: str | set[str]) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    allowed = {schema} if isinstance(schema, str) else schema
    if value.get("schema_version") not in allowed:
        raise ValueError(f"{path}: expected {schema}, got {value.get('schema_version')!r}")
    return value


def _assert_hash(label: str, actual: str, expected: str | None) -> None:
    if expected is not None and actual != expected:
        raise ValueError(f"{label}: stale artifact binding: expected {expected}, got {actual}")


def _selector_key(value: Any) -> tuple[str, str, str] | None:
    if not isinstance(value, dict):
        return None
    return tuple(str(value.get(key) or "") for key in ("country_catalog", "competition_catalog", "club_name"))


def build_matrix(roots: list[Path], *, historical_current_root: Path | None = None) -> dict[str, Any]:
    season_dirs: dict[str, Path] = {}
    for root in roots:
        for path in sorted(root.glob("*/opening-lineups.json")):
            season_dirs[path.parent.name] = path.parent

    rows: list[dict[str, Any]] = []
    for season, directory in sorted(season_dirs.items()):
        lineup_path = directory / "opening-lineups.json"
        lineup = _load(lineup_path, {"pm99-transfermarkt-opening-lineup-source-v1", "pm99-composed-opening-lineup-source-v1"})
        lineup_sha = digest(lineup_path)
        row: dict[str, Any] = {
            "season": season,
            "artifact_directory": str(directory),
            "lineups": lineup["summary"],
            "opening_lineups_sha256": lineup_sha,
        }
        current_intake_sha = None
        current_allocation_sha = None
        current_binding_errors: list[str] = []
        if historical_current_root is not None:
            current_path = historical_current_root / season / "current.json"
            plan_path = directory / "plan.json"
            if not current_path.is_file():
                current_binding_errors.append("historical-current-manifest-missing")
            else:
                current = json.loads(current_path.read_text(encoding="utf-8"))
                row["historical_current_revision"] = current.get("revision_id")
                current_intake_sha = ((current.get("artifacts") or {}).get("intake") or {}).get("sha256")
                current_allocation_sha = ((current.get("artifacts") or {}).get("allocation") or {}).get("sha256")
            if not plan_path.is_file():
                current_binding_errors.append("current-plan-missing")
            elif current_intake_sha is not None:
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
                if (plan.get("source_intake") or {}).get("sha256") != current_intake_sha:
                    current_binding_errors.append("current-plan-intake-stale")

        preallocation_path = directory / "opening-squad-preallocation.json"
        if preallocation_path.is_file():
            preallocation = _load(preallocation_path, "pm99-opening-squad-preallocation-v1")
            _assert_hash(f"{season} preallocation/lineup", lineup_sha, preallocation["sources"].get("opening_lineup_sha256"))
            row["preallocation"] = preallocation["summary"]
            row["opening_squad_preallocation_sha256"] = digest(preallocation_path)
            if current_intake_sha is not None and preallocation["sources"].get("source_intake_sha256") != current_intake_sha:
                current_binding_errors.append("preallocation-intake-stale")
        else:
            row["preallocation_status"] = "missing"

        manager_path = directory / "opening-manager-ledger.json"
        if manager_path.is_file():
            managers = _load(manager_path, "pm99-opening-manager-ledger-v1")
            _assert_hash(f"{season} manager/lineup", lineup_sha, managers["sources"].get("opening_lineup_receipt_sha256"))
            row["managers"] = managers["summary"]
            captured_selectors = {
                key for club in lineup.get("clubs") or []
                if isinstance(club, dict) and club.get("first_league_fixture_date")
                and (key := _selector_key(club.get("source_selector"))) is not None
            }
            manager_selectors = {
                key for manager in managers.get("managers") or []
                if isinstance(manager, dict) and str(manager.get("manager_name") or "").strip()
                and (key := _selector_key(manager.get("source_selector"))) is not None
            }
            row["captured_club_manager_count"] = len(captured_selectors & manager_selectors)
            row["opening_manager_ledger_sha256"] = digest(manager_path)
        else:
            row["manager_status"] = "missing"

        audit_path = directory / "preallocation-package-audit.json"
        if audit_path.is_file():
            audit = _load(audit_path, "pm99-season-source-package-build-audit-v1")
            if "opening_squad_preallocation_sha256" in row:
                _assert_hash(
                    f"{season} package/preallocation",
                    row["opening_squad_preallocation_sha256"],
                    audit.get("opening_squad_preallocation_sha256"),
                )
            row["package"] = {
                "coverage": audit["coverage"],
                "release_eligible": audit["release_eligible"],
                "hard_blocker_count": len(audit.get("hard_blockers") or []),
            }
            row["preallocation_package_audit_sha256"] = digest(audit_path)
            if current_intake_sha is not None and audit.get("source_intake_sha256") != current_intake_sha:
                current_binding_errors.append("package-intake-stale")
            if current_allocation_sha is not None and audit.get("carrier_allocation_sha256") != current_allocation_sha:
                current_binding_errors.append("package-allocation-stale")
        else:
            row["package_status"] = "missing"

        row["historical_current_binding_errors"] = current_binding_errors
        captured = int(row["lineups"].get("captured_club_count", 0))
        complete_xi = int(row.get("preallocation", {}).get("opening-xi-complete-club-count", -1))
        captured_managers = int(row.get("captured_club_manager_count", -1))
        row["exact_opening_evidence_complete"] = complete_xi == captured and captured_managers == captured
        row["evidence_integrator_ready"] = (
            all(key in row for key in ("preallocation", "managers", "package"))
            and row["exact_opening_evidence_complete"]
            and not current_binding_errors
        )
        rows.append(row)

    return {
        "schema_version": SCHEMA,
        "coverage": {
            "season_count": len(rows),
            "lineup_captured_club_count": sum(row["lineups"].get("captured_club_count", 0) for row in rows),
            "opening_xi_complete_club_count": sum(row.get("preallocation", {}).get("opening-xi-complete-club-count", 0) for row in rows),
            "resolved_manager_count": sum(row.get("managers", {}).get("resolved_manager_count", 0) for row in rows),
            "integrator_ready_season_count": sum(bool(row["evidence_integrator_ready"]) for row in rows),
        },
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, action="append", required=True)
    parser.add_argument("--historical-current-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    matrix = build_matrix(args.root, historical_current_root=args.historical_current_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(matrix))
    print(json.dumps(matrix["coverage"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
