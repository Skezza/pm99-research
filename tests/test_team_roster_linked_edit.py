from pathlib import Path

from app.editor_actions import edit_team_roster_eq_jug_linked
from app.eq_jug_linked import EQLinkedRosterRow, EQLinkedTeamRoster


def test_edit_team_roster_eq_jug_linked_stages_slot_change_without_writing(tmp_path, monkeypatch):
    file_path = tmp_path / "EQTEST.FDI"
    payload = bytearray(b"\x00" * 64)
    payload[10] = 0
    payload[11:15] = (1234).to_bytes(4, "little")
    prefix = b"\x00" * 0x20
    file_path.write_bytes(prefix + payload + b"\x00" * 16)

    roster = EQLinkedTeamRoster(
        eq_record_id=77,
        short_name="Stoke C.",
        stadium_name="Britannia Stadium",
        full_club_name="Stoke City",
        record_size=len(payload),
        mode_byte=0,
        ent_count=1,
        rows=[
            EQLinkedRosterRow(
                slot_index=0,
                flag=0,
                player_record_id=1234,
                player_name="Old PLAYER",
                raw_row_offset=10,
            )
        ],
        payload_offset=0x20,
        payload_length=len(payload),
    )

    monkeypatch.setattr("app.editor_actions.load_eq_linked_team_rosters", lambda **kwargs: [roster])

    result = edit_team_roster_eq_jug_linked(
        team_file=str(file_path),
        player_file="DBDAT/JUG98030.FDI",
        team_query="Stoke",
        slot_number=1,
        player_record_id=3384,
        flag=1,
        write_changes=False,
    )

    assert result.applied_to_disk is False
    assert result.write_changes is False
    assert result.matched_count == 1
    assert len(result.changes) == 1
    change = result.changes[0]
    assert change.eq_record_id == 77
    assert change.slot_number == 1
    assert change.old_flag == 0
    assert change.new_flag == 1
    assert change.old_player_record_id == 1234
    assert change.new_player_record_id == 3384
    assert file_path.read_bytes()[0x20 + 10] == 0


def test_edit_team_roster_eq_jug_linked_writes_slot_change_in_place(tmp_path, monkeypatch):
    file_path = tmp_path / "EQTEST.FDI"
    payload = bytearray(b"\x00" * 64)
    payload[10] = 0
    payload[11:15] = (1234).to_bytes(4, "little")
    prefix = b"\x00" * 0x20
    file_path.write_bytes(prefix + payload + b"\x00" * 16)

    roster = EQLinkedTeamRoster(
        eq_record_id=77,
        short_name="Stoke C.",
        stadium_name="Britannia Stadium",
        full_club_name="Stoke City",
        record_size=len(payload),
        mode_byte=0,
        ent_count=1,
        rows=[
            EQLinkedRosterRow(
                slot_index=0,
                flag=0,
                player_record_id=1234,
                player_name="Old PLAYER",
                raw_row_offset=10,
            )
        ],
        payload_offset=0x20,
        payload_length=len(payload),
    )

    monkeypatch.setattr("app.editor_actions.load_eq_linked_team_rosters", lambda **kwargs: [roster])
    monkeypatch.setattr("app.editor_actions.create_backup", lambda _path: str(file_path) + ".bak")

    result = edit_team_roster_eq_jug_linked(
        team_file=str(file_path),
        player_file="DBDAT/JUG98030.FDI",
        eq_record_id=77,
        slot_number=1,
        player_record_id=3384,
        flag=1,
        write_changes=True,
    )

    updated = file_path.read_bytes()
    assert result.applied_to_disk is True
    assert result.backup_path == str(file_path) + ".bak"
    assert updated[0x20 + 10] == 1
    assert int.from_bytes(updated[0x20 + 11 : 0x20 + 15], "little") == 3384
