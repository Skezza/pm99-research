from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import audit_2015_world_candidate_package_v2 as audit  # noqa: E402


def test_audit_classifies_preserved_membership_as_satisfied_not_blocked() -> None:
    candidate = {
        "schema_version": audit.CANDIDATE_SCHEMA,
        "preserved_constraints": ["foreign-competition-membership-preserve-only"],
        "stage_status": "source-package-candidate",
        "carrier_drafts": [{
            "blockers": ["2015-era-kit-source-required"],
            "opening_fixture": {"status": "metadata-unavailable"},
            "players": [{"rating_disposition": {"status": "identity-resolution-required"}}],
        }],
    }
    result = audit.build_report(candidate)

    assert "foreign-competition-membership-preserve-only" not in result["candidate_blocker_counts"]
    assert result["satisfied_contracts"][0]["code"] == "foreign-competition-membership-preserve-only"
    gaps = {row["code"]: row["count"] for row in result["package_v2_schema_gaps"]}
    assert "opening-fixture-metadata-unavailable" not in gaps
    assert gaps["manager-ent-identity-unresolved"] == 1
    assert gaps["kit-disposition-unresolved"] == 1
    assert gaps["player-identity-resolution-required"] == 1
