from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import foreign_carrier_assignment_v1 as assignments  # noqa: E402
from scripts.merge_footballsquads_captures import merge_captures  # noqa: E402
from scripts import season_source_intake_v1 as intake_lib  # noqa: E402
from scripts import world_fixed_carrier_ledger_v2 as ledger  # noqa: E402


HASH = "a" * 64
SOURCE_A_HASH = "b" * 64
SOURCE_B_HASH = "c" * 64


def _registry() -> dict[str, object]:
    carriers = []
    for carrier_id in (1, 2):
        carriers.append(
            {
                "carrier_id": carrier_id,
                "record_mode": 1,
                "baseline_club": {
                    "name": f"Baseline {carrier_id}",
                    "full_name": f"Baseline {carrier_id} FC",
                    "ground_name": "Ground",
                    "seated_capacity": 10000,
                    "active_manager_carrier_id": 100 + carrier_id,
                },
                "roster_slots": [
                    {
                        "slot_index": slot_index,
                        "player_carrier_id": carrier_id * 1000 + slot_index,
                        "flag": 0,
                        "family": "dd6360",
                        "baseline_name": f"Player {carrier_id}-{slot_index}",
                    }
                    for slot_index in range(3)
                ],
                "topology_policy": "preserve-existing-carrier-and-roster-slots",
            }
        )
    return {
        "schema_version": ledger.REGISTRY_SCHEMA,
        "registry_id": "synthetic-world-fixed-carriers",
        "baseline": {
            "database_files": {
                name: {"relative_path": f"DBDAT/{name}", "sha256": HASH, "size": 100}
                for name in ("ENT98030.FDI", "EQ98030.FDI", "JUG98030.FDI")
            }
        },
        "topology_policy": "preserve-existing-carriers-no-country-division-or-membership-claims",
        "carriers": carriers,
        "known_baseline_duplicate_player_carriers": [],
    }


def _player(*, name: str, nationality: str | None = "ESP") -> dict[str, object]:
    unresolved = [] if nationality is not None else ["nationality"]
    return {
        "shirt_number": 1,
        "name": name,
        "nationality": nationality,
        "position": "M",
        "height_cm": 180,
        "weight_kg": 75,
        "birth_date": "1980-01-01",
        "unresolved_fields": unresolved,
    }


def _capture() -> dict[str, object]:
    return {
        "schema_version": assignments.SOURCE_SCHEMA,
        "source": {
            "title": "Fixture source",
            "repository": "https://example.invalid/source",
            "revision": None,
            "license": "CC0-1.0",
        },
        "season": {"catalog": "2000-2001", "label": "2000/01"},
        # Two clubs demonstrate that a generic merged capture is retained in
        # full even when only one source club is selected for a carrier.
        "clubs": [
            {
                "country_catalog": "spain",
                "competition_catalog": "laliga",
                "club_name": "Historical FC",
                "competition_name": "League",
                "source_path": "spain/2000-2001/laliga/historical.txt",
                "source_sha256": SOURCE_A_HASH,
                "players": [
                    _player(name="Known Player"),
                    _player(name="Unknown Nationality", nationality=None),
                    _player(name="Third Player"),
                ],
            },
            {
                "country_catalog": "spain",
                "competition_catalog": "laliga",
                "club_name": "Unselected FC",
                "competition_name": "League",
                "source_path": "spain/2000-2001/laliga/unselected.txt",
                "source_sha256": SOURCE_B_HASH,
                "players": [_player(name="Unselected Player")],
            },
        ],
        "summary": {
            "club_count": 2,
            "player_count": 4,
            "player_rows_with_unresolved_facts": 1,
            "country_catalogs": ["spain"],
            "competition_catalogs": ["spain/laliga"],
        },
    }


def _candidate_assignment(
    *, registry: dict[str, object], capture: dict[str, object]
) -> dict[str, object]:
    assignment = assignments.initialise_assignment(
        registry=registry,
        source_capture=capture,
        host_reports=[],
        assignment_id="world-2000-01",
    )
    assignment["assignments"] = [
        {
            "carrier_id": 1,
            "status": "candidate",
            "historical_club": {"identity_key": "historical-fc", "name": "Historical FC"},
            "source_selector": {
                "country_catalog": "spain",
                "competition_catalog": "laliga",
                "club_name": "Historical FC",
                "source_path": "spain/2000-2001/laliga/historical.txt",
                "source_sha256": SOURCE_A_HASH,
            },
            "blockers": ["requires-editorial-identity-review"],
        }
    ]
    assignments.validate_assignment(assignment=assignment, registry=registry, source_capture=capture)
    return assignment


def test_intake_is_all_carrier_and_preserves_capture_gaps() -> None:
    registry = _registry()
    capture = _capture()
    assignment = _candidate_assignment(registry=registry, capture=capture)

    intake = intake_lib.build_intake(
        registry=registry,
        source_capture=capture,
        assignment=assignment,
        intake_id="world-2000-01-source-intake",
    )

    intake_lib.validate_intake(
        intake=intake,
        registry=registry,
        source_capture=capture,
        assignment=assignment,
    )
    assert intake["carriers"] == [
        {
            "carrier_id": 1,
            "fixed_roster_slot_count": 3,
            "assignment": assignment["assignments"][0],
            "selected_source_player_count": 3,
            "source_capacity": "meets-fixed-carrier-capacity",
        },
        {
            "carrier_id": 2,
            "fixed_roster_slot_count": 3,
            "assignment": {"status": "unassigned"},
            "selected_source_player_count": 0,
            "source_capacity": "not-selected",
        },
    ]
    source_rows = intake["source_clubs"][0]["players"]
    assert len(source_rows) == 3
    assert source_rows[1]["facts"]["nationality"] is None
    assert source_rows[1]["facts"]["unresolved_fields"] == ["nationality"]
    assert len(source_rows[1]["source_row_sha256"]) == 64
    assert len(intake["source_clubs"]) == 2


def test_audit_reports_non_release_coverage_without_inventing_a_mapping() -> None:
    registry = _registry()
    capture = _capture()
    assignment = _candidate_assignment(registry=registry, capture=capture)
    intake = intake_lib.build_intake(
        registry=registry,
        source_capture=capture,
        assignment=assignment,
        intake_id="world-2000-01-source-intake",
    )

    audit = intake_lib.audit_intake(
        intake=intake,
        registry=registry,
        source_capture=capture,
        assignment=assignment,
    )

    assert audit["coverage"] == {
        "fixed_carrier_count": 2,
        "fixed_roster_slot_count": 6,
        "assignment_status_counts": {"candidate": 1, "unassigned": 1},
        "source_capacity_counts": {"meets-fixed-carrier-capacity": 1, "not-selected": 1},
        "source_club_count": 2,
        "source_player_row_count": 4,
        "source_player_rows_with_unresolved_facts": 1,
        "unresolved_fact_counts": {"nationality": 1},
        "selected_source_club_count": 1,
        "selected_source_player_row_count": 3,
        "selected_source_player_rows_with_unresolved_facts": 1,
        "selected_unresolved_fact_counts": {"nationality": 1},
    }
    assert {row["code"] for row in audit["blockers"]} == {
        "fixed-carrier-identities-not-approved",
        "dated-source-facts-unresolved",
        "captured-clubs-not-selected-for-fixed-carriers",
        "source-intake-is-not-a-package-or-database-build",
    }


def test_intake_rejects_a_mutation_to_source_or_assignment_bound_data() -> None:
    registry = _registry()
    capture = _capture()
    assignment = _candidate_assignment(registry=registry, capture=capture)
    intake = intake_lib.build_intake(
        registry=registry,
        source_capture=capture,
        assignment=assignment,
        intake_id="world-2000-01-source-intake",
    )

    altered_source = copy.deepcopy(intake)
    altered_source["source_clubs"][0]["players"][1]["facts"]["nationality"] = "ESP"
    with pytest.raises(intake_lib.SourceIntakeError, match="exactly match"):
        intake_lib.validate_intake(
            intake=altered_source,
            registry=registry,
            source_capture=capture,
            assignment=assignment,
        )

    altered_mapping = copy.deepcopy(intake)
    altered_mapping["carriers"][0]["assignment"]["status"] = "approved"
    with pytest.raises(intake_lib.SourceIntakeError, match="exactly match"):
        intake_lib.validate_intake(
            intake=altered_mapping,
            registry=registry,
            source_capture=capture,
            assignment=assignment,
        )


def test_intake_accepts_a_generic_merged_footballsquads_capture() -> None:
    split = _capture()
    split["source"]["revision"] = "d" * 40
    split["clubs"] = [split["clubs"][0]]
    calendar = _capture()
    calendar["source"]["revision"] = "d" * 40
    calendar["clubs"] = [calendar["clubs"][1]]
    merged = merge_captures(
        captures=[
            ("calendar.json", calendar, "e" * 64),
            ("split.json", split, "f" * 64),
        ]
    )
    registry = _registry()
    assignment = assignments.initialise_assignment(
        registry=registry,
        source_capture=merged,
        host_reports=[],
        assignment_id="world-merged-source",
    )
    assignment["assignments"] = [
        {
            "carrier_id": 1,
            "status": "candidate",
            "historical_club": {"identity_key": "historical-fc", "name": "Historical FC"},
            "source_selector": {
                "country_catalog": "spain",
                "competition_catalog": "laliga",
                "club_name": "Historical FC",
                "source_path": "spain/2000-2001/laliga/historical.txt",
                "source_sha256": SOURCE_A_HASH,
            },
            "blockers": ["requires-editorial-identity-review"],
        }
    ]

    intake = intake_lib.build_intake(
        registry=registry,
        source_capture=merged,
        assignment=assignment,
        intake_id="world-merged-source-intake",
    )

    intake_lib.validate_intake(
        intake=intake,
        registry=registry,
        source_capture=merged,
        assignment=assignment,
    )
    assert intake["source"] == merged["source"]
    assert intake["source"]["inputs"] == [
        {
            "capture_name": "calendar.json",
            "sha256": "e" * 64,
            "catalog": "2000-2001",
            "label": "2000/01",
        },
        {
            "capture_name": "split.json",
            "sha256": "f" * 64,
            "catalog": "2000-2001",
            "label": "2000/01",
        },
    ]
