#!/usr/bin/env python3
"""Apply small, source-cited editorial corrections to an opening preallocation."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preallocation", type=Path, required=True)
    parser.add_argument("--overrides", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-audit", type=Path, required=True)
    args = parser.parse_args()
    source_raw = args.preallocation.read_bytes()
    override_raw = args.overrides.read_bytes()
    result = copy.deepcopy(json.loads(source_raw))
    overrides = json.loads(override_raw)
    if result.get("schema_version") != "pm99-opening-squad-preallocation-v1":
        parser.error("unsupported preallocation schema")
    season = (result.get("season") or {}).get("label")
    if overrides.get("schema_version") != "pm99-opening-preallocation-overrides-v1" or overrides.get("season") != season:
        parser.error("override schema or season mismatch")
    clubs = {row["selector"]["club_name"]: row for row in result.get("source_clubs") or []}
    applied = []
    for row in overrides.get("corrections") or []:
        club_name = str(row.get("club") or "")
        player_name = str(row.get("player") or "")
        club = clubs.get(club_name)
        if club is None:
            parser.error(f"override club is not selected: {club_name}")
        match_facts = row.get("match_facts") or {}
        if not isinstance(match_facts, dict):
            parser.error(f"match_facts must be an object: {club_name}/{player_name}")
        matches = [
            player for player in club["players"]
            if (player.get("facts") or {}).get("name") == player_name
            and all((player.get("facts") or {}).get(field) == value for field, value in match_facts.items())
        ]
        if not matches and row.get("allow_already_absent") is True:
            applied.append({
                "club": club_name, "player": player_name,
                "action": "already-absent", "source_url": row.get("source_url"),
                "reason": row.get("reason"), "match_facts": match_facts,
            })
            continue
        if len(matches) != 1:
            parser.error(f"override player match count for {club_name}/{player_name}: {len(matches)}")
        action = row.get("action")
        if action == "exclude-from-opening-squad":
            if matches[0].get("opening_xi_order") is not None:
                parser.error(f"cannot exclude sourced first-XI player: {club_name}/{player_name}")
            club["players"].remove(matches[0])
        elif action == "set-fact":
            field = str(row.get("field") or "")
            if field not in {"position", "nationality", "height_cm", "weight_kg", "shirt_number", "birth_date"}:
                parser.error(f"unsupported corrected fact: {field}")
            matches[0]["facts"][field] = row.get("value")
            unresolved = matches[0]["facts"].get("unresolved_fields") or []
            matches[0]["facts"]["unresolved_fields"] = [value for value in unresolved if value != field]
        else:
            parser.error(f"unsupported override action: {action}")
        applied.append({
            "club": club_name,
            "player": player_name,
            "action": action,
            "source_url": row.get("source_url"),
            "reason": row.get("reason"),
            "match_facts": match_facts,
        })
    result.setdefault("sources", {})["editorial_overrides_sha256"] = hashlib.sha256(override_raw).hexdigest()
    audit = {
        "schema_version": "pm99-opening-preallocation-override-audit-v1",
        "season": season,
        "input_preallocation_sha256": hashlib.sha256(source_raw).hexdigest(),
        "overrides_sha256": hashlib.sha256(override_raw).hexdigest(),
        "output_preallocation_sha256": hashlib.sha256(canonical(result)).hexdigest(),
        "applied": applied,
    }
    for path, value in ((args.output, result), (args.output_audit, audit)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical(value))
    print(json.dumps({"applied_correction_count": len(applied)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
