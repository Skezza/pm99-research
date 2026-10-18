"""Synthetic integration tests for the native PM99 Season Package V2 compiler.

The fixtures below are deliberately constructed DMFI/PM99-shaped byte streams.
They are not copied game data and contain no proprietary database records.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.fdi_indexed import IndexedFDIFile
from app.models import PlayerRecord
from app.xor import xor_decode, xor_encode
from scripts import season_package_compiler_v2 as compiler
from scripts import season_package_v2 as package_v2
from scripts import season_pipeline_buildplan_v2 as buildplan
from scripts import season_pipeline_v2 as pipeline
from scripts import season_review_v2 as review_v2
from scripts import probe_dd6360_native_metadata as native_metadata_probe
from scripts import probe_mode1_dd6361_core as dd6361_core_probe


HASH = "a" * 64
FORBIDDEN_RUNTIME_DIRS = [
    "CACHE", "RUNTIME", "SAVE", "SAVEGAME", "SAVEGAMES", "SAVES", "TEMP", "TMP"
]


def test_startup_order_follows_opening_selection_not_roster_storage_order():
    package = {"clubs": [{"id": "club", "roster_player_ids": ["reserve", "outfield", "keeper"],
                         "opening": {"starting_xi_player_ids": ["keeper", "outfield"],
                                     "substitute_player_ids": []}}],
               "players": [{"id": p} for p in ["reserve", "outfield", "keeper"]]}
    assert compiler._club_player_orders(package) == {"keeper": 1, "outfield": 2, "reserve": 3}
    package["clubs"][0]["opening"]["substitute_player_ids"] = ["reserve"]
    assert compiler._club_player_orders(package)["reserve"] == 3
    package["clubs"][0]["opening"]["substitute_player_ids"] = ["keeper"]
    with pytest.raises(compiler.SeasonCompilerError, match="invalid opening selection"):
        compiler._club_player_orders(package)


def _indexed_fdi(records: list[tuple[int, str, bytes]]) -> bytes:
    """Build a minimal indexed FDI container from synthetic decoded records."""

    header = bytearray(b"DMFIv1.0")
    header.extend(struct.pack("<I", 0))
    header.extend(struct.pack("<I", 0))
    header.extend(struct.pack("<I", len(records)))
    encoded = [xor_encode(payload) for _record_id, _key, payload in records]
    offset = len(header) + sum(4 + 1 + len(key.encode("cp1252")) + 8 for _id, key, _payload in records)
    directory = bytearray()
    for (record_id, key, _payload), blob in zip(records, encoded, strict=True):
        key_bytes = key.encode("cp1252")
        directory.extend(struct.pack("<I", record_id))
        directory.append(len(key_bytes))
        directory.extend(key_bytes)
        directory.extend(struct.pack("<I", offset))
        directory.extend(struct.pack("<I", len(blob)))
        offset += len(blob)
    return bytes(header + directory + b"".join(encoded))


def _dd6361_player_payload(index: int, *, role: int = 0) -> bytes:
    """Create a safe variable-name dd6361 payload with a visible-skill tail."""

    surname = f"CARRIER{chr(65 + index)}"
    display = f"John {surname}"
    prefix = (
        bytes([len(surname) ^ 0x61, 0x61])
        + surname.encode("cp1252")
        + bytes([len(display) ^ 0x61, 0x61])
        + display.encode("cp1252")
    )
    year = struct.pack("<H", 1990)
    native_identity = bytes(value ^ 0x61 for value in struct.pack("<H", index)) + b"a"
    payload = bytearray(struct.pack("<H", 42) + b"\xdd\x63\x61" + native_identity + prefix)
    anchor = len(payload)
    payload.extend(b"\x60" * 18)
    # This is the same parser-backed indexed suffix arrangement used by the
    # editor's variable-name writer tests.
    fields = [10, 0, 13, 9, 16, 8, 0, 0, 30, 1, 5, 2, 16, 11, year[0], year[1], 170, 68]
    for offset, value in enumerate(fields):
        payload[anchor + offset] = value ^ 0x61
    for slot in range(6):
        payload[anchor + 2 + slot] = (role + 1 if slot == 0 else 0) ^ 0x61
    while len(payload) < 116:
        payload.append(0x60)
    for offset in range(12):
        payload[116 - 19 + offset] = 50 ^ 0x61
    return bytes(payload)


def _dd6360_player_payload(index: int, *, role_code: int = 0) -> bytes:
    """Build a foreign-safe compact player fixture with a native role stream."""

    name = f"Carrier {chr(64 + index)}"
    given, surname = name.split(" ", 1)
    display = f"{given} {surname.upper()}"
    prefix = (
        bytes([len(surname) ^ 0x61, 0x61])
        + surname.encode("cp1252")
        + bytes([len(display) ^ 0x61, 0x61])
        + display.encode("cp1252")
    )
    native_identity = bytes(value ^ 0x61 for value in struct.pack("<H", index)) + b"a"
    payload = bytearray(struct.pack("<H", 42) + b"\xdd\x63\x60" + native_identity + prefix)
    role = (role_code + 1) ^ 0x61
    # Actual loader consumes one byte, skips one, then reads six roles.
    payload.extend(bytes([0x61, 0x61, role, 0x61, 0x61, 0x61, 0x61, 0x61]))
    fields = [
        10,  # nationality
        77,  # preserve-only control byte
        1, 1,  # parser and visible broad position: defender
        1, 1, 1990 & 0xFF, 1990 >> 8,
        180, 75,
        *[40 for _ in range(9)],
    ]
    payload.extend(bytes(value ^ 0x61 for value in fields))
    payload.extend(b"\x60" * 80)
    return bytes(payload)


def test_mode1_position_plan_accepts_a_new_broad_position_and_role_candidates() -> None:
    """Foreign compact writes retain both opaque controls around six roles."""

    payload = bytearray(_dd6360_player_payload(1))
    role_start = compiler._native_dd6360_role_start(payload)
    payload[role_start + 10] = 3 ^ 0x61  # baseline parser byte differs from visible defender byte
    start, position, roles = compiler._plan_mode1_dd6360_player_fields(
        decoded=bytes(payload),
        facts={"fine_roles": [0], "primary_position": "M", "shirt_number": 0},
        player_id="fixture-player",
    )
    assert start == role_start
    assert position == 2
    assert roles == [0]


def test_mode1_position_plan_accepts_a_tactical_role_rewrite() -> None:
    payload = _dd6360_player_payload(1)
    _start, _position, roles = compiler._plan_mode1_dd6360_player_fields(
        decoded=payload,
        facts={"fine_roles": [9, 4], "primary_position": "M", "shirt_number": 0},
        player_id="fixture-player",
    )
    assert roles == [9, 4]


def test_mode1_core_guard_rejects_an_unknown_baseline_role_byte() -> None:
    """A legacy compact fine-role code remains preserve-only."""

    payload = bytearray(_dd6360_player_payload(1))
    role_start = compiler._native_dd6360_role_start(payload)
    payload[role_start + 2] = 25 ^ 0x61  # stored first-role value 24
    with pytest.raises(compiler.SeasonCompilerError, match="preserve-only legacy fine-role"):
        compiler._plan_mode1_dd6360_player_fields(
            decoded=bytes(payload),
            facts={"fine_roles": [4], "primary_position": "D", "shirt_number": 0},
            player_id="fixture-player",
        )


def test_dd6360_metadata_probe_changes_only_the_first_real_fine_role_slot(tmp_path: Path) -> None:
    source = tmp_path / "JUG98030.FDI"
    destination = tmp_path / "JUG98030.probe.FDI"
    source.write_bytes(_indexed_fdi([(1, "", _dd6360_player_payload(1))]))

    receipt = native_metadata_probe.patch(
        source,
        destination,
        record_id=1,
        updates={},
        skills=None,
        role=9,
        position=None,
    )

    before_entry = IndexedFDIFile.from_bytes(source.read_bytes()).entries[0]
    after_file = destination.read_bytes()
    after_entry = IndexedFDIFile.from_bytes(after_file).entries[0]
    before = before_entry.decode_payload(source.read_bytes())
    after = after_entry.decode_payload(after_file)
    role_start = compiler._native_dd6360_role_start(after)
    before_fields = compiler._read_native_dd6360_fields(before, compiler._native_dd6360_role_start(before))
    after_fields = compiler._read_native_dd6360_fields(after, role_start)

    assert after_fields["fine_role_codes"] == [9, *before_fields["fine_role_codes"][1:]]
    assert after[role_start] == before[compiler._native_dd6360_role_start(before)]
    assert after[role_start + 1] == before[compiler._native_dd6360_role_start(before) + 1]
    assert receipt["requested_fine_role_slot_0"] == 9
    assert receipt["changed_payload_offsets"] == [role_start + 2]


def test_dd6360_metadata_probe_writes_only_the_native_handling_byte(tmp_path: Path) -> None:
    source = tmp_path / "JUG98030.FDI"
    destination = tmp_path / "JUG98030.handling.FDI"
    source.write_bytes(_indexed_fdi([(1, "", _dd6360_player_payload(1))]))

    receipt = native_metadata_probe.patch(
        source,
        destination,
        record_id=1,
        updates={},
        skills=None,
        role=None,
        position=None,
        handling=72,
    )

    before_file = source.read_bytes()
    after_file = destination.read_bytes()
    before_entry = IndexedFDIFile.from_bytes(before_file).entries[0]
    after_entry = IndexedFDIFile.from_bytes(after_file).entries[0]
    before = before_entry.decode_payload(before_file)
    after = after_entry.decode_payload(after_file)
    role_start = compiler._native_dd6360_role_start(after)
    assert compiler._read_native_dd6360_fields(after, role_start)["handling"] == 72
    assert compiler._read_native_dd6360_fields(after, role_start)["skills"] == compiler._read_native_dd6360_fields(before, compiler._native_dd6360_role_start(before))["skills"]
    assert receipt["changed_payload_offsets"] == [role_start + 27]
    assert receipt["unchanged_elsewhere"] is True


def test_mode1_dd6361_core_probe_preserves_role_window_and_index_preamble(tmp_path: Path) -> None:
    source = tmp_path / "JUG98030.FDI"
    destination = tmp_path / "JUG98030.probe.FDI"
    payload = bytearray(_dd6361_player_payload(1, role=4))
    payload[:2] = b"\x57\x61"
    source.write_bytes(_indexed_fdi([(10958, "", bytes(payload))]))

    receipt = dd6361_core_probe.patch(
        source,
        destination,
        record_id=10958,
        nationality=22,
        birth_day=2,
        birth_month=8,
        birth_year=1980,
        height=190,
        weight=80,
        position=3,
        skills=[99] * 9,
    )

    before_entry = IndexedFDIFile.from_bytes(source.read_bytes()).entries[0]
    after_file = destination.read_bytes()
    after_entry = IndexedFDIFile.from_bytes(after_file).entries[0]
    before = before_entry.decode_payload(source.read_bytes())
    after = after_entry.decode_payload(after_file)
    assert after[:2] == before[:2] == b"\x57\x61"
    assert receipt["fine_role_bytes_preserved"] is True
    assert receipt["after"]["position"] == 3
    assert receipt["after"]["nationality"] == 22
    assert receipt["after"]["attributes"][3:12] == [99] * 9


def _raw_inline_string(text: str) -> bytes:
    value = text.encode("cp1252")
    return len(value).to_bytes(2, "little") + bytes(byte ^ 0x61 for byte in value)


def _synthetic_eq_decoded_payload(player_start: int = 1) -> bytes:
    """Build a parser-backed large mode-0 EQ raw record, then outer-decode it."""

    raw = bytearray(b"\x00" * 0x2A)
    raw[0x24:0x26] = (100).to_bytes(2, "little")
    raw[0x26:0x28] = (700).to_bytes(2, "little")
    raw[0x29] = 0
    raw.extend(_raw_inline_string("Old Town"))
    raw.extend(_raw_inline_string("Old Ground"))
    raw.extend(b"\x00\x00")  # ordinary and extended metadata header bytes
    raw.extend(_raw_inline_string("Old Town FC"))
    raw.extend((10_000).to_bytes(4, "little", signed=True))
    raw.extend((0).to_bytes(4, "little", signed=True))
    raw.extend(b"\x00" * 6)
    raw.extend(b"\x00" * 2)  # record_size > 0x207 extra scalar pair
    raw.extend((10_000).to_bytes(4, "little"))
    raw.extend(_raw_inline_string("Chair"))
    raw.extend((1_000).to_bytes(4, "little"))
    raw.extend((1_000).to_bytes(4, "little"))
    raw.extend(_raw_inline_string("Sponsor"))
    raw.extend(_raw_inline_string("Supplier"))
    raw.extend(b"\x00" * (3 + 20 + 15 + 46))
    raw.extend(b"\x00")  # sparse count
    raw.extend(b"\x00" * 0x6E7)
    raw.extend(bytes([1]) + (1).to_bytes(4, "little"))  # existing active manager link
    raw.extend(bytes([16]))
    for player_id in range(player_start, player_start + 16):
        raw.extend(bytes([0]) + player_id.to_bytes(4, "little"))
    return xor_decode(bytes(raw))


def _synthetic_mode1_eq_decoded_payload(player_start: int = 1, *, roster_count: int = 16) -> bytes:
    """Build a parser-backed mode-1 carrier with a terminal fixed roster."""

    raw = bytearray(b"\x00" * 0x2A)
    raw[0x24:0x26] = (100).to_bytes(2, "little")
    raw[0x26:0x28] = (700).to_bytes(2, "little")
    raw[0x29] = 1
    raw.extend(_raw_inline_string("Old World"))
    raw.extend(_raw_inline_string("Old World Ground"))
    raw.extend(b"\x00\x00")
    raw.extend(_raw_inline_string("Old World Club"))
    raw.extend((30_000).to_bytes(4, "little", signed=True))
    raw.extend((0).to_bytes(4, "little", signed=True))
    raw.extend(b"\x00" * 6)
    raw.extend(b"\x00" * 0x6E7)
    raw.extend(bytes([1]) + (1).to_bytes(4, "little"))
    raw.extend(bytes([roster_count]))
    for player_id in range(player_start, player_start + roster_count):
        raw.extend(bytes([player_id % 2]) + player_id.to_bytes(4, "little"))
    return xor_decode(bytes(raw))


def _manager_payload() -> bytes:
    name = b"Old Manager"
    xor_length = lambda value: bytes([value ^ 0x61, 0x61])
    return xor_length(len(name) + 1) + b"\xdd\x63\x60" + bytes([1 ^ 0x61, 0x61]) + xor_length(len(name)) + name


def _proof() -> dict[str, str]:
    return {"grade": "static-contract", "artifact_id": "receipt-contract"}


def _native_package() -> dict[str, object]:
    players: list[dict[str, object]] = []
    portraits: list[dict[str, object]] = []
    for carrier in range(1, 17):
        player_id = f"player-{carrier:02d}"
        players.append({
            "id": player_id,
            "person_id": f"person-fixture-player-{carrier}",
            "carrier_id": carrier,
            "carrier_family": "dd6361",
            "club_id": "club-307",
            "name": f"Target {chr(64 + carrier)}",
            "facts": {
                "birth_date": "1990-01-01",
                "nationality": "ENG",
                "height_cm": 180,
                "weight_kg": 75,
                "primary_position": "G" if carrier == 1 else "M",
                "fine_roles": [0],
                "shirt_number": carrier,
            },
            "ratings": {
                "profile": "pm99-visible-skills-v1",
                "values": {field: 60 for field in (
                    "quality", "speed", "stamina", "aggression", "passing", "tackling",
                    "heading", "shooting", "dribbling", "handling",
                )},
                "provenance": {
                    "method": "synthetic reviewed editorial fixture",
                    "proof_grade": "reviewed-editorial",
                    "source_ids": ["source-ledger"],
                },
            },
            "proof": _proof(),
        })
        portraits.append({"player_id": player_id, "status": "native-no-photo", "proof": _proof()})
    return {
        "schema_version": "pm99-season-package-v2",
        "package_id": "pm99-2015-16-compiler-fixture",
        "season": {"start_year": 2015, "end_year": 2016, "label": "2015/16"},
        "scope": {
            "id": "english-four-divisions",
            "title": "Synthetic compiler fixture",
            "countries": ["ENG"],
            "competition_policy": "proven-membership-only",
        },
        "artifacts": [
            {"id": "calendar-output", "kind": "calendar-patch", "sha256": HASH},
            {"id": "kit-home", "kind": "kit-render", "sha256": HASH},
            {"id": "receipt-contract", "kind": "season-input", "sha256": HASH},
        ],
        "sources": [{
            "id": "source-ledger",
            "title": "Synthetic player ledger",
            "proof_grade": "source-captured",
            "evidence_artifact_id": "receipt-contract",
        }],
        "clubs": [{
            "id": "club-307",
            "identity_id": "club-fixture-town",
            "carrier_id": 307,
            "name": "Fixture Town",
            "full_name": "Fixture Town FC",
            "division": "Premier League",
            "ground_name": "Fixture Ground",
            "seated_capacity": 12_345,
            "starting_finance": 20_000_000,
            "manager_id": "manager-1",
            "roster_player_ids": [player["id"] for player in players],
            "opening": {
                "fixture_date": "2015-08-08",
                "starting_xi_player_ids": [player["id"] for player in players[:11]],
                "substitute_player_ids": [player["id"] for player in players[11:16]],
                "formation": "4-4-2",
                "tactics_positions": [[128, 55, 128, 55] for _ in range(11)],
                "proof": _proof(),
            },
            "proof": _proof(),
        }],
        "players": players,
        "managers": [{"id": "manager-1", "person_id": "person-fixture-manager", "carrier_id": 1, "name": "Fixture Manager", "proof": _proof()}],
        "assets": {
            "kits": [{"club_id": "club-307", "artifact_ids": ["kit-home"], "proof": _proof()}],
            "portraits": portraits,
        },
        "calendar": {
            "base_year": 1998,
            "target_year": 2015,
            "target_rollover_year": 2016,
            "patch_artifact_id": "calendar-output",
            "proof": _proof(),
        },
        "proofs": [{"id": "proof-static", "grade": "static-contract", "artifact_id": "receipt-contract", "covers": ["fixture"]}],
        "migration": {"status": "native-v2", "source_artifact_ids": ["receipt-contract"], "known_gaps": []},
    }


def _native_mode1_package() -> dict[str, object]:
    """A strict package that may use only the fixed mode-1 carrier lanes."""

    package = _native_package()
    package["package_id"] = "pm99-2015-16-mode1-compiler-fixture"
    package["scope"] = {
        "id": "existing-world-carriers",
        "title": "Synthetic fixed foreign carrier fixture",
        "countries": ["ENG"],
        "competition_policy": "existing-carriers-only",
    }
    club = package["clubs"][0]
    club["id"] = "club-308"
    club["carrier_id"] = 308
    club["name"] = "World Fixture"
    club["full_name"] = "World Fixture Club"
    club["ground_name"] = "World Fixture Ground"
    club.pop("starting_finance")
    for player in package["players"]:
        player["carrier_family"] = "dd6360"
        player["club_id"] = "club-308"
        player["facts"] = {
            **player["facts"],
            "primary_position": "D",
            "fine_roles": [0],
            "shirt_number": 0,
        }
    package["assets"]["kits"][0]["club_id"] = "club-308"
    return package


def _write_fixture_base(tmp_path: Path) -> tuple[Path, Path]:
    base = tmp_path / "base"
    dbdat = base / "DBDAT"
    dbdat.mkdir(parents=True)
    dbdat.joinpath("JUG98030.FDI").write_bytes(
        _indexed_fdi([(carrier, "", _dd6361_player_payload(carrier)) for carrier in range(1, 17)])
    )
    dbdat.joinpath("EQ98030.FDI").write_bytes(_indexed_fdi([(307, "", _synthetic_eq_decoded_payload())]))
    dbdat.joinpath("ENT98030.FDI").write_bytes(_indexed_fdi([(1, "", _manager_payload())]))
    # Commas deliberately separate the parser's country names.
    dbdat.joinpath("TEXTOS.PKF").write_bytes(
        bytes(byte ^ 0x61 for byte in b"XXX,ALBANIA,ENGLAND,GERMANY,VANUATU")
    )
    package_path = tmp_path / "season-package.json"
    package_v2.write_canonical_package(package_path, _native_package())
    return base, package_path


def _write_mode1_fixture_base(tmp_path: Path, *, roster_count: int = 16) -> tuple[Path, Path]:
    base = tmp_path / "mode1-base"
    dbdat = base / "DBDAT"
    dbdat.mkdir(parents=True)
    dbdat.joinpath("JUG98030.FDI").write_bytes(
        _indexed_fdi([(carrier, "", _dd6360_player_payload(carrier)) for carrier in range(1, roster_count + 1)])
    )
    dbdat.joinpath("EQ98030.FDI").write_bytes(_indexed_fdi([
        (308, "", _synthetic_mode1_eq_decoded_payload(roster_count=roster_count))
    ]))
    dbdat.joinpath("ENT98030.FDI").write_bytes(_indexed_fdi([(1, "", _manager_payload())]))
    dbdat.joinpath("TEXTOS.PKF").write_bytes(
        bytes(byte ^ 0x61 for byte in b"XXX,ALBANIA,ENGLAND,GERMANY,VANUATU")
    )
    package_path = tmp_path / "mode1-season-package.json"
    package = _native_mode1_package()
    package["players"] = package["players"][:roster_count]
    package["clubs"][0]["roster_player_ids"] = [player["id"] for player in package["players"]]
    package["clubs"][0]["opening"]["starting_xi_player_ids"] = package["clubs"][0]["roster_player_ids"][:11]
    package["clubs"][0]["opening"]["substitute_player_ids"] = package["clubs"][0]["roster_player_ids"][11:]
    package["assets"]["portraits"] = package["assets"]["portraits"][:roster_count]
    package_v2.write_canonical_package(package_path, package)
    return base, package_path


def _write_mode1_recycle_fixture_base(tmp_path: Path) -> tuple[Path, Path]:
    """Make a complete synthetic mode-0/mode-1 transaction fixture."""

    base = tmp_path / "mode1-recycle-base"
    dbdat = base / "DBDAT"
    dbdat.mkdir(parents=True)
    dbdat.joinpath("JUG98030.FDI").write_bytes(_indexed_fdi(
        [(carrier, "", _dd6360_player_payload(carrier, role_code=0)) for carrier in range(1, 17)]
        + [(carrier, "", _dd6361_player_payload(carrier, role=0)) for carrier in range(101, 117)]
    ))
    dbdat.joinpath("EQ98030.FDI").write_bytes(_indexed_fdi([
        (307, "", _synthetic_eq_decoded_payload(101)),
        (308, "", _synthetic_mode1_eq_decoded_payload(1)),
    ]))
    dbdat.joinpath("ENT98030.FDI").write_bytes(_indexed_fdi([(1, "", _manager_payload())]))
    dbdat.joinpath("TEXTOS.PKF").write_bytes(
        bytes(byte ^ 0x61 for byte in b"XXX,ALBANIA,ENGLAND,GERMANY,VANUATU")
    )

    package = _native_package()
    package["package_id"] = "pm99-2015-16-mode1-recycle-fixture"
    original_club = package["clubs"][0]
    original_club["id"] = "club-307"
    original_club["carrier_id"] = 307
    original_club["name"] = "Mode Zero"
    original_club["full_name"] = "Mode Zero FC"
    original_club["ground_name"] = "Mode Zero Ground"
    original_players = package["players"]
    for offset, player in enumerate(original_players):
        source_carrier = 101 + offset
        player["carrier_id"] = 201 if offset == 0 else source_carrier
        player["carrier_family"] = "dd6361"
        player["club_id"] = "club-307"
        player["facts"] = {**player["facts"], "primary_position": "G", "fine_roles": [0]}
        if offset == 0:
            player["append_from_carrier_id"] = source_carrier
    original_club["roster_player_ids"] = [player["id"] for player in original_players]
    original_club["opening"]["starting_xi_player_ids"] = original_club["roster_player_ids"][:11]
    original_club["opening"]["substitute_player_ids"] = original_club["roster_player_ids"][11:]

    foreign_players: list[dict[str, object]] = []
    for carrier in list(range(2, 17)) + [101]:
        player_id = f"foreign-{carrier:03d}"
        foreign = {
            **original_players[0],
            "id": player_id,
            "person_id": f"person-{player_id}",
            "carrier_id": carrier,
            "carrier_family": "dd6360",
            "club_id": "club-308",
            "name": "R G" if carrier == 101 else f"F{carrier}",
            "facts": {
                **original_players[0]["facts"],
                "primary_position": "G",
                "fine_roles": [0],
                "shirt_number": 0,
            },
        }
        foreign.pop("append_from_carrier_id", None)
        if carrier == 101:
            foreign["recycle_from_mode1_carrier_id"] = 1
        foreign_players.append(foreign)
    foreign_players.sort(key=lambda row: str(row["id"]))
    foreign_roster = [f"foreign-{carrier:03d}" for carrier in [101] + list(range(2, 17))]
    foreign_club = {
        **original_club,
        "id": "club-308",
        "identity_id": "club-fixture-world",
        "carrier_id": 308,
        "name": "Mode One",
        "full_name": "Mode One FC",
        "ground_name": "Mode One Ground",
        "roster_player_ids": foreign_roster,
        "opening": {
            **original_club["opening"],
            "starting_xi_player_ids": foreign_roster[:11],
            "substitute_player_ids": foreign_roster[11:],
        },
    }
    foreign_club.pop("starting_finance")
    package["clubs"] = [original_club, foreign_club]
    package["players"] = sorted(original_players + foreign_players, key=lambda row: str(row["id"]))
    package["assets"]["kits"] = [
        {"club_id": "club-307", "artifact_ids": ["kit-home"], "proof": _proof()},
        {"club_id": "club-308", "artifact_ids": ["kit-home"], "proof": _proof()},
    ]
    package["assets"]["portraits"] = [
        {"player_id": player["id"], "status": "native-no-photo", "proof": _proof()}
        for player in package["players"]
    ]
    package_path = tmp_path / "mode1-recycle-package.json"
    package_v2.write_canonical_package(package_path, package)
    return base, package_path


def _copy_base(base: Path, destination: Path) -> Path:
    shutil.copytree(base, destination, copy_function=shutil.copyfile)
    return destination


def _payload(path: Path, record_id: int) -> bytes:
    data = path.read_bytes()
    entry = next(item for item in IndexedFDIFile.from_bytes(data).entries if item.record_id == record_id)
    return entry.decode_payload(data)


def _canonical_review_overlay(package_path: Path) -> dict[str, object]:
    package_hash = hashlib.sha256(package_path.read_bytes()).hexdigest()
    return {
        "schema_version": review_v2.OVERRIDES_SCHEMA,
        "override_id": "review-speed-and-portrait",
        "base_package_canonical_sha256": package_hash,
        "artifacts": [],
        "sources": [],
        "proofs": [],
        "data_patches": [{
            "id": "player-01-speed",
            "target": {"entity": "player", "id": "player-01"},
            "expected": {"ratings.values.speed": 60},
            "set": {"ratings.values.speed": 99},
            "reason": "First-fixture playtest found the speed rating too low.",
            "proof": _proof(),
            "rating_provenance": {
                "method": "synthetic gameplay review correction",
                "proof_grade": "static-contract",
                "source_ids": ["source-ledger"],
            },
        }],
        "portrait_patches": [{
            "id": "player-01-no-photo",
            "player_id": "player-01",
            "expected_status": "native-no-photo",
            "action": "set-native-no-photo",
            "reason": "No era-correct source image has been approved yet.",
            "proof": _proof(),
        }],
    }


def test_native_compiler_uses_only_v2_package_and_keeps_base_immutable(tmp_path: Path) -> None:
    base, package_path = _write_fixture_base(tmp_path)
    before = pipeline.build_tree_inventory(base)
    output = _copy_base(base, tmp_path / "materialised")

    receipt = compiler.compile_package_to_tree(
        package_path=package_path,
        base_tree=base,
        materialisation_tree=output,
    )

    assert pipeline.build_tree_inventory(base) == before
    assert receipt["clubs_written"] == 1
    assert receipt["players_written"] == 16
    assert receipt["managers_written"] == 1
    assert receipt["dd6361_visible_handling"]["requested_player_count"] == 16
    assert receipt["portraits"] == {
        "compiler_action": "preserved-for-separate-portrait-stage",
        "native_no_photo_player_ids": [f"player-{carrier:02d}" for carrier in range(1, 17)],
    }
    player = _payload(output / "DBDAT" / "JUG98030.FDI", 1)
    assert player[-16] ^ 0x61 == 60  # speed, the first proven native skill
    assert player[-7] ^ 0x61 == 60  # dd6361's separately proven Handling tail
    team_raw = (output / "DBDAT" / "EQ98030.FDI").read_bytes()
    entry = IndexedFDIFile.from_bytes(team_raw).entries[0]
    from app.eq_jug_linked import parse_eq_external_team_roster_payload
    roster = parse_eq_external_team_roster_payload(team_raw[entry.payload_offset : entry.payload_offset + entry.payload_length], {})
    assert roster is not None
    assert [row.player_record_id for row in roster.rows] == list(range(1, 17))


@pytest.mark.parametrize('birthday', ['2000-07-12', '2004-02-29', '1990-01-01'])
def test_mode0_dd6361_authors_the_literal_year_not_the_carrier_year(tmp_path: Path, birthday: str) -> None:
    base, package_path = _write_fixture_base(tmp_path)
    package = json.loads(package_path.read_text())
    package['players'][0]['facts']['birth_date'] = birthday
    package_path.write_bytes(package_v2.canonical_json_bytes(package))
    output = _copy_base(base, tmp_path / 'materialised')
    compiler.compile_package_to_tree(package_path=package_path, base_tree=base, materialisation_tree=output)
    from scripts.audit_compiled_player_birth_dates_v1 import inspect
    result = inspect(package, (output / 'DBDAT/JUG98030.FDI').read_bytes())
    assert result['failure_count'] == 0


def test_native_compiler_appends_an_explicit_mode0_dd6361_carrier_without_touching_mode1_tail(tmp_path: Path) -> None:
    """The 25-player route appends a new English carrier; it never borrows one.

    The synthetic foreign EQ carrier exists solely to prove that adding a new
    JUG directory row and rebuilding a selected mode-0 roster leaves every
    unrelated mode-1 count/flag/JUG tail byte-for-byte unchanged.
    """

    base, package_path = _write_fixture_base(tmp_path)
    eq_data = _indexed_fdi([
        (307, "", _synthetic_eq_decoded_payload()),
        (308, "", _synthetic_mode1_eq_decoded_payload(17)),
    ])
    base.joinpath("DBDAT", "EQ98030.FDI").write_bytes(eq_data)
    package = package_v2.read_canonical_package(package_path)
    package["players"][0]["carrier_id"] = 33
    package["players"][0]["append_from_carrier_id"] = 1
    appended_package = tmp_path / "append-season-package.json"
    package_v2.write_canonical_package(appended_package, package)
    output = _copy_base(base, tmp_path / "append-materialised")
    before_mode1 = _payload(base / "DBDAT" / "EQ98030.FDI", 308)

    receipt = compiler.compile_package_to_tree(
        package_path=appended_package,
        base_tree=base,
        materialisation_tree=output,
    )

    assert receipt["appended_mode0_dd6361_carrier_ids"] == [33]
    from app.indexed_jug_identity import read_indexed_player_id
    assert read_indexed_player_id(_payload(output / "DBDAT" / "JUG98030.FDI", 33)) == 33
    assert _payload(output / "DBDAT" / "JUG98030.FDI", 33)[2:5] == b"\xdd\x63\x61"
    assert _payload(output / "DBDAT" / "EQ98030.FDI", 308) == before_mode1
    team_raw = (output / "DBDAT" / "EQ98030.FDI").read_bytes()
    selected = next(entry for entry in IndexedFDIFile.from_bytes(team_raw).entries if entry.record_id == 307)
    from app.eq_jug_linked import parse_eq_external_team_roster_payload
    roster = parse_eq_external_team_roster_payload(
        team_raw[selected.payload_offset : selected.payload_offset + selected.payload_length], {}
    )
    assert roster is not None
    assert roster.rows[0].player_record_id == 33


def test_native_compiler_rejects_an_appended_carrier_id_already_owned_by_mode1(tmp_path: Path) -> None:
    """An append ID cannot shadow a live foreign roster reference."""

    base, package_path = _write_fixture_base(tmp_path)
    base.joinpath("DBDAT", "EQ98030.FDI").write_bytes(_indexed_fdi([
        (307, "", _synthetic_eq_decoded_payload()),
        (308, "", _synthetic_mode1_eq_decoded_payload(17)),
    ]))
    package = package_v2.read_canonical_package(package_path)
    package["players"][0]["carrier_id"] = 17
    package["players"][0]["append_from_carrier_id"] = 1
    appended_package = tmp_path / "shadowed-append-season-package.json"
    package_v2.write_canonical_package(appended_package, package)
    output = _copy_base(base, tmp_path / "shadowed-append-materialised")
    before = pipeline.build_tree_inventory(output)

    with pytest.raises(compiler.SeasonCompilerError, match="already referenced by an EQ roster"):
        compiler.compile_package_to_tree(
            package_path=appended_package,
            base_tree=base,
            materialisation_tree=output,
        )
    assert pipeline.build_tree_inventory(output) == before


def test_native_compiler_rejects_compact_player_append_after_runtime_boundary_probe(tmp_path: Path) -> None:
    """Foreign rows may not receive a fresh JUG ID despite a valid static FDI."""

    base, package_path = _write_mode1_fixture_base(tmp_path)
    package = package_v2.read_canonical_package(package_path)
    package["players"][0]["carrier_id"] = 33
    package["players"][0]["append_from_carrier_id"] = 1
    compact_package = tmp_path / "mode1-append-season-package.json"
    package_v2.write_canonical_package(compact_package, package)
    output = _copy_base(base, tmp_path / "mode1-append-materialised")

    before = pipeline.build_tree_inventory(output)
    with pytest.raises(compiler.SeasonCompilerError, match="runtime-blocked"):
        compiler.compile_package_to_tree(
            package_path=compact_package,
            base_tree=base,
            materialisation_tree=output,
        )
    assert pipeline.build_tree_inventory(output) == before


def test_native_compiler_rejects_compact_append_even_with_other_mode1_carriers(tmp_path: Path) -> None:
    """No package shape can override the runtime boundary."""

    base, package_path = _write_mode1_fixture_base(tmp_path)
    base.joinpath("DBDAT", "EQ98030.FDI").write_bytes(_indexed_fdi([
        (308, "", _synthetic_mode1_eq_decoded_payload(1)),
        (309, "", _synthetic_mode1_eq_decoded_payload(17)),
    ]))
    package = package_v2.read_canonical_package(package_path)
    package["players"][0]["carrier_id"] = 33
    package["players"][0]["append_from_carrier_id"] = 1
    compact_package = tmp_path / "partial-mode1-append-season-package.json"
    package_v2.write_canonical_package(compact_package, package)
    output = _copy_base(base, tmp_path / "partial-mode1-append-materialised")
    before = pipeline.build_tree_inventory(output)

    with pytest.raises(compiler.SeasonCompilerError, match="runtime-blocked"):
        compiler.compile_package_to_tree(
            package_path=compact_package,
            base_tree=base,
            materialisation_tree=output,
        )
    assert pipeline.build_tree_inventory(output) == before


def test_native_compiler_recycles_a_mode0_carrier_for_mode1(tmp_path: Path) -> None:
    """The paired append/recycle route must remain an exact two-graph transaction."""

    base, package_path = _write_mode1_recycle_fixture_base(tmp_path)
    output = _copy_base(base, tmp_path / "mode1-recycle-materialised")

    receipt = compiler.compile_package_to_tree(
        package_path=package_path,
        base_tree=base,
        materialisation_tree=output,
    )

    assert receipt["appended_mode0_dd6361_carrier_ids"] == [201]
    assert receipt["mode1_recycled_mode0_carriers"] == [{
        "recycled_carrier_id": 101,
        "mode1_donor_carrier_id": 1,
        "mode0_clone_carrier_id": 201,
        "mode0_target_baseline_role_candidates": [0],
        "mode0_clone_requested_role_candidates": [0],
        "requested_fine_roles": [0],
    }]
    assert _payload(output / "DBDAT" / "JUG98030.FDI", 101)[2:5] == b"\xdd\x63\x60"
    assert _payload(output / "DBDAT" / "JUG98030.FDI", 201)[2:5] == b"\xdd\x63\x61"
    from app.indexed_jug_identity import read_indexed_player_id
    assert read_indexed_player_id(_payload(output / "DBDAT" / "JUG98030.FDI", 101)) == 101
    assert read_indexed_player_id(_payload(output / "DBDAT" / "JUG98030.FDI", 201)) == 201
    eq_data = (output / "DBDAT" / "EQ98030.FDI").read_bytes()
    indexed = IndexedFDIFile.from_bytes(eq_data)
    for team_id, expected_first in ((307, 201), (308, 101)):
        entry = next(item for item in indexed.entries if item.record_id == team_id)
        roster = compiler.parse_eq_external_team_roster_payload(
            eq_data[entry.payload_offset : entry.payload_offset + entry.payload_length], {}
        )
        assert roster is not None
        assert roster.rows[0].player_record_id == expected_first


def test_native_compiler_rejects_mode1_recycle_with_an_incompatible_primary_role(tmp_path: Path) -> None:
    base, package_path = _write_mode1_recycle_fixture_base(tmp_path)
    package = package_v2.read_canonical_package(package_path)
    recycled = next(player for player in package["players"] if player.get("recycle_from_mode1_carrier_id") == 1)
    recycled["facts"]["fine_roles"] = [4]
    incompatible_path = tmp_path / "mode1-recycle-incompatible.json"
    package_v2.write_canonical_package(incompatible_path, package)
    output = _copy_base(base, tmp_path / "mode1-recycle-incompatible-materialised")
    with pytest.raises(compiler.SeasonCompilerError, match="primary fine role 4 is incompatible"):
        compiler.compile_package_to_tree(
            package_path=incompatible_path,
            base_tree=base,
            materialisation_tree=output,
        )


def test_native_compiler_recycles_against_the_declared_clone_role_vector(tmp_path: Path) -> None:
    """A role not present in the old carrier is safe only when the surviving clone writes it."""

    base, package_path = _write_mode1_recycle_fixture_base(tmp_path)
    jug_path = base / "DBDAT" / "JUG98030.FDI"
    before = jug_path.read_bytes()
    records = []
    for entry in IndexedFDIFile.from_bytes(before).entries:
        payload = entry.decode_payload(before)
        # Keep the old English carrier's role vector at 4, but make the
        # compact foreign donor role 3.  The package supplies role 3 for the
        # appended clone; this mirrors the role-3 native recycle control.
        if entry.record_id == 101:
            payload = _dd6361_player_payload(101, role=4)
        elif entry.record_id == 1:
            payload = _dd6360_player_payload(1, role_code=3)
        records.append((int(entry.record_id), str(entry.key), payload))
    jug_path.write_bytes(_indexed_fdi(records))

    package = package_v2.read_canonical_package(package_path)
    clone = next(player for player in package["players"] if player.get("append_from_carrier_id") == 101)
    recycled = next(player for player in package["players"] if player.get("recycle_from_mode1_carrier_id") == 1)
    clone["facts"]["fine_roles"] = [3]
    recycled["facts"]["fine_roles"] = [3]
    package_v2.write_canonical_package(package_path, package)
    output = _copy_base(base, tmp_path / "mode1-recycle-clone-role-materialised")

    receipt = compiler.compile_package_to_tree(
        package_path=package_path,
        base_tree=base,
        materialisation_tree=output,
    )

    assert receipt["mode1_recycled_mode0_carriers"] == [{
        "recycled_carrier_id": 101,
        "mode1_donor_carrier_id": 1,
        "mode0_clone_carrier_id": 201,
        "mode0_target_baseline_role_candidates": [4],
        "mode0_clone_requested_role_candidates": [3],
        "requested_fine_roles": [3],
    }]


def test_shared_preserve_player_order_is_declaration_order_independent() -> None:
    package = {
        "clubs": [
            {"id": "club-b", "roster_player_ids": ["player-shared"], "shared_preserve_player_ids": ["player-shared"]},
            {"id": "club-a", "roster_player_ids": ["player-shared"]},
        ],
        "players": [{"id": "player-shared"}],
    }

    assert compiler._club_player_orders(package) == {"player-shared": 1}

    package["clubs"][0].pop("shared_preserve_player_ids")
    with pytest.raises(compiler.SeasonCompilerError, match="without a shared-preserve declaration"):
        compiler._club_player_orders(package)


def test_native_compiler_writes_mode1_safe_core_and_fine_role_lanes_in_fixed_carrier_slots(tmp_path: Path) -> None:
    base, package_path = _write_mode1_fixture_base(tmp_path)
    output = _copy_base(base, tmp_path / "mode1-materialised")
    before_player = _payload(base / "DBDAT" / "JUG98030.FDI", 1)
    from app.editor_actions import _native_dd6360_role_start, _read_native_dd6360_fields

    before_role_start = _native_dd6360_role_start(before_player)
    before_fields = _read_native_dd6360_fields(before_player, before_role_start)

    package = package_v2.read_canonical_package(package_path)
    package["players"][0]["facts"]["primary_position"] = "M"
    package["players"][0]["facts"]["fine_roles"] = [9, 4]
    package_v2.write_canonical_package(package_path, package)

    receipt = compiler.compile_package_to_tree(
        package_path=package_path,
        base_tree=base,
        materialisation_tree=output,
    )

    assert receipt["mode1_dd6360_core_written_carrier_ids"] == list(range(1, 17))
    status = receipt["team_statuses"][0]
    assert status["record_mode"] == 1
    assert status["opening_tactics"] == "preserved-mode1-unproven"
    assert status["starting_finance"] == "preserved-mode1-unproven"
    assert status["roster_contract"] == "verified-fixed-existing-slot-order"

    after_player = _payload(output / "DBDAT" / "JUG98030.FDI", 1)
    after_role_start = _native_dd6360_role_start(after_player)
    after_fields = _read_native_dd6360_fields(after_player, after_role_start)
    assert after_player[after_role_start] == before_player[before_role_start]
    assert after_player[after_role_start + 7] == before_player[before_role_start + 7]
    assert after_fields["unknown_9"] == before_fields["unknown_9"]
    assert after_fields["fine_role_codes"] == [9, 4, 98, 98, 98, 98]
    assert after_fields["parser_position_code"] == 2
    assert after_fields["visible_position_code"] == 2
    assert after_fields["visible_nationality_code"] == 2  # England in this synthetic TEXTOS table.
    assert after_fields["height_cm"] == 180
    assert after_fields["weight_kg"] == 75
    assert after_fields["skills"] == [60] * 9
    assert after_fields["handling"] == 60
    assert receipt["dd6360_visible_handling_written_carrier_ids"] == list(range(1, 17))

    team_raw = (output / "DBDAT" / "EQ98030.FDI").read_bytes()
    entry = IndexedFDIFile.from_bytes(team_raw).entries[0]
    base_team_raw = (base / "DBDAT" / "EQ98030.FDI").read_bytes()
    base_entry = IndexedFDIFile.from_bytes(base_team_raw).entries[0]
    # Mode 1's 0x6e7-byte pre-link region is intentionally opaque.  A team
    # write may replace its manager link and (when explicitly planned) roster
    # tail, but it must not reinterpret or disturb this opening-state region.
    before_eq_payload = base_team_raw[base_entry.payload_offset : base_entry.payload_offset + base_entry.payload_length]
    after_eq_payload = team_raw[entry.payload_offset : entry.payload_offset + entry.payload_length]
    opaque_start = compiler._mode1_opaque_prelink_offset(before_eq_payload)
    assert after_eq_payload[opaque_start : opaque_start + compiler.EQ_TACTICS_TOTAL_BYTES] == (
        before_eq_payload[opaque_start : opaque_start + compiler.EQ_TACTICS_TOTAL_BYTES]
    )
    from app.eq_jug_linked import parse_eq_external_team_roster_payload

    roster = parse_eq_external_team_roster_payload(team_raw[entry.payload_offset : entry.payload_offset + entry.payload_length], {})
    assert roster is not None
    assert [(row.flag, row.player_record_id) for row in roster.rows] == [
        (player_id % 2, player_id) for player_id in range(1, 17)
    ]


def test_native_compiler_preserves_a_valid_short_mode1_roster(tmp_path: Path) -> None:
    """Existing mode-1 linked tails below sixteen rows are not invented away."""

    base, package_path = _write_mode1_fixture_base(tmp_path, roster_count=14)
    output = _copy_base(base, tmp_path / "mode1-short-roster-materialised")

    receipt = compiler.compile_package_to_tree(
        package_path=package_path,
        base_tree=base,
        materialisation_tree=output,
    )

    status = receipt["team_statuses"][0]
    assert status["record_mode"] == 1
    assert status["roster_count"] == 14
    assert status["roster_contract"] == "verified-fixed-existing-slot-order"


def test_native_compiler_writes_the_isolated_mode1_dd6361_core_lane(tmp_path: Path) -> None:
    base, package_path = _write_mode1_fixture_base(tmp_path)
    jug_path = base / "DBDAT" / "JUG98030.FDI"
    original_jug = jug_path.read_bytes()
    entries = IndexedFDIFile.from_bytes(original_jug).entries
    records = []
    for entry in entries:
        payload = entry.decode_payload(original_jug)
        if entry.record_id == 1:
            payload = bytearray(_dd6361_player_payload(1, role=4))
            payload[:2] = b"\x57\x61"
            payload = bytes(payload)
        records.append((int(entry.record_id), str(entry.key), payload))
    jug_path.write_bytes(_indexed_fdi(records))

    package = package_v2.read_canonical_package(package_path)
    player = package["players"][0]
    player["carrier_family"] = "dd6361"
    player["facts"] = {
        **player["facts"],
        "primary_position": "F",
        "fine_roles": [4],
        "shirt_number": 0,
    }
    package_v2.write_canonical_package(package_path, package)
    output = _copy_base(base, tmp_path / "mode1-dd6361-materialised")

    receipt = compiler.compile_package_to_tree(
        package_path=package_path,
        base_tree=base,
        materialisation_tree=output,
    )

    assert receipt["mode1_dd6361_core_written_carrier_ids"] == [1]
    before = _payload(base / "DBDAT" / "JUG98030.FDI", 1)
    after = _payload(output / "DBDAT" / "JUG98030.FDI", 1)
    assert after[:2] == before[:2] == b"\x57\x61"
    assert compiler._dd6361_active_fine_roles_in_order(after, carrier=1) == [4]
    after_record = PlayerRecord.from_bytes(after, 0)
    assert after_record.position == 3
    assert after_record.nationality == 2
    assert after_record.attributes[3:12] == [60] * 9
    assert after[-7] ^ 0x61 == 60
    assert receipt["dd6361_visible_handling"]["requested_player_count"] == 1


def test_native_compiler_writes_dd6361_core_while_preserving_role_vector(tmp_path: Path) -> None:
    base, package_path = _write_mode1_fixture_base(tmp_path)
    jug_path = base / "DBDAT" / "JUG98030.FDI"
    original_jug = jug_path.read_bytes()
    records = []
    for entry in IndexedFDIFile.from_bytes(original_jug).entries:
        payload = entry.decode_payload(original_jug)
        if entry.record_id == 1:
            payload = _dd6361_player_payload(1, role=4)
        records.append((int(entry.record_id), str(entry.key), payload))
    jug_path.write_bytes(_indexed_fdi(records))

    package = package_v2.read_canonical_package(package_path)
    player = package["players"][0]
    player["carrier_family"] = "dd6361"
    player["facts"] = {
        **player["facts"],
        "primary_position": "F",
        "fine_roles": {"policy": "preserve-existing-mode1"},
        "shirt_number": 0,
    }
    package_v2.write_canonical_package(package_path, package)
    output = _copy_base(base, tmp_path / "mode1-dd6361-role-preserved")

    receipt = compiler.compile_package_to_tree(
        package_path=package_path,
        base_tree=base,
        materialisation_tree=output,
    )

    before = _payload(base / "DBDAT" / "JUG98030.FDI", 1)
    after = _payload(output / "DBDAT" / "JUG98030.FDI", 1)
    before_name_end = compiler._find_dd6361_name_end(before)
    after_name_end = compiler._find_dd6361_name_end(after)
    assert after[after_name_end + 2 : after_name_end + 8] == before[before_name_end + 2 : before_name_end + 8]
    assert PlayerRecord.from_bytes(after, 0).position == 3
    assert receipt["mode1_preserved_player_fields"] == [
        {
            "carrier_id": 1,
            "fields": {
                "fine_roles": {
                    "before_offsets": list(range(before_name_end + 2, before_name_end + 8)),
                    "after_offsets": list(range(after_name_end + 2, after_name_end + 8)),
                    "before_hex": before[before_name_end + 2 : before_name_end + 8].hex(),
                    "after_hex": after[after_name_end + 2 : after_name_end + 8].hex(),
                }
            },
            "result": "field-ranges-byte-identical",
        }
    ]


def test_native_compiler_preserves_each_unavailable_dd6361_fact_by_policy(tmp_path: Path) -> None:
    """The isolated full-player row may omit facts without normalising bytes."""

    base, package_path = _write_mode1_fixture_base(tmp_path)
    jug_path = base / "DBDAT" / "JUG98030.FDI"
    original_jug = jug_path.read_bytes()
    records = []
    for entry in IndexedFDIFile.from_bytes(original_jug).entries:
        payload = entry.decode_payload(original_jug)
        if entry.record_id == 1:
            payload = _dd6361_player_payload(1, role=4)
        records.append((int(entry.record_id), str(entry.key), payload))
    jug_path.write_bytes(_indexed_fdi(records))

    package = package_v2.read_canonical_package(package_path)
    player = package["players"][0]
    player["carrier_family"] = "dd6361"
    player["name"] = "Longer Safe Name"
    preserve = {"policy": "preserve-existing-mode1"}
    player["facts"] = {
        **player["facts"],
        "birth_date": preserve,
        "nationality": preserve,
        "height_cm": preserve,
        "weight_kg": preserve,
        "primary_position": preserve,
        "fine_roles": preserve,
        "shirt_number": preserve,
    }
    package_v2.write_canonical_package(package_path, package)
    output = _copy_base(base, tmp_path / "mode1-dd6361-all-facts-preserved")

    receipt = compiler.compile_package_to_tree(
        package_path=package_path,
        base_tree=base,
        materialisation_tree=output,
    )

    preserved = receipt["mode1_preserved_player_fields"][0]
    assert set(preserved["fields"]) == {
        "birth_date", "fine_roles", "height_cm", "nationality",
        "primary_position", "weight_kg",
    }
    assert all(
        row["before_hex"] == row["after_hex"]
        for row in preserved["fields"].values()
    )


def test_mode1_compiler_allows_a_complete_mode1_roster_transaction_and_role_candidates(tmp_path: Path) -> None:
    base, package_path = _write_mode1_fixture_base(tmp_path)
    package = package_v2.read_canonical_package(package_path)
    package["clubs"][0]["roster_player_ids"][0], package["clubs"][0]["roster_player_ids"][1] = (
        package["clubs"][0]["roster_player_ids"][1],
        package["clubs"][0]["roster_player_ids"][0],
    )
    changed_package = tmp_path / "mode1-roster-change.json"
    package_v2.write_canonical_package(changed_package, package)
    output = _copy_base(base, tmp_path / "mode1-rejected-materialised")
    receipt = compiler.compile_package_to_tree(
        package_path=changed_package,
        base_tree=base,
        materialisation_tree=output,
    )
    assert receipt["team_statuses"][0]["roster_contract"] == (
        "written-proven-mode1-complete-graph-fixed-row-count-and-flags"
    )
    rewritten_file = (output / "DBDAT" / "EQ98030.FDI").read_bytes()
    rewritten_entry = next(
        entry for entry in IndexedFDIFile.from_bytes(rewritten_file).entries if entry.record_id == 308
    )
    from app.eq_jug_linked import parse_eq_external_team_roster_payload
    roster = parse_eq_external_team_roster_payload(
        rewritten_file[rewritten_entry.payload_offset : rewritten_entry.payload_offset + rewritten_entry.payload_length],
        {},
    )
    assert roster is not None
    assert [row.player_record_id for row in roster.rows[:2]] == [2, 1]

    package = package_v2.read_canonical_package(package_path)
    package["players"][0]["facts"]["fine_roles"] = [4, 9]
    changed_package = tmp_path / "mode1-secondary-position-change.json"
    package_v2.write_canonical_package(changed_package, package)
    output = _copy_base(base, tmp_path / "mode1-position-role-materialised")
    compiler.compile_package_to_tree(
        package_path=changed_package,
        base_tree=base,
        materialisation_tree=output,
    )
    after = _payload(output / "DBDAT" / "JUG98030.FDI", 1)
    fields = compiler._read_native_dd6360_fields(after, compiler._native_dd6360_role_start(after))
    assert fields["fine_role_codes"] == [4, 9, 98, 98, 98, 98]


def test_mode1_compiler_never_rewrites_an_unselected_foreign_roster_owner(tmp_path: Path) -> None:
    """A shared JUG carrier must not trigger a hidden foreign donor rewrite."""

    _base, package_path = _write_mode1_fixture_base(tmp_path)
    package = package_v2.read_canonical_package(package_path)
    # Carrier 309 shares player 1 with selected carrier 308.  Its remaining
    # rows only make the terminal roster parser happy; it is deliberately not
    # in the package.
    eq_data = _indexed_fdi([
        (308, "", _synthetic_mode1_eq_decoded_payload()),
        (309, "", _synthetic_mode1_eq_decoded_payload(17)),
    ])
    # Make the fixture overlap exactly one row instead of relying on record
    # directory order or any real PM99 content.
    index = IndexedFDIFile.from_bytes(eq_data)
    raw = bytearray(eq_data)
    second = index.entries[1]
    # EQ roster parsing is against the on-disk raw payload.  Change only the
    # second carrier's first terminal JUG id, leaving the layout and row count
    # intact, so carrier 1 has a selected and an unselected mode-1 owner.
    payload = bytearray(eq_data[second.payload_offset : second.payload_offset + second.payload_length])
    terminal_row_offset = len(payload) - 16 * 5
    payload[terminal_row_offset + 1 : terminal_row_offset + 5] = (1).to_bytes(4, "little")
    raw[second.payload_offset : second.payload_offset + second.payload_length] = payload

    with pytest.raises(compiler.SeasonCompilerError, match="unselected mode-1 roster owner 309"):
        compiler._team_replacements(
            package=package,
            eq_data=bytes(raw),
            ent_carriers={1},
        )


def test_mode1_roster_change_refuses_a_partial_foreign_graph(tmp_path: Path) -> None:
    """A foreign row move cannot be smuggled through a single-club package."""

    _base, package_path = _write_mode1_fixture_base(tmp_path)
    package = package_v2.read_canonical_package(package_path)
    package["clubs"][0]["roster_player_ids"][0], package["clubs"][0]["roster_player_ids"][1] = (
        package["clubs"][0]["roster_player_ids"][1],
        package["clubs"][0]["roster_player_ids"][0],
    )
    # Carrier 309 is a distinct, valid foreign roster.  It is deliberately
    # absent from the package: a changed carrier 308 must make the compiler
    # reject this partial graph instead of silently treating it as a local
    # team edit.
    eq_data = _indexed_fdi([
        (308, "", _synthetic_mode1_eq_decoded_payload(1)),
        (309, "", _synthetic_mode1_eq_decoded_payload(17)),
    ])
    with pytest.raises(compiler.SeasonCompilerError, match="complete foreign graph transaction"):
        compiler._team_replacements(
            package=package,
            eq_data=eq_data,
            ent_carriers={1},
        )


def test_canonical_review_v2_overlay_derives_a_named_package_and_rebuilds_from_base(tmp_path: Path) -> None:
    base, package_path = _write_fixture_base(tmp_path)
    overlay_path = tmp_path / "review.json"
    package_v2.write_canonical_package(overlay_path, _canonical_review_overlay(package_path))
    output = _copy_base(base, tmp_path / "revision-materialised")

    receipt = compiler.compile_package_to_tree(
        package_path=package_path,
        base_tree=base,
        materialisation_tree=output,
        overrides_path=overlay_path,
        derived_package_id="pm99-2015-16-compiler-fixture-r1",
    )

    assert receipt["review_application"]["override_id"] == "review-speed-and-portrait"
    assert receipt["review_overrides_sha256"] == hashlib.sha256(overlay_path.read_bytes()).hexdigest()
    assert receipt["source_season_package_sha256"] == hashlib.sha256(package_path.read_bytes()).hexdigest()
    assert receipt["season_package_sha256"] == receipt["review_application"]["derived_package_canonical_sha256"]
    assert "player-01" in receipt["portraits"]["native_no_photo_player_ids"]
    player = _payload(output / "DBDAT" / "JUG98030.FDI", 1)
    assert player[-16] ^ 0x61 == 99
    assert player[-7] ^ 0x61 == 60
    broken = _canonical_review_overlay(package_path)
    broken["base_package_canonical_sha256"] = "b" * 64
    package_v2.write_canonical_package(overlay_path, broken)
    with pytest.raises(compiler.SeasonCompilerError, match="different canonical season package"):
        compiler.compile_package_to_tree(
            package_path=package_path,
            base_tree=base,
            materialisation_tree=_copy_base(base, tmp_path / "broken-materialised"),
            overrides_path=overlay_path,
            derived_package_id="pm99-2015-16-compiler-fixture-r1",
        )


def test_compiler_rejects_legacy_shape_stale_or_duplicate_review_targets_before_writing(tmp_path: Path) -> None:
    base, package_path = _write_fixture_base(tmp_path)
    overlay_path = tmp_path / "review-overlay.json"
    legacy_shape = {
        "schema_version": review_v2.OVERRIDES_SCHEMA,
        "base_package_sha256": hashlib.sha256(package_path.read_bytes()).hexdigest(),
        "source_review_request_sha256": None,
        "revision_id": "legacy-request",
        "review_note": "The retired prototype schema must fail closed.",
        "players": [], "clubs": [], "managers": [], "portraits": [],
    }
    package_v2.write_canonical_package(overlay_path, legacy_shape)
    untouched = _copy_base(base, tmp_path / "legacy-review-output")
    with pytest.raises(compiler.SeasonCompilerError, match="review overlay cannot derive"):
        compiler.compile_package_to_tree(
            package_path=package_path,
            base_tree=base,
            materialisation_tree=untouched,
            overrides_path=overlay_path,
            derived_package_id="pm99-2015-16-compiler-fixture-r1",
        )
    assert pipeline.build_tree_inventory(untouched) == pipeline.build_tree_inventory(base)

    stale = _canonical_review_overlay(package_path)
    stale["data_patches"][0]["expected"] = {"ratings.values.speed": 59}
    package_v2.write_canonical_package(overlay_path, stale)
    untouched = _copy_base(base, tmp_path / "stale-review-output")
    with pytest.raises(compiler.SeasonCompilerError, match="stale target"):
        compiler.compile_package_to_tree(
            package_path=package_path,
            base_tree=base,
            materialisation_tree=untouched,
            overrides_path=overlay_path,
            derived_package_id="pm99-2015-16-compiler-fixture-r1",
        )
    assert pipeline.build_tree_inventory(untouched) == pipeline.build_tree_inventory(base)

    duplicate = _canonical_review_overlay(package_path)
    duplicate["data_patches"].append({
        "id": "z-player-01-speed-again",
        "target": {"entity": "player", "id": "player-01"},
        "expected": {"ratings.values.speed": 60},
        "set": {"ratings.values.speed": 98},
        "reason": "A duplicate patch must never silently win.",
        "proof": _proof(),
        "rating_provenance": {
            "method": "synthetic duplicate fixture",
            "proof_grade": "static-contract",
            "source_ids": ["source-ledger"],
        },
    })
    package_v2.write_canonical_package(overlay_path, duplicate)
    untouched = _copy_base(base, tmp_path / "duplicate-review-output")
    with pytest.raises(compiler.SeasonCompilerError, match="duplicates target field"):
        compiler.compile_package_to_tree(
            package_path=package_path,
            base_tree=base,
            materialisation_tree=untouched,
            overrides_path=overlay_path,
            derived_package_id="pm99-2015-16-compiler-fixture-r1",
        )
    assert pipeline.build_tree_inventory(untouched) == pipeline.build_tree_inventory(base)


def test_native_compiler_is_a_hashed_buildplan_adapter_with_two_equal_builds(tmp_path: Path) -> None:
    base, package_path = _write_fixture_base(tmp_path)
    reference = _copy_base(base, tmp_path / "reference")
    compiler.compile_package_to_tree(
        package_path=package_path,
        base_tree=base,
        materialisation_tree=reference,
    )
    verified_base = pipeline.make_verified_base_descriptor(base_id="pm99-synthetic-base", tree=base)
    verified_base_path = tmp_path / "verified-base.json"
    pipeline.write_canonical_json(verified_base_path, verified_base)
    package_descriptor = pipeline.canonical_json_document_descriptor(package_path, document_id="season-package")
    outputs = list(compiler.DATABASE_RELATIVE_PATHS)
    stage_inventory = buildplan._build_declared_output_inventory(reference, outputs)
    implementation = ROOT / "scripts" / "season_package_compiler_v2.py"
    expected_receipt = pipeline.make_stage_record(
        stage_id="database-compiler",
        implementation_path=implementation,
        input_fingerprints={
            "base-tree": verified_base["inventory"]["files_fingerprint"],
            "season-package": package_descriptor["canonical_sha256"],
        },
        parameters={"adapter": "pm99-season-package-compiler-v2", "outputs": outputs},
    )
    plan = {
        "schema": buildplan.BUILD_PLAN_SCHEMA,
        "season": "2015-16",
        "base": {
            "base_id": verified_base["base_id"],
            "inventory_fingerprint": verified_base["inventory"]["files_fingerprint"],
        },
        "season_package": {
            "canonical_sha256": package_descriptor["canonical_sha256"],
            "canonical_size": package_descriptor["canonical_size"],
            "schema": package_descriptor["schema"],
        },
        "external_artifacts": [],
        "forbidden_runtime_state_directories": FORBIDDEN_RUNTIME_DIRS,
        "stages": [{
            "id": "database-compiler",
            "order": 1,
            "command": {
                "id": "database-compiler",
                "sha256": pipeline.sha256_file(implementation),
                "args": [
                    "--base-tree", "{base-tree}",
                    "--tree", "{materialisation-tree}",
                    "--package", "{season-package}",
                ],
                "timeout_seconds": 30,
            },
            "outputs": outputs,
            "expected_receipt": expected_receipt,
            "expected_output_inventory": stage_inventory,
        }],
        "expected_final_output_inventory": pipeline.build_tree_inventory(reference),
    }
    plan_path = tmp_path / "build-plan.json"
    buildplan.write_canonical_build_plan(plan_path, plan)

    def materialise(tag: str) -> dict[str, object]:
        return buildplan.run_build_plan_from_paths(
            plan_path=plan_path,
            verified_base_path=verified_base_path,
            base_tree=base,
            season_package=package_path,
            materialisation_tree=tmp_path / f"materialised-{tag}",
            metadata_dir=tmp_path / f"metadata-{tag}",
            local_command_specs=[f"database-compiler={implementation}"],
            external_artifact_specs=[],
        )

    first = materialise("one")
    second = materialise("two")
    first_tree = Path(first["materialisation_tree"])
    second_tree = Path(second["materialisation_tree"])
    assert pipeline.inventory_difference(
        pipeline.build_tree_inventory(first_tree), pipeline.build_tree_inventory(second_tree)
    )["equal"] is True
    assert Path(first["metadata"]["manifest"]).read_bytes() == Path(second["metadata"]["manifest"]).read_bytes()


def test_review_overlay_is_hash_locked_external_input_to_the_buildplan_adapter(tmp_path: Path) -> None:
    base, package_path = _write_fixture_base(tmp_path)
    overlay_path = tmp_path / "review-overlay.json"
    package_v2.write_canonical_package(overlay_path, _canonical_review_overlay(package_path))
    reference = _copy_base(base, tmp_path / "review-reference")
    compiler.compile_package_to_tree(
        package_path=package_path,
        base_tree=base,
        materialisation_tree=reference,
        overrides_path=overlay_path,
        derived_package_id="pm99-2015-16-compiler-fixture-r1",
    )
    verified_base = pipeline.make_verified_base_descriptor(base_id="pm99-synthetic-base", tree=base)
    verified_base_path = tmp_path / "verified-base.json"
    pipeline.write_canonical_json(verified_base_path, verified_base)
    package_descriptor = pipeline.canonical_json_document_descriptor(package_path, document_id="season-package")
    overlay_descriptor = pipeline.external_artifact_descriptor(
        artifact_id="review-overrides", path=overlay_path
    )
    outputs = list(compiler.DATABASE_RELATIVE_PATHS)
    implementation = ROOT / "scripts" / "season_package_compiler_v2.py"
    expected_receipt = pipeline.make_stage_record(
        stage_id="database-compiler",
        implementation_path=implementation,
        input_fingerprints={
            "base-tree": verified_base["inventory"]["files_fingerprint"],
            "season-package": package_descriptor["canonical_sha256"],
        },
        parameters={
            "adapter": "pm99-season-package-compiler-v2",
            "derived-package-id": "pm99-2015-16-compiler-fixture-r1",
            "outputs": outputs,
        },
        external_artifacts=[overlay_descriptor],
    )
    plan = {
        "schema": buildplan.BUILD_PLAN_SCHEMA,
        "season": "2015-16",
        "base": {
            "base_id": verified_base["base_id"],
            "inventory_fingerprint": verified_base["inventory"]["files_fingerprint"],
        },
        "season_package": {
            "canonical_sha256": package_descriptor["canonical_sha256"],
            "canonical_size": package_descriptor["canonical_size"],
            "schema": package_descriptor["schema"],
        },
        "external_artifacts": [overlay_descriptor],
        "forbidden_runtime_state_directories": FORBIDDEN_RUNTIME_DIRS,
        "stages": [{
            "id": "database-compiler",
            "order": 1,
            "command": {
                "id": "database-compiler",
                "sha256": pipeline.sha256_file(implementation),
                "args": [
                    "--base-tree", "{base-tree}",
                    "--tree", "{materialisation-tree}",
                    "--package", "{season-package}",
                    "--overrides", "{external-artifact:review-overrides}",
                    "--derived-package-id", "pm99-2015-16-compiler-fixture-r1",
                ],
                "timeout_seconds": 30,
            },
            "outputs": outputs,
            "expected_receipt": expected_receipt,
            "expected_output_inventory": buildplan._build_declared_output_inventory(reference, outputs),
        }],
        "expected_final_output_inventory": pipeline.build_tree_inventory(reference),
    }
    plan_path = tmp_path / "review-build-plan.json"
    buildplan.write_canonical_build_plan(plan_path, plan)

    def materialise(tag: str) -> dict[str, object]:
        return buildplan.run_build_plan_from_paths(
            plan_path=plan_path,
            verified_base_path=verified_base_path,
            base_tree=base,
            season_package=package_path,
            materialisation_tree=tmp_path / f"review-materialised-{tag}",
            metadata_dir=tmp_path / f"review-metadata-{tag}",
            local_command_specs=[f"database-compiler={implementation}"],
            external_artifact_specs=[f"review-overrides={overlay_path}"],
        )

    first = materialise("one")
    second = materialise("two")
    assert pipeline.inventory_difference(
        pipeline.build_tree_inventory(Path(first["materialisation_tree"])),
        pipeline.build_tree_inventory(Path(second["materialisation_tree"])),
    )["equal"] is True
def test_mode1_player_preserve_rejects_mode0_and_unknown_policy() -> None:
    with pytest.raises(compiler.SeasonCompilerError, match="mode-1 preservation on a mode-0"):
        compiler._mode1_preserved_fields({"shirt_number": {"policy": "preserve-existing-mode1"}}, player_id="player-1", club_mode=0)
    with pytest.raises(compiler.SeasonCompilerError, match="unsupported field policy"):
        compiler._mode1_preserved_fields({"shirt_number": {"policy": "write"}}, player_id="player-1", club_mode=1)


def test_dd6360_mode1_writes_core_while_preserving_role_window() -> None:
    payload = _dd6360_player_payload(1, role_code=4)
    role_start = compiler._native_dd6360_role_start(payload)
    result = compiler._patch_dd6360_mode1_safe_fields(
        payload, position=2, nationality=1, birth_day=1, birth_month=2,
        birth_year=1990, height=181, weight=75,
        skills={key: 60 for key in compiler.SKILLS}, native_role_start=role_start,
        fine_roles=None,
    )
    assert result[role_start + 2:role_start + 8] == payload[role_start + 2:role_start + 8]
    assert result[role_start + 16] != payload[role_start + 16]
