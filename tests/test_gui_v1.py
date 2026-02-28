from types import SimpleNamespace
from pathlib import Path

import app.gui as gui


class _FakeVar:
    def __init__(self):
        self.values = []
        self.current = None

    def set(self, value):
        self.current = value
        self.values.append(value)

    def get(self):
        return self.current


class _FakeIntVar:
    def __init__(self, value=0):
        self.value = int(value)

    def set(self, value):
        self.value = int(value)

    def get(self):
        return self.value


class _FakeRoot:
    def __init__(self):
        self.update_calls = 0

    def update_idletasks(self):
        self.update_calls += 1


class _FakeTree:
    def __init__(self):
        self.rows = []

    def get_children(self):
        return list(range(len(self.rows)))

    def delete(self, *items):
        self.rows.clear()

    def insert(self, parent, index, values=(), tags=()):
        self.rows.append({"values": tuple(values), "tags": tuple(tags)})
        return str(len(self.rows))


class _FakeWidget:
    def __init__(self):
        self.pack_calls = []
        self.config_calls = []

    def pack(self, *args, **kwargs):
        self.pack_calls.append((args, kwargs))

    def pack_forget(self):
        self.pack_calls.append(("forget", {}))

    def config(self, **kwargs):
        self.config_calls.append(dict(kwargs))


class _FakeEditor:
    def __init__(self):
        self.status_var = _FakeVar()
        self.root = _FakeRoot()

    def _format_bulk_summary_lines(self, result):
        return gui.PM99DatabaseEditor._format_bulk_summary_lines(self, result)


def test_format_bulk_summary_lines_truncates_and_shows_extra():
    editor = _FakeEditor()
    file_results = [
        SimpleNamespace(file=f"JUG{i:04d}.FDI", changed_players=i, total_players=100, rows_written=i)
        for i in range(15)
    ]
    result = SimpleNamespace(file_results=file_results)

    lines = gui.PM99DatabaseEditor._format_bulk_summary_lines(editor, result)

    assert len(lines) == 13
    assert lines[0].startswith("JUG0000.FDI: changed=0")
    assert lines[-1] == "... and 3 more file(s)"


def test_open_bulk_player_rename_dialog_runs_dry_run_and_reports(monkeypatch):
    editor = _FakeEditor()
    infos = []
    errors = []

    monkeypatch.setattr(gui.filedialog, "askdirectory", lambda **kwargs: "/tmp/dbdat")
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **kwargs: "/tmp/rename_map.csv")
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: True)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))

    calls = {}

    def fake_bulk_rename_players(data_dir, map_output, dry_run=False):
        calls["args"] = (data_dir, map_output, dry_run)
        return SimpleNamespace(
            files_processed=2,
            rows_written=12,
            map_output=map_output,
            file_results=[
                SimpleNamespace(file="JUG98030.FDI", changed_players=12, total_players=500, rows_written=12),
            ],
        )

    monkeypatch.setattr(gui, "bulk_rename_players", fake_bulk_rename_players)

    gui.PM99DatabaseEditor.open_bulk_player_rename_dialog(editor)

    assert calls["args"] == ("/tmp/dbdat", "/tmp/rename_map.csv", True)
    assert editor.root.update_calls == 1
    assert any("Running bulk player rename" in v for v in editor.status_var.values)
    assert any("dry-run" in v for v in editor.status_var.values)
    assert errors == []
    assert infos and infos[0][0] == "Bulk Rename Players"
    assert "Dry run complete" in infos[0][1]
    assert "/tmp/rename_map.csv" in infos[0][1]


def test_open_bulk_player_revert_dialog_runs_and_reports(monkeypatch):
    editor = _FakeEditor()
    infos = []
    errors = []

    monkeypatch.setattr(gui.filedialog, "askdirectory", lambda **kwargs: "/tmp/dbdat")
    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **kwargs: "/tmp/rename_map.csv")
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: False)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))

    calls = {}

    def fake_revert_player_renames(data_dir, map_input, dry_run=False):
        calls["args"] = (data_dir, map_input, dry_run)
        return SimpleNamespace(
            files_processed=2,
            rows_processed=12,
            map_input=map_input,
            file_results=[
                SimpleNamespace(file="JUG98030.FDI", changed_players=12, total_players=500, rows_written=12),
            ],
        )

    monkeypatch.setattr(gui, "revert_player_renames", fake_revert_player_renames)

    gui.PM99DatabaseEditor.open_bulk_player_revert_dialog(editor)

    assert calls["args"] == ("/tmp/dbdat", "/tmp/rename_map.csv", False)
    assert editor.root.update_calls == 1
    assert any("Running bulk player rename revert" in v for v in editor.status_var.values)
    assert any("Bulk player revert complete" in v for v in editor.status_var.values)
    assert errors == []
    assert infos and infos[0][0] == "Revert Bulk Player Rename"
    assert "Bulk revert complete" in infos[0][1]
    assert "/tmp/rename_map.csv" in infos[0][1]


def test_open_bulk_player_rename_dialog_handles_exception(monkeypatch):
    editor = _FakeEditor()
    infos = []
    errors = []

    monkeypatch.setattr(gui.filedialog, "askdirectory", lambda **kwargs: "/tmp/dbdat")
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **kwargs: "/tmp/rename_map.csv")
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: False)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))
    monkeypatch.setattr(gui, "bulk_rename_players", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    gui.PM99DatabaseEditor.open_bulk_player_rename_dialog(editor)

    assert any(v == "Bulk player rename failed" for v in editor.status_var.values)
    assert infos == []
    assert errors and errors[0][0] == "Bulk Rename Players"
    assert "boom" in errors[0][1]


def test_filter_teams_matches_canonical_alias_without_false_positive():
    editor = SimpleNamespace()
    editor.team_search_var = SimpleNamespace(get=lambda: "Inter Milan")
    editor.team_records = [
        (0x10, SimpleNamespace(name="Inter", full_club_name="Internazionale Milano Football Club", team_id=3425)),
        (0x20, SimpleNamespace(name="Inter Cardiff", full_club_name="Inter Cardiff", team_id=777)),
    ]
    editor.filtered_team_records = []
    populate_calls = []
    editor.populate_team_tree = lambda: populate_calls.append(True)

    gui.PM99DatabaseEditor.filter_teams(editor)

    assert populate_calls == [True]
    assert len(editor.filtered_team_records) == 1
    assert editor.filtered_team_records[0][1].name == "Inter"


def test_load_current_team_roster_populates_authoritative_rows(monkeypatch):
    editor = SimpleNamespace(
        team_roster_tree=_FakeTree(),
        current_team=(0x10, SimpleNamespace(name="Milan")),
        team_file_path="DBDAT/EQ98030.FDI",
        file_path="DBDAT/JUG98030.FDI",
        status_var=_FakeVar(),
    )

    def fake_extract(**kwargs):
        return SimpleNamespace(
            requested_team_results=[
                {
                    "preferred_roster_match": {
                        "provenance": "same_entry_authoritative",
                        "rows": [
                            {"is_empty_slot": False, "pid_candidate": 3937, "dd6361_name": "Demo PLAYER"},
                            {"is_empty_slot": True, "pid_candidate": 0, "dd6361_name": None},
                            {"is_empty_slot": False, "pid_candidate": 4000, "dd6361_name": None},
                        ],
                    }
                }
            ]
        )

    def fake_build_index(**kwargs):
        assert kwargs == {"file_path": "DBDAT/JUG98030.FDI"}
        return {
            3937: {
                "pid": 3937,
                "resolved_bio_name": "Demo PLAYER",
                "mapped10": {"speed": 90, "stamina": 86, "aggression": 85, "quality": 90},
            }
        }

    monkeypatch.setattr(gui, "extract_team_rosters_eq_same_entry_overlap", fake_extract)
    monkeypatch.setattr(gui, "build_player_visible_skill_index_dd6361", fake_build_index)

    gui.PM99DatabaseEditor.load_current_team_roster(editor)

    assert len(editor.team_roster_tree.rows) == 2
    assert editor.team_roster_tree.rows[0]["values"] == (
        1,
        "Demo PLAYER [pid 3937]",
        "?",
        90,
        86,
        85,
        90,
        "?",
        "?",
        "?",
        "?",
        "?",
    )
    assert editor.team_roster_tree.rows[1]["values"] == (
        2,
        "PID 4000 (name unresolved)",
        "?",
        "",
        "",
        "",
        "",
        "?",
        "?",
        "?",
        "?",
        "?",
    )
    assert (
        editor.status_var.get()
        == "Loaded authoritative roster rows for Milan: 2 (static SP/ST/AG/QU only; dynamic columns unresolved)"
    )


def test_toggle_roster_loads_current_team_roster_when_opening():
    editor = SimpleNamespace(
        team_panel_roster_visible=False,
        team_panel_roster_frame=_FakeWidget(),
        team_panel_roster_toggle_btn=_FakeWidget(),
    )
    load_calls = []
    editor.load_current_team_roster = lambda: load_calls.append(True)

    gui.PM99DatabaseEditor._toggle_roster(editor)

    assert editor.team_panel_roster_visible is True
    assert load_calls == [True]
    assert editor.team_panel_roster_frame.pack_calls
    assert editor.team_panel_roster_toggle_btn.config_calls[-1]["text"] == "Hide partial squad roster"


def test_unresolved_roster_values_are_explicit_placeholders():
    assert gui.PM99DatabaseEditor._unresolved_roster_values() == ("?", "?", "?", "?", "?", "?")


def test_open_player_skill_patch_dialog_runs_copy_safe_and_reports(monkeypatch):
    editor = _FakeEditor()
    editor.file_path = "DBDAT/JUG98030.FDI"
    editor.current_record = (0x10, SimpleNamespace(given_name="David Robert", surname="BECKHAM", name=""))
    infos = []
    errors = []

    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **kwargs: "/tmp/JUG98030.FDI")
    ask_calls = []

    def fake_askstring(*args, **kwargs):
        ask_calls.append((args, kwargs))
        if len(ask_calls) == 1:
            return "David Robert BECKHAM"
        return "speed=91, passing=91"

    monkeypatch.setattr(gui.simpledialog, "askstring", fake_askstring)
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: False)
    monkeypatch.setattr(gui.filedialog, "asksaveasfilename", lambda **kwargs: "/tmp/JUG98030.patched.FDI")
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))

    calls = {}

    def fake_parse_assignments(items):
        calls["parse"] = list(items)
        return {"speed": 91, "passing": 91}

    def fake_inspect_action(**kwargs):
        calls["inspect"] = kwargs
        return SimpleNamespace(
            target_query=kwargs["player_name"],
            resolved_bio_name="David Robert BECKHAM",
            mapped10_order=["speed", "stamina", "passing"],
            mapped10={"speed": 90, "stamina": 85, "passing": 90},
        )

    def fake_patch_action(**kwargs):
        calls["patch"] = kwargs
        return SimpleNamespace(
            resolved_bio_name="David Robert BECKHAM",
            output_file="/tmp/JUG98030.patched.FDI",
            in_place=False,
            backup_path=None,
            updates_requested={"speed": 91, "passing": 91},
            mapped10_order=["speed", "stamina", "passing"],
            mapped10_before={"speed": 90, "stamina": 85, "passing": 90},
            mapped10_after={"speed": 91, "stamina": 85, "passing": 91},
            touched_entry_offsets=[0x1234],
        )

    monkeypatch.setattr(gui, "inspect_player_visible_skills_dd6361", fake_inspect_action)
    monkeypatch.setattr(gui, "parse_player_skill_patch_assignments", fake_parse_assignments)
    monkeypatch.setattr(gui, "patch_player_visible_skills_dd6361", fake_patch_action)

    gui.PM99DatabaseEditor.open_player_skill_patch_dialog(editor)

    assert editor.root.update_calls == 1
    assert calls["inspect"] == {
        "file_path": "/tmp/JUG98030.FDI",
        "player_name": "David Robert BECKHAM",
    }
    assert calls["parse"] == ["speed=91", "passing=91"]
    assert calls["patch"] == {
        "file_path": "/tmp/JUG98030.FDI",
        "player_name": "David Robert BECKHAM",
        "updates": {"speed": 91, "passing": 91},
        "output_file": "/tmp/JUG98030.patched.FDI",
        "in_place": False,
        "create_backup_before_write": False,
        "json_output": None,
    }
    assert any("Running dd6361 visible skill patch" in v for v in editor.status_var.values)
    assert any("Visible skill patch" in v for v in editor.status_var.values)
    assert errors == []
    assert infos and infos[0][0] == "Patch Player Visible Skills"
    assert "speed: 90 -> 91" in infos[0][1]
    assert "/tmp/JUG98030.patched.FDI" in infos[0][1]
    # Second prompt should be prefilled from inspected mapped10 values.
    assert len(ask_calls) >= 2
    prefill = ask_calls[1][1].get("initialvalue", "")
    assert "speed=90" in prefill
    assert "stamina=85" in prefill


def test_open_player_skill_patch_dialog_runs_in_place_with_backup(monkeypatch):
    editor = _FakeEditor()
    editor.file_path = "DBDAT/JUG98030.FDI"
    editor.current_record = (0x10, SimpleNamespace(given_name="", surname="", name="David Robert BECKHAM"))
    infos = []
    errors = []

    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **kwargs: "/tmp/JUG98030.FDI")
    prompts = iter(["David Robert BECKHAM", "speed=92"])
    monkeypatch.setattr(gui.simpledialog, "askstring", lambda *args, **kwargs: next(prompts))
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: True)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))

    calls = {}

    monkeypatch.setattr(
        gui,
        "inspect_player_visible_skills_dd6361",
        lambda **kwargs: SimpleNamespace(
            target_query=kwargs["player_name"],
            resolved_bio_name="David Robert BECKHAM",
            mapped10_order=["speed"],
            mapped10={"speed": 90},
        ),
    )
    monkeypatch.setattr(gui, "parse_player_skill_patch_assignments", lambda items: {"speed": 92})

    def fake_patch_action(**kwargs):
        calls["patch"] = kwargs
        return SimpleNamespace(
            resolved_bio_name="David Robert BECKHAM",
            output_file="/tmp/JUG98030.FDI",
            in_place=True,
            backup_path="/tmp/JUG98030.FDI.backup",
            updates_requested={"speed": 92},
            mapped10_order=["speed"],
            mapped10_before={"speed": 90},
            mapped10_after={"speed": 92},
            touched_entry_offsets=[0x1234, 0x5678],
        )

    monkeypatch.setattr(gui, "patch_player_visible_skills_dd6361", fake_patch_action)

    gui.PM99DatabaseEditor.open_player_skill_patch_dialog(editor)

    assert calls["patch"]["output_file"] is None
    assert calls["patch"]["in_place"] is True
    assert calls["patch"]["create_backup_before_write"] is True
    assert errors == []
    assert infos and "Backup: /tmp/JUG98030.FDI.backup" in infos[0][1]


def test_refresh_visible_skill_panel_populates_panel_vars(monkeypatch):
    editor = _FakeEditor()
    editor.file_path = "DBDAT/JUG98030.FDI"
    editor.current_record = (0x10, SimpleNamespace(given_name="David Robert", surname="BECKHAM", name=""))
    editor.visible_skill_field_order = ["speed", "stamina", "passing"]
    editor.visible_skill_vars = {k: _FakeIntVar(0) for k in editor.visible_skill_field_order}
    editor.visible_skill_status_var = _FakeVar()
    editor.visible_skill_baseline = {}
    editor.visible_skill_snapshot = None
    editor._current_player_visible_skill_query = lambda: "David Robert BECKHAM"
    editor._visible_skill_status_text = lambda snapshot=None: "dd6361 visible skills loaded: David Robert BECKHAM"
    editor._set_visible_skill_panel_unavailable = lambda reason="unavailable": None

    monkeypatch.setattr(
        gui,
        "inspect_player_visible_skills_dd6361",
        lambda **kwargs: SimpleNamespace(
            resolved_bio_name="David Robert BECKHAM",
            mapped10_order=["speed", "stamina", "passing"],
            mapped10={"speed": 90, "stamina": 85, "passing": 90},
        ),
    )

    snap = gui.PM99DatabaseEditor.refresh_visible_skill_panel(editor, show_dialog_errors=True)

    assert snap.resolved_bio_name == "David Robert BECKHAM"
    assert editor.visible_skill_baseline == {"speed": 90, "stamina": 85, "passing": 90}
    assert editor.visible_skill_vars["speed"].get() == 90
    assert editor.visible_skill_vars["stamina"].get() == 85
    assert "loaded" in (editor.visible_skill_status_var.get() or "")


def test_patch_visible_skill_panel_in_place_calls_backend(monkeypatch):
    editor = _FakeEditor()
    editor.file_path = "DBDAT/JUG98030.FDI"
    editor.file_data = b""
    editor.visible_skill_snapshot = SimpleNamespace(
        resolved_bio_name="David Robert BECKHAM",
        mapped10={"speed": 90, "stamina": 85},
    )
    editor.visible_skill_field_order = ["speed", "stamina"]
    editor.visible_skill_baseline = {"speed": 90, "stamina": 85}
    editor.visible_skill_vars = {"speed": _FakeIntVar(92), "stamina": _FakeIntVar(85)}
    editor.refresh_visible_skill_panel = lambda show_dialog_errors=False: editor.visible_skill_snapshot
    editor._collect_visible_skill_panel_updates = lambda: ({"speed": 92}, None)
    infos = []
    errors = []
    confirms = []

    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: confirms.append((args, kwargs)) or True)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))

    calls = {}

    def fake_patch_action(**kwargs):
        calls["patch"] = kwargs
        return SimpleNamespace(
            resolved_bio_name="David Robert BECKHAM",
            output_file="DBDAT/JUG98030.FDI",
            backup_path="DBDAT/JUG98030.FDI.backup",
        )

    monkeypatch.setattr(gui, "patch_player_visible_skills_dd6361", fake_patch_action)
    gui.PM99DatabaseEditor.patch_visible_skill_panel_in_place(editor)

    assert calls["patch"] == {
        "file_path": "DBDAT/JUG98030.FDI",
        "player_name": "David Robert BECKHAM",
        "updates": {"speed": 92},
        "output_file": None,
        "in_place": True,
        "create_backup_before_write": True,
        "json_output": None,
    }
    assert confirms, "expected confirmation prompt"
    assert errors == []
    assert infos and "Backup: DBDAT/JUG98030.FDI.backup" in infos[0][1]
    assert any("patched" in str(v).lower() for v in editor.status_var.values)


def test_stage_visible_skill_panel_changes_queues_patch(monkeypatch):
    editor = _FakeEditor()
    editor.file_path = "DBDAT/JUG98030.FDI"
    editor.visible_skill_snapshot = SimpleNamespace(
        resolved_bio_name="David Robert BECKHAM",
        target_query="Beckham",
        mapped10={"speed": 90, "stamina": 85},
    )
    editor.visible_skill_baseline = {"speed": 90, "stamina": 85}
    editor.staged_visible_skill_patches = {}
    editor.visible_skill_status_var = _FakeVar()
    editor._visible_skill_stage_key = lambda file_path, name: (file_path, name.upper())
    editor._collect_visible_skill_panel_updates = lambda: ({"speed": 94}, None)
    infos = []
    errors = []
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))

    gui.PM99DatabaseEditor.stage_visible_skill_panel_changes(editor)

    assert errors == []
    assert infos and "staged" in infos[0][1].lower()
    key = ("DBDAT/JUG98030.FDI", "DAVID ROBERT BECKHAM")
    assert key in editor.staged_visible_skill_patches
    staged = editor.staged_visible_skill_patches[key]
    assert staged["updates"] == {"speed": 94}
    assert any("staged dd6361 visible skills" in str(v).lower() for v in editor.status_var.values)


def test_discard_visible_skill_panel_staged_changes_removes_patch_and_resets_panel(monkeypatch):
    editor = _FakeEditor()
    editor.file_path = "DBDAT/JUG98030.FDI"
    editor.visible_skill_snapshot = SimpleNamespace(
        resolved_bio_name="David Robert BECKHAM",
        mapped10={"speed": 90, "stamina": 85},
    )
    editor.visible_skill_baseline = {"speed": 90, "stamina": 85}
    editor.visible_skill_vars = {"speed": _FakeIntVar(94), "stamina": _FakeIntVar(88)}
    editor.visible_skill_status_var = _FakeVar()
    editor._visible_skill_stage_key = lambda file_path, name: (file_path, name.upper())
    editor._visible_skill_status_text = lambda snapshot=None: "dd6361 visible skills loaded: Beckham"
    editor.staged_visible_skill_patches = {
        ("DBDAT/JUG98030.FDI", "DAVID ROBERT BECKHAM"): {
            "file_path": "DBDAT/JUG98030.FDI",
            "player_name": "David Robert BECKHAM",
            "updates": {"speed": 94},
        }
    }
    infos = []

    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))

    gui.PM99DatabaseEditor.discard_visible_skill_panel_staged_changes(editor)

    assert editor.staged_visible_skill_patches == {}
    assert editor.visible_skill_vars["speed"].get() == 90
    assert editor.visible_skill_vars["stamina"].get() == 85
    assert infos and "discarded staged patch" in infos[0][1].lower()
    assert "speed" in infos[0][1].lower()
    assert any("discarded staged dd6361 visible-skill patch" in str(v).lower() for v in editor.status_var.values)
    assert editor.visible_skill_status_var.get() == "dd6361 visible skills loaded: Beckham"


def test_review_staged_visible_skill_patches_shows_summary_and_marks_current(monkeypatch):
    editor = _FakeEditor()
    editor.file_path = "DBDAT/JUG98030.FDI"
    editor.visible_skill_snapshot = SimpleNamespace(resolved_bio_name="David Robert BECKHAM")
    editor._visible_skill_stage_key = lambda file_path, name: (file_path, name.upper())
    editor.staged_visible_skill_patches = {
        ("DBDAT/JUG98030.FDI", "DAVID ROBERT BECKHAM"): {
            "file_path": "DBDAT/JUG98030.FDI",
            "player_name": "David Robert BECKHAM",
            "updates": {"speed": 94, "passing": 92},
        },
        ("DBDAT/JUG98030.FDI", "PAUL SCHOLES"): {
            "file_path": "DBDAT/JUG98030.FDI",
            "player_name": "Paul SCHOLES",
            "updates": {"shooting": 80},
        },
    }
    infos = []

    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))

    gui.PM99DatabaseEditor.review_staged_visible_skill_patches(editor)

    assert infos and infos[0][0] == "Visible Skills (dd6361)"
    msg = infos[0][1]
    assert "2 total" in msg
    assert "David Robert BECKHAM [JUG98030.FDI]" in msg
    assert "speed=94" in msg and "passing=92" in msg
    assert "[current]" in msg
    assert "Paul SCHOLES [JUG98030.FDI]" in msg


def test_visible_skill_status_text_includes_current_pending_and_global_stage_counts():
    editor = _FakeEditor()
    editor._current_visible_skill_stage_entry = lambda: {"updates": {"speed": 94, "passing": 92}}
    editor.staged_visible_skill_patches = {
        ("DBDAT/JUG98030.FDI", "DAVID ROBERT BECKHAM"): {"updates": {"speed": 94, "passing": 92}},
        ("DBDAT/JUG98030.FDI", "PAUL SCHOLES"): {"updates": {"shooting": 80}},
    }
    snapshot = SimpleNamespace(resolved_bio_name="David Robert BECKHAM")

    text = gui.PM99DatabaseEditor._visible_skill_status_text(editor, snapshot)
    assert "loaded: David Robert BECKHAM" in text
    assert "staged patch pending (2 field(s))" in text

    editor._current_visible_skill_stage_entry = lambda: None
    text = gui.PM99DatabaseEditor._visible_skill_status_text(editor, snapshot)
    assert "2 staged patch(es)" in text

    text = gui.PM99DatabaseEditor._visible_skill_status_text(editor, None)
    assert text == "dd6361 visible skills: not loaded | 2 staged patch(es)"


def test_apply_staged_visible_skill_patches_calls_backend_and_clears_queue(monkeypatch):
    editor = _FakeEditor()
    editor.file_path = None  # avoid file refresh path in helper
    editor.staged_visible_skill_patches = {
        ("DBDAT/JUG98030.FDI", "DAVID ROBERT BECKHAM"): {
            "file_path": "DBDAT/JUG98030.FDI",
            "player_name": "David Robert BECKHAM",
            "updates": {"speed": 95},
        }
    }

    calls = []

    def fake_patch_action(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            file_path=kwargs["file_path"],
            resolved_bio_name=kwargs["player_name"],
            backup_path=None,
        )

    monkeypatch.setattr(gui, "patch_player_visible_skills_dd6361", fake_patch_action)

    results = gui.PM99DatabaseEditor._apply_staged_visible_skill_patches(editor, create_backups=False)

    assert len(results) == 1
    assert calls == [
        {
            "file_path": "DBDAT/JUG98030.FDI",
            "player_name": "David Robert BECKHAM",
            "updates": {"speed": 95},
            "output_file": None,
            "in_place": True,
            "create_backup_before_write": False,
            "json_output": None,
        }
    ]
    assert editor.staged_visible_skill_patches == {}


def test_save_database_applies_staged_visible_skill_patches(tmp_path, monkeypatch):
    editor = _FakeEditor()
    editor.file_path = str(tmp_path / "JUG98030.FDI")
    editor.file_data = b"orig-player-bytes"
    Path(editor.file_path).write_bytes(editor.file_data)
    editor.modified_records = {}
    editor.modified_coach_records = {}
    editor.modified_team_records = {}
    editor.staged_visible_skill_patches = {
        ("DBDAT/JUG98030.FDI", "DAVID ROBERT BECKHAM"): {
            "file_path": editor.file_path,
            "player_name": "David Robert BECKHAM",
            "updates": {"speed": 96},
        }
    }
    editor.coach_file_path = "DBDAT/ENT98030.FDI"
    editor.team_file_path = "DBDAT/EQ98030.FDI"

    infos = []
    errors = []
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: True)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))

    calls = {}

    def fake_apply_staged(create_backups=False):
        calls["create_backups"] = create_backups
        editor.staged_visible_skill_patches.clear()
        return [SimpleNamespace(file_path=editor.file_path)]

    editor._apply_staged_visible_skill_patches = fake_apply_staged

    gui.PM99DatabaseEditor.save_database(editor)

    assert calls["create_backups"] is False
    assert errors == []
    assert infos and infos[0][0] == "Success"
    # Timestamped player backup should be created because staged visible-skill patches target the player file.
    backups = list(tmp_path.glob("JUG98030.FDI.backup_*"))
    assert backups
    assert any("database saved" in str(v).lower() for v in editor.status_var.values)
