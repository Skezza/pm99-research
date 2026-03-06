from argparse import Namespace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.cli as cli
from app.editor_actions import (
    BitmapReferenceFileResult,
    BitmapReferenceHit,
    BitmapReferenceProbeResult,
    DatabaseFileValidation,
    DatabaseValidationResult,
    TeamRosterBatchEditResult,
    TeamRosterBatchPlanRowPreview,
)
from app.main_dat import PM99MainDatFile, PM99MainDatPrefix, PM99PackedDate, load_main_dat


class FakeFDIFile:
    instances = []

    def __init__(self, file_path):
        self.file_path = file_path
        self.modified_records = {}
        self._records = [
            (0x10, SimpleNamespace(team_id=123, name="Old Name", set_name=self._set_name, name_dirty=False)),
        ]
        self.saved = False
        self.__class__.instances.append(self)

    def _set_name(self, new_name):
        self._records[0][1].name = new_name
        self._records[0][1].name_dirty = True

    def load(self):
        return None

    def list_players(self, limit=None):
        return self._records[:limit] if limit else self._records

    def save(self):
        self.saved = True


def test_cmd_search_uses_offset_aware_entries(monkeypatch, capsys):
    entries = [
        SimpleNamespace(offset=0x10, source="scanner", record=SimpleNamespace(name="Alex Smith", team_id=7, squad_number=1)),
        SimpleNamespace(offset=0x20, source="scanner", record=SimpleNamespace(name="Brian Jones", team_id=8, squad_number=2)),
    ]
    monkeypatch.setattr(cli, "gather_player_records", lambda _: (entries, []))

    cli.cmd_search(Namespace(file="dummy.fdi", name="alex", include_uncertain=False, json=False))
    out = capsys.readouterr().out
    assert "0x00000010" in out
    assert "Alex Smith" in out


def test_cmd_validate_database_reports_success(monkeypatch, capsys):
    def fake_validate_database_files(**kwargs):
        assert kwargs == {
            "player_file": "DBDAT/JUG98030.FDI",
            "team_file": "DBDAT/EQ98030.FDI",
            "coach_file": "DBDAT/ENT98030.FDI",
        }
        return SimpleNamespace(
            all_valid=True,
            files=[
                SimpleNamespace(
                    category="players",
                    file_path="DBDAT/JUG98030.FDI",
                    success=True,
                    valid_count=100,
                    uncertain_count=2,
                    detail="re-opened cleanly",
                ),
                SimpleNamespace(
                    category="teams",
                    file_path="DBDAT/EQ98030.FDI",
                    success=True,
                    valid_count=50,
                    uncertain_count=0,
                    detail="re-opened cleanly",
                ),
                SimpleNamespace(
                    category="coaches",
                    file_path="DBDAT/ENT98030.FDI",
                    success=True,
                    valid_count=20,
                    uncertain_count=0,
                    detail="re-opened cleanly",
                ),
            ],
        )

    monkeypatch.setattr(cli, "validate_database_files", fake_validate_database_files)

    cli.cmd_validate_database(
        Namespace(
            players="DBDAT/JUG98030.FDI",
            teams="DBDAT/EQ98030.FDI",
            coaches="DBDAT/ENT98030.FDI",
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert "Database validation: PASS" in out
    assert "players: ok valid=100 uncertain=2" in out
    assert "teams: ok valid=50 uncertain=0" in out
    assert "coaches: ok valid=20 uncertain=0" in out


def test_cmd_search_strict_uses_strict_gatherer(monkeypatch, capsys):
    entries = [
        SimpleNamespace(offset=0x44, source="entry (strict)", record=SimpleNamespace(name="Peter THORNE", team_id=12, squad_number=9)),
    ]
    monkeypatch.setattr(cli, "gather_player_records", lambda _: ([], []))
    monkeypatch.setattr(cli, "gather_player_records_strict", lambda *_args, **_kwargs: (entries, []))

    cli.cmd_search(
        Namespace(
            file="dummy.fdi",
            name="thorne",
            include_uncertain=False,
            json=False,
            strict=True,
            require_team_id=False,
        )
    )
    out = capsys.readouterr().out
    assert "0x00000044" in out
    assert "entry (strict)" in out


def test_cmd_team_search_matches_canonical_alias(monkeypatch, capsys):
    team_entries = [
        SimpleNamespace(
            offset=0x10,
            source="loader",
            record=SimpleNamespace(
                team_id=3937,
                name="Milan",
                full_club_name="Associazione Calcio Milan",
            ),
        ),
        SimpleNamespace(
            offset=0x20,
            source="loader",
            record=SimpleNamespace(
                team_id=1111,
                name="Inter Cardiff",
                full_club_name="Inter Cardiff",
            ),
        ),
    ]
    monkeypatch.setattr(cli, "gather_team_records", lambda _path: (team_entries, []))

    cli.cmd_team_search(
        Namespace(
            file="EQ98030.FDI",
            name="AC Milan",
            include_uncertain=False,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert "Milan" in out
    assert "Inter Cardiff" not in out


def test_cmd_rename_stages_by_offset_not_id(monkeypatch, capsys):
    FakeFDIFile.instances = []
    monkeypatch.setattr(cli, "FDIFile", FakeFDIFile)
    monkeypatch.setattr(cli, "_player_offset_is_writable", lambda *_args, **_kwargs: True)
    captured = {}

    def fake_rename_player_records(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            changes=[SimpleNamespace(offset=0x10, old_name="Old Name", new_name="New Name")],
            matched_count=1,
            valid_count=1,
            uncertain_count=0,
            backup_path="dummy.fdi.backup",
            warnings=[],
        )

    monkeypatch.setattr(cli, "rename_player_records", fake_rename_player_records)

    cli.cmd_rename(Namespace(file="dummy.fdi", id=123, name="New Name", offset=None))
    out = capsys.readouterr().out
    assert captured["file_path"] == "dummy.fdi"
    assert captured["target_old"] == "Old Name"
    assert captured["new_name"] == "New Name"
    assert captured["target_offset"] == 0x10
    assert captured["include_uncertain"] is True
    assert captured["write_changes"] is True
    assert "Renamed 1 player record" in out
    assert "0x00000010" in out


def test_cmd_rename_refuses_non_writable_offset(monkeypatch, capsys):
    FakeFDIFile.instances = []
    monkeypatch.setattr(cli, "FDIFile", FakeFDIFile)
    monkeypatch.setattr(cli, "_player_offset_is_writable", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        cli,
        "rename_player_records",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("rename_player_records should not be called")),
    )

    cli.cmd_rename(Namespace(file="dummy.fdi", id=123, name="New Name", offset=None))
    out = capsys.readouterr().out
    inst = FakeFDIFile.instances[0]
    assert inst.saved is False
    assert inst.modified_records == {}
    assert "Refusing to rename player" in out


def test_cmd_player_rename_runs_post_write_validation_by_default(monkeypatch, capsys):
    captured = {}
    result = SimpleNamespace(
        changes=[SimpleNamespace(offset=0x10, old_name="Old Name", new_name="New Name")],
        matched_count=1,
        valid_count=1,
        uncertain_count=0,
        backup_path=None,
        warnings=[],
        applied_to_disk=True,
    )

    def fake_rename_player_records(**kwargs):
        captured["rename"] = kwargs
        return result

    def fake_validate_database_files(**kwargs):
        captured["validate"] = kwargs
        return SimpleNamespace(
            all_valid=True,
            files=[
                SimpleNamespace(
                    category="players",
                    file_path="DBDAT/JUG98030.FDI",
                    success=True,
                    valid_count=1,
                    uncertain_count=0,
                    detail="re-opened cleanly",
                )
            ],
        )

    monkeypatch.setattr(cli, "rename_player_records", fake_rename_player_records)
    monkeypatch.setattr(cli, "validate_database_files", fake_validate_database_files)

    cli.cmd_player_rename(
        Namespace(
            file="DBDAT/JUG98030.FDI",
            old="Old Name",
            new="New Name",
            include_uncertain=False,
            offset=None,
            dry_run=False,
            skip_validate=False,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert captured["rename"]["write_changes"] is True
    assert captured["validate"] == {
        "player_file": "DBDAT/JUG98030.FDI",
        "team_file": None,
        "coach_file": None,
    }
    assert result.post_write_validation.all_valid is True
    assert "Renamed 1 player record" in out
    assert "Database validation: PASS" in out


def test_cmd_player_rename_can_skip_post_write_validation(monkeypatch, capsys):
    result = SimpleNamespace(
        changes=[SimpleNamespace(offset=0x10, old_name="Old Name", new_name="New Name")],
        matched_count=1,
        valid_count=1,
        uncertain_count=0,
        backup_path=None,
        warnings=[],
        applied_to_disk=True,
    )

    monkeypatch.setattr(cli, "rename_player_records", lambda **_kwargs: result)
    monkeypatch.setattr(
        cli,
        "validate_database_files",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("validate_database_files should not be called")),
    )

    cli.cmd_player_rename(
        Namespace(
            file="DBDAT/JUG98030.FDI",
            old="Old Name",
            new="New Name",
            include_uncertain=False,
            offset=None,
            dry_run=False,
            skip_validate=True,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert "Database validation:" not in out
    assert not hasattr(result, "post_write_validation")


def test_cmd_player_rename_exits_nonzero_when_post_write_validation_fails(monkeypatch, capsys):
    result = SimpleNamespace(
        changes=[SimpleNamespace(offset=0x10, old_name="Old Name", new_name="New Name")],
        matched_count=1,
        valid_count=1,
        uncertain_count=0,
        backup_path=None,
        warnings=[],
        applied_to_disk=True,
    )

    monkeypatch.setattr(cli, "rename_player_records", lambda **_kwargs: result)
    monkeypatch.setattr(
        cli,
        "validate_database_files",
        lambda **_kwargs: SimpleNamespace(
            all_valid=False,
            files=[
                SimpleNamespace(
                    category="players",
                    file_path="DBDAT/JUG98030.FDI",
                    success=False,
                    valid_count=0,
                    uncertain_count=0,
                    detail="broken parse",
                )
            ],
        ),
    )

    with pytest.raises(SystemExit) as excinfo:
        cli.cmd_player_rename(
            Namespace(
                file="DBDAT/JUG98030.FDI",
                old="Old Name",
                new="New Name",
                include_uncertain=False,
                offset=None,
                dry_run=False,
                skip_validate=False,
                json=False,
            )
        )

    out = capsys.readouterr().out
    assert excinfo.value.code == 1
    assert "Database validation: FAIL" in out
    assert "broken parse" in out


def test_cmd_player_edit_stages_requested_metadata_fields(monkeypatch, capsys):
    captured = {}

    def fake_edit_player_metadata_records(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            changes=[
                SimpleNamespace(
                    offset=0x20,
                    name="Paul SCHOLES",
                    changed_fields={"height": (170, 181), "weight": (68, 81)},
                )
            ],
            matched_count=1,
            record_count=7130,
            backup_path=None,
            warnings=[],
        )

    monkeypatch.setattr(cli, "edit_player_metadata_records", fake_edit_player_metadata_records)

    cli.cmd_player_edit(
        Namespace(
            file="DBDAT/JUG98030.FDI",
            name="Paul SCHOLES",
            offset="0x20",
            new_name=None,
            position=None,
            nationality=None,
            dob_day=None,
            dob_month=None,
            dob_year=None,
            height=181,
            weight=81,
            dry_run=True,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert captured["file_path"] == "DBDAT/JUG98030.FDI"
    assert captured["target_name"] == "Paul SCHOLES"
    assert captured["target_offset"] == 0x20
    assert captured["height"] == 181
    assert captured["weight"] == 81
    assert captured["write_changes"] is False
    assert "Staged 1 player record" in out
    assert "weight: 68 -> 81" in out


def test_cmd_player_edit_stages_name_change(monkeypatch, capsys):
    captured = {}

    def fake_edit_player_metadata_records(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            changes=[
                SimpleNamespace(
                    offset=0x20,
                    name="Alan SMITH",
                    changed_fields={"name": ("Paul SCHOLES", "Alan SMITH")},
                )
            ],
            matched_count=1,
            record_count=7130,
            backup_path=None,
            warnings=[],
        )

    monkeypatch.setattr(cli, "edit_player_metadata_records", fake_edit_player_metadata_records)

    cli.cmd_player_edit(
        Namespace(
            file="DBDAT/JUG98030.FDI",
            name="Paul SCHOLES",
            offset="0x20",
            new_name="Alan SMITH",
            position=None,
            nationality=None,
            dob_day=None,
            dob_month=None,
            dob_year=None,
            height=None,
            weight=None,
            dry_run=True,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert captured["new_name"] == "Alan SMITH"
    assert captured["write_changes"] is False
    assert "name: Paul SCHOLES -> Alan SMITH" in out


def test_cmd_player_batch_edit_runs_csv_plan(monkeypatch, capsys, tmp_path):
    captured = {}
    csv_path = tmp_path / "player_plan.csv"
    csv_path.write_text("name,offset,new_name,height\nPaul SCHOLES,0x20,Alan SMITH,181\n", encoding="utf-8")

    def fake_batch_edit_player_metadata_records(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            row_count=1,
            matched_row_count=1,
            record_count=7130,
            csv_path=csv_path,
            changes=[
                SimpleNamespace(
                    offset=0x20,
                    name="Alan SMITH",
                    changed_fields={"name": ("Paul SCHOLES", "Alan SMITH"), "height": (170, 181)},
                )
            ],
            backup_path=None,
            warnings=[],
        )

    monkeypatch.setattr(cli, "batch_edit_player_metadata_records", fake_batch_edit_player_metadata_records)

    cli.cmd_player_batch_edit(
        Namespace(
            file="DBDAT/JUG98030.FDI",
            csv=str(csv_path),
            dry_run=True,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert captured["file_path"] == "DBDAT/JUG98030.FDI"
    assert captured["csv_path"] == str(csv_path)
    assert captured["write_changes"] is False
    assert "Staged 1 player record" in out
    assert f"Plan: {csv_path}" in out
    assert "name: Paul SCHOLES -> Alan SMITH" in out


def test_cmd_team_roster_edit_linked_stages_slot_change(monkeypatch, capsys):
    captured = {}

    def fake_edit_team_roster_eq_jug_linked(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            changes=[
                SimpleNamespace(
                    eq_record_id=341,
                    team_name="Stoke C.",
                    full_club_name="Stoke City",
                    slot_number=1,
                    old_flag=0,
                    new_flag=1,
                    old_player_record_id=1234,
                    new_player_record_id=3384,
                    old_player_name="Old PLAYER",
                    new_player_name="Paul SCHOLES",
                )
            ],
            backup_path=None,
            warnings=[],
        )

    monkeypatch.setattr(cli, "edit_team_roster_eq_jug_linked", fake_edit_team_roster_eq_jug_linked)

    cli.cmd_team_roster_edit_linked(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team="Stoke C.",
            eq_record_id=None,
            slot=1,
            player_id=3384,
            flag=1,
            dry_run=True,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert captured == {
        "team_file": "DBDAT/EQ98030.FDI",
        "player_file": "DBDAT/JUG98030.FDI",
        "team_query": "Stoke C.",
        "eq_record_id": None,
        "slot_number": 1,
        "player_record_id": 3384,
        "flag": 1,
        "write_changes": False,
    }
    assert "Staged 1 parser-backed EQ->JUG linked roster row" in out
    assert "Stoke C. (Stoke City) slot=01" in out
    assert "pid 1234 -> 3384" in out
    assert "flag 0 -> 1" in out


def test_cmd_team_roster_edit_same_entry_stages_slot_change(monkeypatch, capsys):
    captured = {}

    def fake_edit_team_roster_same_entry_authoritative(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            changes=[
                SimpleNamespace(
                    team_offset=0x1C1DBC,
                    team_name="C. At. Madrid",
                    full_club_name="Club Atletico de Madrid",
                    entry_offset=0x6D03,
                    slot_number=2,
                    old_pid_candidate=1234,
                    new_pid_candidate=3384,
                    old_player_name="Old PLAYER",
                    new_player_name="New PLAYER",
                    preserved_tail_bytes_hex="58595a",
                )
            ],
            backup_path=None,
            warnings=[],
        )

    monkeypatch.setattr(cli, "edit_team_roster_same_entry_authoritative", fake_edit_team_roster_same_entry_authoritative)

    cli.cmd_team_roster_edit_same_entry(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team="At. Madrid",
            team_offset="0x1C1DBC",
            slot=2,
            pid=3384,
            dry_run=True,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert captured == {
        "team_file": "DBDAT/EQ98030.FDI",
        "player_file": "DBDAT/JUG98030.FDI",
        "team_query": "At. Madrid",
        "team_offset": 0x1C1DBC,
        "slot_number": 2,
        "pid_candidate": 3384,
        "write_changes": False,
    }
    assert "Staged 1 supported same-entry roster row" in out
    assert "team_offset=0x001C1DBC" in out
    assert "slot=02" in out
    assert "pid 1234 -> 3384" in out
    assert "entry=0x00006D03" in out
    assert "preserved_tail=58595a" in out


def test_cmd_team_roster_promote_player_stages_changes(monkeypatch, capsys):
    captured = {}

    def fake_promote_team_roster_player(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            eq_record_id=341,
            team_name="Stoke C.",
            full_club_name="Stoke City",
            slot_number=13,
            player_record_id=15578,
            old_player_name="Graham KAVANAGH",
            new_player_name="Joe SKERRATT",
            skill_updates_requested={"speed": 99, "stamina": 99},
            visible_skills_before={"speed": 72, "stamina": 65},
            visible_skills_after={"speed": 99, "stamina": 99},
            alias_replacements={"display_name": 1, "surname_title": 2},
            backup_path=None,
            warnings=[],
        )

    monkeypatch.setattr(cli, "promote_team_roster_player", fake_promote_team_roster_player)

    cli.cmd_team_roster_promote_player(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team="Stoke C.",
            eq_record_id=None,
            slot=13,
            new_name="Joe SKERRATT",
            elite_skills=True,
            set_args=[],
            dry_run=True,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert captured == {
        "team_file": "DBDAT/EQ98030.FDI",
        "player_file": "DBDAT/JUG98030.FDI",
        "team_query": "Stoke C.",
        "eq_record_id": None,
        "slot_number": 13,
        "new_name": "Joe SKERRATT",
        "apply_elite_skills": True,
        "skill_updates": {},
        "fixed_name_bytes": False,
        "write_changes": False,
    }
    assert "Staged roster player promotion" in out
    assert "slot=13" in out
    assert "Name: Graham KAVANAGH -> Joe SKERRATT" in out
    assert "Visible stats: speed: 72 -> 99, stamina: 65 -> 99" in out



def test_cmd_team_roster_promote_bulk_name_stages_changes(monkeypatch, capsys):
    captured = {}

    def fake_promote_linked_roster_player_name_bulk(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            eq_record_id=341,
            team_name="Stoke C.",
            full_club_name="Stoke City",
            new_player_name="Joe Skerratt",
            slot_count=25,
            matched_slot_count=25,
            promotions=[
                SimpleNamespace(slot_number=1, old_player_name="Old A", new_player_name="Joe Skerratt"),
                SimpleNamespace(slot_number=2, old_player_name="Old B", new_player_name="Joe Skerratt"),
            ],
            backup_path=None,
            warnings=[],
        )

    monkeypatch.setattr(cli, "promote_linked_roster_player_name_bulk", fake_promote_linked_roster_player_name_bulk)

    cli.cmd_team_roster_promote_bulk_name(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team="Stoke C.",
            eq_record_id=None,
            new_name="Joe Skerratt",
            slot_limit=25,
            elite_skills=False,
            set_args=[],
            dry_run=True,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert captured == {
        "team_file": "DBDAT/EQ98030.FDI",
        "player_file": "DBDAT/JUG98030.FDI",
        "team_query": "Stoke C.",
        "eq_record_id": None,
        "new_name": "Joe Skerratt",
        "slot_limit": 25,
        "apply_elite_skills": False,
        "skill_updates": {},
        "fixed_name_bytes": False,
        "write_changes": False,
    }
    assert "Staged bulk roster promotion" in out
    assert "slots=25/25" in out



def test_cmd_team_roster_promote_player_passes_fixed_name_bytes(monkeypatch, capsys):
    captured = {}

    def fake_promote_team_roster_player(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            eq_record_id=341,
            team_name="Stoke C.",
            full_club_name="Stoke City",
            slot_number=13,
            player_record_id=15578,
            old_player_name="Graham KAVANAGH",
            new_player_name="Joe SKERRATT",
            skill_updates_requested={},
            visible_skills_before={},
            visible_skills_after={},
            alias_replacements={"display_name": 1},
            backup_path=None,
            warnings=[],
        )

    monkeypatch.setattr(cli, "promote_team_roster_player", fake_promote_team_roster_player)

    cli.cmd_team_roster_promote_player(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team="Stoke C.",
            eq_record_id=None,
            slot=13,
            new_name="Joe SKERRATT",
            elite_skills=False,
            set_args=[],
            fixed_name_bytes=True,
            dry_run=True,
            json=False,
        )
    )

    _ = capsys.readouterr().out
    assert captured["fixed_name_bytes"] is True


def test_cmd_team_roster_promote_bulk_name_passes_fixed_name_bytes(monkeypatch, capsys):
    captured = {}

    def fake_promote_linked_roster_player_name_bulk(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            eq_record_id=341,
            team_name="Stoke C.",
            full_club_name="Stoke City",
            new_player_name="Joe Skerratt",
            slot_count=25,
            matched_slot_count=25,
            promotions=[],
            backup_path=None,
            warnings=[],
        )

    monkeypatch.setattr(cli, "promote_linked_roster_player_name_bulk", fake_promote_linked_roster_player_name_bulk)

    cli.cmd_team_roster_promote_bulk_name(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team="Stoke C.",
            eq_record_id=None,
            new_name="Joe Skerratt",
            slot_limit=25,
            elite_skills=False,
            set_args=[],
            fixed_name_bytes=True,
            dry_run=True,
            json=False,
        )
    )

    _ = capsys.readouterr().out
    assert captured["fixed_name_bytes"] is True

def test_cmd_team_roster_promote_bulk_name_prints_skip_diagnostics(monkeypatch, capsys):
    def fake_promote_linked_roster_player_name_bulk(**kwargs):
        return SimpleNamespace(
            eq_record_id=341,
            team_name="Stoke C.",
            full_club_name="Stoke City",
            new_player_name="Joe Skerratt",
            slot_count=4,
            matched_slot_count=2,
            promotions=[
                SimpleNamespace(slot_number=1, old_player_name="Old A", new_player_name="Joe Skerratt"),
                SimpleNamespace(slot_number=3, old_player_name="Old C", new_player_name="Joe Skerratt"),
            ],
            skipped_slots=[
                SimpleNamespace(
                    slot_number=2,
                    player_record_id=9773,
                    player_name="Ray WALLACE",
                    reason_code="fixed_name_unsafe",
                    reason_message="Fixed-length rename could not produce a safe name mutation candidate for this payload",
                )
            ],
            backup_path=None,
            warnings=[],
        )

    monkeypatch.setattr(cli, "promote_linked_roster_player_name_bulk", fake_promote_linked_roster_player_name_bulk)

    cli.cmd_team_roster_promote_bulk_name(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team="Stoke C.",
            eq_record_id=None,
            new_name="Joe Skerratt",
            slot_limit=4,
            elite_skills=False,
            set_args=[],
            fixed_name_bytes=True,
            dry_run=True,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert "Staged bulk roster promotion" in out
    assert "slots=2/4" in out
    assert "Skipped slots: 1" in out
    assert "reason=fixed_name_unsafe" in out


def test_cmd_team_roster_promotion_safety_profiles_skip_reasons(monkeypatch, capsys):
    def fake_promote_linked_roster_player_name_bulk(**kwargs):
        return SimpleNamespace(
            eq_record_id=341,
            team_name="Stoke C.",
            full_club_name="Stoke City",
            new_player_name="Joe Skerratt",
            slot_count=4,
            matched_slot_count=1,
            promotions=[
                SimpleNamespace(
                    slot_number=1,
                    old_player_name="Old A",
                    new_player_name="Joe Skerratt",
                    name_mutation_family="parser_text_spill_salvage",
                ),
            ],
            skipped_slots=[
                SimpleNamespace(
                    slot_number=2,
                    player_record_id=9773,
                    player_name="Ray WALLACE",
                    reason_code="fixed_name_unsafe",
                    reason_message="Fixed-length rename could not produce a safe name mutation candidate",
                ),
                SimpleNamespace(
                    slot_number=3,
                    player_record_id=9774,
                    player_name="Chris SHORT",
                    reason_code="already_target",
                    reason_message="name already matches target",
                ),
                SimpleNamespace(
                    slot_number=4,
                    player_record_id=9775,
                    player_name="Sam BLOCKED",
                    reason_code="promotion_error",
                    reason_message="unexpected parser mismatch",
                ),
            ],
            backup_path=None,
            warnings=[],
        )

    monkeypatch.setattr(cli, "promote_linked_roster_player_name_bulk", fake_promote_linked_roster_player_name_bulk)

    cli.cmd_team_roster_promotion_safety(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team="Stoke C.",
            eq_record_id=None,
            new_name="Joe Skerratt",
            slot_limit=4,
            sample_limit=2,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert "Bulk promotion safety profile" in out
    assert "safe_slots=1/4 skipped=3" in out
    assert "fixed_name_unsafe: 1" in out
    assert "already_target: 1" in out
    assert "promotion_error: 1" in out
    assert "Safe mutation families:" in out
    assert "parser_text_spill_salvage: 1" in out
    assert "Sample skipped slots:" in out


def test_cmd_team_roster_export_template_outputs_summary(monkeypatch, capsys, tmp_path):
    captured = {}

    def fake_export_team_roster_batch_template(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            source="linked",
            team_name="Stoke C.",
            full_club_name="Stoke City",
            row_count=25,
            output_csv=Path(kwargs["output_csv"]),
            eq_record_id=341,
            team_offset=None,
            warnings=[],
        )

    monkeypatch.setattr(cli, "export_team_roster_batch_template", fake_export_team_roster_batch_template)

    csv_path = tmp_path / "stoke_template.csv"
    cli.cmd_team_roster_export_template(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team="Stoke C.",
            eq_record_id=341,
            team_offset=None,
            source="linked",
            csv=str(csv_path),
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert captured == {
        "team_file": "DBDAT/EQ98030.FDI",
        "output_csv": str(csv_path),
        "player_file": "DBDAT/JUG98030.FDI",
        "team_query": "Stoke C.",
        "eq_record_id": 341,
        "team_offset": None,
        "source": "linked",
    }
    assert "Exported roster template" in out
    assert "rows=25" in out

def test_cmd_team_roster_profile_same_entry_prints_tail_buckets(monkeypatch, capsys):
    captured = {}

    def fake_profile_same_entry_authoritative_tail_bytes(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            requested_team_count=2,
            authoritative_team_count=1,
            row_count=3,
            buckets=[
                SimpleNamespace(
                    tail_bytes_hex="58595a",
                    tail_byte_2=0x58,
                    tail_byte_3=0x59,
                    tail_byte_4=0x5A,
                    count=2,
                    sample_teams=["Inline FC"],
                    sample_players=["Old PLAYER"],
                )
            ],
        )

    monkeypatch.setattr(cli, "profile_same_entry_authoritative_tail_bytes", fake_profile_same_entry_authoritative_tail_bytes)

    cli.cmd_team_roster_profile_same_entry(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team=["Inline"],
            limit=5,
            include_fallbacks=False,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert captured == {
        "team_file": "DBDAT/EQ98030.FDI",
        "player_file": "DBDAT/JUG98030.FDI",
        "team_queries": ["Inline"],
        "limit": 5,
        "include_fallbacks": False,
    }
    assert "Authoritative same-entry tail-byte profile" in out
    assert "tail=58595a" in out
    assert "b2=88, b3=89, b4=90" in out
    assert "teams=Inline FC" in out


def test_cmd_team_roster_profile_same_entry_can_include_fallbacks(monkeypatch, capsys):
    captured = {}

    def fake_profile_same_entry_authoritative_tail_bytes(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            requested_team_count=2,
            authoritative_team_count=2,
            row_count=2,
            include_fallbacks=True,
            provenance_counts={
                "known_lineup_anchor_assisted": 1,
                "same_entry_authoritative": 1,
            },
            buckets=[
                SimpleNamespace(
                    provenance="known_lineup_anchor_assisted",
                    tail_bytes_hex="616161",
                    tail_byte_2=0x61,
                    tail_byte_3=0x61,
                    tail_byte_4=0x61,
                    count=1,
                    sample_teams=["Manchester Utd"],
                    sample_players=["Henning BERG"],
                )
            ],
        )

    monkeypatch.setattr(cli, "profile_same_entry_authoritative_tail_bytes", fake_profile_same_entry_authoritative_tail_bytes)

    cli.cmd_team_roster_profile_same_entry(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team=["Manchester Utd"],
            limit=5,
            include_fallbacks=True,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert captured == {
        "team_file": "DBDAT/EQ98030.FDI",
        "player_file": "DBDAT/JUG98030.FDI",
        "team_queries": ["Manchester Utd"],
        "limit": 5,
        "include_fallbacks": True,
    }
    assert "Preferred same-entry tail-byte profile" in out
    assert "provenance_counts=known_lineup_anchor_assisted=1, same_entry_authoritative=1" in out
    assert "provenance=known_lineup_anchor_assisted tail=616161" in out


def test_cmd_team_roster_batch_edit_stages_mixed_changes(monkeypatch, capsys):
    captured = {}

    def fake_batch_edit_team_roster_records(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            linked_changes=[
                SimpleNamespace(
                    eq_record_id=341,
                    team_name="Stoke C.",
                    full_club_name="Stoke City",
                    slot_number=1,
                    old_flag=0,
                    new_flag=1,
                    old_player_record_id=1234,
                    new_player_record_id=3384,
                    old_player_name="Old LINKED",
                    new_player_name="New PLAYER",
                )
            ],
            same_entry_changes=[
                SimpleNamespace(
                    team_offset=0x1111,
                    team_name="Milan",
                    full_club_name="Milan",
                    entry_offset=0x6D03,
                    slot_number=2,
                    old_pid_candidate=2510,
                    new_pid_candidate=2683,
                    old_player_name="Old INLINE",
                    new_player_name="New PLAYER",
                    preserved_tail_bytes_hex="616161",
                )
            ],
            row_count=2,
            matched_row_count=2,
            backup_path=None,
            warnings=[],
        )

    monkeypatch.setattr(cli, "batch_edit_team_roster_records", fake_batch_edit_team_roster_records)

    cli.cmd_team_roster_batch_edit(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            csv="plan.csv",
            dry_run=True,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert captured == {
        "team_file": "DBDAT/EQ98030.FDI",
        "player_file": "DBDAT/JUG98030.FDI",
        "csv_path": "plan.csv",
        "write_changes": False,
    }
    assert "Staged 2 team roster row" in out
    assert "linked=1, same_entry=1" in out
    assert "Stoke C. (Stoke City) slot=01" in out
    assert "team_offset=0x00001111" in out


def test_cmd_team_roster_batch_edit_json_includes_plan_preview(monkeypatch, capsys):
    def fake_batch_edit_team_roster_records(**_kwargs):
        return TeamRosterBatchEditResult(
            file_path=Path("DBDAT/EQ98030.FDI"),
            player_file=Path("DBDAT/JUG98030.FDI"),
            csv_path=Path("plan.csv"),
            linked_changes=[],
            same_entry_changes=[],
            row_count=1,
            matched_row_count=1,
            write_changes=False,
            applied_to_disk=False,
            backup_path=None,
            warnings=[],
            plan_preview=[
                TeamRosterBatchPlanRowPreview(
                    row_number=2,
                    status="no_change",
                    source="linked",
                    team_query="Stoke C.",
                    slot_number=1,
                    diff_summary="Row resolves cleanly but already matches on-disk values",
                )
            ],
        )

    monkeypatch.setattr(cli, "batch_edit_team_roster_records", fake_batch_edit_team_roster_records)

    cli.cmd_team_roster_batch_edit(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            csv="plan.csv",
            dry_run=True,
            json=True,
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert "plan_preview" in payload
    assert payload["plan_preview"][0]["status"] == "no_change"
    assert payload["plan_preview"][0]["team_query"] == "Stoke C."


def test_cmd_bitmap_reference_probe_emits_json(monkeypatch, capsys):
    captured = {}

    def fake_inspect_bitmap_references(**kwargs):
        captured.update(kwargs)
        return BitmapReferenceProbeResult(
            markers=[".BMP", ".TGA"],
            max_hits_per_file=6,
            total_hits=1,
            files=[
                BitmapReferenceFileResult(
                    label="Players",
                    file_path=Path("DBDAT/JUG98030.FDI"),
                    exists=True,
                    read_error="",
                    hit_count=1,
                    hits=[
                        BitmapReferenceHit(
                            offset=0x1234,
                            marker=".BMP",
                            snippet_start=0x1220,
                            snippet_end=0x1240,
                            snippet="...FACE.BMP...",
                        )
                    ],
                )
            ],
        )

    monkeypatch.setattr(cli, "inspect_bitmap_references", fake_inspect_bitmap_references)

    cli.cmd_bitmap_reference_probe(
        Namespace(
            player_file="DBDAT/JUG98030.FDI",
            team_file="DBDAT/EQ98030.FDI",
            coach_file="DBDAT/ENT98030.FDI",
            marker=[".BMP", ".TGA"],
            max_hits=6,
            json=True,
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert captured == {
        "player_file": "DBDAT/JUG98030.FDI",
        "team_file": "DBDAT/EQ98030.FDI",
        "coach_file": "DBDAT/ENT98030.FDI",
        "markers": [".BMP", ".TGA"],
        "max_hits_per_file": 6,
    }
    assert payload["total_hits"] == 1
    assert payload["files"][0]["hits"][0]["marker"] == ".BMP"


def test_cmd_player_name_capacity_emits_json(monkeypatch, capsys):
    captured = {}

    def fake_inspect_player_name_capacities(**kwargs):
        captured.update(kwargs)
        return {
            "file_path": "DBDAT/JUG98030.FDI",
            "record_count": 6688,
            "matched_count": 1,
            "storage_mode": "indexed",
            "target_name": "Bryan SMALL",
            "target_offset": 0x1234,
            "proposed_name": "Joe Skerratt",
            "proposed_name_bytes": 12,
            "limit": 200,
            "truncated": False,
            "records": [
                {
                    "record_id": 3937,
                    "offset": 0x1234,
                    "team_id": 3425,
                    "name": "Bryan SMALL",
                    "source": "indexed-entry",
                    "storage_mode": "indexed",
                    "current_name_bytes": 11,
                    "exact_full_name_max_bytes": 13,
                    "plain_text_max_bytes": 12,
                    "length_prefixed_max_bytes": 13,
                    "structured_window_max_bytes": 11,
                    "can_expand_without_growth": True,
                    "notes": [],
                    "proposed_name": "Joe Skerratt",
                    "proposed_name_bytes": 12,
                    "proposed_within_exact_limit": True,
                    "proposed_may_truncate": True,
                    "proposed_overflow_by": 0,
                }
            ],
        }

    monkeypatch.setattr(cli, "inspect_player_name_capacities", fake_inspect_player_name_capacities)

    cli.cmd_player_name_capacity(
        Namespace(
            file="DBDAT/JUG98030.FDI",
            name="Bryan SMALL",
            offset="0x1234",
            proposed_name="Joe Skerratt",
            include_uncertain=False,
            limit=200,
            json=True,
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert captured == {
        "file_path": "DBDAT/JUG98030.FDI",
        "target_name": "Bryan SMALL",
        "target_offset": 0x1234,
        "proposed_name": "Joe Skerratt",
        "include_uncertain": False,
        "limit": 200,
    }
    assert payload["matched_count"] == 1
    assert payload["records"][0]["proposed_within_exact_limit"] is True


def test_cmd_player_legacy_weight_profile_prints_recommended_offset(monkeypatch, capsys):
    captured = {}

    def fake_profile_player_legacy_weight_candidates(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            record_count=11479,
            candidate_record_count=1382,
            recommended_offset=14,
            height_baseline_exact_ratio=0.4776,
            legacy_valid_record_count=512,
            legacy_slot_record_count=121,
            legacy_matched_record_count=97,
            legacy_exact_match_count=89,
            legacy_exact_match_ratio=0.9175,
            offsets=[
                SimpleNamespace(
                    relative_offset=14,
                    eligible_count=1382,
                    exact_match_count=660,
                    exact_match_ratio=0.4776,
                    mean_abs_error=22.92,
                    top_values=[(30, 547), (72, 51)],
                ),
                SimpleNamespace(
                    relative_offset=17,
                    eligible_count=1382,
                    exact_match_count=0,
                    exact_match_ratio=0.0,
                    mean_abs_error=53.25,
                    top_values=[(0, 660), (35, 131)],
                ),
            ],
        )

    monkeypatch.setattr(cli, "profile_player_legacy_weight_candidates", fake_profile_player_legacy_weight_candidates)

    cli.cmd_player_legacy_weight_profile(
        Namespace(
            file="DBDAT/JUG98030.FDI",
            start_offset=14,
            end_offset=18,
            top_values=8,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert captured == {
        "file_path": "DBDAT/JUG98030.FDI",
        "start_offset": 14,
        "end_offset": 18,
        "top_values": 8,
    }
    assert "Legacy weight candidate profile" in out
    assert "recommended_offset=14" in out
    assert "baseline height@marker+13 exact_ratio=0.4776" in out
    assert "name-only validation: valid_records=512 slot_records=121 matched=97 exact=89 ratio=0.9175" in out
    assert "marker+14: eligible=1382 exact=660 ratio=0.4776" in out


def test_cmd_player_inspect_prints_indexed_metadata(monkeypatch, capsys):
    captured = {}

    def fake_inspect_player_metadata_records(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            record_count=11479,
            records=[
                SimpleNamespace(
                    offset=0x5A8EA,
                    record_id=3384,
                    name="Paul SCHOLES",
                    attribute_prefix=[77, 89, 107],
                    post_weight_byte=30,
                    trailer_byte=19,
                    sidecar_byte=13,
                    indexed_unknown_0=10,
                    indexed_unknown_1=0,
                    face_components=[12, 8, 15, 7],
                    nationality=30,
                    indexed_unknown_9=1,
                    indexed_unknown_10=5,
                    position=2,
                    birth_day=16,
                    birth_month=11,
                    birth_year=1974,
                    height=170,
                    weight=68,
                    suffix_anchor=0x1A,
                )
            ],
        )

    monkeypatch.setattr(cli, "inspect_player_metadata_records", fake_inspect_player_metadata_records)

    cli.cmd_player_inspect(
        Namespace(
            file="DBDAT/JUG98030.FDI",
            name="Paul SCHOLES",
            offset="0x5A8EA",
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert captured["file_path"] == "DBDAT/JUG98030.FDI"
    assert captured["target_name"] == "Paul SCHOLES"
    assert captured["target_offset"] == 0x5A8EA
    assert "Paul SCHOLES" in out
    assert "u0=10" in out
    assert "u1=0" in out
    assert "u9=1" in out
    assert "u10=5" in out
    assert "ht=170" in out
    assert "wt=68" in out
    assert "tail_prefix=[77, 89, 107]" in out
    assert "postwt=30" in out
    assert "posthint=nat-search-mirror" in out
    assert "trail=19" in out
    assert "sidecar=13" in out
    assert "face=[12, 8, 15, 7]" in out
    assert "ui-grey" in out
    assert "red/auburn?" in out


def test_cmd_player_suffix_profile_prints_top_buckets(monkeypatch, capsys):
    captured = {}

    def fake_profile_indexed_player_suffix_bytes(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            record_count=11479,
            anchored_count=1954,
            filtered_count=23,
            nationality_filter=44,
            position_filter=None,
            buckets=[
                SimpleNamespace(
                    indexed_unknown_9=1,
                    indexed_unknown_10=1,
                    count=21,
                    sample_names=["Henning BERG", "Tore KVARME"],
                )
            ],
        )

    monkeypatch.setattr(cli, "profile_indexed_player_suffix_bytes", fake_profile_indexed_player_suffix_bytes)

    cli.cmd_player_suffix_profile(
        Namespace(
            file="DBDAT/JUG98030.FDI",
            nationality=44,
            position=None,
            limit=5,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert captured["file_path"] == "DBDAT/JUG98030.FDI"
    assert captured["nationality"] == 44
    assert captured["position"] is None
    assert captured["limit"] == 5
    assert "nat=44" in out
    assert "u9=1 u10=1" in out
    assert "count=21" in out
    assert "Henning BERG" in out
    assert "fair/blond?" in out


def test_cmd_player_leading_profile_prints_top_buckets(monkeypatch, capsys):
    captured = {}

    def fake_profile_indexed_player_leading_bytes(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            record_count=11479,
            anchored_count=1954,
            filtered_count=495,
            nationality_filter=None,
            position_filter=None,
            indexed_unknown_0_filter=None,
            indexed_unknown_1_filter=1,
            indexed_unknown_9_filter=None,
            indexed_unknown_10_filter=None,
            position_counts=[(1, 167), (3, 143), (2, 135), (0, 50)],
            nationality_counts=[(30, 324), (45, 25), (19, 23)],
            buckets=[
                SimpleNamespace(
                    indexed_unknown_0=19,
                    indexed_unknown_1=1,
                    count=32,
                    sample_names=["Craig MOORE", "Pavel SRNICEK"],
                )
            ],
        )

    monkeypatch.setattr(cli, "profile_indexed_player_leading_bytes", fake_profile_indexed_player_leading_bytes)

    cli.cmd_player_leading_profile(
        Namespace(
            file="DBDAT/JUG98030.FDI",
            nationality=None,
            position=None,
            u0=None,
            u1=1,
            u9=None,
            u10=None,
            limit=5,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert captured["file_path"] == "DBDAT/JUG98030.FDI"
    assert captured["nationality"] is None
    assert captured["position"] is None
    assert captured["indexed_unknown_0"] is None
    assert captured["indexed_unknown_1"] == 1
    assert captured["indexed_unknown_9"] is None
    assert captured["indexed_unknown_10"] is None
    assert captured["limit"] == 5
    assert "u1=1" in out
    assert "positions=pos=1(167), pos=3(143), pos=2(135), pos=0(50)" in out
    assert "nationalities=nat=30(324), nat=45(25), nat=19(23)" in out
    assert "u0=19 u1=1" in out
    assert "count=32" in out
    assert "Craig MOORE" in out
    assert "ui-green" in out


def test_cmd_player_tail_prefix_profile_prints_top_buckets(monkeypatch, capsys):
    captured = {}

    def fake_profile_indexed_player_attribute_prefixes(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            record_count=11479,
            anchored_count=1954,
            filtered_count=4,
            nationality_filter=30,
            position_filter=2,
            indexed_unknown_0_filter=10,
            indexed_unknown_1_filter=0,
            indexed_unknown_9_filter=1,
            indexed_unknown_10_filter=5,
            attribute_0_filter=77,
            attribute_1_filter=89,
            attribute_2_filter=107,
            post_weight_byte_filter=30,
            trailer_byte_filter=19,
            sidecar_byte_filter=13,
            layout_verified_count=4,
            layout_mismatch_count=0,
            attribute_0_counts=[(77, 4)],
            attribute_1_counts=[(89, 4)],
            attribute_2_counts=[(107, 4)],
            post_weight_byte_counts=[(30, 4)],
            post_weight_nationality_eligible_count=4,
            post_weight_nationality_match_count=4,
            post_weight_nationality_match_ratio=1.0,
            post_weight_divergent_counts=[(30, 3)],
            post_weight_nationality_mismatch_pairs=[(30, 31, 2), (30, 45, 1)],
            post_weight_group_clusters=[
                SimpleNamespace(
                    post_weight_byte=30,
                    total_count=3,
                    nationality_counts=[(31, 2), (45, 1)],
                    sample_names=["Mark KENNEDY", "Iwan ROBERTS"],
                )
            ],
            trailer_byte_counts=[(19, 4)],
            sidecar_byte_counts=[(13, 4)],
            buckets=[
                SimpleNamespace(
                    attribute_0=77,
                    attribute_1=89,
                    attribute_2=107,
                    count=4,
                    sample_names=["Paul SCHOLES"],
                )
            ],
            signature_buckets=[
                SimpleNamespace(
                    attribute_0=77,
                    attribute_1=89,
                    attribute_2=107,
                    trailer_byte=19,
                    sidecar_byte=13,
                    count=4,
                    sample_names=["Paul SCHOLES"],
                )
            ],
        )

    monkeypatch.setattr(cli, "profile_indexed_player_attribute_prefixes", fake_profile_indexed_player_attribute_prefixes)

    cli.cmd_player_tail_prefix_profile(
        Namespace(
            file="DBDAT/JUG98030.FDI",
            nationality=30,
            position=2,
            u0=10,
            u1=0,
            u9=1,
            u10=5,
            a0=77,
            a1=89,
            a2=107,
            post_weight=30,
            trail=19,
            sidecar=13,
            limit=5,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert captured["file_path"] == "DBDAT/JUG98030.FDI"
    assert captured["nationality"] == 30
    assert captured["position"] == 2
    assert captured["indexed_unknown_0"] == 10
    assert captured["indexed_unknown_1"] == 0
    assert captured["indexed_unknown_9"] == 1
    assert captured["indexed_unknown_10"] == 5
    assert captured["attribute_0"] == 77
    assert captured["attribute_1"] == 89
    assert captured["attribute_2"] == 107
    assert captured["post_weight_byte"] == 30
    assert captured["trailer_byte"] == 19
    assert captured["sidecar_byte"] == 13
    assert captured["limit"] == 5
    assert "nat=30" in out
    assert "u0=10" in out
    assert "u9=1" in out
    assert "a0=77" in out
    assert "a1=89" in out
    assert "a2=107" in out
    assert "postwt=30" in out
    assert "trail=19" in out
    assert "sidecar=13" in out
    assert "structural signature" in out
    assert "layout=verified=4 mismatch=0" in out
    assert "attr0=a0=77(4)" in out
    assert "attr1=a1=89(4)" in out
    assert "attr2=a2=107(4)" in out
    assert "post_weight=postwt=30(4)" in out
    assert "post_weight_vs_nat=match=4/4 ratio=1.0000" in out
    assert "post_weight_group_keys=postwt=30(3)" in out
    assert "post_weight_mismatches=postwt=30->nat=31(2), postwt=30->nat=45(1)" in out
    assert "post_weight_group_clusters=postwt=30[3]: nat=31(2), nat=45(1)" in out
    assert "trailer=trail=19(4)" in out
    assert "sidecar0=13(4)" in out
    assert "tail_prefix=[77, 89, 107]: count=4" in out
    assert "tail_signature=[77, 89, 107 | trail=19 sidecar=13]: count=4" in out
    assert "Paul SCHOLES" in out


def test_cmd_player_leading_profile_prints_guard_hints(monkeypatch, capsys):
    def fake_profile_indexed_player_leading_bytes(**kwargs):
        return SimpleNamespace(
            record_count=11479,
            anchored_count=1954,
            filtered_count=1,
            nationality_filter=None,
            position_filter=None,
            indexed_unknown_0_filter=None,
            indexed_unknown_1_filter=None,
            indexed_unknown_9_filter=None,
            indexed_unknown_10_filter=None,
            position_counts=[],
            nationality_counts=[],
            buckets=[
                SimpleNamespace(
                    indexed_unknown_0=0x63,
                    indexed_unknown_1=3,
                    count=1,
                    sample_names=["Sentinel PLAYER"],
                )
            ],
        )

    monkeypatch.setattr(cli, "profile_indexed_player_leading_bytes", fake_profile_indexed_player_leading_bytes)

    cli.cmd_player_leading_profile(
        Namespace(
            file="DBDAT/JUG98030.FDI",
            nationality=None,
            position=None,
            u0=None,
            u1=None,
            u9=None,
            u10=None,
            limit=5,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert "u0=99 u1=3" in out
    assert "guard=u0-reserved?+u1-excluded?" in out


def test_build_club_index_rows_aggregates_and_ranks():
    strict_hits = [
        {
            "name": "Peter THORNE",
            "offset": 0x100,
            "team_id": 0,
            "target_mentions": ["Stoke City (97)", "Stoke City"],
            "association_type": "strict_subrecord_context",
            "confidence_score": 0.88,
            "confidence_band": "high",
        },
    ]
    heuristic_hits = [
        {
            "name": "Peter THORNE",
            "offset": 0x200,
            "team_id": 0,
            "target_mentions": ["Stoke City"],
            "association_type": "heuristic_blob_context",
            "confidence_score": 0.41,
            "confidence_band": "low",
        },
        {
            "name": "Someone Else",
            "offset": 0x300,
            "team_id": 12,
            "target_mentions": ["Stoke City"],
            "association_type": "heuristic_blob_context",
            "confidence_score": 0.65,
            "confidence_band": "medium",
        },
    ]

    rows = cli._build_club_index_rows("Stoke City", strict_hits, heuristic_hits)

    assert [row["player_name"] for row in rows] == ["Peter THORNE", "Someone Else"]
    peter = rows[0]
    assert peter["club_normalized"] == "Stoke City"
    assert peter["evidence_count"] == 2
    assert peter["strict_evidence_count"] == 1
    assert peter["heuristic_evidence_count"] == 1
    assert peter["best_confidence_band"] == "high"
    assert peter["mentions"] == ["Stoke City"]
    assert peter["offsets"] == [0x100, 0x200]


def test_resolve_club_query_to_teams_matches_exact(monkeypatch):
    team_entries = [
        SimpleNamespace(
            offset=0x10,
            source="loader",
            record=SimpleNamespace(team_id=77, name="Stoke City"),
        ),
        SimpleNamespace(
            offset=0x20,
            source="loader",
            record=SimpleNamespace(team_id=88, name="Swindon Town"),
        ),
    ]
    monkeypatch.setattr(cli, "gather_team_records", lambda _path: (team_entries, []))

    rows = cli._resolve_club_query_to_teams("Stoke City (97)", "EQ98030.FDI")

    assert len(rows) == 1
    assert rows[0]["team_id"] == 77
    assert rows[0]["match_kind"] == "exact"
    assert rows[0]["match_score"] == 1.0


def test_export_club_investigate_csv_and_json(tmp_path):
    payload = {
        "club_index": [
            {
                "club_query": "Stoke City",
                "club_normalized": "Stoke City",
                "player_name": "Peter THORNE",
                "best_confidence_score": 0.42,
                "best_confidence_band": "low",
                "best_association_type": "heuristic_blob_context",
                "best_offset": 0x1C1DBC,
                "evidence_count": 1,
                "strict_evidence_count": 0,
                "heuristic_evidence_count": 1,
                "team_ids": [],
                "mentions": ["Stoke City"],
            }
        ]
    }

    csv_path = tmp_path / "stoke.csv"
    json_path = tmp_path / "stoke.json"

    written_csv = cli._export_club_investigate(payload, str(csv_path))
    written_json = cli._export_club_investigate(payload, str(json_path))

    assert written_csv == csv_path
    assert written_json == json_path
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "player_name" in csv_text
    assert "Peter THORNE" in csv_text
    assert "0x001C1DBC" in csv_text
    json_text = json_path.read_text(encoding="utf-8")
    assert "Peter THORNE" in json_text


def test_cmd_main_dat_inspect_emits_json(tmp_path, capsys):
    file_path = tmp_path / "main.dat"
    payload = PM99MainDatFile(
        prefix=PM99MainDatPrefix(
            header_version=0x1E,
            format_version=0x0C,
            primary_label="Slot A",
            secondary_label="Profile A",
            save_date=PM99PackedDate(day=27, month=2, year=2026),
            hour=18,
            minute=5,
            flag_bytes=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
            scalar_byte=11,
        ),
        opaque_tail=b"\xAA\xBB",
    )
    file_path.write_bytes(payload.to_bytes())

    cli.cmd_main_dat_inspect(Namespace(file=str(file_path), json=True))

    out = capsys.readouterr().out
    assert '"header_version": 30' in out
    assert '"header_matches_expected": true' in out
    assert '"opaque_tail_size": 2' in out


def test_cmd_main_dat_edit_writes_copy_and_preserves_tail(tmp_path, capsys):
    file_path = tmp_path / "main.dat"
    payload = PM99MainDatFile(
        prefix=PM99MainDatPrefix(
            header_version=0x1E,
            format_version=0x0C,
            primary_label="Slot A",
            secondary_label="Profile A",
            save_date=PM99PackedDate(day=27, month=2, year=2026),
            hour=18,
            minute=5,
            flag_bytes=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
            scalar_byte=11,
        ),
        opaque_tail=b"\xAA\xBB\xCC\xDD",
    )
    file_path.write_bytes(payload.to_bytes())

    cli.cmd_main_dat_edit(
        Namespace(
            file=str(file_path),
            primary_label="Edited Slot",
            secondary_label=None,
            day=None,
            month=None,
            year=None,
            hour=21,
            minute=9,
            scalar_byte=12,
            flag_byte=["0=7", "9=0xEE"],
            output_file=None,
            in_place=False,
            no_backup=False,
            json=False,
        )
    )

    out = capsys.readouterr().out
    edited_path = tmp_path / "main.edited.dat"
    assert "Changed fields:" in out
    assert edited_path.exists()

    edited = load_main_dat(edited_path)
    original = load_main_dat(file_path)
    assert edited.prefix.primary_label == "Edited Slot"
    assert edited.prefix.hour == 21
    assert edited.prefix.minute == 9
    assert edited.prefix.scalar_byte == 12
    assert edited.prefix.flag_bytes[0] == 7
    assert edited.prefix.flag_bytes[9] == 0xEE
    assert edited.opaque_tail == original.opaque_tail


def test_club_query_aliases_include_root_and_abbrev():
    aliases = cli._club_query_aliases("Stoke City")
    assert "Stoke City" in aliases
    assert "Stoke" in aliases
    assert any(a in aliases for a in ("Stoke C.", "Stoke C"))

    qpr_aliases = cli._club_query_aliases("Queens Park Rangers")
    assert "QPR" in qpr_aliases
    assert "Q.P.R." in qpr_aliases

    wba_aliases = cli._club_query_aliases("West Bromwich Albion")
    assert "WBA" in wba_aliases


def test_extract_query_mentions_finds_abbrev_and_root():
    text = "Some text ... Stoke C. (98) ... later Stoke ... end"
    center = text.index("later")
    aliases = cli._club_query_aliases("Stoke City")
    mentions = cli._extract_query_mentions(text, center, aliases, window=200, limit=10)
    matched_texts = [m["text"] for m in mentions]
    assert any("Stoke C" in t for t in matched_texts)
    assert any(t.lower() == "stoke" for t in matched_texts)


def test_cmd_roster_reconcile_pdf_delegates_to_shared_module(monkeypatch):
    import app.roster_reconcile as roster_reconcile

    calls = {}
    fake_result = SimpleNamespace(pdf_rows=2, teams=1, summary_counts={"isolated_default": 1}, team_summaries=[])

    def fake_reconcile_pdf_rosters(**kwargs):
        calls["reconcile"] = kwargs
        return fake_result

    def fake_write_reconcile_outputs(result, **kwargs):
        calls["write"] = {"result": result, **kwargs}

    def fake_print_reconcile_run_summary(result, top_n=10):
        calls["print"] = {"result": result, "top_n": top_n}

    monkeypatch.setattr(roster_reconcile, "reconcile_pdf_rosters", fake_reconcile_pdf_rosters)
    monkeypatch.setattr(roster_reconcile, "write_reconcile_outputs", fake_write_reconcile_outputs)
    monkeypatch.setattr(roster_reconcile, "print_reconcile_run_summary", fake_print_reconcile_run_summary)

    cli.cmd_roster_reconcile_pdf(
        Namespace(
            pdf="/tmp/test.pdf",
            player_file="DBDAT/JUG98030.FDI",
            default_window=800,
            wide_window=10000,
            json_output="/tmp/out.json",
            csv_output="/tmp/out.csv",
            team_summary_csv="/tmp/teams.csv",
            team="Stoke City",
            name_hints=None,
        )
    )

    assert calls["reconcile"] == {
        "pdf_path": "/tmp/test.pdf",
        "player_file": "DBDAT/JUG98030.FDI",
        "default_window": 800,
        "wide_window": 10000,
        "team_filter": "Stoke City",
        "name_hints_path": None,
    }
    assert calls["write"]["result"] is fake_result
    assert calls["write"]["json_output"] == "/tmp/out.json"
    assert calls["write"]["csv_output"] == "/tmp/out.csv"
    assert calls["write"]["team_summary_csv"] == "/tmp/teams.csv"
    assert calls["print"]["result"] is fake_result


def test_cmd_player_skill_patch_delegates_to_dd6361_probe(monkeypatch, capsys, tmp_path):
    calls = {}

    def fake_parse_assignments(items):
        calls["parse"] = list(items)
        return {"speed": 91, "passing": 91}

    def fake_patch_action(**kwargs):
        calls["patch"] = kwargs
        return SimpleNamespace(
            resolved_bio_name="David Robert BECKHAM",
            output_file=kwargs["output_file"],
            backup_path=None,
            updates_requested={"speed": 91, "passing": 91},
            mapped10_order=["speed", "stamina", "passing"],
            mapped10_before={"speed": 90, "stamina": 85, "passing": 90},
            mapped10_after={"speed": 91, "stamina": 85, "passing": 91},
            verification_all_requested_fields_match=True,
            touched_entry_offsets=[0x1234, 0x5678],
            raw_payload={"ok": True},
        )

    monkeypatch.setattr(cli, "parse_player_skill_patch_assignments", fake_parse_assignments)
    monkeypatch.setattr(cli, "patch_player_visible_skills_dd6361", fake_patch_action)

    output_file = tmp_path / "beckham_patched.fdi"
    report_file = tmp_path / "beckham_patched.json"
    cli.cmd_player_skill_patch(
        Namespace(
            file="DBDAT/JUG98030.FDI",
            name="Beckham",
            set_args=["speed=91", "passing=91"],
            output_file=str(output_file),
            in_place=False,
            no_backup=False,
            json_output=str(report_file),
            skip_validate=True,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert calls["parse"] == ["speed=91", "passing=91"]
    assert calls["patch"] == {
        "file_path": "DBDAT/JUG98030.FDI",
        "player_name": "Beckham",
        "updates": {"speed": 91, "passing": 91},
        "output_file": str(output_file),
        "in_place": False,
        "create_backup_before_write": False,
        "json_output": str(report_file),
    }
    assert "David Robert BECKHAM" in out
    assert "speed: 90 -> 91" in out
    assert "passing: 90 -> 91" in out
    assert "Verification: ok" in out


def test_cmd_player_skill_patch_in_place_enables_backup(monkeypatch, capsys):
    calls = {}

    monkeypatch.setattr(cli, "parse_player_skill_patch_assignments", lambda items: {"speed": 91})

    def fake_patch_action(**kwargs):
        calls["patch"] = kwargs
        return SimpleNamespace(
            resolved_bio_name="David Robert BECKHAM",
            output_file=kwargs["file_path"],
            backup_path=str(kwargs["file_path"]) + ".backup",
            updates_requested={"speed": 91},
            mapped10_order=["speed"],
            mapped10_before={"speed": 90},
            mapped10_after={"speed": 91},
            verification_all_requested_fields_match=True,
            touched_entry_offsets=[0x1234],
            raw_payload={"ok": True},
        )

    monkeypatch.setattr(cli, "patch_player_visible_skills_dd6361", fake_patch_action)

    cli.cmd_player_skill_patch(
        Namespace(
            file="DBDAT/JUG98030.FDI",
            name="Beckham",
            set_args=["speed=91"],
            output_file=None,
            in_place=True,
            no_backup=False,
            json_output=None,
            skip_validate=True,
            json=False,
        )
    )

    assert calls["patch"]["output_file"] is None
    assert calls["patch"]["in_place"] is True
    assert calls["patch"]["create_backup_before_write"] is True
    out = capsys.readouterr().out
    assert "Backup:" in out


def test_cmd_player_skill_patch_rejects_no_backup_without_in_place(capsys):
    with pytest.raises(SystemExit):
        cli.cmd_player_skill_patch(
            Namespace(
                file="DBDAT/JUG98030.FDI",
                name="Beckham",
                set_args=["speed=91"],
                output_file=None,
                in_place=False,
                no_backup=True,
                json_output=None,
                skip_validate=True,
                json=False,
            )
        )
    err = capsys.readouterr().err
    assert "--no-backup only applies with --in-place" in err


def test_cmd_player_skill_patch_json_includes_post_write_validation(monkeypatch, tmp_path):
    captured = {}
    output_file = tmp_path / "beckham_patched.fdi"

    monkeypatch.setattr(cli, "parse_player_skill_patch_assignments", lambda items: {"speed": 91})
    monkeypatch.setattr(
        cli,
        "patch_player_visible_skills_dd6361",
        lambda **kwargs: SimpleNamespace(
            output_file=Path(kwargs["output_file"]),
            raw_payload={"ok": True},
        ),
    )
    monkeypatch.setattr(
        cli,
        "validate_database_files",
        lambda **kwargs: captured.setdefault(
            "validation",
            {
                "args": kwargs,
                "result": DatabaseValidationResult(
                    all_valid=True,
                    files=[
                        DatabaseFileValidation(
                            category="players",
                            file_path=Path(output_file),
                            success=True,
                            valid_count=1,
                            uncertain_count=0,
                            detail="re-opened cleanly",
                        )
                    ],
                ),
            },
        )["result"],
    )
    monkeypatch.setattr(
        cli,
        "_emit",
        lambda value, as_json=False: captured.setdefault("emit", {"value": value, "as_json": as_json}),
    )

    cli.cmd_player_skill_patch(
        Namespace(
            file="DBDAT/JUG98030.FDI",
            name="Beckham",
            set_args=["speed=91"],
            output_file=str(output_file),
            in_place=False,
            no_backup=False,
            json_output=None,
            skip_validate=False,
            json=True,
        )
    )

    assert captured["validation"]["args"] == {
        "player_file": str(output_file),
        "team_file": None,
        "coach_file": None,
    }
    assert captured["emit"]["as_json"] is True
    assert captured["emit"]["value"]["ok"] is True
    assert captured["emit"]["value"]["post_write_validation"]["all_valid"] is True


def test_cmd_team_roster_extract_delegates_to_shared_action(monkeypatch, capsys, tmp_path):
    calls = {}
    def fake_extract_linked(**kwargs):
        calls["extract"] = kwargs
        return [
            {
                "provenance": "eq_jug_linked_parser",
                "team_name": "Stoke C",
                "full_club_name": "Stoke City",
                "eq_record_id": 99,
                "mode_byte": 1,
                "ent_count": 1,
                "rows": [
                    {"slot_index": 0, "flag": 0, "pid": 15578, "player_name": "Graham KAVANAGH"},
                    {"slot_index": 1, "flag": 0, "pid": 32960, "player_name": "Scott James TAYLOR"},
                ],
            }
        ]

    def fail_overlap(**kwargs):
        raise AssertionError("heuristic extractor should not be used in authoritative mode")

    monkeypatch.setattr(cli, "extract_team_rosters_eq_jug_linked", fake_extract_linked)
    monkeypatch.setattr(cli, "extract_team_rosters_eq_same_entry_overlap", fail_overlap)

    report_file = tmp_path / "team_roster_report.json"
    cli.cmd_team_roster_extract(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team=["Stoke"],
            top_examples=10,
            row_limit=10,
            include_fallbacks=False,
            json_output=str(report_file),
            json=False,
        )
    )

    assert calls["extract"] == {
        "team_file": "DBDAT/EQ98030.FDI",
        "player_file": "DBDAT/JUG98030.FDI",
        "team_queries": ["Stoke"],
    }
    out = capsys.readouterr().out
    assert "Selection mode: authoritative_only" in out
    assert "Stoke C (Stoke City): provenance=eq_jug_linked_parser" in out
    assert "slot=01 pid=15578 flag=0 Graham KAVANAGH" in out
    assert "Report:" in out
    assert '"team_name": "Stoke C"' in report_file.read_text(encoding="utf-8")


def test_cmd_team_roster_extract_json_passthrough(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "extract_team_rosters_eq_jug_linked",
        lambda **kwargs: [{"hello": "world"}],
    )

    cli.cmd_team_roster_extract(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team=[],
            top_examples=15,
            row_limit=25,
            include_fallbacks=False,
            json_output=None,
            json=True,
        )
    )

    out = capsys.readouterr().out
    assert '"hello": "world"' in out


def test_cmd_team_roster_linked_prints_parser_backed_rows(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "extract_team_rosters_eq_jug_linked",
        lambda **kwargs: [
            {
                "provenance": "eq_jug_linked_parser",
                "team_name": "Inter",
                "full_club_name": "Internazionale Milano Football Club",
                "eq_record_id": 12,
                "mode_byte": 1,
                "ent_count": 1,
                "rows": [
                    {"slot_index": 0, "flag": 0, "pid": 3937, "player_name": "Demo PLAYER"},
                    {"slot_index": 1, "flag": 1, "pid": 4000, "player_name": ""},
                ],
            }
        ],
    )

    cli.cmd_team_roster_linked(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team=["Inter Milan"],
            row_limit=10,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert "Inter (Internazionale Milano Football Club): provenance=eq_jug_linked_parser" in out
    assert "slot=01 pid= 3937 flag=0 Demo PLAYER" in out
    assert "slot=02 pid= 4000 flag=1 (name unresolved)" in out


def test_cmd_team_roster_linked_json_passthrough(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "extract_team_rosters_eq_jug_linked",
        lambda **kwargs: [{"team_name": "Inter", "rows": []}],
    )

    cli.cmd_team_roster_linked(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team=[],
            row_limit=25,
            json=True,
        )
    )

    out = capsys.readouterr().out
    assert '"team_name": "Inter"' in out


def test_team_query_matches_canonical_alias_without_broad_false_positive():
    from app.editor_helpers import team_query_matches

    assert team_query_matches(
        "Inter Milan",
        team_name="Inter",
        full_club_name="Internazionale Milano Football Club",
    )
    assert not team_query_matches(
        "Inter Milan",
        team_name="Inter Cardiff",
        full_club_name="Inter Cardiff",
    )


def test_cmd_team_roster_extract_prints_heuristic_candidate_warning(monkeypatch, capsys):
    fake_result = SimpleNamespace(
        team_count=532,
        dd6361_pid_name_count=2009,
        same_entry_overlap_coverage={
            "status_counts": {"perfect_same_entry_run_overlap": 487, "weak_same_entry_overlap": 23},
            "strong_or_better_count": 487,
            "strong_or_better_ratio": 0.9154,
        },
        final_extraction_coverage={
            "covered_count": 508,
            "covered_ratio": 0.955,
            "circular_shift_fallback_count": 21,
            "guarded_covered_count": 507,
            "guarded_covered_ratio": 0.953,
            "circular_shift_flagged_anchor_collision_count": 1,
        },
        requested_team_results=[
            {
                "team_name": "Middlesbrough",
                "full_club_name": "Middlesbrough Football Club",
                "team_id": 4449,
                "team_offset": 0x1AD03,
                "status": "weak_same_entry_overlap",
                "circular_shift_candidate_status": "order_fallback_circular_shift_same_entry_run",
                "heuristic_warnings": [
                    {
                        "type": "known_lineup_anchor_collision",
                        "dataset_key": "manutd",
                        "message": "Candidate run overlaps known lineup anchor 'manutd' (18/18 anchor PIDs)",
                    }
                ],
                "containing_entry": {"entry_offset": 0x15B3C, "length": 21504},
                "top_run_match": {
                    "run_index": 2,
                    "overlap_hits_in_team_raw": 1,
                    "non_empty_row_count": 27,
                    "second_best_overlap_hits": 1,
                    "rows": [],
                },
                "circular_shift_candidate_match": {
                    "run_index": 0,
                    "non_empty_row_count": 23,
                    "selection_method": "circular_shift_same_entry",
                    "rows": [],
                },
            }
        ],
        raw_payload={"ok": True},
    )
    monkeypatch.setattr(cli, "extract_team_rosters_eq_same_entry_overlap", lambda **kwargs: fake_result)

    cli.cmd_team_roster_extract(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team=["Middlesbrough"],
            top_examples=15,
            row_limit=10,
            include_fallbacks=True,
            json_output=None,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert "Heuristic candidate coverage" in out
    assert "Guarded heuristic coverage" in out
    assert "WARNING Candidate run overlaps known lineup anchor 'manutd'" in out
    assert "candidate_run index=0" in out


def test_cmd_team_roster_extract_default_authoritative_hides_fallback_sections(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "extract_team_rosters_eq_jug_linked",
        lambda **kwargs: [
            {
                "provenance": "eq_jug_linked_parser",
                "team_name": "Middlesbrough",
                "full_club_name": "Middlesbrough Football Club",
                "eq_record_id": 4449,
                "mode_byte": 0,
                "ent_count": 1,
                "rows": [],
            }
        ],
    )
    monkeypatch.setattr(
        cli,
        "extract_team_rosters_eq_same_entry_overlap",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("heuristic extractor should not be used")),
    )

    cli.cmd_team_roster_extract(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team=["Middlesbrough"],
            top_examples=15,
            row_limit=10,
            include_fallbacks=False,
            json_output=None,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert "Selection mode: authoritative_only" in out
    assert "Middlesbrough (Middlesbrough Football Club): provenance=eq_jug_linked_parser" in out
    assert "Heuristic candidate coverage" not in out
    assert "candidate_run index=0" not in out


def test_cmd_team_roster_extract_prints_anchor_assisted_window(monkeypatch, capsys):
    fake_result = SimpleNamespace(
        team_count=532,
        dd6361_pid_name_count=2009,
        same_entry_overlap_coverage={},
        final_extraction_coverage={},
        requested_team_results=[
            {
                "team_name": "Manchester Utd",
                "full_club_name": "Manchester United F. C",
                "team_id": 0,
                "team_offset": 0x1580B,
                "status": "moderate_same_entry_overlap",
                "containing_entry": {"entry_offset": 0x6D03, "length": 60928},
                "top_run_match": {
                    "run_index": 7,
                    "overlap_hits_in_team_raw": 6,
                    "non_empty_row_count": 11,
                    "second_best_overlap_hits": 5,
                    "rows": [],
                },
                "known_lineup_anchor_assisted_match": {
                    "dataset_key": "manutd",
                    "entry_offset": 0x15B3C,
                    "hit_count": 18,
                    "exact_anchor_count": 18,
                    "stride5_window": {
                        "delta_positions": [5, 5, 5, 5],
                        "rows": [
                            {
                                "pid_candidate": 3385,
                                "dd6361_name": "David Robert BECKHAM",
                                "is_empty_slot": False,
                                "is_anchor_pid": True,
                            },
                            {
                                "pid_candidate": 8434,
                                "dd6361_name": "Philip John NEVILLE",
                                "is_empty_slot": False,
                                "is_anchor_pid": False,
                            },
                        ],
                    },
                },
            }
        ],
        raw_payload={"ok": True},
    )
    monkeypatch.setattr(cli, "extract_team_rosters_eq_same_entry_overlap", lambda **kwargs: fake_result)

    cli.cmd_team_roster_extract(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team=["Manchester Utd"],
            top_examples=15,
            row_limit=10,
            include_fallbacks=True,
            json_output=None,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert "anchor_assisted dataset=manutd" in out
    assert "anchor_run_window rows=2" in out
    assert "A pid= 3385  David Robert BECKHAM" in out


def test_cmd_team_roster_extract_prints_pseudo_adjacent_candidate(monkeypatch, capsys):
    fake_result = SimpleNamespace(
        team_count=532,
        dd6361_pid_name_count=2009,
        same_entry_overlap_coverage={},
        final_extraction_coverage={},
        requested_team_results=[
            {
                "team_name": "Wimbledonl",
                "full_club_name": "Wimbledon Football Club",
                "team_id": 0,
                "team_offset": 0x1B578,
                "status": "no_same_entry_overlap_hits",
                "containing_entry": {"entry_offset": 0x1B04B, "length": 47360},
                "heuristic_warnings": [
                    {
                        "type": "adjacent_pseudo_team_record_reassignment",
                        "message": "Adjacent pseudo-team record 'ELONEX' has a strong roster match; candidate run copied for review",
                    }
                ],
                "preferred_roster_match": {
                    "provenance": "adjacent_pseudo_team_record_reassignment",
                    "row_count": 27,
                    "provisional": True,
                    "rows": [],
                },
                "top_run_match": {
                    "run_index": 0,
                    "overlap_hits_in_team_raw": 0,
                    "non_empty_row_count": 27,
                    "second_best_overlap_hits": 0,
                    "rows": [],
                },
                "adjacent_pseudo_team_reassignment_candidate": {
                    "run_index": 1,
                    "non_empty_row_count": 27,
                    "source_pseudo_team_name": "ELONEX",
                    "rows": [
                        {
                            "pid_candidate": 9238,
                            "dd6361_name": "Neil SULLIVAN",
                            "is_empty_slot": False,
                            "xor_pid_found_in_team_raw": True,
                        }
                    ],
                },
            }
        ],
        raw_payload={"ok": True},
    )
    monkeypatch.setattr(cli, "extract_team_rosters_eq_same_entry_overlap", lambda **kwargs: fake_result)

    cli.cmd_team_roster_extract(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team=["Wimbledon"],
            top_examples=15,
            row_limit=10,
            include_fallbacks=True,
            json_output=None,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert "preferred_roster provenance=adjacent_pseudo_team_record_reassignment" in out
    assert "WARNING Adjacent pseudo-team record 'ELONEX'" in out
    assert "pseudo_adjacent_candidate run=1" in out
    assert "pid= 9238  Neil SULLIVAN" in out


def test_cmd_team_roster_extract_anchor_interval_duplicate_hidden_but_warning_shown(monkeypatch, capsys):
    fake_result = SimpleNamespace(
        team_count=532,
        dd6361_pid_name_count=2009,
        same_entry_overlap_coverage={},
        final_extraction_coverage={},
        preferred_roster_coverage={"covered_count": 514, "club_like_team_count": 530, "club_like_covered_count": 514},
        requested_team_results=[
            {
                "team_name": "R.C.D. Mallorca",
                "full_club_name": "Real Club Deportivo Mallorca",
                "team_id": 0,
                "team_offset": 0x7000,
                "status": "moderate_same_entry_overlap",
                "containing_entry": {"entry_offset": 0x6D03, "length": 60928},
                "heuristic_warnings": [
                    {
                        "type": "anchor_interval_contested_run",
                        "message": "Assigned run 7 is also the current best same-entry run for 1 other team(s)",
                        "run_index": 7,
                        "contested_team_names_preview": ["Manchester Utd"],
                    }
                ],
                "top_run_match": {
                    "run_index": 7,
                    "overlap_hits_in_team_raw": 5,
                    "non_empty_row_count": 20,
                    "second_best_overlap_hits": 4,
                    "rows": [
                        {
                            "pid_candidate": 3385,
                            "dd6361_name": "David Robert BECKHAM",
                            "is_empty_slot": False,
                            "xor_pid_found_in_team_raw": False,
                        }
                    ],
                },
                "anchor_interval_monotonic_candidate": {
                    "run_index": 7,
                    "non_empty_row_count": 20,
                    "anchor_interval": {"left_run_index": 6, "right_run_index": 9},
                    "rows": [
                        {
                            "pid_candidate": 3385,
                            "dd6361_name": "David Robert BECKHAM",
                            "is_empty_slot": False,
                            "xor_pid_found_in_team_raw": False,
                        }
                    ],
                },
                "preferred_roster_match": {
                    "provenance": "anchor_interval_monotonic_same_entry",
                    "row_count": 20,
                    "provisional": True,
                    "rows": [],
                },
            }
        ],
        raw_payload={"ok": True},
    )
    monkeypatch.setattr(cli, "extract_team_rosters_eq_same_entry_overlap", lambda **kwargs: fake_result)

    cli.cmd_team_roster_extract(
        Namespace(
            file="DBDAT/EQ98030.FDI",
            player_file="DBDAT/JUG98030.FDI",
            team=["Mallorca"],
            top_examples=15,
            row_limit=10,
            include_fallbacks=True,
            json_output=None,
            json=False,
        )
    )

    out = capsys.readouterr().out
    assert "preferred_roster provenance=anchor_interval_monotonic_same_entry" in out
    assert "WARNING Assigned run 7 is also the current best same-entry run" in out
    assert "contested_with=Manchester Utd" in out
    assert "best_run index=7" in out
    assert "anchor_interval_candidate run=7" not in out
