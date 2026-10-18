#!/usr/bin/env python3
"""Resolve season-wide squad overlaps to one 2015 opening-date owner.

FootballSquads/NTF season pages include arrivals and departures across the
whole campaign.  This reviewed table selects the club held at the 2015
opening snapshot.  The other fixed slot preserves its native player row; it
is never filled with a duplicate or invented identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
from pathlib import Path
from typing import Any

SCHEMA = "pm99-world-2015-person-ownership-decisions-v1"

# Reviewed 2015 transfer chronology. Most overlaps are January 2016 moves
# included by both season-wide club lists; the retained carrier is the player
# holder at the opening snapshot, before that move.
OPENING_OWNER: dict[str, int] = {
    "arberzeneli": 953, "arteagamanuel": 2952, "barretodiego": 3201,
    "cristianchavez": 9017, "farrugiajeanpaul": 2152, "florenthanin": 1105,
    "gustavwikheim": 1358, "iverfossum": 1358, "kieffermoore": 1354,
    "lasikrichard": 1458, "leandrodamiao": 2809, "leonardosanchez": 9027,
    "lobzhanidzeucha": 1653, "malcom": 2806, "martinlinnes": 1353,
    "matiaskranevitter": 9001, "matiaszaldivia": 9017, "mauriciocuero": 9004,
    "merkisgiorgos": 1655, "michaelchristensen": 1209, "mikaeldyrestam": 1356,
    "milanovzhivko": 1502, "oleselnæs": 1351, "osmardanielferreyra": 9010,
    "pabloarmero": 2800, "rafaelgalhardo": 2805, "rajkovicpredrag": 701,
    "samir": 2800, "shechteritay": 2102, "simonkroon": 951,
    "stengrytebust": 1356, "stianringstad": 1357, "tobiasmikkelsen": 1351,
    "turgemanalon": 2102, "vukcevicmarko": 704, "zeballospablo": 3200,
}


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def build(audit: dict[str, Any]) -> dict[str, Any]:
    overlaps = audit.get("overlaps") or []
    names = {str(row["strict_identity"]["normalised_name"]) for row in overlaps}
    if names != set(OPENING_OWNER):
        raise ValueError(f"review table/audit mismatch: missing={sorted(names-set(OPENING_OWNER))} extra={sorted(set(OPENING_OWNER)-names)}")
    decisions: list[dict[str, Any]] = []
    for overlap in overlaps:
        identity = overlap["strict_identity"]
        owner = OPENING_OWNER[str(identity["normalised_name"])]
        retained_rows = [row for row in overlap["candidates"] if int(row["team_carrier_id"]) == owner]
        if len(retained_rows) != 1:
            raise ValueError(f"reviewed owner is not unique for {identity}")
        retained = retained_rows[0]
        displaced = [row for row in overlap["candidates"] if row is not retained]
        query = urllib.parse.urlencode({"query": retained["source_player_name"]})
        decisions.append({
            "strict_identity": identity,
            "action": "retain-one-opening-date-owner",
            "retained": {key: retained[key] for key in ("team_carrier_id", "slot_index", "player_carrier_id")},
            "displaced": [{**{key: row[key] for key in ("team_carrier_id", "slot_index", "player_carrier_id")}, "disposition": "preserve-native-carrier-row"} for row in displaced],
            "evidence": [
                {"source_url": f"https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche?{query}", "as_of_date": "2015-08-01", "note": f"Reviewed 2015 transfer chronology retains {retained['club_name']} at the opening snapshot; season-wide squad sources can list both pre- and post-transfer clubs."},
                {"source_url": retained["source_selector"]["source_path"], "as_of_date": "2015-season-source", "note": "Content-addressed dated squad source for the retained club; selector SHA is recorded in the overlap audit."},
            ],
        })
    decisions.sort(key=lambda row: (row["strict_identity"]["normalised_name"], row["strict_identity"]["birth_date"], row["strict_identity"]["nationality"]))
    return {
        "schema_version": SCHEMA,
        "source_overlap_audit_sha256": hashlib.sha256(canonical_bytes(audit)).hexdigest(),
        "policy": "one opening-date owner per strict person identity; displaced fixed slots preserve native rows; no duplicate or invented player",
        "coverage": {"decision_count": len(decisions), "retained_identity_count": len(decisions), "displaced_slot_count": sum(len(row["displaced"]) for row in decisions)},
        "decisions": decisions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overlap-audit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raw = args.overlap_audit.read_bytes()
    audit = json.loads(raw)
    if raw != canonical_bytes(audit):
        parser.error("overlap audit must be canonical JSON")
    result = build(audit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(result["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
