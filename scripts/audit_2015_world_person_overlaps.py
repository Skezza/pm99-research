#!/usr/bin/env python3
"""Emit exact same-person candidates which need opening-date club ownership."""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.season_package_v2 import canonical_json_bytes

SCHEMA = "pm99-world-2015-person-overlap-audit-v1"


def _name_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    return "".join(char.casefold() for char in text if char.isalnum())


def audit(candidate: Mapping[str, Any]) -> dict[str, Any]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for club in candidate.get("carrier_drafts") or []:
        for player in club.get("players") or []:
            source = player.get("source_player") or {}
            if not all(isinstance(source.get(key), str) for key in ("name", "birth_date", "nationality")):
                continue
            key = (_name_key(source["name"]), source["birth_date"], source["nationality"])
            groups[key].append({
                "team_carrier_id": int(club["carrier_id"]),
                "club_name": club["club"]["source_club_name"],
                "slot_index": int(player["slot_index"]),
                "player_carrier_id": int(player["player_carrier_id"]),
                "source_player_name": source["name"],
                "birth_date": source["birth_date"],
                "nationality": source["nationality"],
                "source_selector": club["club"].get("source_selector"),
            })
    overlaps = []
    for (name_key, birth_date, nationality), rows in sorted(groups.items()):
        if len(rows) < 2:
            continue
        overlaps.append({
            "strict_identity": {"normalised_name": name_key, "birth_date": birth_date, "nationality": nationality},
            "candidates": sorted(rows, key=lambda row: (row["team_carrier_id"], row["slot_index"])),
            "required_decision": "select exactly one opening-date club owner or provide evidence that these are distinct people",
        })
    return {
        "schema_version": SCHEMA,
        "result": "blocked-opening-date-person-ownership" if overlaps else "pass",
        "overlap_identity_count": len(overlaps),
        "overlap_row_count": sum(len(row["candidates"]) for row in overlaps),
        "overlaps": overlaps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    value = audit(json.loads(args.candidate.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(value))
    print(json.dumps({key: value[key] for key in ("result", "overlap_identity_count", "overlap_row_count")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
