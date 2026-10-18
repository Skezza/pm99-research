#!/usr/bin/env python3
"""Audit shared-JUG recycle roles demanded by a dated foreign player plan.

This is a no-write release gate.  It compares immutable roster ownership in
the fixed-carrier registry with the selected 2015 rows.  Only the second and
later owner of a shared compact carrier needs a recycle transaction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
from app.fdi_indexed import IndexedFDIFile
from scripts.season_package_compiler_v2 import _native_dd6360_role_start, _read_native_dd6360_fields

SCHEMA = "pm99-world-2015-recycle-role-demand-v1"
POSITION_ROLE = {"G": 0, "D": 4, "M": 9, "F": 12}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(*, registry_path: Path, player_plan_path: Path, capacity_path: Path) -> dict[str, Any]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    plan = json.loads(player_plan_path.read_text(encoding="utf-8"))
    capacity = json.loads(capacity_path.read_text(encoding="utf-8"))

    owners: dict[int, list[int]] = defaultdict(list)
    for club in registry["carriers"]:
        team_id = int(club["carrier_id"])
        for row in club["roster_slots"]:
            owners[int(row["player_carrier_id"])].append(team_id)
    owners = {player_id: sorted(set(team_ids)) for player_id, team_ids in owners.items()}

    qualified = {int(value) for value in capacity["runtime_qualified_primary_fine_role_codes"]}
    dbdat_value = (capacity.get("input") or {}).get("dbdat")
    jug_path = Path(dbdat_value) / "JUG98030.FDI" if isinstance(dbdat_value, str) else None
    jug_data = jug_path.read_bytes() if jug_path is not None else b""
    jug_entries = (
        {int(e.record_id): e for e in IndexedFDIFile.from_bytes(jug_data).entries}
        if jug_path is not None else {}
    )
    demands: list[dict[str, Any]] = []
    selected_team_ids = {int(club["carrier_id"]) for club in plan["carrier_plans"]}
    for club in sorted(plan["carrier_plans"], key=lambda value: int(value["carrier_id"])):
        team_id = int(club["carrier_id"])
        for row in sorted(club["rows"], key=lambda value: int(value["slot_index"])):
            player_id = int(row["player_carrier_id"])
            player_owners = owners.get(player_id, [])
            position = str(row["source_player"]["position"])
            role = POSITION_ROLE.get(position)
            reason = None
            retained_team = player_owners[0] if player_owners else team_id
            if len(player_owners) >= 2 and team_id != player_owners[0]:
                reason = "shared-compact-carrier-extra-owner"
            else:
                entry = jug_entries.get(player_id)
                if entry is not None:
                    payload = entry.decode_payload(jug_data)
                    if payload[2:5] == b"\xdd\x63\x60":
                        try:
                            fields = _read_native_dd6360_fields(payload, _native_dd6360_role_start(payload))
                            native_roles = [int(v) for v in fields["fine_role_codes"] if int(v) != 98]
                        except Exception:
                            native_roles = []
                        if not native_roles or not 0 <= native_roles[0] <= 17:
                            reason = "native-compact-primary-role-is-preserve-only-or-invalid"
            if reason is None:
                continue
            demands.append({
                "player_carrier_id": player_id,
                "retained_team_carrier_id": retained_team,
                "recycle_team_carrier_id": team_id,
                "slot_index": int(row["slot_index"]),
                "historical_player_name": str(row["source_player"]["name"]),
                "source_broad_position": position,
                "required_primary_fine_role_code": role,
                "runtime_qualified": role in qualified if role is not None else False,
                "reason": reason,
            })

    required_roles = Counter(row["required_primary_fine_role_code"] for row in demands)
    unqualified = sorted(role for role in required_roles if role is None or role not in qualified)
    unresolved_duplicate_slots = []
    for duplicate in capacity["duplicate_slots"]:
        player_id = int(duplicate["shared_compact_carrier_id"])
        for team_id in duplicate["recycle_required_for_mode1_team_carrier_ids"]:
            if int(team_id) not in selected_team_ids:
                unresolved_duplicate_slots.append({
                    "player_carrier_id": player_id,
                    "recycle_team_carrier_id": int(team_id),
                    "reason": "carrier-has-no-selected-2015-player-plan",
                })

    return {
        "schema_version": SCHEMA,
        "sources": {
            "registry_sha256": _sha256(registry_path),
            "player_plan_sha256": _sha256(player_plan_path),
            "capacity_audit_sha256": _sha256(capacity_path),
        },
        "selected_carrier_count": len(selected_team_ids),
        "native_role_scan": "performed" if jug_path is not None else "not-requested-by-input",
        "recycle_demand_count": len(demands),
        "required_role_counts": {str(key): value for key, value in sorted(required_roles.items())},
        "runtime_qualified_role_codes": sorted(qualified),
        "runtime_unqualified_required_role_codes": unqualified,
        "unresolved_duplicate_slot_count": len(unresolved_duplicate_slots),
        "unresolved_duplicate_slots": unresolved_duplicate_slots,
        "demands": demands,
        "result": "pass-for-selected-carriers" if not unqualified else "blocked-unqualified-role",
        "release_note": "A world release also requires the unresolved duplicate slots to receive dated player plans.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--player-plan", required=True, type=Path)
    parser.add_argument("--capacity-audit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = audit(
        registry_path=args.registry.resolve(),
        player_plan_path=args.player_plan.resolve(),
        capacity_path=args.capacity_audit.resolve(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "result": report["result"]}, sort_keys=True))
    return 0 if report["result"] == "pass-for-selected-carriers" else 1


if __name__ == "__main__":
    raise SystemExit(main())
