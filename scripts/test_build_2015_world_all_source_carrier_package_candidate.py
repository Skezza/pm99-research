from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_2015_world_all_source_carrier_package_candidate as candidate  # noqa: E402


def test_candidate_refuses_a_recycle_audit_with_unqualified_required_roles() -> None:
    with pytest.raises(candidate.AllCarrierCandidateError, match="not qualified"):
        candidate.build_candidate(
            source_draft={"schema_version": candidate.DRAFT_SCHEMA},
            reconciliation={"schema_version": candidate.RECON_SCHEMA},
            opening_join={"schema_version": candidate.JOIN_SCHEMA},
            assets={"schema_version": candidate.ASSET_SCHEMA, "clubs": []},
            recycle={"schema_version": candidate.RECYCLE_SCHEMA, "result": "blocked-unqualified-role", "runtime_unqualified_required_role_codes": [7]},
            source_hashes={},
        )


def test_ambiguous_fifa_name_uses_identity_safe_editorial_fallback() -> None:
    row = {"fifa16": {"status": "fifa16-ambiguous-name", "candidate_fifa16_player_ids": [1, 2]}}
    result = candidate._rating(row)

    assert result == {
        "status": "editorial-fallback-required",
        "fifa16_match_status": "fifa16-ambiguous-name",
        "candidate_fifa16_player_ids": [1, 2],
        "reason": "FIFA16 candidates do not share the FootballSquads DOB; deterministic editorial rating fallback required",
        "identity_basis": "FootballSquads-club-DOB-nationality; FIFA-candidates-retained-as-nonmatching-rating-provenance",
    }


def test_integrated_candidate_requires_the_current_recycle_receipt() -> None:
    assert candidate._expected_recycle_allocation_count(302) == 29
    assert candidate._expected_recycle_allocation_count(317) == 30
    assert candidate._expected_recycle_allocation_count(362) == 32
    assert candidate._expected_recycle_allocation_count(372) == 36
