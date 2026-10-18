from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import foreign_carrier_assignment_v1 as assignments  # noqa: E402
from scripts import world_fixed_carrier_ledger_v2 as ledger  # noqa: E402


HASH = "a" * 64


def _registry() -> dict[str, object]:
    return {
        "schema_version": ledger.REGISTRY_SCHEMA,
        "registry_id": "synthetic-world-fixed-carriers",
        "baseline": {"database_files": {name: {"relative_path": f"DBDAT/{name}", "sha256": HASH, "size": 100} for name in ("ENT98030.FDI", "EQ98030.FDI", "JUG98030.FDI")}},
        "topology_policy": "preserve-existing-carriers-no-country-division-or-membership-claims",
        "carriers": [{
            "carrier_id": 1,
            "record_mode": 1,
            "baseline_club": {"name": "Baseline", "full_name": "Baseline FC", "ground_name": "Ground", "seated_capacity": 10000, "active_manager_carrier_id": 101},
            "roster_slots": [{"slot_index": index, "player_carrier_id": 1000 + index, "flag": 0, "family": "dd6360", "baseline_name": f"Player {index}"} for index in range(16)],
            "topology_policy": "preserve-existing-carrier-and-roster-slots",
        }],
        "known_baseline_duplicate_player_carriers": [],
    }


def _capture() -> dict[str, object]:
    source_hash = "b" * 64
    return {
        "schema_version": assignments.SOURCE_SCHEMA,
        "source": {"title": "Fixture", "repository": "https://example.invalid", "revision": None, "license": "CC0-1.0"},
        "season": {"catalog": "2015-2016", "label": "2015/16"},
        "clubs": [{
            "country_catalog": "spain", "competition_catalog": "laliga", "club_name": "Historical FC", "competition_name": "League", "source_path": "spain/2015-2016/laliga/historical.txt", "source_sha256": source_hash,
            "players": [{"name": f"Player {index}"} for index in range(16)],
        }],
        "summary": {"club_count": 1, "player_count": 16, "player_rows_with_unresolved_facts": 0, "country_catalogs": ["spain"], "competition_catalogs": ["spain/laliga"]},
    }


def _host_report() -> tuple[dict[str, object], str]:
    report = {
        "schema": assignments.HOST_REPORT_SCHEMA,
        "read_only": True,
        "capture_id": "spain-fixture",
        "base": {"eq98030_sha256": HASH},
        "accepted_host_mappings": [{"eq_record_id": 1, "host_country": "Spain", "evidence": {"sha256": "c" * 64}}],
    }
    return report, hashlib.sha256(assignments.canonical_json_bytes(report)).hexdigest()


def _approved_row() -> dict[str, object]:
    return {
        "carrier_id": 1,
        "status": "approved",
        "historical_club": {"identity_key": "historical-fc", "name": "Historical FC"},
        "source_selector": {"country_catalog": "spain", "competition_catalog": "laliga", "club_name": "Historical FC", "source_path": "spain/2015-2016/laliga/historical.txt", "source_sha256": "b" * 64},
        "blockers": [],
    }


def test_approved_assignment_requires_reviewed_same_country_host_evidence() -> None:
    registry = _registry()
    capture = _capture()
    assignment = assignments.initialise_assignment(registry=registry, source_capture=capture, host_reports=[_host_report()], assignment_id="world-2015-16")
    assignment["assignments"] = [_approved_row()]
    assignments.validate_assignment(assignment=assignment, registry=registry, source_capture=capture)
    audit = assignments.audit_assignment(assignment=assignment, registry=registry, source_capture=capture)
    assert audit["result"] == "identity-assignment-complete-not-content-release"
    assert audit["coverage"]["host_country_evidence_count"] == 1


def test_assignment_rejects_cross_country_or_undersized_source() -> None:
    registry = _registry()
    capture = _capture()
    assignment = assignments.initialise_assignment(registry=registry, source_capture=capture, host_reports=[_host_report()], assignment_id="world-2015-16")
    assignment["assignments"] = [_approved_row()]
    wrong = copy.deepcopy(assignment)
    wrong["assignments"][0]["source_selector"]["country_catalog"] = "italy"
    with pytest.raises(assignments.AssignmentError, match="not in the captured season"):
        assignments.validate_assignment(assignment=wrong, registry=registry, source_capture=capture)

    short = copy.deepcopy(capture)
    short["clubs"][0]["players"] = short["clubs"][0]["players"][:-1]
    short_assignment = assignments.initialise_assignment(
        registry=registry, source_capture=short, host_reports=[_host_report()], assignment_id="world-2015-16"
    )
    short_assignment["assignments"] = [_approved_row()]
    with pytest.raises(assignments.AssignmentError, match="smaller than its fixed PM99 capacity"):
        assignments.validate_assignment(assignment=short_assignment, registry=registry, source_capture=short)


def test_assignment_cannot_approve_a_carrier_without_picker_evidence() -> None:
    registry = _registry()
    capture = _capture()
    assignment = assignments.initialise_assignment(registry=registry, source_capture=capture, host_reports=[], assignment_id="world-2015-16")
    assignment["assignments"] = [_approved_row()]
    with pytest.raises(assignments.AssignmentError, match="no reviewed host-country evidence"):
        assignments.validate_assignment(assignment=assignment, registry=registry, source_capture=capture)


def test_review_proposal_is_a_deterministic_overlay_not_a_base_mutation() -> None:
    registry = _registry()
    capture = _capture()
    base = assignments.initialise_assignment(
        registry=registry, source_capture=capture, host_reports=[_host_report()], assignment_id="world-2015-16"
    )
    proposal = {
        "schema_version": assignments.PROPOSAL_SCHEMA,
        "assignment_id": "world-2015-16",
        "source_capture_sha256": base["source_capture_sha256"],
        "assignments": [_approved_row()],
    }
    derived = assignments.apply_proposals(assignment=base, proposals=[proposal])
    assert base["assignments"] == []
    assignments.validate_assignment(assignment=derived, registry=registry, source_capture=capture)

    wrong = copy.deepcopy(proposal)
    wrong["source_capture_sha256"] = "f" * 64
    with pytest.raises(assignments.AssignmentError, match="different historic source capture"):
        assignments.apply_proposals(assignment=base, proposals=[wrong])


def test_rebind_to_a_composed_capture_requires_old_binding_and_revalidates_selectors() -> None:
    registry = _registry()
    capture = _capture()
    base = assignments.initialise_assignment(
        registry=registry,
        source_capture=capture,
        host_reports=[_host_report()],
        assignment_id="world-2000-01-fixed-carriers",
    )
    merged = copy.deepcopy(capture)
    merged["source"]["title"] = "Fixture source bundle"
    merged["source"]["inputs"] = [{"capture_name": "fixture.json", "sha256": "d" * 64, "catalog": "2000-2001", "label": "2000/01"}]
    merged["season"] = {"catalog": "2000-01-hybrid", "label": "2000/01"}

    rebound = assignments.rebind_assignment_to_capture(
        assignment=base,
        registry=registry,
        previous_source_capture=capture,
        source_capture=merged,
        assignment_id="world-2000-01-composed-fixed-carriers",
    )

    assert base["assignment_id"] == "world-2000-01-fixed-carriers"
    assert rebound["assignment_id"] == "world-2000-01-composed-fixed-carriers"
    assert rebound["source_capture_sha256"] != base["source_capture_sha256"]
    assignments.validate_assignment(assignment=rebound, registry=registry, source_capture=merged)

    stale_previous = copy.deepcopy(capture)
    stale_previous["clubs"][0]["club_name"] = "Different FC"
    with pytest.raises(assignments.AssignmentError, match="locked to a different historic source capture"):
        assignments.rebind_assignment_to_capture(
            assignment=base,
            registry=registry,
            previous_source_capture=stale_previous,
            source_capture=merged,
            assignment_id="world-2000-01-composed-fixed-carriers",
        )
