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
from scripts import foreign_carrier_candidate_queue_v1 as queue_lib  # noqa: E402
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
            "baseline_club": {"name": "F.C. Barcelona", "full_name": "Barcelona", "ground_name": "Ground", "seated_capacity": 10000, "active_manager_carrier_id": 101},
            "roster_slots": [{"slot_index": index, "player_carrier_id": 1000 + index, "flag": 0, "family": "dd6360", "baseline_name": f"Player {index}"} for index in range(16)],
            "topology_policy": "preserve-existing-carrier-and-roster-slots",
        }],
        "known_baseline_duplicate_player_carriers": [],
    }


def _capture(player_count: int = 16) -> dict[str, object]:
    return {
        "schema_version": assignments.SOURCE_SCHEMA,
        "source": {"title": "Fixture", "repository": "https://example.invalid", "revision": None, "license": "CC0-1.0"},
        "season": {"catalog": "2015-2016", "label": "2015/16"},
        "clubs": [{
            "country_catalog": "spain", "competition_catalog": "laliga", "club_name": "Barcelona", "competition_name": "League", "source_path": "spain/2015-2016/laliga/barcelona.txt", "source_sha256": "b" * 64,
            "players": [{"name": f"Player {index}"} for index in range(player_count)],
        }],
        "summary": {"club_count": 1, "player_count": player_count, "player_rows_with_unresolved_facts": 0, "country_catalogs": ["spain"], "competition_catalogs": ["spain/laliga"]},
    }


def _assignment(registry: dict[str, object], capture: dict[str, object]) -> dict[str, object]:
    host_report = {
        "schema": assignments.HOST_REPORT_SCHEMA,
        "read_only": True,
        "capture_id": "spain-fixture",
        "base": {"eq98030_sha256": HASH},
        "accepted_host_mappings": [{"eq_record_id": 1, "host_country": "Spain", "evidence": {"sha256": "c" * 64}}],
    }
    return assignments.initialise_assignment(
        registry=registry,
        source_capture=capture,
        host_reports=[(host_report, hashlib.sha256(assignments.canonical_json_bytes(host_report)).hexdigest())],
        assignment_id="world-2015-16",
    )


def test_queue_is_candidate_only_and_handles_display_name_variation() -> None:
    registry = _registry()
    capture = _capture()
    queue = queue_lib.build_candidate_queue(registry=registry, source_capture=capture, assignment=_assignment(registry, capture))

    assert queue["coverage"]["candidate_state_counts"] == {"single-name-token-candidate": 1}
    row = queue["queue"][0]
    assert row["candidate_state"] == "single-name-token-candidate"
    assert row["assignment_state"] == "unassigned"
    assert row["candidates"][0]["source_selector"]["club_name"] == "Barcelona"
    assert row["candidates"][0]["match"]["baseline_tokens"] == ["barcelona"]
    assert "requires-editorial-carrier-identity-approval" in row["candidate_blockers"]
    queue_lib.validate_candidate_queue(queue=queue, registry=registry, source_capture=capture, assignment=_assignment(registry, capture))


def test_queue_keeps_short_roster_as_visible_non_approval_signal() -> None:
    registry = _registry()
    capture = _capture(player_count=15)
    queue = queue_lib.build_candidate_queue(registry=registry, source_capture=capture, assignment=_assignment(registry, capture))
    assert queue["queue"][0]["candidates"][0]["slot_capacity"] == "below-fixed-carrier-capacity"


def test_queue_rejects_any_stale_or_hand_edited_output() -> None:
    registry = _registry()
    capture = _capture()
    assignment = _assignment(registry, capture)
    queue = queue_lib.build_candidate_queue(registry=registry, source_capture=capture, assignment=assignment)
    changed = copy.deepcopy(queue)
    changed["queue"][0]["candidate_state"] = "approved"
    with pytest.raises(queue_lib.CandidateQueueError, match="does not exactly match"):
        queue_lib.validate_candidate_queue(queue=changed, registry=registry, source_capture=capture, assignment=assignment)
