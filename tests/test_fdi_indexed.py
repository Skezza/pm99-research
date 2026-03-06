import struct

import app.editor_actions as editor_actions
import app.loaders as loaders
from app.fdi_indexed import IndexedFDIFile
from app.models import PlayerRecord
from app.xor import write_string, xor_encode


def _build_indexed_fdi(records):
    header = bytearray(b"DMFIv1.0")
    header.extend(struct.pack("<I", 0))
    header.extend(struct.pack("<I", 0))
    header.extend(struct.pack("<I", len(records)))

    index = bytearray()
    encoded_payloads = []
    payload_offset = len(header)
    for record_id, key, payload in records:
        key_bytes = key.encode("cp1252")
        payload_offset += 4 + 1 + len(key_bytes) + 4 + 4
        encoded_payloads.append(xor_encode(payload))

    running_offset = payload_offset
    for (record_id, key, _payload), encoded_payload in zip(records, encoded_payloads):
        key_bytes = key.encode("cp1252")
        index.extend(struct.pack("<I", record_id))
        index.append(len(key_bytes))
        index.extend(key_bytes)
        index.extend(struct.pack("<I", running_offset))
        index.extend(struct.pack("<I", len(encoded_payload)))
        running_offset += len(encoded_payload)

    return bytes(header + index + b"".join(encoded_payloads))


def test_indexed_fdi_file_parses_and_decodes_payloads():
    file_bytes = _build_indexed_fdi(
        [
            (1, "", b"FIRST"),
            (2, "TEAM", b"SECOND"),
        ]
    )

    parsed = IndexedFDIFile.from_bytes(file_bytes)

    assert parsed.record_count == 2
    assert parsed.index_end_offset == 0x14 + 13 + 17
    assert parsed.entries[0].record_id == 1
    assert parsed.entries[0].key == ""
    assert parsed.entries[0].decode_payload(file_bytes) == b"FIRST"
    assert parsed.entries[1].record_id == 2
    assert parsed.entries[1].key == "TEAM"
    assert parsed.entries[1].decode_payload(file_bytes) == b"SECOND"


def test_load_teams_uses_indexed_fdi_container_offsets(tmp_path, monkeypatch):
    separator = bytes([0x61, 0xDD, 0x63])
    payload = b"junk" + separator + b"Alpha FC" + separator + b"Beta Town"
    file_bytes = _build_indexed_fdi([(77, "", payload)])
    path = tmp_path / "EQTEST.FDI"
    path.write_bytes(file_bytes)

    class FakeTeamRecord:
        def __init__(self, data, record_offset):
            self.raw_data = bytes(data)
            self.original_raw_data = bytes(data)
            self.record_offset = record_offset
            self.name = data[3:].decode("latin-1")
            self.team_id = 77

    monkeypatch.setattr(loaders, "TeamRecord", FakeTeamRecord)

    teams = loaders.load_teams(str(path))
    parsed_offset = IndexedFDIFile.from_bytes(file_bytes).entries[0].payload_offset

    assert [team.name for _, team in teams] == ["Alpha FC", "Beta Town"]
    assert teams[0][1].container_encoding == "indexed_xor"
    assert teams[0][1].container_offset == parsed_offset
    assert teams[0][1].container_length == len(payload)
    assert teams[0][1].container_relative_offset == payload.find(separator)
    assert teams[1][1].container_offset == parsed_offset


def test_write_modified_team_subrecords_supports_indexed_xor(tmp_path):
    original_subrecord = b"Old Team|Old Ground"
    new_subrecord = b"New Team|Old Ground"
    decoded_payload = b"HEADER" + original_subrecord + b"TRAILER"
    file_bytes = _build_indexed_fdi([(10, "", decoded_payload)])
    path = tmp_path / "EQWRITE.FDI"
    path.write_bytes(file_bytes)

    parsed = IndexedFDIFile.from_bytes(file_bytes)
    entry = parsed.entries[0]

    team = type("FakeIndexedTeam", (), {})()
    team.container_offset = entry.payload_offset
    team.container_relative_offset = len(b"HEADER")
    team.container_length = entry.payload_length
    team.container_encoding = "indexed_xor"
    team.original_raw_data = original_subrecord
    team.raw_data = new_subrecord

    backup_path = editor_actions._write_modified_team_subrecords(
        path,
        file_bytes,
        [(entry.payload_offset + len(b"HEADER"), team)],
    )

    assert backup_path is not None
    updated_bytes = path.read_bytes()
    updated_payload = IndexedFDIFile.from_bytes(updated_bytes).entries[0].decode_payload(updated_bytes)
    assert updated_payload == b"HEADER" + new_subrecord + b"TRAILER"


def test_load_coaches_uses_indexed_fdi_container_offsets(tmp_path):
    payload = b"Alex Ferguson"
    file_bytes = _build_indexed_fdi([(88, "", payload)])
    path = tmp_path / "ENTTEST.FDI"
    path.write_bytes(file_bytes)

    coaches = loaders.load_coaches(str(path))
    parsed_offset = IndexedFDIFile.from_bytes(file_bytes).entries[0].payload_offset

    assert len(coaches) == 1
    _, coach = coaches[0]
    assert coach.full_name == "Alex Ferguson"
    assert coach.container_encoding == "indexed_xor"
    assert coach.container_offset == parsed_offset
    assert coach.container_length == len(payload)


def test_write_coach_staged_records_supports_indexed_xor(tmp_path):
    payload = b"Alex Ferguson"
    file_bytes = _build_indexed_fdi([(88, "", payload)])
    path = tmp_path / "ENTWRITE.FDI"
    path.write_bytes(file_bytes)

    coaches = loaders.load_coaches(str(path))
    assert len(coaches) == 1

    offset, coach = coaches[0]
    coach.set_name("Alan", "Ferguson")
    backup_path = editor_actions.write_coach_staged_records(str(path), [(offset, coach)])

    assert backup_path is not None
    updated_bytes = path.read_bytes()
    updated_payload = IndexedFDIFile.from_bytes(updated_bytes).entries[0].decode_payload(updated_bytes)
    assert updated_payload == b"Alan Ferguson"


def test_write_modified_entries_supports_variable_length_indexed_payloads(tmp_path):
    file_bytes = _build_indexed_fdi(
        [
            (10, "A", b"ALAN"),
            (11, "B", b"BOB"),
        ]
    )
    path = tmp_path / "JUGWRITE.FDI"
    path.write_bytes(file_bytes)

    parsed = IndexedFDIFile.from_bytes(file_bytes)
    first = parsed.entries[0]
    second = parsed.entries[1]

    class FakeIndexedRecord:
        def __init__(self, payload: bytes, *, container_offset: int, container_length: int):
            self._payload = payload
            self.container_offset = container_offset
            self.container_length = container_length
            self.container_encoding = "indexed_xor"

        def to_bytes(self) -> bytes:
            return self._payload

    staged = FakeIndexedRecord(
        b"ALEXANDER",
        container_offset=first.payload_offset,
        container_length=first.payload_length,
    )

    backup_path = editor_actions._write_modified_entries(path, file_bytes, [(first.payload_offset, staged)])
    assert backup_path is not None

    updated_bytes = path.read_bytes()
    reparsed = IndexedFDIFile.from_bytes(updated_bytes)
    updated_first = reparsed.entries[0]
    updated_second = reparsed.entries[1]

    assert updated_first.decode_payload(updated_bytes) == b"ALEXANDER"
    assert updated_first.payload_length == len(xor_encode(b"ALEXANDER"))
    assert updated_second.decode_payload(updated_bytes) == b"BOB"
    expected_delta = len(xor_encode(b"ALEXANDER")) - first.payload_length
    assert updated_second.payload_offset == second.payload_offset + expected_delta


def test_write_player_staged_records_can_skip_backup_creation(tmp_path):
    file_bytes = _build_indexed_fdi([(10, "", b"ALAN")])
    path = tmp_path / "JUGNOBACKUP.FDI"
    path.write_bytes(file_bytes)
    parsed = IndexedFDIFile.from_bytes(file_bytes)
    entry = parsed.entries[0]

    class FakeIndexedRecord:
        def __init__(self, payload: bytes, *, container_offset: int, container_length: int):
            self._payload = payload
            self.container_offset = container_offset
            self.container_length = container_length
            self.container_encoding = "indexed_xor"

        def to_bytes(self) -> bytes:
            return self._payload

    staged = FakeIndexedRecord(
        b"ALEXANDER",
        container_offset=entry.payload_offset,
        container_length=entry.payload_length,
    )

    backup_path = editor_actions.write_player_staged_records(
        str(path),
        [(entry.payload_offset, staged)],
        create_backup_before_write=False,
    )
    assert backup_path is None
    assert not list(tmp_path.glob("JUGNOBACKUP.FDI.backup*"))

    updated_bytes = path.read_bytes()
    reparsed = IndexedFDIFile.from_bytes(updated_bytes)
    assert reparsed.entries[0].decode_payload(updated_bytes) == b"ALEXANDER"


def _build_minimal_player_payload(*, team_id: int, squad_number: int, given: str, surname: str) -> bytes:
    header = struct.pack("<H", int(team_id)) + bytes([int(squad_number) & 0xFF]) + b"\x00\x00"
    metadata = (b"\x61" * 4) + (b"\x00" * 10)
    attr_encoded = bytes([50 ^ 0x61] * 12)
    trailing = b"\x00" * 7
    return header + write_string(given) + write_string(surname) + metadata + attr_encoded + trailing


def test_promote_team_roster_player_supports_variable_length_indexed_name(tmp_path, monkeypatch):
    original_payload = _build_minimal_player_payload(
        team_id=3425,
        squad_number=13,
        given="Paul",
        surname="SCHOLES",
    )
    file_bytes = _build_indexed_fdi([(15578, "", original_payload)])
    player_path = tmp_path / "JUG98030.FDI"
    team_path = tmp_path / "EQ98030.FDI"
    player_path.write_bytes(file_bytes)
    team_path.write_bytes(b"EQ")

    class _FakeRow:
        player_record_id = 15578
        player_name = "Paul SCHOLES"

    class _FakeRoster:
        eq_record_id = 341
        short_name = "Stoke C."
        full_club_name = "Stoke City"
        rows = [_FakeRow()]

    monkeypatch.setattr(
        editor_actions,
        "load_eq_linked_team_rosters",
        lambda **_kwargs: [_FakeRoster()],
    )

    result = editor_actions.promote_team_roster_player(
        team_file=str(team_path),
        player_file=str(player_path),
        team_query="Stoke",
        slot_number=1,
        new_name="Joseph Skerratt",
        write_changes=True,
    )

    assert result.applied_to_disk is True
    assert result.old_player_name == "Paul SCHOLES"
    assert result.new_player_name == "Joseph Skerratt"
    assert result.alias_replacements.get("display_name") == 1
    assert result.backup_path is not None

    updated_bytes = player_path.read_bytes()
    reparsed = IndexedFDIFile.from_bytes(updated_bytes)
    updated_entry = reparsed.entries[0]
    updated_payload = updated_entry.decode_payload(updated_bytes)
    updated_record = PlayerRecord.from_bytes(updated_payload, updated_entry.payload_offset)

    assert updated_record.name == "Joseph Skerratt"
    assert updated_entry.payload_length > len(original_payload)
