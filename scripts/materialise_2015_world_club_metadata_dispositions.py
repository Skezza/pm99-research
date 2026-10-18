#!/usr/bin/env python3
"""Join dated manager/stadium facts to every selected 2015 world carrier.

The receipt deliberately distinguishes a manager observed in the opening
fixture, a reported fixture stadium, and a permanent ground/capacity fact.
Missing facts receive an explicit preserve disposition; fixture evidence is
never promoted into a capacity claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "pm99-world-2015-club-metadata-dispositions-v1"


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def build(*, draft: dict[str, Any], fixture_receipt: dict[str, Any], identity_receipt: dict[str, Any], wikipedia_receipt: dict[str, Any] | None = None) -> dict[str, Any]:
    selected = {int(row["carrier_id"]): row for row in draft.get("proposals", []) if row.get("status") == "source-squad-ready"}
    fixtures_by_id = {int((row.get("source_club") or {}).get("id")): row for row in fixture_receipt.get("clubs", []) if (row.get("source_club") or {}).get("id") is not None}
    mapping_by_carrier: dict[int, dict[str, Any]] = {}
    for mapping in identity_receipt.get("mappings", []):
        for carrier_id in mapping.get("selected_source_draft_carrier_ids", []):
            carrier_id = int(carrier_id)
            if carrier_id in mapping_by_carrier:
                raise ValueError(f"carrier {carrier_id} has more than one fixture identity")
            mapping_by_carrier[carrier_id] = mapping
    wiki_by_carrier = {int(row["carrier_id"]): row for row in (wikipedia_receipt or {}).get("rows", []) if row.get("status") == "exact-season-infobox-match"}

    rows: list[dict[str, Any]] = []
    for carrier_id, proposal in sorted(selected.items()):
        mapping = mapping_by_carrier.get(carrier_id)
        fixture = None
        if mapping is not None:
            source_id = (mapping.get("transfermarkt_source_club") or {}).get("id")
            fixture = fixtures_by_id.get(int(source_id)) if source_id is not None else None
        wiki = wiki_by_carrier.get(carrier_id)
        opening = (fixture or {}).get("opening_fixture") or {}
        home_ground = (fixture or {}).get("first_home_fixture_ground_evidence") or {}
        manager = opening.get("declared_manager") or ((wiki or {}).get("facts") or {}).get("manager")
        stadium = ((wiki or {}).get("facts") or {}).get("stadium") or home_ground.get("reported_stadium")
        capacity = ((wiki or {}).get("facts") or {}).get("capacity")
        rows.append({
            "carrier_id": carrier_id,
            "source_club_name": proposal.get("source_club_name"),
            "manager": {
                "status": "dated-source-fact" if manager else "preserve-existing-no-dated-source",
                "value": manager,
                "source_url": opening.get("source_url") if opening.get("declared_manager") else ((wiki or {}).get("page") or {}).get("title"),
                "scope": "opening-fixture-declared-manager" if opening.get("declared_manager") else ("2015-16-season-infobox" if manager else "unavailable"),
            },
            "stadium": {
                "status": "dated-season-ground-fact" if ((wiki or {}).get("facts") or {}).get("stadium") else ("fixture-stadium-evidence-only" if stadium else "preserve-existing-no-dated-source"),
                "value": stadium,
                "source_url": ((wiki or {}).get("page") or {}).get("title") if ((wiki or {}).get("facts") or {}).get("stadium") else home_ground.get("source_url"),
                "scope": "2015-16-season-infobox" if ((wiki or {}).get("facts") or {}).get("stadium") else ("first-home-domestic-fixture" if stadium else "unavailable"),
            },
            "capacity": {
                "status": "dated-season-capacity-fact" if capacity else "preserve-existing-no-season-scoped-source",
                "value": capacity,
                "source_url": ((wiki or {}).get("page") or {}).get("title") if capacity else None,
                "scope": "2015-16-season-infobox" if capacity else "unavailable",
            },
            "write_policy": "write only dated source facts; fixture-stadium evidence is review-only; preserve every unavailable field",
        })
    return {
        "schema_version": SCHEMA,
        "policy": "one row per source-ready carrier; exact source identity joins only; no inferred capacity; unavailable fields preserve native bytes",
        "sources": {"draft_sha256": digest(draft), "fixture_receipt_sha256": digest(fixture_receipt), "identity_receipt_sha256": digest(identity_receipt), "wikipedia_receipt_sha256": digest(wikipedia_receipt) if wikipedia_receipt else None},
        "coverage": {
            "selected_carrier_count": len(rows),
            "manager_fact_count": sum(row["manager"]["status"] == "dated-source-fact" for row in rows),
            "fixture_stadium_evidence_count": sum(row["stadium"]["status"] == "fixture-stadium-evidence-only" for row in rows),
            "dated_season_stadium_fact_count": sum(row["stadium"]["status"] == "dated-season-ground-fact" for row in rows),
            "dated_season_capacity_fact_count": sum(row["capacity"]["status"] == "dated-season-capacity-fact" for row in rows),
            "metadata_disposition_row_count": len(rows),
        },
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--fixture-receipt", required=True, type=Path)
    parser.add_argument("--identity-receipt", required=True, type=Path)
    parser.add_argument("--wikipedia-receipt", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    result = build(draft=load(args.draft), fixture_receipt=load(args.fixture_receipt), identity_receipt=load(args.identity_receipt), wikipedia_receipt=load(args.wikipedia_receipt) if args.wikipedia_receipt else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(result["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
