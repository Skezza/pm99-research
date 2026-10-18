#!/usr/bin/env python3
"""Cluster unassigned real carriers across a verified coverage matrix."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.capture_transfermarkt_historical_squads_v1 import canonical_bytes
from scripts.season_carrier_allocation_v1 import ENGLISH_NON_LEAGUE_CARRIER_IDS, group_for_carrier


def build(matrix: dict[str, Any], registries: dict[str, dict[str, Any]], matrix_sha256: str) -> dict[str, Any]:
    countries: collections.Counter[str] = collections.Counter()
    carriers: dict[tuple[str, int], dict[str, Any]] = {}
    for row in matrix["seasons"]:
        season = str(row["season"])
        registry = registries[season]
        by_id = {int(value["carrier_id"]): value for value in registry["carriers"]}
        for carrier_id in row["unassigned_real_carrier_ids"]:
            carrier_id = int(carrier_id)
            group = "english-non-league" if carrier_id in ENGLISH_NON_LEAGUE_CARRIER_IDS else group_for_carrier(carrier_id)
            group = group or "unclassified-real-carrier"
            countries[group] += 1
            key = (group, carrier_id)
            value = carriers.setdefault(key, {
                "baseline_club": (by_id[carrier_id].get("baseline_club") or {}).get("name"),
                "carrier_id": carrier_id, "country_group": group, "seasons": [],
            })
            value["seasons"].append(season)
    carrier_rows = []
    for value in carriers.values():
        value["season_count"] = len(value["seasons"])
        carrier_rows.append(value)
    carrier_rows.sort(key=lambda row: (-row["season_count"], row["country_group"], row["carrier_id"]))
    return {
        "carrier_gaps": carrier_rows,
        "country_groups": [
            {"carrier_season_gap_count": count, "country_group": group}
            for group, count in sorted(countries.items(), key=lambda item: (-item[1], item[0]))
        ],
        "coverage_matrix_sha256": matrix_sha256,
        "schema_version": "pm99-historical-squad-recurring-gap-matrix-v1",
        "summary": {"carrier_season_gap_count": sum(countries.values()), "unique_carrier_gap_count": len(carriers)},
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-matrix", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    raw = args.coverage_matrix.read_bytes()
    matrix = json.loads(raw)
    registries = {
        row["season"]: json.loads((ROOT / "seasons" / row["season"] / "fixed-carrier-registry.json").read_text())
        for row in matrix["seasons"]
    }
    result = build(matrix, registries, hashlib.sha256(raw).hexdigest())
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
