from pathlib import Path
from types import SimpleNamespace

from app.editor_actions import (
    batch_edit_team_roster_records,
    edit_team_roster_same_entry_authoritative,
    profile_same_entry_authoritative_tail_bytes,
)
from app.xor import decode_entry, encode_entry


def test_edit_team_roster_same_entry_authoritative_stages_without_writing(tmp_path, monkeypatch):
    file_path = tmp_path / "EQTEST.FDI"
    payload = bytearray(b"\x00" * 24)
    payload[5] = 0x34 ^ 0x61
    payload[6] = 0x12 ^ 0x61
    payload[7:10] = b"\x61\x61\x61"
    file_path.write_bytes(encode_entry(bytes(payload)))

    probe_result = SimpleNamespace(
        requested_team_results=[
            {
                "team_offset": 0x1111,
                "team_name": "Inline FC",
                "full_club_name": "Inline Football Club",
                "preferred_roster_match": {
                    "provenance": "same_entry_authoritative",
                    "rows": [
                        {
                            "pos": 5,
                            "pid_candidate": 0x1234,
                            "is_empty_slot": False,
                            "dd6361_name": "Old PLAYER",
                            "tail_bytes_hex": "616161",
                        }
                    ],
                    "source": {"entry_offset": 0},
                },
            }
        ]
    )

    monkeypatch.setattr("app.editor_actions.extract_team_rosters_eq_same_entry_overlap", lambda **kwargs: probe_result)
    monkeypatch.setattr(
        "app.editor_actions.build_player_visible_skill_index_dd6361",
        lambda **kwargs: {0x1234: {"resolved_bio_name": "Old PLAYER"}, 0x3384: {"resolved_bio_name": "New PLAYER"}},
    )

    result = edit_team_roster_same_entry_authoritative(
        team_file=str(file_path),
        player_file="DBDAT/JUG98030.FDI",
        team_query="Inline",
        slot_number=1,
        pid_candidate=0x3384,
        write_changes=False,
    )

    assert result.applied_to_disk is False
    assert result.write_changes is False
    assert len(result.changes) == 1
    change = result.changes[0]
    assert change.old_pid_candidate == 0x1234
    assert change.new_pid_candidate == 0x3384
    assert change.old_player_name == "Old PLAYER"
    assert change.new_player_name == "New PLAYER"
    assert change.preserved_tail_bytes_hex == "616161"

    decoded, _ = decode_entry(file_path.read_bytes(), 0)
    assert decoded[5] == (0x34 ^ 0x61)
    assert decoded[6] == (0x12 ^ 0x61)
    assert decoded[7:10] == b"\x61\x61\x61"


def test_edit_team_roster_same_entry_authoritative_writes_only_pid_bytes(tmp_path, monkeypatch):
    file_path = tmp_path / "EQTEST.FDI"
    payload = bytearray(b"\x00" * 24)
    payload[5] = 0x34 ^ 0x61
    payload[6] = 0x12 ^ 0x61
    payload[7:10] = b"\x61\x61\x61"
    file_path.write_bytes(encode_entry(bytes(payload)))

    probe_result = SimpleNamespace(
        requested_team_results=[
            {
                "team_offset": 0x1111,
                "team_name": "Inline FC",
                "full_club_name": "Inline Football Club",
                "preferred_roster_match": {
                    "provenance": "same_entry_authoritative",
                    "rows": [
                        {
                            "pos": 5,
                            "pid_candidate": 0x1234,
                            "is_empty_slot": False,
                            "dd6361_name": "Old PLAYER",
                            "tail_bytes_hex": "616161",
                        }
                    ],
                    "source": {"entry_offset": 0},
                },
            }
        ]
    )

    monkeypatch.setattr("app.editor_actions.extract_team_rosters_eq_same_entry_overlap", lambda **kwargs: probe_result)
    monkeypatch.setattr(
        "app.editor_actions.build_player_visible_skill_index_dd6361",
        lambda **kwargs: {0x1234: {"resolved_bio_name": "Old PLAYER"}, 0x3384: {"resolved_bio_name": "New PLAYER"}},
    )
    monkeypatch.setattr("app.editor_actions.create_backup", lambda _path: str(file_path) + ".bak")

    result = edit_team_roster_same_entry_authoritative(
        team_file=str(file_path),
        player_file="DBDAT/JUG98030.FDI",
        team_query="Inline",
        slot_number=1,
        pid_candidate=0x3384,
        write_changes=True,
    )

    decoded, _ = decode_entry(file_path.read_bytes(), 0)
    assert result.applied_to_disk is True
    assert result.backup_path == str(file_path) + ".bak"
    assert decoded[5] == (0x84 ^ 0x61)
    assert decoded[6] == (0x33 ^ 0x61)
    assert decoded[7:10] == b"\x61\x61\x61"


def test_profile_same_entry_authoritative_tail_bytes_counts_buckets(monkeypatch):
    monkeypatch.setattr(
        "app.editor_actions.gather_team_records",
        lambda _file: (
            [SimpleNamespace(record=SimpleNamespace(name="Inline FC", full_club_name="Inline Football Club"))],
            [],
        ),
    )
    monkeypatch.setattr(
        "app.editor_actions.extract_team_rosters_eq_same_entry_overlap",
        lambda **kwargs: SimpleNamespace(
            requested_team_results=[
                {
                    "team_name": "Inline FC",
                    "full_club_name": "Inline Football Club",
                    "preferred_roster_match": {
                        "provenance": "same_entry_authoritative",
                        "rows": [
                            {
                                "is_empty_slot": False,
                                "dd6361_name": "Old PLAYER",
                                "tail_bytes_hex": "58595a",
                                "tail_byte_2": 0x58,
                                "tail_byte_3": 0x59,
                                "tail_byte_4": 0x5A,
                            },
                            {
                                "is_empty_slot": False,
                                "dd6361_name": "New PLAYER",
                                "row5_raw_hex": "f0f158595a",
                            },
                        ],
                    },
                }
            ]
        ),
    )

    result = profile_same_entry_authoritative_tail_bytes(
        team_file="DBDAT/EQ98030.FDI",
        player_file="DBDAT/JUG98030.FDI",
        team_queries=None,
        limit=5,
    )

    assert result.requested_team_count == 1
    assert result.authoritative_team_count == 1
    assert result.row_count == 2
    assert len(result.buckets) == 1
    bucket = result.buckets[0]
    assert bucket.tail_bytes_hex == "58595a"
    assert bucket.tail_byte_2 == 0x58
    assert bucket.tail_byte_3 == 0x59
    assert bucket.tail_byte_4 == 0x5A
    assert bucket.count == 2
    assert bucket.sample_teams == ["Inline FC (Inline Football Club)"]
    assert bucket.sample_players == ["Old PLAYER", "New PLAYER"]


def test_profile_same_entry_authoritative_tail_bytes_can_include_fallbacks(monkeypatch):
    monkeypatch.setattr(
        "app.editor_actions.gather_team_records",
        lambda _file: (
            [
                SimpleNamespace(record=SimpleNamespace(name="Inline FC", full_club_name="Inline Football Club")),
                SimpleNamespace(record=SimpleNamespace(name="Man Utd", full_club_name="Manchester Utd")),
            ],
            [],
        ),
    )
    monkeypatch.setattr(
        "app.editor_actions.extract_team_rosters_eq_same_entry_overlap",
        lambda **kwargs: SimpleNamespace(
            requested_team_results=[
                {
                    "team_name": "Inline FC",
                    "full_club_name": "Inline Football Club",
                    "preferred_roster_match": {
                        "provenance": "same_entry_authoritative",
                        "rows": [
                            {
                                "is_empty_slot": False,
                                "dd6361_name": "Old PLAYER",
                                "tail_bytes_hex": "616161",
                                "tail_byte_2": 0x61,
                                "tail_byte_3": 0x61,
                                "tail_byte_4": 0x61,
                            }
                        ],
                    },
                },
                {
                    "team_name": "Manchester Utd",
                    "full_club_name": "Manchester United",
                    "preferred_roster_match": {
                        "provenance": "known_lineup_anchor_assisted",
                        "rows": [
                            {
                                "is_empty_slot": False,
                                "dd6361_name": "Henning BERG",
                                "row5_raw_hex": "5d66616161",
                            }
                        ],
                    },
                },
            ]
        ),
    )

    result = profile_same_entry_authoritative_tail_bytes(
        team_file="DBDAT/EQ98030.FDI",
        player_file="DBDAT/JUG98030.FDI",
        team_queries=None,
        limit=5,
        include_fallbacks=True,
    )

    assert result.include_fallbacks is True
    assert result.authoritative_team_count == 2
    assert result.row_count == 2
    assert result.provenance_counts == {
        "same_entry_authoritative": 1,
        "known_lineup_anchor_assisted": 1,
    }
    assert len(result.buckets) == 2
    assert {bucket.provenance for bucket in result.buckets} == {
        "same_entry_authoritative",
        "known_lineup_anchor_assisted",
    }
    assert all(bucket.tail_bytes_hex == "616161" for bucket in result.buckets)


def test_edit_team_roster_same_entry_authoritative_supports_known_lineup_anchor_assisted(tmp_path, monkeypatch):
    file_path = tmp_path / "EQTEST.FDI"
    payload = bytearray(b"\x00" * 24)
    payload[5] = 0x34 ^ 0x61
    payload[6] = 0x12 ^ 0x61
    payload[7:10] = b"\x61\x61\x61"
    file_path.write_bytes(encode_entry(bytes(payload)))

    probe_result = SimpleNamespace(
        requested_team_results=[
            {
                "team_offset": 0x2222,
                "team_name": "Manchester Utd",
                "full_club_name": "Manchester United",
                "preferred_roster_match": {
                    "provenance": "known_lineup_anchor_assisted",
                    "rows": [
                        {
                            "pos": 5,
                            "pid_candidate": 0x1234,
                            "is_empty_slot": False,
                            "dd6361_name": "Old PLAYER",
                            "row5_raw_hex": "3412616161",
                        }
                    ],
                    "source": {"entry_offset": 0},
                },
            }
        ]
    )

    monkeypatch.setattr("app.editor_actions.extract_team_rosters_eq_same_entry_overlap", lambda **kwargs: probe_result)
    monkeypatch.setattr(
        "app.editor_actions.build_player_visible_skill_index_dd6361",
        lambda **kwargs: {0x1234: {"resolved_bio_name": "Old PLAYER"}, 0x3384: {"resolved_bio_name": "New PLAYER"}},
    )

    result = edit_team_roster_same_entry_authoritative(
        team_file=str(file_path),
        player_file="DBDAT/JUG98030.FDI",
        team_query="Manchester Utd",
        slot_number=1,
        pid_candidate=0x3384,
        write_changes=False,
    )

    assert len(result.changes) == 1
    change = result.changes[0]
    assert change.provenance == "known_lineup_anchor_assisted"
    assert change.preserved_tail_bytes_hex == "616161"


def test_batch_edit_team_roster_records_writes_linked_and_same_entry(tmp_path, monkeypatch):
    file_path = tmp_path / "EQTEST.FDI"
    csv_path = tmp_path / "roster_plan.csv"

    file_bytes = bytearray(b"\x00" * 96)
    file_bytes[10 + 2] = 0
    file_bytes[10 + 3 : 10 + 7] = (0x04D2).to_bytes(4, "little")
    inline_payload = bytearray(b"\x00" * 16)
    inline_payload[3] = 0x34 ^ 0x61
    inline_payload[4] = 0x12 ^ 0x61
    inline_payload[5:8] = b"\x61\x61\x61"
    encoded_inline = encode_entry(bytes(inline_payload))
    file_bytes[32 : 32 + len(encoded_inline)] = encoded_inline
    file_path.write_bytes(bytes(file_bytes))

    csv_path.write_text(
        "\n".join(
            [
                "team,source,slot,player_id,flag,pid",
                "Linked FC,linked,1,3384,1,",
                "Inline FC,same_entry,1,,,13188",
            ]
        ),
        encoding="utf-8",
    )

    linked_roster = SimpleNamespace(
        eq_record_id=341,
        short_name="Linked FC",
        full_club_name="Linked Football Club",
        payload_offset=10,
        payload_length=12,
        rows=[
            SimpleNamespace(
                slot_index=0,
                flag=0,
                player_record_id=0x04D2,
                player_name="Old LINKED",
                raw_row_offset=2,
            )
        ],
    )
    same_entry_probe = SimpleNamespace(
        requested_team_results=[
            {
                "team_offset": 0x1111,
                "team_name": "Inline FC",
                "full_club_name": "Inline Football Club",
                "preferred_roster_match": {
                    "provenance": "same_entry_authoritative",
                    "rows": [
                        {
                            "pos": 3,
                            "pid_candidate": 0x1234,
                            "is_empty_slot": False,
                            "dd6361_name": "Old INLINE",
                            "tail_bytes_hex": "616161",
                        }
                    ],
                    "source": {"entry_offset": 32},
                },
            }
        ]
    )

    monkeypatch.setattr("app.editor_actions.load_eq_linked_team_rosters", lambda **kwargs: [linked_roster])
    monkeypatch.setattr("app.editor_actions.extract_team_rosters_eq_same_entry_overlap", lambda **kwargs: same_entry_probe)
    monkeypatch.setattr(
        "app.editor_actions.build_player_visible_skill_index_dd6361",
        lambda **kwargs: {
            0x1234: {"resolved_bio_name": "Old INLINE"},
            0x04D2: {"resolved_bio_name": "Old LINKED"},
            3384: {"resolved_bio_name": "New PLAYER"},
        },
    )
    monkeypatch.setattr("app.editor_actions.create_backup", lambda _path: str(file_path) + ".bak")

    result = batch_edit_team_roster_records(
        team_file=str(file_path),
        player_file="DBDAT/JUG98030.FDI",
        csv_path=str(csv_path),
        write_changes=True,
    )

    data = file_path.read_bytes()
    assert result.applied_to_disk is True
    assert result.backup_path == str(file_path) + ".bak"
    assert result.row_count == 2
    assert result.matched_row_count == 2
    assert len(result.linked_changes) == 1
    assert len(result.same_entry_changes) == 1
    assert len(result.plan_preview) == 2
    assert [int(getattr(row, "row_number", 0) or 0) for row in result.plan_preview] == [2, 3]
    assert [str(getattr(row, "status", "") or "") for row in result.plan_preview] == ["change", "change"]
    assert [str(getattr(row, "source", "") or "") for row in result.plan_preview] == ["linked", "same_entry"]
    assert data[12] == 1
    assert int.from_bytes(data[13:17], "little") == 3384

    decoded_inline, _ = decode_entry(data, 32)
    assert decoded_inline[3] == (0x84 ^ 0x61)
    assert decoded_inline[4] == (0x33 ^ 0x61)
    assert decoded_inline[5:8] == b"\x61\x61\x61"
