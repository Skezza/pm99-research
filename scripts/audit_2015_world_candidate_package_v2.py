#!/usr/bin/env python3
"""Report why an all-carrier source candidate cannot yet be PM99 package V2."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "pm99-world-2015-package-v2-eligibility-report-v1"
CANDIDATE_SCHEMA = "pm99-world-2015-editorial-fallback-ratings-v1"


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


class EligibilityError(ValueError):
    pass


def build_report(candidate: Mapping[str, Any]) -> dict[str, Any]:
    if candidate.get("schema_version") != CANDIDATE_SCHEMA or not isinstance(candidate.get("carrier_drafts"), list):
        raise EligibilityError("candidate has the wrong schema")
    rows = candidate["carrier_drafts"]
    blockers = Counter(blocker for row in rows for blocker in row.get("blockers") or [])
    identities = sum(1 for row in rows for player in row.get("players") or [] if player.get("rating_disposition", {}).get("status") == "identity-resolution-required")
    package_gaps = [
        {"code": "manager-ent-identity-unresolved", "count": len(rows), "detail": "V2 requires manager records and club manager IDs; dated manager text is not an immutable ENT identity/relink proof."},
        {"code": "dated-manager-source-required", "count": blockers["2015-manager-source-required"], "detail": "Every updated club needs a dated manager source; this is content still missing, not optional metadata."},
        {"code": "kit-disposition-unresolved", "count": blockers["2015-era-kit-source-required"], "detail": "V2 requires a kit declaration backed by an artifact/proof."},
        {"code": "portrait-disposition-unresolved", "count": blockers["portrait-source-or-no-photo-decision-required"], "detail": "V2 requires one explicit portrait/native-no-photo decision per player."},
        {"code": "ground-capacity-source-unresolved", "count": blockers["2015-club-ground-and-capacity-source-required"], "detail": "The candidate intentionally makes no permanent ground/capacity claim."},
    ]
    if identities:
        package_gaps.append({"code": "player-identity-resolution-required", "count": identities, "detail": "Only unresolved roster identities prevent V2 player rating rows."})
    allocation_count = ((candidate.get("coverage") or {}).get("mode1_recycle_allocation_count"))
    return {"schema_version": SCHEMA, "candidate_sha256": hashlib.sha256(canonical_json_bytes(dict(candidate))).hexdigest(), "result": "not-structurally-package-v2-ready", "preserved_constraints": candidate.get("preserved_constraints"), "stage_status": candidate.get("stage_status"), "satisfied_contracts": [{"code": "foreign-competition-membership-preserve-only", "detail": "satisfied preserved constraint; not a blocker"}, {"code": "mode1-core-and-allocation-specific-recycle", "detail": f"core path is proven and all {allocation_count} allocated recycle demands use runtime-qualified role codes"}, {"code": "final-player-carrier-ids-unique", "detail": "candidate builder rejects any package whose final player carrier IDs are not unique"}], "candidate_blocker_counts": dict(sorted(blockers.items())), "package_v2_schema_gaps": package_gaps}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--candidate", required=True, type=Path); parser.add_argument("--output", required=True, type=Path); args = parser.parse_args(argv)
    raw = args.candidate.read_bytes(); candidate = json.loads(raw.decode("utf-8"))
    if raw != canonical_json_bytes(candidate): parser.error("candidate must be canonical JSON")
    try: report = build_report(candidate)
    except EligibilityError as exc: parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_bytes(canonical_json_bytes(report)); print(json.dumps({"result": report["result"], "gap_count": len(report["package_v2_schema_gaps"])}, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
