from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import season_calendar_package_overlay_v1 as calendar_overlay
from scripts import season_canonical_promotion_factory_v1 as factory
from scripts import season_package_v2 as package_v2
from scripts import season_pipeline_v2 as pipeline_v2
from scripts import test_season_package_v2 as fixtures


def _verified_base() -> dict:
    return {
        "schema": "pm99-verified-base-v2",
        "base_id": "pm99-fixture-clean",
        "inventory": {
            "schema": "pm99-file-inventory-v2",
            "files": [],
            "file_count": 0,
            "total_bytes": 0,
            "files_fingerprint": hashlib.sha256(b"[]").hexdigest(),
        },
    }


def _bound_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    package = fixtures._valid_package()
    second_club = copy.deepcopy(package["clubs"][0])
    second_club.update({
        "id": "club-101",
        "identity_id": "club-fixture-borough",
        "carrier_id": 101,
        "name": "Fixture Borough",
        "manager_id": "manager-2",
        "roster_player_ids": [f"player-{number}" for number in range(13, 24)],
    })
    second_club["opening"]["starting_xi_player_ids"] = list(second_club["roster_player_ids"])
    second_manager = copy.deepcopy(package["managers"][0])
    second_manager.update({
        "id": "manager-2",
        "person_id": "person-fixture-manager-2",
        "carrier_id": 2,
        "name": "Fixture Borough Manager",
    })
    for carrier_id in range(13, 24):
        player = copy.deepcopy(package["players"][carrier_id - 13])
        player.update({
            "id": f"player-{carrier_id}",
            "person_id": f"person-fixture-player-{carrier_id}",
            "carrier_id": carrier_id,
            "club_id": "club-101",
            "name": f"Player {carrier_id}",
        })
        player["facts"]["shirt_number"] = carrier_id
        package["players"].append(player)
        portrait = copy.deepcopy(package["assets"]["portraits"][carrier_id - 13])
        portrait["player_id"] = player["id"]
        package["assets"]["portraits"].append(portrait)
    second_kit = copy.deepcopy(package["assets"]["kits"][0])
    second_kit["club_id"] = "club-101"
    package["clubs"].append(second_club)
    package["managers"].append(second_manager)
    package["assets"]["kits"].append(second_kit)
    package["clubs"].sort(key=lambda row: row["id"])
    package["players"].sort(key=lambda row: row["id"])
    package["managers"].sort(key=lambda row: row["id"])
    package["assets"]["kits"].sort(key=lambda row: row["club_id"])
    package["assets"]["portraits"].sort(key=lambda row: row["player_id"])
    receipt = {
        "schema_version": "pm99-calendar-patch-v1", "base_year": 1998,
        "target_year": 2015, "target_rollover_year": 2016,
        "patch_count": 853, "after_sha256": "b" * 64,
        "source_operand_counts": {"1998": 50, "1999": 803},
    }
    bound, audit = calendar_overlay.bind_calendar(
        package=package, receipt=receipt, receipt_relative_path="calendar-receipt.json",
        receipt_sha256="a" * 64, executable_sha256="b" * 64,
    )
    package_path = tmp_path / "bound.json"
    package_v2.write_canonical_package(package_path, bound)
    audit["output_package_sha256"] = package_v2.sha256_file(package_path)
    audit_path = tmp_path / "calendar-audit.json"
    audit_path.write_bytes(package_v2.canonical_json_bytes(audit))
    base_path = tmp_path / "base.json"
    base_path.write_bytes(package_v2.canonical_json_bytes(_verified_base()))
    return package_path, audit_path, base_path


def _alias_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    package_path, calendar_audit_path, base_path = _bound_fixture(tmp_path)
    source = json.loads(package_path.read_text(encoding="utf-8"))
    alias = copy.deepcopy(source)
    source_player = source["players"][0]
    alias_player = alias["players"][0]
    alias_player["name"] = "Alias"
    alias_path = tmp_path / "alias.json"
    package_v2.write_canonical_package(alias_path, alias)
    alias_audit = {
        "schema_version": "pm99-season-package-display-alias-repair-v1",
        "state": "alias-bound-static-candidate-only",
        "season": alias["season"],
        "release_eligible": False,
        "input": {
            "package_sha256": package_v2.sha256_file(package_path),
            "base_inventory_fingerprint": _verified_base()["inventory"]["files_fingerprint"],
            "calendar_contract_sha256": hashlib.sha256(
                package_v2.canonical_json_bytes(source["calendar"])
            ).hexdigest(),
        },
        "calendar_contract_preserved": True,
        "changed_players": [{
            "player_id": source_player["id"],
            "person_id": source_player["person_id"],
            "carrier_id": source_player["carrier_id"],
            "source_name": source_player.get("source_name", source_player["name"]),
            "previous_display_name": source_player["name"],
            "display_name": alias_player["name"],
            "method": "source-derived-surname",
        }],
        "coverage": {"changed_display_name_count": 1},
        "output": {"package_sha256": package_v2.sha256_file(alias_path)},
    }
    alias_audit_path = tmp_path / "alias-audit.json"
    alias_audit_path.write_bytes(package_v2.canonical_json_bytes(alias_audit))
    return package_path, calendar_audit_path, base_path, alias_path, alias_audit_path


def _alias_roster_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path, Path, Path]:
    package_path, calendar_audit_path, base_path, alias_path, alias_audit_path = _alias_fixture(tmp_path)
    alias = json.loads(alias_path.read_text(encoding="utf-8"))
    preserved = copy.deepcopy(alias["players"][0])
    preserved.update({
        "id": "player-12",
        "person_id": "person-12",
        "carrier_id": 12,
        "carrier_family": "dd6360",
        "name": "Preserved Player",
        "policy": "preserve-existing-mode1",
        "facts": {
            key: {"policy": "preserve-existing-mode1"}
            for key in preserved["facts"]
        },
    })
    preserved["ratings"]["provenance"] = {
        "method": "preserved-baseline-readback",
        "proof_grade": "static-contract",
        "source_ids": ["source-ledger"],
    }
    alias["players"].append(preserved)
    alias["players"].sort(key=lambda row: row["id"])
    alias["clubs"][0]["roster_player_ids"].append("player-12")
    alias["assets"]["portraits"].append({
        "player_id": "player-12",
        "status": "unresolved",
        "proof": {"grade": "static-contract", "artifact_id": "receipt-contract"},
        "review_reason": "restored fixed base roster row is whole-record preserve-only; no dated portrait claim",
    })
    alias["assets"]["portraits"].sort(key=lambda row: row["player_id"])
    roster_path = tmp_path / "roster.json"
    package_v2.write_canonical_package(roster_path, alias)
    roster_audit = {
        "schema_version": "pm99-mode1-roster-base-reconciliation-v1",
        "state": "base-roster-reconciled-static-candidate-only",
        "season": alias["season"],
        "release_eligible": False,
        "input": {
            "package_sha256": package_v2.sha256_file(alias_path),
            "verified_base_sha256": package_v2.sha256_file(base_path),
            "base_inventory_fingerprint": _verified_base()["inventory"]["files_fingerprint"],
            "base_eq98030_sha256": "c" * 64,
            "base_jug98030_sha256": "d" * 64,
        },
        "reconciliation": {
            "club_carrier_id": 100,
            "club_id": "club-100",
            "base_roster_player_carrier_ids": list(range(1, 13)),
            "input_roster_player_carrier_ids": list(range(1, 12)),
            "output_roster_player_carrier_ids": list(range(1, 13)),
            "restored_players": [{
                "player_id": "player-12",
                "carrier_id": 12,
                "person_id": "person-12",
                "name": "Preserved Player",
                "payload_sha256": "e" * 64,
                "whole_record_policy": "preserve-existing-mode1",
                "portrait_status": "unresolved",
            }],
        },
        "output": {"package_sha256": package_v2.sha256_file(roster_path)},
    }
    roster_audit_path = tmp_path / "roster-audit.json"
    roster_audit_path.write_bytes(package_v2.canonical_json_bytes(roster_audit))
    return (
        package_path, calendar_audit_path, base_path, alias_path, alias_audit_path,
        roster_path, roster_audit_path,
    )


def _alias_roster_chain_fixture(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path, Path, Path, Path, Path, Path]:
    (
        package_path, calendar_audit_path, base_path, alias_path, alias_audit_path,
        roster_path, roster_audit_path,
    ) = _alias_roster_fixture(tmp_path)
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    preserved = copy.deepcopy(next(row for row in roster["players"] if row["id"] == "player-13"))
    preserved.update({
        "id": "player-24",
        "person_id": "person-24",
        "carrier_id": 24,
        "carrier_family": "dd6360",
        "name": "Second Preserved Player",
        "policy": "preserve-existing-mode1",
        "facts": {
            key: {"policy": "preserve-existing-mode1"}
            for key in preserved["facts"]
        },
    })
    preserved["ratings"]["provenance"] = {
        "method": "preserved-baseline-readback",
        "proof_grade": "static-contract",
        "source_ids": ["source-ledger"],
    }
    roster["players"].append(preserved)
    roster["players"].sort(key=lambda row: row["id"])
    second_club = next(row for row in roster["clubs"] if row["id"] == "club-101")
    second_club["roster_player_ids"].append("player-24")
    roster["assets"]["portraits"].append({
        "player_id": "player-24",
        "status": "unresolved",
        "proof": {"grade": "static-contract", "artifact_id": "receipt-contract"},
        "review_reason": "restored fixed base roster row is whole-record preserve-only; no dated portrait claim",
    })
    roster["assets"]["portraits"].sort(key=lambda row: row["player_id"])
    chain_path = tmp_path / "roster-chain.json"
    package_v2.write_canonical_package(chain_path, roster)
    chain_audit = {
        "schema_version": "pm99-mode1-roster-base-reconciliation-v1",
        "state": "base-roster-reconciled-static-candidate-only",
        "season": roster["season"],
        "release_eligible": False,
        "input": {
            "package_sha256": package_v2.sha256_file(roster_path),
            "verified_base_sha256": package_v2.sha256_file(base_path),
            "base_inventory_fingerprint": _verified_base()["inventory"]["files_fingerprint"],
            "base_eq98030_sha256": "c" * 64,
            "base_jug98030_sha256": "d" * 64,
        },
        "reconciliation": {
            "club_carrier_id": 101,
            "club_id": "club-101",
            "base_roster_player_carrier_ids": list(range(13, 25)),
            "input_roster_player_carrier_ids": list(range(13, 24)),
            "output_roster_player_carrier_ids": list(range(13, 25)),
            "restored_players": [{
                "player_id": "player-24",
                "carrier_id": 24,
                "person_id": "person-24",
                "name": "Second Preserved Player",
                "payload_sha256": "f" * 64,
                "whole_record_policy": "preserve-existing-mode1",
                "portrait_status": "unresolved",
            }],
        },
        "output": {"package_sha256": package_v2.sha256_file(chain_path)},
    }
    chain_audit_path = tmp_path / "roster-chain-audit.json"
    chain_audit_path.write_bytes(package_v2.canonical_json_bytes(chain_audit))
    return (
        package_path, calendar_audit_path, base_path, alias_path, alias_audit_path,
        roster_path, roster_audit_path, chain_path, chain_audit_path,
    )


def test_creates_valid_workspace_candidate_but_never_a_release(tmp_path: Path) -> None:
    package_path, audit_path, base_path = _bound_fixture(tmp_path)
    output_dir = tmp_path / "candidate"
    result = factory.create_candidate(
        package_path=package_path, calendar_audit_path=audit_path,
        base_descriptor_path=base_path, output_dir=output_dir,
    )
    assert result["state"] == "canonical-workspace-candidate-only"
    assert result["release_eligible"] is False
    assert package_v2.sha256_file(output_dir / "season-package.candidate.json") == package_v2.sha256_file(package_path)
    workspace = json.loads((output_dir / "workspace.json").read_text(encoding="utf-8"))
    assert workspace["season"] == "2015-16"
    assert result["static_contracts"] == {
        "calendar_binding": "passed", "season_package_v2_strict": "passed",
        "verified_base_descriptor": "passed", "workspace_contract": "passed",
        "workspace_prepare": "passed",
    }
    plan = json.loads((output_dir / "build-plan.candidate.json").read_text(encoding="utf-8"))
    assert plan["state"] == "blocked-before-binary-compile"
    assert plan["target_build_plan_schema"] == "pm99-season-build-plan-v2"


def test_rejects_calendar_audit_for_another_package(tmp_path: Path) -> None:
    package_path, audit_path, base_path = _bound_fixture(tmp_path)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit["output_package_sha256"] = "c" * 64
    audit_path.write_bytes(package_v2.canonical_json_bytes(audit))
    with pytest.raises(factory.PromotionFactoryError, match="exact package byte stream"):
        factory.create_candidate(
            package_path=package_path, calendar_audit_path=audit_path,
            base_descriptor_path=base_path, output_dir=tmp_path / "candidate",
        )
    assert not (tmp_path / "candidate").exists()


def test_accepts_source_build_audit_only_when_it_preserves_the_full_calendar_chain(tmp_path: Path) -> None:
    package_path, overlay_path, base_path = _bound_fixture(tmp_path)
    package = json.loads(package_path.read_text(encoding="utf-8"))
    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    artifact = next(row for row in package["artifacts"] if row["id"] == package["calendar"]["patch_artifact_id"])
    source_build_audit = {
        "schema_version": "pm99-season-source-package-build-audit-v1",
        "draft_package_sha256": package_v2.sha256_file(package_path),
        "calendar_binding": {
            "audit_sha256": hashlib.sha256(package_v2.canonical_json_bytes(overlay)).hexdigest(),
            "template_package_sha256": overlay["output_package_sha256"],
            "receipt_sha256": overlay["receipt_sha256"],
            "executable_sha256": overlay["executable_sha256"],
            "patch_count": overlay["patch_count"],
            "runtime_validation_pending": True,
            "overlay_audit": overlay,
            "calendar": package["calendar"],
            "artifact": artifact,
        },
    }
    source_audit_path = tmp_path / "source-build-audit.json"
    source_audit_path.write_bytes(package_v2.canonical_json_bytes(source_build_audit))

    result = factory.create_candidate(
        package_path=package_path, calendar_audit_path=source_audit_path,
        base_descriptor_path=base_path, output_dir=tmp_path / "candidate",
    )

    assert result["calendar"]["calendar_binding_path"] == "source-build-preserved-overlay"


def test_creates_alias_bound_candidate_only_from_an_exact_display_only_receipt(tmp_path: Path) -> None:
    package_path, calendar_audit_path, base_path, alias_path, alias_audit_path = _alias_fixture(tmp_path)

    result = factory.create_alias_bound_candidate(
        source_package_path=package_path, alias_package_path=alias_path,
        alias_audit_path=alias_audit_path, calendar_audit_path=calendar_audit_path,
        base_descriptor_path=base_path, output_dir=tmp_path / "candidate",
    )

    assert result["state"] == "canonical-workspace-candidate-only"
    assert result["release_eligible"] is False
    assert result["static_contracts"]["display_alias_binding"] == "passed"
    assert result["input"]["calendar_bound_package_sha256"] == package_v2.sha256_file(package_path)
    assert result["input"]["display_alias_binding"]["alias_package_sha256"] == package_v2.sha256_file(alias_path)
    assert package_v2.sha256_file(tmp_path / "candidate" / "season-package.candidate.json") == package_v2.sha256_file(alias_path)
    workspace = json.loads((tmp_path / "candidate" / "workspace.json").read_text(encoding="utf-8"))
    assert workspace["workspace_id"] == "world-2015-16-alias-bound-canonical-candidate"


def test_rejects_alias_audit_that_does_not_describe_the_package_diff(tmp_path: Path) -> None:
    package_path, calendar_audit_path, base_path, alias_path, alias_audit_path = _alias_fixture(tmp_path)
    alias_audit = json.loads(alias_audit_path.read_text(encoding="utf-8"))
    alias_audit["changed_players"][0]["display_name"] = "Incorrect"
    alias_audit_path.write_bytes(package_v2.canonical_json_bytes(alias_audit))

    with pytest.raises(factory.PromotionFactoryError, match="exactly describe package name changes"):
        factory.create_alias_bound_candidate(
            source_package_path=package_path, alias_package_path=alias_path,
            alias_audit_path=alias_audit_path, calendar_audit_path=calendar_audit_path,
            base_descriptor_path=base_path, output_dir=tmp_path / "candidate",
        )
    assert not (tmp_path / "candidate").exists()


def test_creates_alias_and_mode1_roster_bound_candidate_only_from_exact_receipts(tmp_path: Path) -> None:
    (
        package_path, calendar_audit_path, base_path, alias_path, alias_audit_path,
        roster_path, roster_audit_path,
    ) = _alias_roster_fixture(tmp_path)

    result = factory.create_alias_roster_bound_candidate(
        source_package_path=package_path, alias_package_path=alias_path,
        alias_audit_path=alias_audit_path, roster_package_path=roster_path,
        roster_audit_path=roster_audit_path, calendar_audit_path=calendar_audit_path,
        base_descriptor_path=base_path, output_dir=tmp_path / "candidate",
    )

    assert result["state"] == "canonical-workspace-candidate-only"
    assert result["release_eligible"] is False
    assert result["static_contracts"]["display_alias_binding"] == "passed"
    assert result["static_contracts"]["mode1_roster_reconciliation_binding"] == "passed"
    assert result["input"]["mode1_roster_reconciliation_binding"]["restored_player_count"] == 1
    assert package_v2.sha256_file(tmp_path / "candidate" / "season-package.candidate.json") == package_v2.sha256_file(roster_path)
    workspace = json.loads((tmp_path / "candidate" / "workspace.json").read_text(encoding="utf-8"))
    assert workspace["workspace_id"] == "world-2015-16-alias-roster-bound-canonical-candidate"


def test_rejects_mode1_roster_audit_that_does_not_describe_the_package_diff(tmp_path: Path) -> None:
    (
        package_path, calendar_audit_path, base_path, alias_path, alias_audit_path,
        roster_path, roster_audit_path,
    ) = _alias_roster_fixture(tmp_path)
    roster_audit = json.loads(roster_audit_path.read_text(encoding="utf-8"))
    roster_audit["reconciliation"]["restored_players"][0]["name"] = "Wrong player"
    roster_audit_path.write_bytes(package_v2.canonical_json_bytes(roster_audit))

    with pytest.raises(factory.PromotionFactoryError, match="does not exactly describe a preserved player"):
        factory.create_alias_roster_bound_candidate(
            source_package_path=package_path, alias_package_path=alias_path,
            alias_audit_path=alias_audit_path, roster_package_path=roster_path,
            roster_audit_path=roster_audit_path, calendar_audit_path=calendar_audit_path,
            base_descriptor_path=base_path, output_dir=tmp_path / "candidate",
        )
    assert not (tmp_path / "candidate").exists()


def test_creates_candidate_from_an_ordered_chain_of_mode1_roster_repairs(tmp_path: Path) -> None:
    (
        package_path, calendar_audit_path, base_path, alias_path, alias_audit_path,
        roster_path, roster_audit_path, chain_path, chain_audit_path,
    ) = _alias_roster_chain_fixture(tmp_path)

    result = factory.create_alias_roster_chain_bound_candidate(
        source_package_path=package_path,
        alias_package_path=alias_path,
        alias_audit_path=alias_audit_path,
        roster_package_paths=[roster_path, chain_path],
        roster_audit_paths=[roster_audit_path, chain_audit_path],
        calendar_audit_path=calendar_audit_path,
        base_descriptor_path=base_path,
        output_dir=tmp_path / "candidate",
    )

    bindings = result["input"]["mode1_roster_reconciliation_bindings"]
    assert result["static_contracts"]["mode1_roster_reconciliation_bindings"] == "passed"
    assert [binding["restored_club_carrier_id"] for binding in bindings] == [100, 101]
    assert bindings[1]["source_package_sha256"] == package_v2.sha256_file(roster_path)
    assert bindings[1]["roster_package_sha256"] == package_v2.sha256_file(chain_path)
    assert package_v2.sha256_file(tmp_path / "candidate" / "season-package.candidate.json") == package_v2.sha256_file(chain_path)
