"""Tests for the preserve-only fixed-carrier world ledger."""

from __future__ import annotations

import hashlib
import importlib.util
import struct
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).with_name("fixed_carrier_world_ledger_v1.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("fixed_carrier_ledger_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _indexed_file(entries: list[tuple[int, bytes]]) -> bytes:
    directory_size = sum(4 + 1 + len(f"R{record_id}") + 8 for record_id, _ in entries)
    payload_start = 0x14 + directory_size
    directory, payloads = bytearray(), bytearray()
    for record_id, payload in entries:
        key = f"R{record_id}".encode("ascii")
        encoded = bytes(value ^ 0x61 for value in payload)
        directory.extend(struct.pack("<I", record_id))
        directory.extend((len(key),))
        directory.extend(key)
        directory.extend(struct.pack("<II", payload_start + len(payloads), len(encoded)))
        payloads.extend(encoded)
    return b"DMFIv1.0" + struct.pack("<III", 0, 0, len(entries)) + directory + payloads


def _package() -> dict:
    artifact_hash = "a" * 64
    proof = {"grade": "static-contract", "artifact_id": "receipt-contract"}
    players, portraits = [], []
    for carrier_id in range(1, 12):
        player_id = f"player-{carrier_id}"
        players.append({
            "id": player_id,
            "person_id": f"person-fixture-{carrier_id}",
            "carrier_id": carrier_id,
            "carrier_family": "dd6361",
            "club_id": "club-100",
            "name": f"Player {carrier_id}",
            "facts": {
                "birth_date": f"19{80 + carrier_id:02d}-01-01",
                "nationality": "ENG", "height_cm": 180, "weight_kg": 75,
                "primary_position": "G" if carrier_id == 1 else "M",
                "fine_roles": [0], "shirt_number": carrier_id,
            },
            "ratings": {
                "profile": "pm99-visible-skills-v1",
                "values": {key: 60 for key in (
                    "quality", "speed", "stamina", "aggression", "passing", "tackling",
                    "heading", "shooting", "dribbling", "handling",
                )},
                "provenance": {"method": "fixture", "proof_grade": "reviewed-editorial", "source_ids": ["source-ledger"]},
            },
            "proof": proof,
        })
        portraits.append({
            "player_id": player_id,
            "status": "native-no-photo" if carrier_id == 1 else "applied",
            **({"review_reason": "No safe period portrait found"} if carrier_id == 1 else {
                "original_artifact_id": "portrait-original", "crop_artifact_id": "portrait-crop",
                "conversion_receipt_artifact_id": "portrait-conversion", "output_container_artifact_id": "portrait-output",
            }),
            "proof": proof,
        })
    return {
        "schema_version": "pm99-season-package-v2",
        "package_id": "pm99-2015-16-fixture",
        "season": {"start_year": 2015, "end_year": 2016, "label": "2015/16"},
        "scope": {"id": "world-existing-carriers", "title": "Fixture", "countries": ["ENG"], "competition_policy": "existing-carriers-only"},
        "artifacts": sorted([
            {"id": "calendar-output", "kind": "calendar-patch", "sha256": artifact_hash},
            {"id": "kit-home", "kind": "kit-render", "sha256": artifact_hash},
            {"id": "receipt-contract", "kind": "season-input", "sha256": artifact_hash},
            {"id": "portrait-original", "kind": "portrait-original", "sha256": artifact_hash},
            {"id": "portrait-crop", "kind": "portrait-crop", "sha256": artifact_hash},
            {"id": "portrait-conversion", "kind": "portrait-conversion", "sha256": artifact_hash},
            {"id": "portrait-output", "kind": "database-output", "sha256": artifact_hash},
        ], key=lambda row: row["id"]),
        "sources": [{"id": "source-ledger", "title": "Captured fixture", "proof_grade": "source-captured", "evidence_artifact_id": "receipt-contract"}],
        "clubs": [{
            "id": "club-100", "identity_id": "club-fixture-town", "carrier_id": 100,
            "name": "Fixture Town", "division": "Fixed carrier", "manager_id": "manager-1",
            "roster_player_ids": [f"player-{number}" for number in range(1, 12)],
            "opening": {
                "fixture_date": "2015-08-08", "starting_xi_player_ids": [f"player-{number}" for number in range(1, 12)],
                "substitute_player_ids": [], "formation": "4-4-2",
                "tactics_positions": [[128, 55, 128, 55] for _ in range(11)], "proof": proof,
            }, "proof": proof,
        }],
        "players": sorted(players, key=lambda row: row["id"]),
        "managers": [{"id": "manager-1", "person_id": "person-manager", "carrier_id": 1, "name": "Fixture Manager", "proof": proof}],
        "assets": {"kits": [{"club_id": "club-100", "artifact_ids": ["kit-home"], "proof": proof}], "portraits": sorted(portraits, key=lambda row: row["player_id"])},
        "calendar": {"base_year": 1998, "target_year": 2015, "target_rollover_year": 2016, "patch_artifact_id": "calendar-output", "proof": proof},
        "proofs": [{"id": "proof-static", "grade": "static-contract", "artifact_id": "receipt-contract", "covers": ["fixture"]}],
        "migration": {"status": "native-v2", "source_artifact_ids": ["receipt-contract"], "known_gaps": []},
    }


def _ledger(module, package_path: Path, base_eq: Path) -> dict:
    lock = module.inspect_base_eq(base_eq)
    return {
        "schema_version": "pm99-fixed-carrier-world-ledger-v1",
        "ledger_id": "world-2015-16-fixture-carriers",
        "package_sha256": hashlib.sha256(package_path.read_bytes()).hexdigest(),
        "season_label": "2015/16",
        "topology_lock": lock,
        "sources": [{
            "id": "club-identity-source", "title": "Captured club source",
            "evidence_sha256": "b" * 64, "package_source_ids": ["source-ledger"],
        }],
        "carrier_assignments": [{
            "club_id": "club-100", "carrier_id": 100, "carrier_ordinal": 0,
            "identity_source_ids": ["club-identity-source"],
        }],
        "portrait_policy": {"on_unavailable": "native-no-photo", "on_unsafe_conversion": "native-no-photo", "emit_review_queue": True},
    }


def test_valid_fixed_carrier_ledger_emits_nonblocking_native_no_photo_queue(tmp_path: Path) -> None:
    module = _load_module()
    package_path, base_eq = tmp_path / "season.json", tmp_path / "EQ98030.FDI"
    module.write_canonical_package(package_path, _package())
    base_eq.write_bytes(_indexed_file([(100, b"club fixture"), (200, b"unassigned")]))
    ledger_path = tmp_path / "carriers.json"
    module.write_canonical_ledger(ledger_path, _ledger(module, package_path, base_eq))

    report = module.validate_ledger(
        module.read_canonical_ledger(ledger_path), module.read_canonical_package(package_path),
        package_path=package_path, base_eq=base_eq,
    )

    assert report["release_blocking"] is False
    assert report["counts"] == {"applied": 10, "native-no-photo": 1, "unresolved": 0}
    assert report["review_queue"] == [{
        "player_id": "player-1", "carrier_id": 1, "club_id": "club-100", "player_name": "Player 1",
        "portrait_status": "native-no-photo", "review_reason": "No safe period portrait found",
        "required_materialisation": "remove inherited carrier photo; use PM99 native no-photo state",
    }]


def test_ledger_rejects_wrong_carrier_ordinal_and_carrier_move(tmp_path: Path) -> None:
    module = _load_module()
    package_path, base_eq = tmp_path / "season.json", tmp_path / "EQ98030.FDI"
    module.write_canonical_package(package_path, _package())
    base_eq.write_bytes(_indexed_file([(100, b"club fixture")]))
    ledger = _ledger(module, package_path, base_eq)
    ledger["carrier_assignments"][0]["carrier_ordinal"] = 1
    with pytest.raises(module.LedgerValidationError, match="carrier_ordinal"):
        module.validate_ledger(ledger, module.read_canonical_package(package_path), package_path=package_path, base_eq=base_eq)

    ledger = _ledger(module, package_path, base_eq)
    ledger["carrier_assignments"][0]["carrier_id"] = 200
    with pytest.raises(module.LedgerValidationError, match="cannot move a club"):
        module.validate_ledger(ledger, module.read_canonical_package(package_path), package_path=package_path, base_eq=base_eq)


def test_output_audit_refuses_an_unassigned_eq_payload_change(tmp_path: Path) -> None:
    module = _load_module()
    package_path, base_eq, output_eq = tmp_path / "season.json", tmp_path / "EQ98030.FDI", tmp_path / "out.FDI"
    module.write_canonical_package(package_path, _package())
    base_eq.write_bytes(_indexed_file([(100, b"club fixture"), (200, b"unassigned")]))
    ledger = _ledger(module, package_path, base_eq)
    package = module.read_canonical_package(package_path)
    module.validate_ledger(ledger, package, package_path=package_path, base_eq=base_eq)

    output_eq.write_bytes(_indexed_file([(100, b"club changed"), (200, b"unassigned")]))
    passed = module.audit_output_eq(ledger, base_eq, output_eq)
    assert passed["result"] == "passed"
    assert passed["changed_carrier_ids"] == [100]

    output_eq.write_bytes(_indexed_file([(100, b"club changed"), (200, b"bad change")]))
    rejected = module.audit_output_eq(ledger, base_eq, output_eq)
    assert rejected["result"] == "failed"
    assert rejected["forbidden_changed_carrier_ids"] == [200]
