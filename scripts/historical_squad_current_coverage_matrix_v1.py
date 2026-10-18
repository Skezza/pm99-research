#!/usr/bin/env python3
"""Audit hash-bound current squad revisions and consolidate carrier coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.capture_transfermarkt_historical_squads_v1 import canonical_bytes
from scripts.season_historical_squad_backfill_batch_v1 import CURRENT_SCHEMA
from scripts.season_carrier_allocation_v1 import SYSTEM_SELECTION_IDS

SCHEMA = "pm99-historical-squad-current-coverage-matrix-v1"


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def audit(season: str, season_root: Path) -> dict[str, Any]:
    local = (season_root / season).resolve()
    manifest_raw = (local / "current.json").read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest.get("schema_version") != CURRENT_SCHEMA or manifest.get("season") != season:
        raise ValueError(f"{season}: invalid current manifest")
    documents: dict[str, dict[str, Any]] = {}
    for name, row in manifest["artifacts"].items():
        path = (local / row["path"]).resolve()
        path.relative_to(local)
        payload = path.read_bytes()
        if _sha(payload) != row["sha256"]:
            raise ValueError(f"{season}: {name} hash mismatch")
        documents[name] = json.loads(payload)
    allocation = documents["allocation"]
    registry = json.loads((ROOT / "seasons" / season / "fixed-carrier-registry.json").read_text())
    real_ids = {int(row["carrier_id"]) for row in registry["carriers"]} - SYSTEM_SELECTION_IDS
    assigned_ids = {int(row["carrier_id"]) for row in allocation["assignments"]}
    if not assigned_ids <= real_ids:
        raise ValueError(f"{season}: allocation assigns a system selection or unknown carrier")
    unassigned_ids = sorted(real_ids - assigned_ids)
    quality_gaps = allocation.get("gaps", [])
    return {
        "allocation_sha256": manifest["artifacts"]["allocation"]["sha256"],
        "assigned_real_carrier_count": len(assigned_ids),
        "current_manifest_sha256": _sha(manifest_raw),
        "intake_sha256": manifest["artifacts"]["intake"]["sha256"],
        "release_capacity_eligible_count": allocation["coverage"].get("release_capacity_eligible_count", len(assigned_ids)),
        "revision_id": manifest["revision_id"], "season": season,
        "source_club_count": len(documents["source"].get("clubs", [])),
        "source_excess_count": sum(row.get("status") == "source-club-exceeds-fixed-country-capacity" for row in quality_gaps),
        "system_selection_preserve_count": len(SYSTEM_SELECTION_IDS),
        "thin_below_xi_source_count": sum(row.get("status") == "source-club-below-opening-xi-minimum-blocked" for row in quality_gaps),
        "unassigned_real_carrier_count": len(unassigned_ids),
        "unassigned_real_carrier_ids": unassigned_ids,
        "xi_source_eligible_count": allocation["coverage"].get("xi_source_eligible_count"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season-root", type=Path, default=ROOT / ".local/season-historical-squad-backfill-v1")
    parser.add_argument("--season", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = {"schema_version": SCHEMA, "seasons": [audit(s, args.season_root) for s in args.season]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps({"output": str(args.output), "season_count": len(result["seasons"]), "sha256": _sha(args.output.read_bytes())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
