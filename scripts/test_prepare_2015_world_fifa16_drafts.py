from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import prepare_2015_world_fifa16_drafts as drafts  # noqa: E402
from scripts import world_fixed_carrier_ledger_v2 as ledger  # noqa: E402


HASH = "a" * 64


def _registry() -> dict[str, object]:
    carrier = {
        "carrier_id": 1,
        "record_mode": 1,
        "baseline_club": {
            "name": "FC Example",
            "full_name": "FC Example",
            "ground_name": "Example Ground",
            "seated_capacity": 10_000,
            "active_manager_carrier_id": 101,
        },
        "roster_slots": [
            {
                "slot_index": index,
                "player_carrier_id": 1000 + index,
                "flag": 0,
                "family": "dd6360",
                "baseline_name": f"Baseline {index}",
            }
            for index in range(16)
        ],
        "topology_policy": "preserve-existing-carrier-and-roster-slots",
    }
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
        "carriers": [carrier],
        "known_baseline_duplicate_player_carriers": [],
    }


def _row(index: int, *, nationality: str = "England") -> dict[str, str]:
    return {
        "player_id": str(90_000 + index),
        "name": f"Example Player {index}",
        "club": "FC Example",
        "nationality": nationality,
        "height": "180",
        "weight": "75",
        "birthdate": "1990-01-01",
        "rating": "70",
        "sprint_speed": "70",
        "stamina": "70",
        "aggression": "70",
        "short_pass": "70",
        "stand_tackle": "70",
        "heading": "70",
        "finishing": "70",
        "dribbling": "70",
        "gk_handling": "10",
        "preferred_positions": "CM",
        "club_kit_number": str(index + 1),
    }


def test_prefill_creates_blocked_rows_that_remain_valid_v2_ledgers() -> None:
    registry = _registry()
    base = ledger.initialise_ledger(registry=registry, ledger_id="world-2015-16", start_year=2015)
    output, report = drafts.build_prefilled_ledger(
        registry=registry,
        base_ledger=base,
        fifa_rows=[_row(index) for index in range(16)],
        fifa_sha256=HASH,
    )
    ledger.validate_ledger(registry=registry, ledger=output)
    assert report["coverage"] == {
        "foreign_carrier_count": 1,
        "strict_current_club_candidate_carrier_count": 1,
        "blocked_prefilled_carrier_count": 1,
        "blocked_prefilled_player_slot_count": 16,
        "skipped_carrier_count": 0,
        "unsupported_pm99_nationality_row_count": 0,
    }
    update = output["carrier_updates"][0]
    assert update["status"] == "blocked"
    assert update["club"]["ground_name"] == "Unresolved 2015 ground"
    assert update["kit"]["status"] == "unresolved"
    assert update["players"][0]["portrait"]["status"] == "unresolved"
    assert update["players"][0]["facts"]["nationality"] == "ENG"
    assert "foreign-competition-membership-preserve-only" in update["blockers"]


def test_prefill_reports_unsupported_nationality_without_inventing_a_country() -> None:
    registry = _registry()
    base = ledger.initialise_ledger(registry=registry, ledger_id="world-2015-16", start_year=2015)
    rows = [_row(index, nationality="Atlantis") for index in range(16)]
    output, report = drafts.build_prefilled_ledger(
        registry=registry, base_ledger=base, fifa_rows=rows, fifa_sha256=HASH
    )
    assert output["carrier_updates"][0]["players"][0]["facts"]["nationality"] == "XXX"
    assert report["coverage"]["unsupported_pm99_nationality_row_count"] == 16
    assert report["unsupported_pm99_nationality_rows"][0]["fifa_nationality"] == "Atlantis"


def test_prefill_refuses_to_merge_an_existing_reviewed_ledger() -> None:
    registry = _registry()
    base = ledger.initialise_ledger(registry=registry, ledger_id="world-2015-16", start_year=2015)
    occupied = copy.deepcopy(base)
    occupied["sources"] = [{"id": "other", "title": "Other", "kind": "other", "content_sha256": HASH}]
    with __import__("pytest").raises(drafts.FIFA16DraftError, match="empty, hash-locked"):
        drafts.build_prefilled_ledger(
            registry=registry, base_ledger=occupied, fifa_rows=[_row(index) for index in range(16)], fifa_sha256=HASH
        )


def test_canonical_output_is_stable() -> None:
    registry = _registry()
    base = ledger.initialise_ledger(registry=registry, ledger_id="world-2015-16", start_year=2015)
    one, report_one = drafts.build_prefilled_ledger(
        registry=registry, base_ledger=base, fifa_rows=[_row(index) for index in range(16)], fifa_sha256=HASH
    )
    two, report_two = drafts.build_prefilled_ledger(
        registry=registry, base_ledger=base, fifa_rows=[_row(index) for index in range(16)], fifa_sha256=HASH
    )
    assert drafts.canonical_json_bytes(one) == drafts.canonical_json_bytes(two)
    assert hashlib.sha256(drafts.canonical_json_bytes(report_one)).hexdigest() == hashlib.sha256(
        drafts.canonical_json_bytes(report_two)
    ).hexdigest()
