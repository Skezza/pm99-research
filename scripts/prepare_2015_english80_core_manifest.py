#!/usr/bin/env python3
"""Create a reviewable native-80 selection for the 2015/16 English season.

PM99 has four native English selector panels of twenty clubs. This script does
not alter a database: it turns the 92-club source ledger into an explicit
80-club Core80 selection and assigns every target to a runner-proven native EQ
carrier.
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
SELECTION_SEED = "pm99-2015-16-core80-v1"
TARGET_DIVISION_BY_PANEL = {
    "division_01": "Premier League",
    "division_02": "Championship",
    "division_03": "League One",
    "division_04": "League Two",
}
# Bury was subsequently dissolved and has no onward historical-season use.
# The remaining choices are deliberately seed-ranked, never hidden in a
# hand-edited binary or inferred from a raw carrier ID.
PREFERRED_OMISSIONS = {"Championship": (), "League One": ("Bury",), "League Two": ()}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_rank(division: str, club: str) -> str:
    return hashlib.sha256(f"{SELECTION_SEED}|{division}|{club}".encode("utf-8")).hexdigest()


def _json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _normalise_name(value: str) -> str:
    return "".join(char.casefold() for char in str(value or "") if char.isalnum())


def _load_slots(selector_map: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_division: dict[str, list[dict[str, Any]]] = {}
    for panel in list(selector_map.get("divisions") or []):
        panel_key = str(panel.get("division_key") or "")
        division = TARGET_DIVISION_BY_PANEL.get(panel_key)
        teams = list(panel.get("teams") or [])
        if division is None or len(teams) != 20:
            raise ValueError(f"Expected one 20-cell mapped panel for {panel_key!r}")
        ids = [int(team.get("eq_record_id")) for team in teams]
        if len(set(ids)) != 20:
            raise ValueError(f"Mapped panel {panel_key} has duplicate carrier IDs")
        by_division[division] = [
            {
                "native_panel": panel_key,
                "native_row_index": int(team.get("row_index")),
                "team_select_x": int(team.get("team_select_x")),
                "team_select_y": int(team.get("team_select_y")),
                "carrier_eq_record_id": int(team.get("eq_record_id")),
                "carrier_original_short_name": str(team.get("eq_short_name") or ""),
            }
            for team in teams
        ]
    if set(by_division) != set(TARGET_DIVISION_BY_PANEL.values()):
        raise ValueError("Selector map does not cover all four target divisions")
    return by_division


def build_selection(*, source_ledger: dict[str, Any], selector_map: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    clubs = list(source_ledger.get("clubs") or [])
    counts = Counter(str(club.get("division")) for club in clubs)
    expected_counts = {"Premier League": 20, "Championship": 24, "League One": 24, "League Two": 24}
    if counts != expected_counts:
        raise ValueError(f"Source ledger is not the expected 2015/16 20/24/24/24 shape: {dict(counts)}")
    if len({_normalise_name(str(club.get("club"))) for club in clubs}) != len(clubs):
        raise ValueError("Source ledger has duplicate club names")

    slots_by_division = _load_slots(selector_map)
    selected_by_division: dict[str, list[dict[str, Any]]] = {}
    omitted: list[dict[str, Any]] = []
    selection_receipts: list[dict[str, Any]] = []

    for division in ("Premier League", "Championship", "League One", "League Two"):
        candidates = [club for club in clubs if str(club["division"]) == division]
        desired_count = len(slots_by_division[division])
        preferred = {_normalise_name(name) for name in PREFERRED_OMISSIONS.get(division, ())}
        preferred_rows = [club for club in candidates if _normalise_name(str(club["club"])) in preferred]
        if len(preferred_rows) > len(candidates) - desired_count:
            raise ValueError(f"Preferred omission set overfills {division}")
        remaining_to_omit = len(candidates) - desired_count - len(preferred_rows)
        ranked = sorted(
            (club for club in candidates if club not in preferred_rows),
            key=lambda club: _seed_rank(division, str(club["club"])),
        )
        seeded_rows = ranked[:remaining_to_omit]
        omitted_rows = preferred_rows + seeded_rows
        selected_rows = [club for club in candidates if club not in omitted_rows]
        if len(selected_rows) != desired_count:
            raise ValueError(f"Selection count mismatch for {division}")
        # Source-ledger order is stable/alphabetical. It makes a visual Core80
        # selection reproducible without claiming the game stores real EFL
        # competition membership bytes.
        selected_rows.sort(key=lambda club: str(club["club"]).casefold())
        selected_by_division[division] = selected_rows
        for club in preferred_rows:
            omitted.append({"club": str(club["club"]), "division": division, "reason": "preferred-defunct-club"})
        for club in seeded_rows:
            omitted.append(
                {
                    "club": str(club["club"]),
                    "division": division,
                    "reason": "seeded-core80-omission",
                    "seed": SELECTION_SEED,
                    "rank_sha256": _seed_rank(division, str(club["club"])),
                }
            )
        selection_receipts.append(
            {
                "division": division,
                "source_club_count": len(candidates),
                "selected_club_count": len(selected_rows),
                "omitted_club_count": len(omitted_rows),
            }
        )

    selected_clubs: list[dict[str, Any]] = []
    slot_assignments: list[dict[str, Any]] = []
    for division in ("Premier League", "Championship", "League One", "League Two"):
        for club, slot in zip(selected_by_division[division], slots_by_division[division], strict=True):
            assigned = copy.deepcopy(club)
            assigned["carrier_eq_record_id"] = int(slot["carrier_eq_record_id"])
            assigned["native_selector"] = slot
            selected_clubs.append(assigned)
            slot_assignments.append(
                {
                    "club": str(assigned["club"]),
                    "division": division,
                    **slot,
                }
            )
    selected_ids = [int(club["carrier_eq_record_id"]) for club in selected_clubs]
    if len(selected_clubs) != 80 or len(set(selected_ids)) != 80:
        raise ValueError("Core80 selection did not produce 80 unique carrier assignments")

    selection = {
        "schema_version": "pm99-2015-16-core80-selection-v1",
        "season": SEASON,
        "status": "reviewed-algorithmic-selection",
        "selection_seed": SELECTION_SEED,
        "source_shape": expected_counts,
        "target_shape": {division: 20 for division in TARGET_DIVISION_BY_PANEL.values()},
        "source_ledger_sha256": None,
        "selector_map_sha256": None,
        "selection_receipts": selection_receipts,
        "omitted_clubs": sorted(omitted, key=lambda item: (item["division"], item["club"])),
        "slot_assignments": slot_assignments,
    }
    core_ledger = {
        **{key: value for key, value in source_ledger.items() if key != "clubs"},
        "schema_version": "pm99-2015-16-core80-source-ledger-v1",
        "clubs": selected_clubs,
        "core80_selection": selection,
    }
    return selection, core_ledger


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-ledger", required=True, type=Path)
    parser.add_argument("--selector-map", required=True, type=Path)
    parser.add_argument("--selection-output", required=True, type=Path)
    parser.add_argument("--core-ledger-output", required=True, type=Path)
    args = parser.parse_args()

    source_path = args.source_ledger.resolve()
    map_path = args.selector_map.resolve()
    selection, core_ledger = build_selection(
        source_ledger=json.loads(source_path.read_text(encoding="utf-8")),
        selector_map=json.loads(map_path.read_text(encoding="utf-8")),
    )
    selection["source_ledger_sha256"] = _sha256(source_path)
    selection["selector_map_sha256"] = _sha256(map_path)
    core_ledger["core80_selection"] = selection
    _json_dump(args.selection_output.resolve(), selection)
    _json_dump(args.core_ledger_output.resolve(), core_ledger)
    print(
        json.dumps(
            {
                "status": "pass",
                "clubs": len(core_ledger["clubs"]),
                "omitted": selection["omitted_clubs"],
                "selection_output": str(args.selection_output),
                "core_ledger_output": str(args.core_ledger_output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
