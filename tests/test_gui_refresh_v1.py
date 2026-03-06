from pathlib import Path
from types import SimpleNamespace

import app.gui_refresh as gui_refresh


class _FakeVar:
    def __init__(self) -> None:
        self.values: list[str] = []
        self.current = None

    def set(self, value):
        self.current = value
        self.values.append(value)

    def get(self):
        return self.current


class _FakeRoot:
    def __init__(self) -> None:
        self.update_calls = 0

    def update_idletasks(self) -> None:
        self.update_calls += 1


def test_run_roster_batch_import_stages_operations_and_reports_counts(monkeypatch, tmp_path):
    team_file = tmp_path / "EQ98030.FDI"
    player_file = tmp_path / "JUG98030.FDI"
    csv_file = tmp_path / "roster_plan.csv"
    team_file.write_bytes(b"\x00")
    player_file.write_bytes(b"\x00")
    csv_file.write_text("source,team,slot,player_id\nlinked,Stoke C.,1,3937\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_batch_edit_team_roster_records(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            row_count=3,
            matched_row_count=2,
            linked_changes=[
                SimpleNamespace(
                    team_name="Stoke C",
                    full_club_name="Stoke C",
                    eq_record_id=3425,
                    slot_number=1,
                    new_player_record_id=3937,
                    new_flag=1,
                )
            ],
            same_entry_changes=[
                SimpleNamespace(
                    team_name="Milan",
                    full_club_name="AC Milan",
                    team_offset=0x2710,
                    slot_number=2,
                    new_pid_candidate=2510,
                    provenance="same_entry_authoritative",
                )
            ],
            warnings=[SimpleNamespace(message="row 4 duplicate target slot")],
            backup_path=None,
            applied_to_disk=False,
        )

    monkeypatch.setattr(gui_refresh, "batch_edit_team_roster_records", fake_batch_edit_team_roster_records)

    staged_ops: list[dict[str, object]] = []
    refresh_calls: list[bool] = []
    editor = SimpleNamespace(
        team_file_path=str(team_file),
        coach_file_path=str(tmp_path / "ENT98030.FDI"),
        status_var=_FakeVar(),
        toolbar_status_var=_FakeVar(),
        root=_FakeRoot(),
        _resolve_player_file_for_roster=lambda: str(player_file),
        _resolve_club_offset_for_roster_operation=lambda **_kwargs: 44,
        _upsert_staged_roster_slot_change=lambda operation: staged_ops.append(dict(operation)) or True,
        _refresh_after_roster_staging_update=lambda: refresh_calls.append(True),
    )

    lines = gui_refresh.PM99DatabaseEditor._run_roster_batch_import(
        editor,
        csv_path=str(csv_file),
    )

    assert captured["team_file"] == str(team_file)
    assert captured["player_file"] == str(player_file)
    assert captured["csv_path"] == str(csv_file)
    assert captured["write_changes"] is False
    assert len(staged_ops) == 2
    assert staged_ops[0]["mode"] == "linked"
    assert staged_ops[1]["mode"] == "same_entry"
    assert lines[0] == "Batch import staged"
    assert any("Linked rows staged: 1" in line for line in lines)
    assert any("Same-entry rows staged: 1" in line for line in lines)
    assert any("First warning:" == line for line in lines)
    assert editor.toolbar_status_var.current == "Roster batch staged"
    assert refresh_calls


def test_preview_roster_batch_import_returns_plan_preview_payload(monkeypatch, tmp_path):
    team_file = tmp_path / "EQ98030.FDI"
    player_file = tmp_path / "JUG98030.FDI"
    csv_file = tmp_path / "roster_plan.csv"
    team_file.write_bytes(b"\x00")
    player_file.write_bytes(b"\x00")
    csv_file.write_text("source,team,slot,player_id\nlinked,Stoke C.,1,3937\n", encoding="utf-8")

    def fake_batch_edit_team_roster_records(**_kwargs):
        return SimpleNamespace(
            row_count=1,
            matched_row_count=1,
            linked_changes=[],
            same_entry_changes=[],
            warnings=[],
            plan_preview=[
                SimpleNamespace(
                    row_number=2,
                    status="no_change",
                    source="linked",
                    team_query="Stoke C.",
                    slot_number=1,
                    diff_summary="Row resolves cleanly but already matches on-disk values",
                )
            ],
        )

    monkeypatch.setattr(gui_refresh, "batch_edit_team_roster_records", fake_batch_edit_team_roster_records)

    editor = SimpleNamespace(
        team_file_path=str(team_file),
        status_var=_FakeVar(),
        toolbar_status_var=_FakeVar(),
        root=_FakeRoot(),
        _resolve_player_file_for_roster=lambda: str(player_file),
    )

    result, team_path, player_path, plan_path = gui_refresh.PM99DatabaseEditor._preview_roster_batch_import(
        editor,
        csv_path=str(csv_file),
    )

    assert team_path == str(team_file)
    assert player_path == str(player_file)
    assert str(plan_path) == str(csv_file)
    assert len(list(getattr(result, "plan_preview", []) or [])) == 1
    assert editor.toolbar_status_var.current == "Roster batch preview ready"


def test_stage_roster_bulk_promotions_stages_and_reports_skips(monkeypatch):
    captured: dict[str, object] = {}

    def fake_promote_linked_roster_player_name_bulk(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            slot_count=4,
            matched_slot_count=2,
            promotions=[
                SimpleNamespace(
                    team_name="Stoke C.",
                    full_club_name="Stoke City",
                    eq_record_id=341,
                    slot_number=1,
                    new_player_name="Joe Skerratt",
                    skill_updates_requested={"speed": 99},
                ),
                SimpleNamespace(
                    team_name="Stoke C.",
                    full_club_name="Stoke City",
                    eq_record_id=341,
                    slot_number=2,
                    new_player_name="Joe Skerratt",
                    skill_updates_requested={"speed": 99},
                ),
            ],
            skipped_slots=[
                SimpleNamespace(
                    slot_number=3,
                    player_record_id=9773,
                    player_name="Ray WALLACE",
                    reason_code="fixed_name_unsafe",
                    reason_message="Fixed-length rename could not produce a safe name mutation candidate",
                )
            ],
            warnings=[],
        )

    monkeypatch.setattr(gui_refresh, "promote_linked_roster_player_name_bulk", fake_promote_linked_roster_player_name_bulk)

    staged_ops: list[dict[str, object]] = []
    upsert_results = iter([True, False])
    refresh_calls: list[bool] = []

    editor = SimpleNamespace(
        current_team=(44, SimpleNamespace(name="Stoke C.")),
        current_roster_rows=[SimpleNamespace(meta={"mode": "linked", "team_query": "Stoke C.", "eq_record_id": 341}, player_name="Old A")],
        team_file_path="DBDAT/EQ98030.FDI",
        status_var=_FakeVar(),
        toolbar_status_var=_FakeVar(),
        root=_FakeRoot(),
        _resolve_player_file_for_roster=lambda: "DBDAT/JUG98030.FDI",
        _resolve_club_offset_for_roster_operation=lambda **_kwargs: 44,
        staged_roster_promotion_skips={},
        _upsert_staged_roster_promotion=lambda operation: staged_ops.append(dict(operation)) or next(upsert_results),
        _refresh_after_roster_staging_update=lambda: refresh_calls.append(True),
        _team_name=lambda _team: "Stoke C.",
    )

    lines = gui_refresh.PM99DatabaseEditor._stage_roster_bulk_promotions(
        editor,
        new_name="Joe Skerratt",
        elite_skills=True,
        slot_limit=4,
    )

    assert captured["team_file"] == "DBDAT/EQ98030.FDI"
    assert captured["player_file"] == "DBDAT/JUG98030.FDI"
    assert captured["team_query"] == "Stoke C."
    assert captured["eq_record_id"] == 341
    assert captured["new_name"] == "Joe Skerratt"
    assert captured["slot_limit"] == 4
    assert captured["apply_elite_skills"] is True
    assert captured["fixed_name_bytes"] is True
    assert captured["write_changes"] is False

    assert len(staged_ops) == 2
    assert staged_ops[0]["slot_number"] == 1
    assert staged_ops[1]["slot_number"] == 2
    assert refresh_calls
    assert len(editor.staged_roster_promotion_skips) == 1
    skip_item = next(iter(editor.staged_roster_promotion_skips.values()))
    assert skip_item["slot_number"] == 3
    assert skip_item["reason_code"] == "fixed_name_unsafe"
    assert editor.toolbar_status_var.current == "Bulk roster promotion staged"
    assert "staged new=1, updated existing=1" in "\n".join(lines)
    assert "Skipped slots: 1" in "\n".join(lines)
    assert any("fixed_name_unsafe" in line for line in lines)


def test_profile_bulk_promotion_safety_formats_reason_breakdown(monkeypatch):
    captured: dict[str, object] = {}

    def fake_promote_linked_roster_player_name_bulk(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            eq_record_id=341,
            team_name="Stoke C.",
            full_club_name="Stoke City",
            new_player_name="Joe Skerratt",
            slot_count=4,
            matched_slot_count=1,
            skipped_slots=[],
        )

    def fake_summarize_team_roster_bulk_promotion(_result, sample_limit=12):
        return SimpleNamespace(
            eq_record_id=341,
            team_name="Stoke C.",
            full_club_name="Stoke City",
            new_player_name="Joe Skerratt",
            slot_count=4,
            matched_slot_count=1,
            skipped_slot_count=3,
            fixed_name_unsafe_count=2,
            already_target_count=1,
            other_skip_count=0,
            reason_counts={"fixed_name_unsafe": 2, "already_target": 1},
            safe_family_counts={"parser_text_spill_prefix_clip": 1},
            sample_skips=[
                SimpleNamespace(
                    slot_number=2,
                    player_record_id=9773,
                    player_name="Ray WALLACE",
                    reason_code="fixed_name_unsafe",
                    reason_message="unsafe payload",
                )
            ],
        )

    monkeypatch.setattr(gui_refresh, "promote_linked_roster_player_name_bulk", fake_promote_linked_roster_player_name_bulk)
    monkeypatch.setattr(gui_refresh, "summarize_team_roster_bulk_promotion", fake_summarize_team_roster_bulk_promotion)

    editor = SimpleNamespace(
        team_file_path="DBDAT/EQ98030.FDI",
        _resolve_player_file_for_roster=lambda: "DBDAT/JUG98030.FDI",
    )

    lines = gui_refresh.PM99DatabaseEditor._profile_bulk_promotion_safety(
        editor,
        team_query="Stoke C.",
        eq_record_id=341,
        new_name="Joe Skerratt",
        slot_limit=4,
        sample_limit=8,
    )

    assert captured["write_changes"] is False
    assert captured["fixed_name_bytes"] is True
    assert captured["eq_record_id"] == 341
    summary = "\n".join(lines)
    assert "Linked Roster Promotion Safety Profile" in summary
    assert "Safe slots: 1/4" in summary
    assert "fixed_name_unsafe=2" in summary
    assert "Reason counts:" in summary
    assert "fixed_name_unsafe: 2" in summary
    assert "Safe mutation families:" in summary
    assert "parser_text_spill_prefix_clip: 1" in summary
    assert "Sample skipped slots:" in summary




def test_league_view_status_bucket_prefers_probe_promoted_source():
    bucket = gui_refresh._league_view_status_bucket(
        source="competition_probe_contract",
        status="probe-promoted",
        confidence="medium",
    )
    assert bucket == "Promoted"


def test_league_view_status_bucket_flags_review_states():
    bucket = gui_refresh._league_view_status_bucket(
        source="sequence_fallback",
        status="probe-mismatch",
        confidence="review",
    )
    assert bucket == "Review"


def test_league_view_matches_filters_checks_query_and_bucket():
    assert gui_refresh._league_view_matches_filters(
        query="stoke",
        selected_bucket="Promoted",
        team_name="Stoke C",
        country="England",
        league="First Division",
        team_id=3425,
        bucket="Promoted",
    )
    assert not gui_refresh._league_view_matches_filters(
        query="milan",
        selected_bucket="Promoted",
        team_name="Stoke C",
        country="England",
        league="First Division",
        team_id=3425,
        bucket="Promoted",
    )
    assert not gui_refresh._league_view_matches_filters(
        query="stoke",
        selected_bucket="Fallback",
        team_name="Stoke C",
        country="England",
        league="First Division",
        team_id=3425,
        bucket="Promoted",
    )


def test_save_database_rolls_back_player_file_on_mid_save_failure(monkeypatch, tmp_path):
    player_file = tmp_path / "JUG98030.FDI"
    team_file = tmp_path / "EQ98030.FDI"
    coach_file = tmp_path / "ENT98030.FDI"
    player_original = b"PLAYER_ORIGINAL"
    team_original = b"TEAM_ORIGINAL"
    coach_original = b"COACH_ORIGINAL"
    player_file.write_bytes(player_original)
    team_file.write_bytes(team_original)
    coach_file.write_bytes(coach_original)

    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        gui_refresh,
        "write_player_staged_records",
        lambda file_path, _records, create_backup_before_write=False: Path(file_path).write_bytes(b"PLAYER_WRITTEN"),
    )
    monkeypatch.setattr(gui_refresh.messagebox, "askyesno", lambda *args, **kwargs: True)
    monkeypatch.setattr(gui_refresh.messagebox, "showinfo", lambda *args, **kwargs: None)
    monkeypatch.setattr(gui_refresh.messagebox, "showwarning", lambda *args, **kwargs: None)
    monkeypatch.setattr(gui_refresh.messagebox, "showerror", lambda title, message: errors.append((title, message)))
    monkeypatch.setattr(
        gui_refresh,
        "write_team_staged_records",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("team write exploded")),
    )
    monkeypatch.setattr(gui_refresh, "write_coach_staged_records", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        gui_refresh,
        "validate_database_files",
        lambda **_kwargs: SimpleNamespace(all_valid=True, files=[]),
    )

    commit_calls: list[bool] = []
    footer_refresh_calls: list[bool] = []
    editor = SimpleNamespace(
        _has_staged_changes=lambda: True,
        status_var=_FakeVar(),
        toolbar_status_var=_FakeVar(),
        root=_FakeRoot(),
        modified_records={100: SimpleNamespace()},
        modified_team_records={200: SimpleNamespace()},
        modified_coach_records={},
        staged_visible_skill_patches={},
        staged_roster_slot_changes={},
        staged_roster_promotions={},
        file_path=str(player_file),
        team_file_path=str(team_file),
        coach_file_path=str(coach_file),
        file_data=player_original,
        validation_state=gui_refresh.ValidationBannerState(),
        _apply_staged_visible_skill_patches=lambda: None,
        _apply_staged_roster_slot_changes_to_disk=lambda **_kwargs: (0, 0),
        _apply_staged_roster_promotions_to_disk=lambda **_kwargs: (0, 0),
        _commit_staged_records_to_loaded_state=lambda *_args: commit_calls.append(True),
        _refresh_footer_state=lambda: footer_refresh_calls.append(True),
    )

    result = gui_refresh.PM99DatabaseEditor.save_database(editor)

    assert result is False
    assert player_file.read_bytes() == player_original
    assert team_file.read_bytes() == team_original
    assert coach_file.read_bytes() == coach_original
    assert not commit_calls
    assert footer_refresh_calls
    assert editor.status_var.current == "Save failed; rollback attempted"
    assert errors
    assert "Rollback summary:" in errors[0][1]
    assert "Restored JUG98030.FDI" in errors[0][1]


def test_save_database_handles_visible_skill_only_staged_changes(monkeypatch, tmp_path):
    player_file = tmp_path / "JUG98030.FDI"
    team_file = tmp_path / "EQ98030.FDI"
    coach_file = tmp_path / "ENT98030.FDI"
    player_file.write_bytes(b"PLAYER_ORIGINAL")
    team_file.write_bytes(b"TEAM_ORIGINAL")
    coach_file.write_bytes(b"COACH_ORIGINAL")

    infos: list[tuple[str, str]] = []
    monkeypatch.setattr(gui_refresh.messagebox, "askyesno", lambda *args, **kwargs: True)
    monkeypatch.setattr(gui_refresh.messagebox, "showinfo", lambda title, message: infos.append((title, message)))
    monkeypatch.setattr(gui_refresh.messagebox, "showwarning", lambda *args, **kwargs: None)
    monkeypatch.setattr(gui_refresh.messagebox, "showerror", lambda *args, **kwargs: None)
    monkeypatch.setattr(gui_refresh, "write_team_staged_records", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gui_refresh, "write_coach_staged_records", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        gui_refresh,
        "validate_database_files",
        lambda **_kwargs: SimpleNamespace(all_valid=True, files=[]),
    )

    footer_refresh_calls: list[bool] = []
    commit_calls: list[tuple[dict[int, object], dict[int, object], dict[int, object]]] = []

    def _apply_visible_patch():
        player_file.write_bytes(b"PLAYER_PATCHED")

    editor = SimpleNamespace(
        _has_staged_changes=lambda: True,
        status_var=_FakeVar(),
        toolbar_status_var=_FakeVar(),
        root=_FakeRoot(),
        modified_records={},
        modified_team_records={},
        modified_coach_records={},
        staged_visible_skill_patches={("player", "query"): {"updates": {"speed": 99}}},
        staged_roster_slot_changes={},
        staged_roster_promotions={},
        file_path=str(player_file),
        team_file_path=str(team_file),
        coach_file_path=str(coach_file),
        file_data=player_file.read_bytes(),
        validation_state=gui_refresh.ValidationBannerState(),
        _apply_staged_visible_skill_patches=_apply_visible_patch,
        _apply_staged_roster_slot_changes_to_disk=lambda **_kwargs: (0, 0),
        _apply_staged_roster_promotions_to_disk=lambda **_kwargs: (0, 0),
        _commit_staged_records_to_loaded_state=lambda p, t, c: commit_calls.append((p, t, c)),
        _refresh_footer_state=lambda: footer_refresh_calls.append(True),
    )

    result = gui_refresh.PM99DatabaseEditor.save_database(editor)

    assert result is True
    assert player_file.read_bytes() == b"PLAYER_PATCHED"
    assert commit_calls
    assert footer_refresh_calls
    assert editor.status_var.current == "Database saved and validated"
    assert editor.toolbar_status_var.current == "Saved"
    assert infos
    assert infos[0][0] == "Save All"


def test_save_database_applies_staged_roster_changes_and_promotions(monkeypatch, tmp_path):
    player_file = tmp_path / "JUG98030.FDI"
    team_file = tmp_path / "EQ98030.FDI"
    coach_file = tmp_path / "ENT98030.FDI"
    player_file.write_bytes(b"PLAYER_ORIGINAL")
    team_file.write_bytes(b"TEAM_ORIGINAL")
    coach_file.write_bytes(b"COACH_ORIGINAL")

    infos: list[tuple[str, str]] = []
    validation_calls: list[dict[str, object]] = []

    monkeypatch.setattr(gui_refresh.messagebox, "askyesno", lambda *args, **kwargs: True)
    monkeypatch.setattr(gui_refresh.messagebox, "showinfo", lambda title, message: infos.append((title, message)))
    monkeypatch.setattr(gui_refresh.messagebox, "showwarning", lambda *args, **kwargs: None)
    monkeypatch.setattr(gui_refresh.messagebox, "showerror", lambda *args, **kwargs: None)
    monkeypatch.setattr(gui_refresh, "write_team_staged_records", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gui_refresh, "write_coach_staged_records", lambda *_args, **_kwargs: None)

    def fake_validate_database_files(**kwargs):
        validation_calls.append(dict(kwargs))
        return SimpleNamespace(all_valid=True, files=[])

    monkeypatch.setattr(gui_refresh, "validate_database_files", fake_validate_database_files)

    applied_slot_calls: list[bool] = []
    applied_promo_calls: list[bool] = []
    commit_calls: list[bool] = []
    footer_refresh_calls: list[bool] = []

    editor = SimpleNamespace(
        _has_staged_changes=lambda: True,
        status_var=_FakeVar(),
        toolbar_status_var=_FakeVar(),
        root=_FakeRoot(),
        modified_records={},
        modified_team_records={},
        modified_coach_records={},
        staged_visible_skill_patches={},
        staged_roster_slot_changes={
            ("linked", 3425, 1): {
                "mode": "linked",
                "eq_record_id": 3425,
                "slot_number": 1,
                "player_record_id": 3937,
                "new_flag": 1,
            }
        },
        staged_roster_promotions={
            ("promote", 3425, 1): {
                "eq_record_id": 3425,
                "slot_number": 1,
                "new_name": "Joe Skerratt",
            }
        },
        file_path=str(player_file),
        team_file_path=str(team_file),
        coach_file_path=str(coach_file),
        file_data=player_file.read_bytes(),
        validation_state=gui_refresh.ValidationBannerState(),
        _apply_staged_visible_skill_patches=lambda: None,
        _apply_staged_roster_slot_changes_to_disk=lambda **_kwargs: applied_slot_calls.append(True) or (2, 0),
        _apply_staged_roster_promotions_to_disk=lambda **_kwargs: applied_promo_calls.append(True) or (1, 1),
        _commit_staged_records_to_loaded_state=lambda *_args: commit_calls.append(True),
        _refresh_footer_state=lambda: footer_refresh_calls.append(True),
    )

    result = gui_refresh.PM99DatabaseEditor.save_database(editor)

    assert result is True
    assert applied_slot_calls
    assert applied_promo_calls
    assert commit_calls
    assert footer_refresh_calls
    assert validation_calls
    assert validation_calls[0]["player_file"] == str(player_file)
    assert validation_calls[0]["team_file"] == str(team_file)
    assert validation_calls[0]["coach_file"] is None
    assert infos
    assert "Staged roster slot updates applied: 2 row(s), 0 warning(s)" in infos[0][1]
    assert "Staged roster promotions applied: 1 promotion(s), 1 warning(s)" in infos[0][1]


def test_save_database_blocks_unsafe_player_edits_in_safe_mode(monkeypatch, tmp_path):
    player_file = tmp_path / "JUG98030.FDI"
    team_file = tmp_path / "EQ98030.FDI"
    coach_file = tmp_path / "ENT98030.FDI"
    player_file.write_bytes(b"PLAYER_ORIGINAL")
    team_file.write_bytes(b"TEAM_ORIGINAL")
    coach_file.write_bytes(b"COACH_ORIGINAL")

    errors: list[tuple[str, str]] = []
    confirmations: list[tuple[str, str]] = []
    monkeypatch.setattr(gui_refresh.messagebox, "askyesno", lambda title, message: confirmations.append((title, message)) or True)
    monkeypatch.setattr(gui_refresh.messagebox, "showerror", lambda title, message: errors.append((title, message)))
    monkeypatch.setattr(gui_refresh.messagebox, "showinfo", lambda *args, **kwargs: None)
    monkeypatch.setattr(gui_refresh.messagebox, "showwarning", lambda *args, **kwargs: None)

    editor = SimpleNamespace(
        _has_staged_changes=lambda: True,
        modified_records={100: SimpleNamespace(name_dirty=False)},
        modified_team_records={},
        modified_coach_records={},
        staged_visible_skill_patches={},
        staged_roster_slot_changes={},
        staged_roster_promotions={},
        file_path=str(player_file),
        team_file_path=str(team_file),
        coach_file_path=str(coach_file),
        dirty_state=gui_refresh.DirtyRecordState(field_dirty_map={"players:100": {"team_id"}}),
    )

    result = gui_refresh.PM99DatabaseEditor.save_database(editor)

    assert result is False
    assert errors
    assert "Save blocked by safety checks" in errors[0][1]
    assert "Safe mode is active" in errors[0][1]
    assert not confirmations


def test_save_plan_confirmation_lines_include_promotion_skip_diagnostics():
    save_plan = {
        "changed_players": {},
        "changed_teams": {},
        "changed_coaches": {},
        "staged_skills": {},
        "staged_slot_changes": [],
        "staged_promotions": [{"slot_number": 1}],
        "staged_promotion_skips": [
            {
                "team_query": "Stoke C.",
                "slot_number": 3,
                "player_record_id": 9773,
                "reason_code": "fixed_name_unsafe",
                "reason_message": "Fixed-length rename could not produce a safe name mutation candidate",
            }
        ],
        "name_only_player_count": 0,
        "non_name_player_count": 0,
    }

    lines = gui_refresh.PM99DatabaseEditor._build_save_plan_confirmation_lines(save_plan)

    summary = "\n".join(lines)
    assert "- Promotion skips (diagnostics): 1" in summary
    assert "Bulk promotion skips (not written):" in summary
    assert "Stoke C. slot 03 pid 9773: fixed_name_unsafe" in summary


def test_save_database_confirmation_includes_save_plan(monkeypatch, tmp_path):
    player_file = tmp_path / "JUG98030.FDI"
    team_file = tmp_path / "EQ98030.FDI"
    coach_file = tmp_path / "ENT98030.FDI"
    player_file.write_bytes(b"PLAYER_ORIGINAL")
    team_file.write_bytes(b"TEAM_ORIGINAL")
    coach_file.write_bytes(b"COACH_ORIGINAL")

    confirmations: list[tuple[str, str]] = []
    monkeypatch.setattr(gui_refresh.messagebox, "askyesno", lambda title, message: confirmations.append((title, message)) or False)
    monkeypatch.setattr(gui_refresh.messagebox, "showerror", lambda *args, **kwargs: None)
    monkeypatch.setattr(gui_refresh.messagebox, "showinfo", lambda *args, **kwargs: None)
    monkeypatch.setattr(gui_refresh.messagebox, "showwarning", lambda *args, **kwargs: None)

    editor = SimpleNamespace(
        _has_staged_changes=lambda: True,
        modified_records={},
        modified_team_records={},
        modified_coach_records={},
        staged_visible_skill_patches={("player", "query"): {"updates": {"speed": 99}}},
        staged_roster_slot_changes={},
        staged_roster_promotions={},
        file_path=str(player_file),
        team_file_path=str(team_file),
        coach_file_path=str(coach_file),
        dirty_state=gui_refresh.DirtyRecordState(),
    )

    result = gui_refresh.PM99DatabaseEditor.save_database(editor)

    assert result is False
    assert confirmations
    assert confirmations[0][0] == "Save All"
    assert "Save plan:" in confirmations[0][1]
    assert "- Visible skill patches: 1" in confirmations[0][1]



def test_export_current_roster_csv_writes_batch_template(monkeypatch, tmp_path):
    captured = {}
    infos: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []

    output_csv = tmp_path / "stoke_template.csv"
    monkeypatch.setattr(gui_refresh.filedialog, "asksaveasfilename", lambda **_kwargs: str(output_csv))
    monkeypatch.setattr(gui_refresh.messagebox, "showinfo", lambda title, message: infos.append((title, message)))
    monkeypatch.setattr(gui_refresh.messagebox, "showerror", lambda title, message: errors.append((title, message)))

    def fake_export_team_roster_batch_template(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(row_count=25, warnings=[])

    monkeypatch.setattr(gui_refresh, "export_team_roster_batch_template", fake_export_team_roster_batch_template)

    editor = SimpleNamespace(
        current_roster_rows=[
            SimpleNamespace(meta={"mode": "linked", "eq_record_id": 341}),
            SimpleNamespace(meta={"mode": "linked", "eq_record_id": 341}),
        ],
        current_team=(0x1000, SimpleNamespace(name="Stoke C.")),
        _team_name=lambda team: getattr(team, "name", ""),
        team_file_path="DBDAT/EQ98030.FDI",
        _resolve_player_file_for_roster=lambda: "DBDAT/JUG98030.FDI",
        status_var=_FakeVar(),
    )

    gui_refresh.PM99DatabaseEditor.export_current_roster_csv(editor)

    assert captured == {
        "team_file": "DBDAT/EQ98030.FDI",
        "player_file": "DBDAT/JUG98030.FDI",
        "output_csv": str(output_csv),
        "team_query": "Stoke C.",
        "eq_record_id": 341,
        "team_offset": None,
        "source": "linked",
    }
    assert not errors
    assert infos
    assert "Exported batch template" in (editor.status_var.current or "")
