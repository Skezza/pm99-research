from pathlib import Path

import pytest

import app.editor_actions as editor_actions
from app.editor_actions import (
    TeamRosterPlayerPromotionResult,
    clone_team_roster_eq_jug_linked,
    edit_team_roster_eq_jug_linked,
    export_team_roster_batch_template,
    promote_linked_roster_player_name_bulk,
    summarize_team_roster_bulk_promotion,
)
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



def test_clone_team_roster_eq_jug_linked_stages_full_slot_swap(tmp_path, monkeypatch):
    file_path = tmp_path / "EQTEST.FDI"
    payload = bytearray(b"\x00" * 80)
    payload[10] = 0
    payload[11:15] = (101).to_bytes(4, "little")
    payload[20] = 1
    payload[21:25] = (102).to_bytes(4, "little")
    prefix = b"\x00" * 0x20
    file_path.write_bytes(prefix + payload + b"\x00" * 16)

    source_roster = EQLinkedTeamRoster(
        eq_record_id=1,
        short_name="Source FC",
        stadium_name="A",
        full_club_name="Source Football Club",
        record_size=len(payload),
        mode_byte=0,
        ent_count=2,
        rows=[
            EQLinkedRosterRow(slot_index=0, flag=7, player_record_id=2001, player_name="S1", raw_row_offset=10),
            EQLinkedRosterRow(slot_index=1, flag=8, player_record_id=2002, player_name="S2", raw_row_offset=20),
        ],
        payload_offset=0x20,
        payload_length=len(payload),
    )
    target_roster = EQLinkedTeamRoster(
        eq_record_id=2,
        short_name="Stoke C.",
        stadium_name="B",
        full_club_name="Stoke City",
        record_size=len(payload),
        mode_byte=0,
        ent_count=2,
        rows=[
            EQLinkedRosterRow(slot_index=0, flag=0, player_record_id=101, player_name="T1", raw_row_offset=10),
            EQLinkedRosterRow(slot_index=1, flag=1, player_record_id=102, player_name="T2", raw_row_offset=20),
        ],
        payload_offset=0x20,
        payload_length=len(payload),
    )

    monkeypatch.setattr(
        "app.editor_actions.load_eq_linked_team_rosters",
        lambda **kwargs: [source_roster, target_roster],
    )

    result = clone_team_roster_eq_jug_linked(
        team_file=str(file_path),
        player_file="DBDAT/JUG98030.FDI",
        source_eq_record_id=1,
        target_eq_record_id=2,
        slot_limit=2,
        write_changes=False,
    )

    assert result.applied_to_disk is False
    assert result.matched_count == 2
    assert len(result.changes) == 2
    assert result.changes[0].new_player_record_id == 2001
    assert result.changes[1].new_player_record_id == 2002


def test_export_team_roster_batch_template_writes_linked_rows(tmp_path, monkeypatch):
    output_csv = tmp_path / "stoke_template.csv"
    roster = EQLinkedTeamRoster(
        eq_record_id=77,
        short_name="Stoke C.",
        stadium_name="Britannia",
        full_club_name="Stoke City",
        record_size=128,
        mode_byte=0,
        ent_count=2,
        rows=[
            EQLinkedRosterRow(slot_index=0, flag=0, player_record_id=3384, player_name="Player One", raw_row_offset=10),
            EQLinkedRosterRow(slot_index=1, flag=1, player_record_id=3937, player_name="Player Two", raw_row_offset=20),
        ],
        payload_offset=0x20,
        payload_length=128,
    )

    monkeypatch.setattr("app.editor_actions.load_eq_linked_team_rosters", lambda **kwargs: [roster])

    result = export_team_roster_batch_template(
        team_file="DBDAT/EQ98030.FDI",
        player_file="DBDAT/JUG98030.FDI",
        team_query="Stoke",
        output_csv=str(output_csv),
        source="linked",
    )

    assert result.row_count == 2
    assert result.source == "linked"
    text = output_csv.read_text(encoding="utf-8")
    assert "team,source,eq_record_id,team_offset,slot,player_id,flag,pid" in text
    assert "Stoke C.,linked,77,,1,3384,0," in text
    assert "Stoke C.,linked,77,,2,3937,1," in text


def test_promote_linked_roster_player_name_bulk_runs_reusable_slot_loop(monkeypatch):
    roster = EQLinkedTeamRoster(
        eq_record_id=3425,
        short_name="Stoke C.",
        stadium_name="Britannia",
        full_club_name="Stoke City",
        record_size=128,
        mode_byte=0,
        ent_count=3,
        rows=[
            EQLinkedRosterRow(slot_index=0, flag=0, player_record_id=1001, player_name="A", raw_row_offset=10),
            EQLinkedRosterRow(slot_index=1, flag=0, player_record_id=1002, player_name="B", raw_row_offset=20),
            EQLinkedRosterRow(slot_index=2, flag=0, player_record_id=1003, player_name="C", raw_row_offset=30),
        ],
        payload_offset=0,
        payload_length=128,
    )
    monkeypatch.setattr("app.editor_actions.load_eq_linked_team_rosters", lambda **kwargs: [roster])

    seen_slots = []

    def fake_promote_team_roster_player(**kwargs):
        slot_number = int(kwargs["slot_number"])
        seen_slots.append(slot_number)
        return TeamRosterPlayerPromotionResult(
            team_file=Path(kwargs["team_file"]),
            player_file=Path(kwargs["player_file"]),
            eq_record_id=3425,
            team_name="Stoke C.",
            full_club_name="Stoke City",
            slot_number=slot_number,
            player_record_id=1000 + slot_number,
            old_player_name=f"Old {slot_number}",
            new_player_name=str(kwargs["new_name"]),
            skill_updates_requested={},
            visible_skills_before={},
            visible_skills_after={},
            alias_replacements={"display_name": 1},
            backup_path=None,
            write_changes=bool(kwargs.get("write_changes", False)),
            applied_to_disk=False,
            warnings=[],
        )

    monkeypatch.setattr("app.editor_actions.promote_team_roster_player", fake_promote_team_roster_player)

    result = promote_linked_roster_player_name_bulk(
        team_file="DBDAT/EQ98030.FDI",
        player_file="DBDAT/JUG98030.FDI",
        team_query="Stoke",
        new_name="Joe Skerratt",
        slot_limit=2,
        write_changes=False,
    )

    assert result.slot_count == 2
    assert result.matched_slot_count == 2
    assert len(result.promotions) == 2
    assert len(result.skipped_slots) == 0
    assert seen_slots == [1, 2]
    assert result.applied_to_disk is False


def test_summarize_team_roster_bulk_promotion_counts_skip_families():
    result = type("Result", (), {
        "eq_record_id": 3425,
        "team_name": "Stoke C.",
        "full_club_name": "Stoke City",
        "new_player_name": "Joe Skerratt",
        "slot_count": 4,
        "matched_slot_count": 1,
        "promotions": [
            type("Promotion", (), {
                "name_mutation_family": "parser_text_spill_salvage",
            })(),
        ],
        "skipped_slots": [
            type("Skip", (), {
                "slot_number": 2,
                "player_record_id": 9773,
                "player_name": "Ray WALLACE",
                "reason_code": "fixed_name_unsafe",
                "reason_message": "unsafe payload",
            })(),
            type("Skip", (), {
                "slot_number": 3,
                "player_record_id": 9774,
                "player_name": "Joe SKERRATT",
                "reason_code": "already_target",
                "reason_message": "already matched",
            })(),
            type("Skip", (), {
                "slot_number": 4,
                "player_record_id": 9775,
                "player_name": "Sam BLOCKED",
                "reason_code": "promotion_error",
                "reason_message": "decode mismatch",
            })(),
        ],
    })()

    summary = summarize_team_roster_bulk_promotion(result, sample_limit=2)

    assert summary.eq_record_id == 3425
    assert summary.slot_count == 4
    assert summary.matched_slot_count == 1
    assert summary.skipped_slot_count == 3
    assert summary.fixed_name_unsafe_count == 1
    assert summary.already_target_count == 1
    assert summary.other_skip_count == 1
    assert summary.reason_counts == {
        "fixed_name_unsafe": 1,
        "already_target": 1,
        "promotion_error": 1,
    }
    assert summary.safe_family_counts == {"parser_text_spill_salvage": 1}
    assert len(summary.sample_skips) == 2
    assert summary.sample_skips[0].slot_number == 2


def test_mutate_indexed_player_name_fixed_safe_allows_parser_text_spill_family(monkeypatch):
    decoded_payload = b"decoded_payload_"
    text_candidate = b"text_candidate__"
    parser_candidate = b"parser_candidate"

    class _Record:
        def __init__(self, name: str) -> None:
            self.name = name

    def fake_from_bytes(payload, _offset):
        if payload == decoded_payload:
            return _Record("Old Name")
        if payload == text_candidate:
            return _Record("Joe Skerratt suffix")
        if payload == parser_candidate:
            return _Record("Joe Skerratt")
        raise AssertionError("unexpected payload")

    monkeypatch.setattr(editor_actions.PlayerRecord, "from_bytes", staticmethod(fake_from_bytes))
    monkeypatch.setattr(
        editor_actions,
        "replace_text_in_decoded",
        lambda *_args, **_kwargs: (text_candidate, True),
    )

    def fake_length_prefixed(**_kwargs):
        raise RuntimeError("Fixed-length rename could not parse given-name slot bounds")

    monkeypatch.setattr(editor_actions, "_mutate_indexed_player_name_fixed_bytes", fake_length_prefixed)
    monkeypatch.setattr(
        editor_actions,
        "_build_parser_fixed_name_candidate",
        lambda **_kwargs: parser_candidate,
    )
    monkeypatch.setattr(
        editor_actions,
        "_candidate_change_profile",
        lambda _original, candidate: (36, 5, 41) if candidate in {text_candidate, parser_candidate} else (0, -1, -1),
    )
    monkeypatch.setattr(editor_actions, "_sync_fixed_name_aliases", lambda **kwargs: kwargs["payload"])

    mutated, applied_name, family = editor_actions._mutate_indexed_player_name_fixed_safe(
        decoded_payload=decoded_payload,
        payload_offset=0,
        new_name="Joe Skerratt",
    )

    assert mutated == parser_candidate
    assert applied_name == "Joe Skerratt"
    assert family == "parser_text_spill_salvage"


def test_mutate_indexed_player_name_fixed_safe_allows_parser_text_spill_no_alias_sync(monkeypatch):
    decoded_payload = b"decoded_payload_"
    text_candidate = b"text_candidate__"
    parser_candidate = b"parser_candidate"
    synced_candidate = b"sync_candidate__"

    class _Record:
        def __init__(self, name: str) -> None:
            self.name = name

    def fake_from_bytes(payload, _offset):
        if payload == decoded_payload:
            return _Record("Old Name")
        if payload == text_candidate:
            return _Record("Joe Skerratt suffix")
        if payload == parser_candidate:
            return _Record("Joe Skerratt")
        if payload == synced_candidate:
            return _Record("Joe Skerratt")
        raise AssertionError("unexpected payload")

    monkeypatch.setattr(editor_actions.PlayerRecord, "from_bytes", staticmethod(fake_from_bytes))
    monkeypatch.setattr(
        editor_actions,
        "replace_text_in_decoded",
        lambda *_args, **_kwargs: (text_candidate, True),
    )

    def fake_length_prefixed(**_kwargs):
        raise RuntimeError("Fixed-length rename could not parse given-name slot bounds")

    monkeypatch.setattr(editor_actions, "_mutate_indexed_player_name_fixed_bytes", fake_length_prefixed)
    monkeypatch.setattr(
        editor_actions,
        "_build_parser_fixed_name_candidate",
        lambda **_kwargs: parser_candidate,
    )

    def fake_change_profile(_original, candidate):
        if candidate == parser_candidate:
            return (40, 5, 60)
        if candidate == synced_candidate:
            return (190, 5, 220)
        if candidate == text_candidate:
            return (36, 5, 41)
        return (0, -1, -1)

    monkeypatch.setattr(editor_actions, "_candidate_change_profile", fake_change_profile)
    monkeypatch.setattr(editor_actions, "_sync_fixed_name_aliases", lambda **_kwargs: synced_candidate)

    mutated, applied_name, family = editor_actions._mutate_indexed_player_name_fixed_safe(
        decoded_payload=decoded_payload,
        payload_offset=0,
        new_name="Joe Skerratt",
    )

    assert mutated == parser_candidate
    assert applied_name == "Joe Skerratt"
    assert family == "parser_text_spill_no_alias_sync"


def test_mutate_indexed_player_name_fixed_safe_allows_parser_text_spill_prefix_clip(monkeypatch):
    decoded_payload = b"A" * 700
    text_candidate = b"C" * 700
    parser_candidate = decoded_payload[:5] + (b"B" * 590) + decoded_payload[595:]
    clipped_candidate = decoded_payload[:5] + parser_candidate[5:129] + decoded_payload[129:]

    class _Record:
        def __init__(self, name: str) -> None:
            self.name = name

    def fake_from_bytes(payload, _offset):
        if payload == decoded_payload:
            return _Record("Old Name")
        if payload == text_candidate:
            return _Record("Joe Skerratt suffix")
        if payload == parser_candidate:
            return _Record("Joe Skerratt")
        if payload == clipped_candidate:
            return _Record("Joe Skerratt")
        raise AssertionError("unexpected payload")

    monkeypatch.setattr(editor_actions.PlayerRecord, "from_bytes", staticmethod(fake_from_bytes))
    monkeypatch.setattr(
        editor_actions,
        "replace_text_in_decoded",
        lambda *_args, **_kwargs: (text_candidate, True),
    )

    def fake_length_prefixed(**_kwargs):
        raise RuntimeError("Fixed-length rename could not parse given-name slot bounds")

    monkeypatch.setattr(editor_actions, "_mutate_indexed_player_name_fixed_bytes", fake_length_prefixed)
    monkeypatch.setattr(
        editor_actions,
        "_build_parser_fixed_name_candidate",
        lambda **_kwargs: parser_candidate,
    )
    monkeypatch.setattr(editor_actions, "_sync_fixed_name_aliases", lambda **kwargs: kwargs["payload"])

    mutated, applied_name, family = editor_actions._mutate_indexed_player_name_fixed_safe(
        decoded_payload=decoded_payload,
        payload_offset=0,
        new_name="Joe Skerratt",
    )

    assert mutated == clipped_candidate
    assert applied_name == "Joe Skerratt"
    assert family == "parser_text_spill_prefix_clip"


def test_mutate_indexed_player_name_fixed_safe_keeps_text_spill_guard_for_other_families(monkeypatch):
    decoded_payload = b"decoded_payload_"
    text_candidate = b"text_candidate__"
    parser_candidate = b"parser_candidate"

    class _Record:
        def __init__(self, name: str) -> None:
            self.name = name

    def fake_from_bytes(payload, _offset):
        if payload == decoded_payload:
            return _Record("Old Name")
        if payload == text_candidate:
            return _Record("Joe Skerratt suffix")
        if payload == parser_candidate:
            return _Record("Joe Skerratt")
        raise AssertionError("unexpected payload")

    monkeypatch.setattr(editor_actions.PlayerRecord, "from_bytes", staticmethod(fake_from_bytes))
    monkeypatch.setattr(
        editor_actions,
        "replace_text_in_decoded",
        lambda *_args, **_kwargs: (text_candidate, True),
    )

    def fake_length_prefixed(**_kwargs):
        raise RuntimeError("Fixed-length rename requires valid length-prefixed name slots")

    monkeypatch.setattr(editor_actions, "_mutate_indexed_player_name_fixed_bytes", fake_length_prefixed)
    monkeypatch.setattr(
        editor_actions,
        "_build_parser_fixed_name_candidate",
        lambda **_kwargs: parser_candidate,
    )
    monkeypatch.setattr(
        editor_actions,
        "_candidate_change_profile",
        lambda _original, candidate: (36, 5, 41) if candidate in {text_candidate, parser_candidate} else (0, -1, -1),
    )
    monkeypatch.setattr(editor_actions, "_sync_fixed_name_aliases", lambda **kwargs: kwargs["payload"])

    with pytest.raises(RuntimeError) as exc_info:
        editor_actions._mutate_indexed_player_name_fixed_safe(
            decoded_payload=decoded_payload,
            payload_offset=0,
            new_name="Joe Skerratt",
        )

    assert "parser_candidate:blocked_by_text_replace" in str(exc_info.value)


def test_promote_linked_roster_player_name_bulk_collects_skip_diagnostics(monkeypatch):
    roster = EQLinkedTeamRoster(
        eq_record_id=3425,
        short_name="Stoke C.",
        stadium_name="Britannia",
        full_club_name="Stoke City",
        record_size=128,
        mode_byte=0,
        ent_count=3,
        rows=[
            EQLinkedRosterRow(slot_index=0, flag=0, player_record_id=1001, player_name="Old A", raw_row_offset=10),
            EQLinkedRosterRow(slot_index=1, flag=0, player_record_id=1002, player_name="Old B", raw_row_offset=20),
            EQLinkedRosterRow(slot_index=2, flag=0, player_record_id=1003, player_name="Joe Skerratt", raw_row_offset=30),
        ],
        payload_offset=0,
        payload_length=128,
    )
    monkeypatch.setattr("app.editor_actions.load_eq_linked_team_rosters", lambda **kwargs: [roster])

    def fake_promote_team_roster_player(**kwargs):
        slot_number = int(kwargs["slot_number"])
        if slot_number == 2:
            raise RuntimeError(
                "Fixed-length rename could not produce a safe name mutation candidate for this payload "
                "[length_prefixed:error=invalid bounds]"
            )
        return TeamRosterPlayerPromotionResult(
            team_file=Path(kwargs["team_file"]),
            player_file=Path(kwargs["player_file"]),
            eq_record_id=3425,
            team_name="Stoke C.",
            full_club_name="Stoke City",
            slot_number=slot_number,
            player_record_id=1000 + slot_number,
            old_player_name=f"Old {slot_number}",
            new_player_name=str(kwargs["new_name"]),
            skill_updates_requested={},
            visible_skills_before={},
            visible_skills_after={},
            alias_replacements={"display_name": 1},
            backup_path=None,
            write_changes=False,
            applied_to_disk=False,
            warnings=[],
        )

    monkeypatch.setattr("app.editor_actions.promote_team_roster_player", fake_promote_team_roster_player)

    result = promote_linked_roster_player_name_bulk(
        team_file="DBDAT/EQ98030.FDI",
        player_file="DBDAT/JUG98030.FDI",
        team_query="Stoke",
        new_name="Joe Skerratt",
        slot_limit=3,
        write_changes=False,
    )

    assert result.slot_count == 3
    assert result.matched_slot_count == 1
    assert len(result.promotions) == 1
    assert len(result.skipped_slots) == 2
    by_slot = {item.slot_number: item for item in result.skipped_slots}
    assert by_slot[2].reason_code == "fixed_name_unsafe"
    assert "safe name mutation candidate" in by_slot[2].reason_message
    assert by_slot[3].reason_code == "already_target"
    assert by_slot[3].player_name == "Joe Skerratt"
