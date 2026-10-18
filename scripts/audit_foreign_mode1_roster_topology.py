#!/usr/bin/env python3
"""Audit that a materialisation preserves every registered foreign roster tail.

This is a no-write guard for composing the English and foreign season lanes.
The world registry records the only established foreign topology: the existing
mode-1 EQ carrier, terminal roster-row order, player carrier and row flag.
Any change is a build failure, not an invitation to infer membership.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.eq_jug_linked import parse_eq_external_team_roster_payload  # noqa: E402
from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from scripts import world_fixed_carrier_ledger_v2 as ledger  # noqa: E402


REPORT_SCHEMA = "pm99-foreign-mode1-roster-topology-audit-v1"


def _slots_from_registry(carrier: Mapping[str, Any]) -> list[dict[str, int]]:
    return [
        {
            "slot_index": int(slot["slot_index"]),
            "flag": int(slot["flag"]),
            "player_carrier_id": int(slot["player_carrier_id"]),
        }
        for slot in carrier["roster_slots"]
    ]


def compare_slots(*, expected: list[Mapping[str, int]], actual: list[Mapping[str, int]] | None) -> dict[str, Any] | None:
    """Return one compact deterministic difference or ``None`` on equality."""

    if actual is None:
        return {"kind": "unparseable-or-missing-terminal-roster"}
    expected_normalised = [dict(row) for row in expected]
    actual_normalised = [dict(row) for row in actual]
    if actual_normalised == expected_normalised:
        return None
    limit = min(len(expected_normalised), len(actual_normalised))
    first_difference = next(
        (
            index for index in range(limit)
            if expected_normalised[index] != actual_normalised[index]
        ),
        limit,
    )
    result: dict[str, Any] = {
        "kind": "fixed-roster-tail-changed",
        "expected_count": len(expected_normalised),
        "actual_count": len(actual_normalised),
        "first_difference_slot_index": first_difference,
    }
    if first_difference < len(expected_normalised):
        result["expected_slot"] = expected_normalised[first_difference]
    if first_difference < len(actual_normalised):
        result["actual_slot"] = actual_normalised[first_difference]
    return result


def audit(*, registry: Mapping[str, Any], dbdat: Path) -> dict[str, Any]:
    """Compare every immutable mode-1 roster tail without inspecting history."""

    ledger.validate_registry(registry)
    eq_path = dbdat / "EQ98030.FDI"
    if not eq_path.is_file() or eq_path.is_symlink():
        raise ValueError(f"missing regular EQ98030.FDI under {dbdat}")
    data = eq_path.read_bytes()
    entries = {int(entry.record_id): entry for entry in IndexedFDIFile.from_bytes(data).entries}
    changed: list[dict[str, Any]] = []
    for carrier in registry["carriers"]:
        carrier_id = int(carrier["carrier_id"])
        entry = entries.get(carrier_id)
        actual = None
        if entry is not None:
            raw = data[entry.payload_offset : entry.payload_offset + entry.payload_length]
            parsed = parse_eq_external_team_roster_payload(raw, {})
            if parsed is not None:
                actual = [
                    {
                        "slot_index": int(row.slot_index),
                        "flag": int(row.flag),
                        "player_carrier_id": int(row.player_record_id),
                    }
                    for row in parsed.rows
                ]
        difference = compare_slots(expected=_slots_from_registry(carrier), actual=actual)
        if difference is not None:
            changed.append({"carrier_id": carrier_id, **difference})
    return {
        "schema_version": REPORT_SCHEMA,
        "result": "pass" if not changed else "fail",
        "registry_id": str(registry["registry_id"]),
        "foreign_carrier_count": len(registry["carriers"]),
        "changed_carrier_count": len(changed),
        "changed_carriers": changed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--dbdat", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    registry, _ = ledger.read_canonical_json(args.registry, label="fixed-carrier registry")
    report = audit(registry=registry, dbdat=args.dbdat.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(ledger.canonical_json_bytes(report))
    print(json.dumps({
        "result": report["result"],
        "foreign_carrier_count": report["foreign_carrier_count"],
        "changed_carrier_count": report["changed_carrier_count"],
        "report": str(args.output),
    }, sort_keys=True))
    return 0 if report["result"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
