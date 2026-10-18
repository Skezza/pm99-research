from __future__ import annotations

import copy
import shutil
from pathlib import Path

from scripts import season_package_compiler_v2 as compiler
from scripts import season_package_v2 as package_v2
from scripts.season_english_mode0_package_adapter_v1 import build_package
from scripts.test_season_package_compiler_v2 import (
    _indexed_fdi,
    _manager_payload,
    _native_package,
    _dd6361_player_payload,
    _synthetic_eq_decoded_payload,
)


def _foreign_shell() -> dict:
    package = copy.deepcopy(_native_package())
    package["package_id"] = "pm99-2015-16-empty-foreign-fixture"
    package["scope"] = {
        "id": "foreign-fixture",
        "title": "Synthetic empty foreign fragment",
        "countries": ["ESP"],
        "competition_policy": "existing-carriers-only",
    }
    package["clubs"] = []
    package["players"] = []
    package["managers"] = []
    package["assets"] = {"kits": [], "portraits": []}
    package_v2.validate_package(package, strict=True)
    return package


def _english_input(player_count: int = 17) -> dict:
    players = []
    for number in range(1, player_count + 1):
        players.append({
            "source_order": number,
            "opening_xi": number <= 11,
            "facts": {
                "name": f"English {chr(64 + number)}",
                "position": "G" if number == 1 else "D" if number <= 5 else "M" if number <= 9 else "F",
                "birth_date": "1990-01-01",
                "nationality": None,
                "height_cm": None,
                "weight_kg": None,
                "shirt_number": number,
            },
            "ratings": {field: 100 if field == "quality" else 60 for field in (
                "quality", "speed", "stamina", "aggression", "passing", "tackling",
                "heading", "shooting", "dribbling", "handling",
            )},
            "unresolved_secondary_facts": ["nationality", "height_cm", "weight_kg"],
            "portrait": {"status": "no-image"},
        })
    return {
        "schema_version": "pm99-english-mode0-compiler-input-v1",
        "season": "2015/16",
        "authoring_audit_sha256": "a" * 64,
        "binary_preflight": {"required": True, "source_files": [], "rules": []},
        "clubs": [{
            "carrier_id": 307,
            "club": "Fixture Town",
            "division": "Premier League",
            "manager": {"manager_name": "Fixture Manager", "source_url": "https://example.test/manager"},
            "kit": {"policy": "historical-target-season", "source_url": "https://example.test/kit"},
            "opening": {"fixture_date": "2015-08-08", "formation": "4-4-2", "source_url": "https://example.test/match"},
            "players": players,
        }],
    }


def _base_tree(tmp_path: Path) -> Path:
    base = tmp_path / "base"
    dbdat = base / "DBDAT"
    dbdat.mkdir(parents=True)
    dbdat.joinpath("JUG98030.FDI").write_bytes(_indexed_fdi([
        (carrier, "", _dd6361_player_payload(carrier)) for carrier in range(1, 17)
    ]))
    dbdat.joinpath("EQ98030.FDI").write_bytes(_indexed_fdi([
        (307, "", _synthetic_eq_decoded_payload())
    ]))
    second_manager = bytearray(_manager_payload())
    marker = second_manager.find(b"\xdd\x63\x60")
    second_manager[marker + 3 : marker + 5] = bytes([2 ^ 0x61, 0x61])
    dbdat.joinpath("ENT98030.FDI").write_bytes(_indexed_fdi([
        (1, "", _manager_payload()), (2, "", bytes(second_manager)),
    ]))
    dbdat.joinpath("TEXTOS.PKF").write_bytes(bytes(byte ^ 0x61 for byte in b"XXX,ALBANIA,ENGLAND,GERMANY,VANUATU"))
    return base


def test_adapter_is_deterministic_and_compiles_its_merged_package(tmp_path: Path) -> None:
    base = _base_tree(tmp_path)
    english = _english_input()
    foreign = _foreign_shell()
    dbdat = base / "DBDAT"
    kwargs = {
        "compiler_input": english,
        "foreign_package": foreign,
        "jug_data": dbdat.joinpath("JUG98030.FDI").read_bytes(),
        "eq_data": dbdat.joinpath("EQ98030.FDI").read_bytes(),
        "ent_data": dbdat.joinpath("ENT98030.FDI").read_bytes(),
        "package_id": "pm99-2015-16-merged-fixture",
    }
    package, receipt = build_package(**kwargs)
    assert (package, receipt) == build_package(**kwargs)
    assert receipt["reused_player_carriers"] == 16
    assert receipt["appended_player_carriers"] == [{"carrier_id": 17, "append_from_carrier_id": 1}]
    assert package["players"][0]["ratings"]["values"]["quality"] == 99
    assert package["players"][0]["fact_fallbacks"][0]["field"] == "height_cm"
    assert package["players"][0]["facts"]["nationality"] == "UNK"
    package_v2.validate_package(package, strict=True)

    package_path = tmp_path / "merged.json"
    package_v2.write_canonical_package(package_path, package)
    materialisation = tmp_path / "tree"
    shutil.copytree(base, materialisation)
    compiler_receipt = compiler.compile_package_to_tree(
        package_path=package_path,
        base_tree=base,
        materialisation_tree=materialisation,
    )
    assert compiler_receipt["clubs_written"] == 1
    assert compiler_receipt["players_written"] == 17
    assert compiler_receipt["appended_mode0_dd6361_carrier_ids"] == [17]
    assert base.joinpath("DBDAT/JUG98030.FDI").read_bytes() == kwargs["jug_data"]
