#!/usr/bin/env python3
"""Audit the maximum safe V2 projection from the enriched world-2015 draft.

This is intentionally not a PM99 writer.  It emits a canonical source receipt
and only emits a ``pm99-season-package-v2`` when the current V2 schema and
compiler can preserve every unsupported lane without inventing metadata.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))
from scripts.season_package_v2 import canonical_json_bytes

SCHEMA = "pm99-world-2015-v2-package-projection-v1"
CANDIDATE_SCHEMA = "pm99-world-2015-editorial-fallback-ratings-v1"
PORTRAIT_SCHEMA = "pm99-world-2015-portrait-materialisation-v1"


class ProjectionError(ValueError):
    pass


def _hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _portrait_index(receipt: Mapping[str, Any]) -> dict[tuple[int, int], Mapping[str, Any]]:
    rows = [*(receipt.get("successes") or []), *(receipt.get("failures") or [])]
    index: dict[tuple[int, int], Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("carrier_id"), int) or not isinstance(row.get("slot_index"), int):
            continue
        key = (int(row["carrier_id"]), int(row["slot_index"]))
        if key in index:
            raise ProjectionError(f"portrait receipt duplicates carrier/slot {key}")
        index[key] = row
    return index


def build(candidate: Mapping[str, Any], portraits: Mapping[str, Any]) -> dict[str, Any]:
    if candidate.get("schema_version") != CANDIDATE_SCHEMA:
        raise ProjectionError("candidate schema is unsupported")
    if portraits.get("schema_version") != PORTRAIT_SCHEMA:
        raise ProjectionError("portrait materialisation schema is unsupported")
    carriers = candidate.get("carrier_drafts")
    if not isinstance(carriers, list) or len(carriers) != 317:
        raise ProjectionError("expected enriched 317-carrier candidate")
    indexed = _portrait_index(portraits)
    declarations = []
    for club in sorted(carriers, key=lambda row: int(row["carrier_id"])):
        cid = int(club["carrier_id"])
        for player in sorted(club.get("players") or [], key=lambda row: int(row["slot_index"])):
            key = (cid, int(player["slot_index"]))
            material = indexed.get(key)
            status = "native-no-photo"
            disposition = player.get("portrait_disposition") or {}
            if material and material.get("status") == "approved-crop-conversion-candidate":
                status = "applied"
            declarations.append({
                "player_carrier_id": int(player["player_carrier_id"]),
                "carrier_id": cid,
                "slot_index": key[1],
                "status": status,
                "materialisation_status": material.get("status") if material else "no-fifa16-portrait-candidate; explicit-native-no-photo",
                "materialisation_player_carrier_id": material.get("player_carrier_id") if material else None,
                "reason": material.get("reason") if material else disposition.get("reason"),
            })
    final_ids = [row["player_carrier_id"] for row in declarations]
    if len(final_ids) != 6819 or len(final_ids) != len(set(final_ids)):
        raise ProjectionError("candidate final player carrier IDs must be exactly 6,819 and unique")
    counts = Counter(row["status"] for row in declarations)
    if counts != Counter({"applied": 3458, "native-no-photo": 3361}):
        raise ProjectionError(f"unexpected remapped portrait status counts: {dict(counts)}")
    blockers = [
        {"code": "manager-preserve-not-representable", "count": 317, "detail": "V2 requires each club manager_id to resolve to an ENT carrier; dated manager text has no safe ENT identity/relink mapping and compiler always patches the EQ manager link."},
        {"code": "ground-capacity-preserve-not-implemented", "count": 317, "detail": "Ground/capacity are optional in schema but current compiler unconditionally rewrites both lanes; no dated permanent ground/capacity source is available."},
        {"code": "kit-preserve-not-representable", "count": 317, "detail": "V2 requires a backed kit artifact set for every club; no reviewed 2015 kit artifact may be invented."},
        {"code": "birth-date-review-required", "count": 6, "detail": "Six player rows lack source DOB, which V2 player facts require."},
        {"code": "shirt-number-preserve-not-implemented", "count": 26, "detail": "Foreign shirt numbers are preserve-only but V2 currently requires a concrete integer that compiler writes."},
    ]
    return {
        "schema_version": SCHEMA,
        "result": "no-nonempty-strict-pm99-season-package-v2-under-current-schema-runtime",
        "candidate_sha256": _hash(candidate),
        "portrait_materialisation_sha256": _hash(portraits),
        "preserved_constraints": ["foreign-competition-membership-preserve-only", "opening-policy-preserve-existing-mode1"],
        "compiler_graph": {"allocation_count": candidate.get("coverage", {}).get("mode1_recycle_allocation_count"), "final_player_carrier_id_count": len(final_ids), "final_player_carrier_ids_unique": True},
        "portrait_declarations": declarations,
        "coverage": {"carrier_count": len(carriers), "slot_count": len(declarations), "portrait_status_counts": dict(sorted(counts.items())), "maximum_compileable_club_count": 0, "maximum_compileable_player_count": 0},
        "blockers": blockers,
        "no_binary_write": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--portrait-materialisation", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    candidate = json.loads(args.candidate.read_text()); portraits = json.loads(args.portrait_materialisation.read_text())
    try: output = build(candidate, portraits)
    except ProjectionError as exc: parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_bytes(canonical_json_bytes(output))
    print(json.dumps(output["coverage"], sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
