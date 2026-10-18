#!/usr/bin/env python3
"""Assign the complete 2015/16 English season to PM99's 92 native carriers.

PM99 does not store an editable division value on each club record.  Its
opening competitions are built from fixed carrier records: 20 selectable
carriers in each new-game panel, plus four game-used carriers in each Football
League division.  This script turns the native carrier contract into a
reviewable source ledger for the historical compiler.  Its picker slots are a
1998 baseline, not a prediction of the exact twenty clubs offered after a
full variable-length historical rewrite; that is captured after build.

It never adds a club, changes the executable, or silently drops the four
non-picker clubs in each 24-club division.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SEASON = "2015/16"
DIVISIONS = ("Premier League", "Championship", "League One", "League Two")
TARGET_DIVISION_BY_PANEL = {
    "division_01": "Premier League",
    "division_02": "Championship",
    "division_03": "League One",
    "division_04": "League Two",
}

# These records are absent from PM99's 20-icon picker in the *vanilla 1998*
# database, but appear in its fresh-game league tables and fixtures. The
# values identify native membership carriers; rewritten picker availability is
# separately proven from a capture of the built database.
HIDDEN_CARRIERS_BY_DIVISION = {
    "Premier League": (),
    "Championship": (321, 328, 332, 365),
    "League One": (335, 350, 355, 366),
    "League Two": (324, 359, 371, 3306),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _normalise(value: str) -> str:
    return "".join(char.casefold() for char in str(value or "") if char.isalnum())


def _picker_slots(selector_map: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for panel in list(selector_map.get("divisions") or []):
        panel_key = str(panel.get("division_key") or "")
        division = TARGET_DIVISION_BY_PANEL.get(panel_key)
        rows = list(panel.get("teams") or [])
        if division is None or len(rows) != 20:
            raise ValueError(f"Expected one 20-club picker panel for {panel_key!r}")
        slots: list[dict[str, Any]] = []
        for row in rows:
            slots.append(
                {
                    "carrier_eq_record_id": int(row["eq_record_id"]),
                    "picker_visible": True,
                    "picker_visibility_basis": "vanilla-1998-baseline-only",
                    "native_panel": panel_key,
                    "native_row_index": int(row["row_index"]),
                    "team_select_x": int(row["team_select_x"]),
                    "team_select_y": int(row["team_select_y"]),
                    "carrier_original_short_name": str(row.get("eq_short_name") or ""),
                }
            )
        if len({slot["carrier_eq_record_id"] for slot in slots}) != len(slots):
            raise ValueError(f"Picker panel {panel_key} contains duplicate carrier IDs")
        result[division] = sorted(slots, key=lambda slot: int(slot["native_row_index"]))
    if set(result) != set(DIVISIONS):
        raise ValueError("Selector map does not provide all four English panels")
    return result


def build_native92_manifest(*, source_ledger: dict[str, Any], selector_map: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    clubs = list(source_ledger.get("clubs") or [])
    expected_counts = {"Premier League": 20, "Championship": 24, "League One": 24, "League Two": 24}
    counts = Counter(str(club.get("division") or "") for club in clubs)
    if counts != expected_counts:
        raise ValueError(f"Source ledger is not a 20/24/24/24 English season: {dict(counts)}")
    normalised_names = [_normalise(str(club.get("club") or "")) for club in clubs]
    if not all(normalised_names) or len(set(normalised_names)) != len(normalised_names):
        raise ValueError("Source ledger must contain one non-empty unique club name per club")

    picker_by_division = _picker_slots(selector_map)
    assigned_clubs: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []
    for division in DIVISIONS:
        candidates = sorted(
            (club for club in clubs if str(club["division"]) == division),
            key=lambda club: _normalise(str(club["club"])),
        )
        slots = [*picker_by_division[division]]
        slots.extend(
            {
                "carrier_eq_record_id": carrier_id,
                "picker_visible": False,
                "picker_visibility_basis": "vanilla-1998-baseline-only",
                "native_panel": None,
                "native_row_index": None,
                "team_select_x": None,
                "team_select_y": None,
                "carrier_original_short_name": None,
            }
            for carrier_id in HIDDEN_CARRIERS_BY_DIVISION[division]
        )
        if len(candidates) != len(slots):
            raise ValueError(f"{division} has {len(candidates)} clubs but {len(slots)} native carriers")
        for club, slot in zip(candidates, slots, strict=True):
            assigned = copy.deepcopy(club)
            assigned["carrier_eq_record_id"] = int(slot["carrier_eq_record_id"])
            assigned["native_selector"] = dict(slot)
            assigned_clubs.append(assigned)
            assignments.append({"club": str(assigned["club"]), "division": division, **slot})

    carrier_ids = [int(club["carrier_eq_record_id"]) for club in assigned_clubs]
    if len(assigned_clubs) != 92 or len(set(carrier_ids)) != 92:
        raise ValueError("Native92 assignment must use exactly 92 unique carrier records")
    hidden_ids = {carrier_id for ids in HIDDEN_CARRIERS_BY_DIVISION.values() for carrier_id in ids}
    if not hidden_ids <= set(carrier_ids):
        raise ValueError("Native92 assignment omitted a hidden game-used carrier")

    registry = {
        "schema_version": "pm99-native-english92-carrier-registry-v1",
        "season": SEASON,
        "status": "native-membership-runtime-proven",
        "carrier_count": len(carrier_ids),
        "picker_carrier_count": sum(len(rows) for rows in picker_by_division.values()),
        "hidden_game_used_carrier_count": len(hidden_ids),
        "picker_availability_contract": "must-be-captured-from-the-built-database",
        "division_shape": expected_counts,
        "hidden_carriers_by_division": HIDDEN_CARRIERS_BY_DIVISION,
        "assignments": assignments,
    }
    ledger = {
        **{key: value for key, value in source_ledger.items() if key != "clubs"},
        "schema_version": "pm99-2015-16-native92-source-ledger-v1",
        "clubs": assigned_clubs,
        "native92_carrier_registry": registry,
    }
    return registry, ledger


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-ledger", required=True, type=Path)
    parser.add_argument("--selector-map", required=True, type=Path)
    parser.add_argument("--registry-output", required=True, type=Path)
    parser.add_argument("--ledger-output", required=True, type=Path)
    args = parser.parse_args()
    source_path = args.source_ledger.resolve()
    selector_path = args.selector_map.resolve()
    registry, ledger = build_native92_manifest(
        source_ledger=json.loads(source_path.read_text(encoding="utf-8")),
        selector_map=json.loads(selector_path.read_text(encoding="utf-8")),
    )
    registry["source_ledger_sha256"] = _sha256(source_path)
    registry["selector_map_sha256"] = _sha256(selector_path)
    ledger["native92_carrier_registry"] = registry
    _dump_json(args.registry_output.resolve(), registry)
    _dump_json(args.ledger_output.resolve(), ledger)
    print(json.dumps({"status": "pass", "clubs": len(ledger["clubs"]), "registry": str(args.registry_output), "ledger": str(args.ledger_output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
