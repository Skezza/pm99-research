#!/usr/bin/env python3
"""Resolve PM99's native English selector cells to immutable EQ record IDs.

The new-game selector is a presentation surface, not a record-ID sequence.
This read-only audit starts from a runner-native-click capture, translates its
small OCR abbreviations through an explicit reviewable alias table, and joins
each cell to the parser-backed EQ/JUG linked-roster catalog.  It fails closed
on an empty, ambiguous, duplicate, or unmatched cell.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
if str(EDITOR) not in sys.path:
    sys.path.insert(0, str(EDITOR))

from app.eq_jug_linked import load_eq_linked_team_rosters  # noqa: E402


# These are display/OCR corrections from the runner's clean, client-coordinate
# capture. They are intentionally exact—not fuzzy matching—and every result is
# validated against the parsed EQ linked-roster catalog below.
DISPLAY_ALIASES = {
    "blackburnr": "Blackburn R.",
    "charitonath": "Charlton Ath.",
    "leedsutd": "Leeds Utd.",
    "newcastlelitd": "Newcastle Utd.",
    "nottinghamf": "Nottingham F.",
    "sheffieldw": "Sheffield W.",
    "tottenhamh": "Tottenham H.",
    "birminghamc": "Birmingham C.",
    "boltonw": "Bolton W.",
    "crewealex": "Crewe Alex.",
    "crystalpal": "Crystal Pal.",
    "grimsbyt": "Grimsby T.",
    "ipswich": "Ipswich",
    "norwichc": "Norwich C.",
    "sheffielditd": "Sheffield Utd.",
    "stockportcc": "Stockport C.",
    "tranmererov": "Tranmere Rov.",
    "wba": "WBA",
    "bristolrevers": "Bristol Rovers",
    "colchesteru": "Colchester U.",
    "lincolnc": "Lincoln C.",
    "macclesfieldt": "Macclesfield T.",
    "manchesterc": "Manchester C.",
    "nerthamptont": "Northampton T.",
    "nottscc": "Notts C.",
    "prestonne": "Preston North End",
    "stokec": "Stoke C.",
    "wiganath": "Wigan Ath.",
    "wycombew": "Wycombe W.",
    "brightonandha": "Brighton & HA",
    "cardiffc": "Cardiff C.",
    "carlisieu": "Carlisle U.",
    "chesterc": "Chester C.",
    "exeterc": "Exeter C.",
    "hartlepoolu": "Hartlepool U.",
    "hullc": "Hull C.",
    "leyton": "Leyton O.",
    "leytono": "Leyton O.",
    "mansfieldt": "Mansfield T.",
    "rotherhamu": "Rotherham U.",
    "scunthorpeu": "Scunthorpe U.",
    "shrewsburyt": "Shrewsbury T.",
    "torquaylu": "Torquay U.",
}


def _key(value: str) -> str:
    text = str(value or "").casefold()
    text = text.replace("&", "and")
    return "".join(char for char in text if char.isalnum())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_name(raw_label: str) -> str:
    key = _key(raw_label)
    return DISPLAY_ALIASES.get(key, str(raw_label or "").strip())


def _catalog_by_name(eq_path: Path, jug_path: Path) -> dict[str, list[Any]]:
    catalog: dict[str, list[Any]] = {}
    for roster in load_eq_linked_team_rosters(team_file=str(eq_path), player_file=str(jug_path)):
        for name in (roster.short_name, roster.full_club_name):
            normalized = _key(name)
            if normalized:
                catalog.setdefault(normalized, []).append(roster)
    return catalog


def _entry_for_label(label: str, catalog: dict[str, list[Any]]) -> Any:
    canonical = _resolve_name(label)
    matches = catalog.get(_key(canonical), [])
    unique = {int(item.eq_record_id): item for item in matches}
    if len(unique) != 1:
        ids = sorted(unique)
        raise ValueError(
            f"Selector label {label!r} -> {canonical!r} resolved to {len(ids)} EQ records: {ids}"
        )
    return canonical, next(iter(unique.values()))


def build_map(*, selector_path: Path, eq_path: Path, jug_path: Path) -> dict[str, Any]:
    capture = json.loads(selector_path.read_text(encoding="utf-8"))
    divisions = list(capture.get("divisions") or [])
    if len(divisions) != 4:
        raise ValueError(f"Expected four selector divisions, got {len(divisions)}")

    catalog = _catalog_by_name(eq_path, jug_path)
    output_divisions: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    seen_points: set[tuple[int, int, int, int]] = set()

    for division in divisions:
        division_key = str(division.get("division_key") or "")
        division_x = int(division.get("division_select_x") or -1)
        division_y = int(division.get("division_select_y") or -1)
        teams = list(division.get("teams") or [])
        if len(teams) != 20:
            raise ValueError(f"{division_key} has {len(teams)} team cells, expected 20")

        rows: list[dict[str, Any]] = []
        for team in teams:
            label = str(team.get("text") or "").strip()
            if not label:
                raise ValueError(f"{division_key} contains an empty OCR label")
            canonical, roster = _entry_for_label(label, catalog)
            eq_record_id = int(roster.eq_record_id)
            point = (
                division_x,
                division_y,
                int(team.get("team_select_x") or -1),
                int(team.get("team_select_y") or -1),
            )
            if eq_record_id in seen_ids:
                raise ValueError(f"Duplicate EQ record id in selector surface: {eq_record_id}")
            if point in seen_points:
                raise ValueError(f"Duplicate selector point: {point}")
            seen_ids.add(eq_record_id)
            seen_points.add(point)
            rows.append(
                {
                    "row_index": int(team.get("row_index") or 0),
                    "team_select_x": int(team.get("team_select_x") or -1),
                    "team_select_y": int(team.get("team_select_y") or -1),
                    "observed_label": label,
                    "canonical_team_name": canonical,
                    "eq_record_id": eq_record_id,
                    "eq_short_name": str(roster.short_name),
                    "eq_full_club_name": str(roster.full_club_name),
                    "mode_byte": int(roster.mode_byte),
                }
            )
        output_divisions.append(
            {
                "division_key": division_key,
                "division_select_x": division_x,
                "division_select_y": division_y,
                "teams": rows,
            }
        )

    if len(seen_ids) != 80:
        raise ValueError(f"Expected 80 unique native selector EQ records, got {len(seen_ids)}")

    ids = sorted(seen_ids)
    return {
        "schema_version": "pm99-native-english-selector-eq-map-v1",
        "status": "pass",
        "inputs": {
            "selector_capture": str(selector_path),
            "selector_capture_sha256": _sha256(selector_path),
            "eq_file": str(eq_path),
            "eq_file_sha256": _sha256(eq_path),
            "jug_file": str(jug_path),
            "jug_file_sha256": _sha256(jug_path),
        },
        "selector_cell_count": 80,
        "unique_eq_record_count": len(ids),
        "eq_record_ids": ids,
        "eq_record_id_ranges": [
            {"start": start, "end": end, "count": count}
            for start, end, count in _contiguous_ranges(ids)
        ],
        "mode_counts": {
            str(mode): int(count)
            for mode, count in sorted(
                Counter(team["mode_byte"] for division in output_divisions for team in division["teams"]).items()
            )
        },
        "divisions": output_divisions,
    }


def _contiguous_ranges(values: list[int]) -> list[tuple[int, int, int]]:
    if not values:
        return []
    start = previous = values[0]
    output: list[tuple[int, int, int]] = []
    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue
        output.append((start, previous, previous - start + 1))
        start = previous = value
    output.append((start, previous, previous - start + 1))
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selector-capture", required=True, type=Path)
    parser.add_argument("--eq-file", required=True, type=Path)
    parser.add_argument("--jug-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    result = build_map(
        selector_path=args.selector_capture.resolve(),
        eq_path=args.eq_file.resolve(),
        jug_path=args.jug_file.resolve(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output), "eq_record_ids": result["eq_record_ids"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
