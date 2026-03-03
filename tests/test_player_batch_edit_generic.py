import struct
from pathlib import Path

from app.editor_actions import batch_edit_player_metadata_records, edit_player_metadata_records, inspect_player_metadata_records
from app.models import DirectoryEntry, FDIHeader, PlayerRecord
from app.xor import encode_entry, write_string


def _build_generic_player_file(file_path: Path) -> int:
    record = PlayerRecord(
        given_name="Paul",
        surname="SCHOLES",
        name="Paul SCHOLES",
        team_id=42,
        squad_number=8,
        skills=[50] * 10,
        version=700,
    )
    entry_bytes = record.to_bytes()
    entry_offset = 0x28
    payload = bytearray()
    payload += FDIHeader(
        signature=b"DMFIv1.0",
        record_count=1,
        version=2,
        max_offset=entry_offset + len(entry_bytes),
        dir_size=8,
    ).to_bytes()
    payload += DirectoryEntry(offset=entry_offset, tag=ord("P"), index=0).to_bytes()
    payload += entry_bytes
    file_path.write_bytes(bytes(payload))
    return entry_offset


def _build_legacy_weight_player_file(file_path: Path, *, weight: int = 78) -> int:
    year_bytes = struct.pack("<H", 1974)
    decoded = bytearray()
    decoded += struct.pack("<H", 42)
    decoded += bytes([8, 0, 0])
    decoded += write_string("Paul")
    decoded += write_string("SCHOLES")
    decoded += b"\x61" * 4
    metadata = bytearray(b"\x00" * 11)
    metadata[3] = 2 ^ 0x61
    metadata[4] = 44 ^ 0x61
    metadata[5] = 16 ^ 0x61
    metadata[6] = 11 ^ 0x61
    metadata[7] = year_bytes[0] ^ 0x61
    metadata[8] = year_bytes[1] ^ 0x61
    metadata[9] = 178 ^ 0x61
    metadata[10] = int(weight) ^ 0x61
    decoded += metadata
    decoded += bytes([50 ^ 0x61] * 12)
    decoded += b"\x00" * 7

    entry_bytes = encode_entry(bytes(decoded))
    entry_offset = 0x28
    payload = bytearray()
    payload += FDIHeader(
        signature=b"DMFIv1.0",
        record_count=1,
        version=2,
        max_offset=entry_offset + len(entry_bytes),
        dir_size=8,
    ).to_bytes()
    payload += DirectoryEntry(offset=entry_offset, tag=ord("P"), index=0).to_bytes()
    payload += entry_bytes
    file_path.write_bytes(bytes(payload))
    return entry_offset


def test_generic_player_edit_stages_name_change_without_writing(tmp_path):
    file_path = tmp_path / "GENERIC.FDI"
    _build_generic_player_file(file_path)

    result = edit_player_metadata_records(
        str(file_path),
        target_name="Paul SCHOLES",
        new_name="Alan SMITH",
        write_changes=False,
    )

    assert result.applied_to_disk is False
    assert result.write_changes is False
    assert result.matched_count == 1
    assert len(result.changes) == 1
    assert result.changes[0].changed_fields["name"] == ("Paul SCHOLES", "Alan SMITH")
    assert len(result.staged_records) == 1


def test_generic_player_edit_stages_metadata_change_without_writing(tmp_path):
    file_path = tmp_path / "GENERIC.FDI"
    _build_generic_player_file(file_path)

    result = edit_player_metadata_records(
        str(file_path),
        target_name="Paul SCHOLES",
        height=181,
        nationality=44,
        write_changes=False,
    )

    assert result.applied_to_disk is False
    assert result.write_changes is False
    assert result.matched_count == 1
    assert len(result.changes) == 1
    assert result.changes[0].changed_fields["height"] == (175, 181)
    assert result.changes[0].changed_fields["nationality"] == (97, 44)
    assert len(result.staged_records) == 1


def test_generic_player_edit_skips_weight_without_legacy_slot(tmp_path):
    file_path = tmp_path / "GENERIC.FDI"
    _build_generic_player_file(file_path)

    result = edit_player_metadata_records(
        str(file_path),
        target_name="Paul SCHOLES",
        weight=81,
        write_changes=False,
    )

    assert result.matched_count == 1
    assert result.changes == []
    assert result.warnings
    assert "parser-backed in-place weight slot" in result.warnings[0].message


def test_generic_player_edit_stages_weight_change_when_legacy_slot_exists(tmp_path):
    file_path = tmp_path / "LEGACY_WEIGHT.FDI"
    _build_legacy_weight_player_file(file_path, weight=78)

    result = edit_player_metadata_records(
        str(file_path),
        target_name="Paul SCHOLES",
        weight=81,
        write_changes=False,
    )

    assert result.applied_to_disk is False
    assert result.matched_count == 1
    assert len(result.changes) == 1
    assert result.changes[0].changed_fields["weight"] == (78, 81)
    assert len(result.staged_records) == 1


def test_generic_player_inspect_uses_name_only_path_for_non_index_layout(tmp_path):
    file_path = tmp_path / "GENERIC.FDI"
    _build_generic_player_file(file_path)

    result = inspect_player_metadata_records(
        str(file_path),
        "Paul SCHOLES",
    )

    assert result.storage_mode == "name_only"
    assert result.matched_count == 1
    assert result.records[0].weight is None


def test_generic_player_batch_edit_stages_name_change_without_writing(tmp_path):
    file_path = tmp_path / "GENERIC.FDI"
    entry_offset = _build_generic_player_file(file_path)
    csv_path = tmp_path / "player_batch.csv"
    csv_path.write_text(
        "name,offset,new_name\n"
        f"Paul SCHOLES,0x{entry_offset:X},Alan SMITH\n",
        encoding="utf-8",
    )

    result = batch_edit_player_metadata_records(
        str(file_path),
        str(csv_path),
        write_changes=False,
    )

    assert result.applied_to_disk is False
    assert result.write_changes is False
    assert result.row_count == 1
    assert result.matched_row_count == 1
    assert len(result.changes) == 1
    assert result.changes[0].changed_fields["name"] == ("Paul SCHOLES", "Alan SMITH")
    assert len(result.staged_records) == 1


def test_generic_player_batch_edit_stages_metadata_change_without_writing(tmp_path):
    file_path = tmp_path / "GENERIC.FDI"
    entry_offset = _build_generic_player_file(file_path)
    csv_path = tmp_path / "player_batch.csv"
    csv_path.write_text(
        "name,offset,height,nationality\n"
        f"Paul SCHOLES,0x{entry_offset:X},181,44\n",
        encoding="utf-8",
    )

    result = batch_edit_player_metadata_records(
        str(file_path),
        str(csv_path),
        write_changes=False,
    )

    assert result.applied_to_disk is False
    assert result.write_changes is False
    assert result.row_count == 1
    assert result.matched_row_count == 1
    assert len(result.changes) == 1
    assert result.changes[0].changed_fields["height"] == (175, 181)
    assert result.changes[0].changed_fields["nationality"] == (97, 44)
    assert len(result.staged_records) == 1
