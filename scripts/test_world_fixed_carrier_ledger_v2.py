"""Deterministic tests for the fixed-carrier world authoring ledger.

The fixtures are metadata-only.  They do not include a PM99 database or any
proprietary player, club, image or source material.
"""

from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import world_fixed_carrier_ledger_v2 as ledger  # noqa: E402


HASH = "a" * 64


def _slot(slot_index: int, player_carrier_id: int) -> dict[str, object]:
    return {
        "slot_index": slot_index,
        "player_carrier_id": player_carrier_id,
        "flag": slot_index % 2,
        "family": "dd6360",
        "baseline_name": f"Baseline {player_carrier_id}",
    }


def _carrier(carrier_id: int, manager_id: int, player_start: int) -> dict[str, object]:
    return {
        "carrier_id": carrier_id,
        "record_mode": 1,
        "baseline_club": {
            "name": f"Baseline {carrier_id}",
            "full_name": f"Baseline {carrier_id} FC",
            "ground_name": f"Ground {carrier_id}",
            "seated_capacity": 10_000,
            "active_manager_carrier_id": manager_id,
        },
        "roster_slots": [_slot(index, player_start + index) for index in range(16)],
        "topology_policy": "preserve-existing-carrier-and-roster-slots",
    }


def _registry() -> dict[str, object]:
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
        "carriers": [_carrier(1, 101, 1001), _carrier(2, 102, 2001)],
        "known_baseline_duplicate_player_carriers": [],
    }


def _sources() -> list[dict[str, str]]:
    return [
        {"id": "club-source", "title": "Club source", "kind": "club", "content_sha256": HASH},
        {"id": "kit-source", "title": "Kit source", "kind": "kit", "content_sha256": HASH},
        {"id": "manager-source", "title": "Manager source", "kind": "manager", "content_sha256": HASH},
        {"id": "player-source", "title": "Player source", "kind": "player", "content_sha256": HASH},
        {"id": "portrait-source", "title": "Portrait source", "kind": "portrait", "content_sha256": HASH},
    ]


def _player(slot: dict[str, object], *, person_id: str | None = None) -> dict[str, object]:
    carrier = int(slot["player_carrier_id"])
    return {
        "slot_index": int(slot["slot_index"]),
        "player_carrier_id": carrier,
        "person_id": person_id or f"player-{carrier}",
        "name": f"Historical Player {carrier}",
        "facts": {
            "birth_date": "1990-01-01",
            "nationality": "ENG",
            "height_cm": 180,
            "weight_kg": 75,
            "primary_position": "D",
            "fine_roles": [0],
            "shirt_number": 2,
        },
        "ratings": {
            "quality": 60,
            "speed": 60,
            "stamina": 60,
            "aggression": 60,
            "passing": 60,
            "tackling": 60,
            "heading": 60,
            "shooting": 60,
            "dribbling": 60,
            "handling": 10,
        },
        "source_ids": ["player-source"],
        "portrait": {"status": "applied", "source_ids": ["portrait-source"]},
    }


def _complete_update(registry_carrier: dict[str, object]) -> dict[str, object]:
    carrier_id = int(registry_carrier["carrier_id"])
    return {
        "carrier_id": carrier_id,
        "status": "complete",
        "club": {
            "identity_key": f"club-{carrier_id}",
            "name": f"Historical Club {carrier_id}",
            "full_name": f"Historical Club {carrier_id} FC",
            "ground_name": f"Historical Ground {carrier_id}",
            "seated_capacity": 20_000,
            "source_ids": ["club-source"],
        },
        "manager": {
            "carrier_id": registry_carrier["baseline_club"]["active_manager_carrier_id"],
            "person_id": f"manager-{carrier_id}",
            "name": f"Historical Manager {carrier_id}",
            "source_ids": ["manager-source"],
        },
        "kit": {"status": "applied", "source_ids": ["kit-source"]},
        "players": [_player(slot) for slot in registry_carrier["roster_slots"]],
        "blockers": [],
    }


def test_initialised_ledger_is_hash_locked_and_reports_all_unassigned() -> None:
    registry = _registry()
    ledger.validate_registry(registry)
    source = ledger.initialise_ledger(registry=registry, ledger_id="world-2015-16", start_year=2015)
    ledger.validate_ledger(registry=registry, ledger=source)
    report = ledger.audit_ledger(registry=registry, ledger=source)
    assert source["registry_sha256"] == hashlib.sha256(ledger.canonical_json_bytes(registry)).hexdigest()
    assert report["coverage"] == {
        "foreign_carrier_total": 2,
        "carrier_status_counts": {"unassigned": 2},
        "complete_player_slot_count": 0,
        "kit_status_counts": {},
        "portrait_status_counts": {},
    }
    assert {row["code"] for row in report["blockers"]} == {"world-content-incomplete"}
    assert report["scope_exclusions"][0]["code"] == "foreign-topology-preserved"


def test_complete_carrier_requires_every_slot_sources_and_a_portrait_decision() -> None:
    registry = _registry()
    source = ledger.initialise_ledger(registry=registry, ledger_id="world-2015-16", start_year=2015)
    source["sources"] = _sources()
    update = _complete_update(registry["carriers"][0])
    update["players"][0]["portrait"] = {
        "status": "native-no-photo",
        "reason": "No era-correct source image found after review.",
    }
    source["carrier_updates"] = [update]
    ledger.validate_ledger(registry=registry, ledger=source)
    report = ledger.audit_ledger(registry=registry, ledger=source)
    assert report["coverage"]["carrier_status_counts"] == {"complete": 1, "unassigned": 1}
    assert report["coverage"]["complete_player_slot_count"] == 16
    assert report["coverage"]["kit_status_counts"] == {"applied": 1}
    assert report["coverage"]["portrait_status_counts"] == {"applied": 15, "native-no-photo": 1}

    bad = copy.deepcopy(source)
    bad["carrier_updates"][0]["players"] = bad["carrier_updates"][0]["players"][:-1]
    with pytest.raises(ledger.WorldLedgerError, match="every existing roster slot"):
        ledger.validate_ledger(registry=registry, ledger=bad)

    bad = copy.deepcopy(source)
    bad["carrier_updates"][0]["players"][0]["portrait"] = {"status": "unresolved"}
    with pytest.raises(ledger.WorldLedgerError, match="cannot leave a portrait unresolved"):
        ledger.validate_ledger(registry=registry, ledger=bad)


def test_complete_carrier_accepts_a_2000s_birth_date() -> None:
    registry = _registry()
    source = ledger.initialise_ledger(registry=registry, ledger_id="world-2017-18", start_year=2017)
    source["sources"] = _sources()
    update = _complete_update(registry["carriers"][0])
    update["players"][0]["facts"]["birth_date"] = "2000-07-12"
    source["carrier_updates"] = [update]

    ledger.validate_ledger(registry=registry, ledger=source)

    bad = copy.deepcopy(source)
    bad["carrier_updates"][0]["kit"] = {"status": "unresolved", "reason": "No era-correct source kit found."}
    with pytest.raises(ledger.WorldLedgerError, match="cannot leave a kit unresolved"):
        ledger.validate_ledger(registry=registry, ledger=bad)


def test_fixed_slots_and_person_identity_cannot_be_silently_reused() -> None:
    registry = _registry()
    source = ledger.initialise_ledger(registry=registry, ledger_id="world-2015-16", start_year=2015)
    source["sources"] = _sources()
    first = _complete_update(registry["carriers"][0])
    second = _complete_update(registry["carriers"][1])
    second["players"][0]["person_id"] = first["players"][0]["person_id"]
    source["carrier_updates"] = [first, second]
    with pytest.raises(ledger.WorldLedgerError, match="assigned to different JUG carriers"):
        ledger.validate_ledger(registry=registry, ledger=source)

    bad = copy.deepcopy(source)
    bad["carrier_updates"] = [first]
    bad["carrier_updates"][0]["players"][0]["player_carrier_id"] = 999_999
    with pytest.raises(ledger.WorldLedgerError, match="changes a fixed player carrier or order"):
        ledger.validate_ledger(registry=registry, ledger=bad)

    bad = copy.deepcopy(source)
    bad["carrier_updates"] = [first]
    bad["carrier_updates"][0]["membership"] = "invented league"
    with pytest.raises(ledger.WorldLedgerError, match="unsupported fields"):
        ledger.validate_ledger(registry=registry, ledger=bad)


def test_canonical_read_write_round_trip_rejects_noncanonical_json(tmp_path: Path) -> None:
    registry = _registry()
    source = ledger.initialise_ledger(registry=registry, ledger_id="world-2015-16", start_year=2015)
    path = tmp_path / "ledger.json"
    ledger.write_canonical_json(path, source)
    loaded, digest = ledger.read_canonical_json(path, label="test ledger")
    assert loaded == source
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    path.write_text('{ "ledger_id": "world-2015-16" }\n', encoding="utf-8")
    with pytest.raises(ledger.WorldLedgerError, match="canonical JSON"):
        ledger.read_canonical_json(path, label="test ledger")
