from types import SimpleNamespace
from pathlib import Path

import app.gui as gui
from app.models import PlayerRecord


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
        self._selection = []

    def get_children(self):
        return [row["id"] for row in self.rows]

    def delete(self, *items):
        self.rows.clear()
        self._selection = []

    def insert(self, parent, index, values=(), tags=()):
        item_id = f"item{len(self.rows) + 1}"
        self.rows.append({"id": item_id, "values": tuple(values), "tags": tuple(tags)})
        return item_id

    def selection(self):
        return tuple(self._selection)

    def set_selection(self, *item_ids):
        self._selection = [str(item_id) for item_id in item_ids]

    def item(self, item_id):
        item_id = str(item_id)
        for row in self.rows:
            if row["id"] == item_id:
                return dict(row)
        return {}


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

    def configure(self, **kwargs):
        self.config(**kwargs)


class _FakeDestroyableWidget:
    def __init__(self):
        self.destroy_calls = 0

    def destroy(self):
        self.destroy_calls += 1


class _FakeContainer:
    def winfo_children(self):
        return []


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


def test_start_analysis_notebook_sets_title_and_selects_tab(monkeypatch):
    children = [_FakeDestroyableWidget(), _FakeDestroyableWidget()]

    class _FakeHost:
        def winfo_children(self):
            return list(children)

    created = {}

    class _FakeNotebookWidget:
        def __init__(self, parent):
            created["parent"] = parent
            self.pack_calls = []

        def pack(self, *args, **kwargs):
            self.pack_calls.append((args, kwargs))

    class _FakeNotebookSelector:
        def __init__(self):
            self.selected = None

        def select(self, tab):
            self.selected = tab

    monkeypatch.setattr(gui.ttk, "Notebook", _FakeNotebookWidget)

    editor = SimpleNamespace(
        analysis_report_container=_FakeHost(),
        analysis_report_title_var=_FakeVar(),
        analysis_report_hint_var=_FakeVar(),
        notebook=_FakeNotebookSelector(),
        analysis_tab="analysis-tab",
    )

    notebook = gui.PM99DatabaseEditor._start_analysis_notebook(editor, "Inspect Player Metadata")

    assert isinstance(notebook, _FakeNotebookWidget)
    assert created["parent"] is editor.analysis_report_container
    assert all(child.destroy_calls == 1 for child in children)
    assert editor.analysis_report_title_var.current == "Inspect Player Metadata"
    assert "latest confirmed parser-backed inspection output" in editor.analysis_report_hint_var.current
    assert editor.notebook.selected == "analysis-tab"


def test_format_player_metadata_inspect_report_surfaces_tail_prefix_for_name_only():
    editor = _FakeEditor()
    result = SimpleNamespace(
        storage_mode="name_only",
        record_count=3,
        records=[
            SimpleNamespace(
                offset=0x200,
                record_id=0,
                name="David BATTY",
                suffix_anchor=None,
                attribute_prefix=[1, 0, 25],
                indexed_unknown_0=None,
                indexed_unknown_1=None,
                face_components=[],
                nationality=44,
                indexed_unknown_9=None,
                indexed_unknown_10=None,
                position=2,
                birth_day=2,
                birth_month=12,
                birth_year=1968,
                height=178,
                weight=78,
            )
        ],
    )

    report = gui.PM99DatabaseEditor._format_player_metadata_inspect_report(editor, result)

    assert "Matched 1 player record(s) (parsed_records=3)" in report
    assert "tail_prefix=[1, 0, 25]" in report
    assert "read-only non-stat prefix" in report


def test_display_record_surfaces_weight_and_enables_indexed_field(monkeypatch):
    raw = b"\x00\x00\xdd\x63\x61Paul SCHOLES" + (b"\x00" * 32)
    record = SimpleNamespace(
        given_name="Paul",
        surname="SCHOLES",
        name="Paul SCHOLES",
        team_id=7,
        squad_number=18,
        nationality=30,
        dob=(16, 11, 1974),
        height=170,
        weight=68,
        attributes=[],
        raw_data=raw,
        get_position_name=lambda: "Midfielder",
    )
    editor = SimpleNamespace(
        given_name_var=_FakeVar(),
        surname_var=_FakeVar(),
        team_id_var=_FakeVar(),
        squad_var=_FakeVar(),
        position_var=_FakeVar(),
        nationality_var=_FakeVar(),
        dob_day_var=_FakeVar(),
        dob_month_var=_FakeVar(),
        dob_year_var=_FakeVar(),
        height_var=_FakeVar(),
        weight_var=_FakeVar(),
        weight_hint_var=_FakeVar(),
        weight_spinbox=_FakeWidget(),
        attr_container=_FakeContainer(),
        attr_vars=[],
        attr_labels=[],
        refresh_visible_skill_panel=lambda **kwargs: None,
        _set_visible_skill_panel_unavailable=lambda *_args, **_kwargs: None,
    )

    monkeypatch.setattr(gui, "SAVE_NAME_ONLY", False)

    gui.PM99DatabaseEditor.display_record(editor, record)

    assert editor.nationality_var.current == 30
    assert editor.weight_var.current == "68"
    assert editor.weight_hint_var.current == "(indexed JUG only)"
    assert editor.weight_spinbox.config_calls[-1]["state"] == "normal"


def test_display_record_enables_legacy_weight_slot(monkeypatch):
    raw = b"\x00" * 5 + b"Paul SCHOLES".ljust(15, b" ") + (b"\x61" * 4) + (b"\x00" * 11) + (b"\x00" * 19)
    record = SimpleNamespace(
        given_name="Paul",
        surname="SCHOLES",
        name="Paul SCHOLES",
        team_id=7,
        squad_number=18,
        nationality=44,
        dob=(16, 11, 1974),
        height=178,
        weight=78,
        attributes=[],
        raw_data=raw,
        get_position_name=lambda: "Midfielder",
    )
    editor = SimpleNamespace(
        given_name_var=_FakeVar(),
        surname_var=_FakeVar(),
        team_id_var=_FakeVar(),
        squad_var=_FakeVar(),
        position_var=_FakeVar(),
        nationality_var=_FakeVar(),
        dob_day_var=_FakeVar(),
        dob_month_var=_FakeVar(),
        dob_year_var=_FakeVar(),
        height_var=_FakeVar(),
        weight_var=_FakeVar(),
        weight_hint_var=_FakeVar(),
        weight_spinbox=_FakeWidget(),
        attr_container=_FakeContainer(),
        attr_vars=[],
        attr_labels=[],
        refresh_visible_skill_panel=lambda **kwargs: None,
        _set_visible_skill_panel_unavailable=lambda *_args, **_kwargs: None,
    )

    monkeypatch.setattr(gui, "SAVE_NAME_ONLY", False)

    gui.PM99DatabaseEditor.display_record(editor, record)

    assert editor.weight_var.current == "78"
    assert editor.weight_hint_var.current == "(legacy marker slot)"
    assert editor.weight_spinbox.config_calls[-1]["state"] == "normal"


def test_apply_changes_updates_weight(monkeypatch):
    record = PlayerRecord(
        given_name="Paul",
        surname="SCHOLES",
        name="Paul SCHOLES",
        team_id=7,
        squad_number=18,
        nationality=30,
        position_primary=2,
        birth_day=16,
        birth_month=11,
        birth_year=1974,
        height=170,
        weight=68,
        skills=[50] * 10,
        version=700,
    )
    record.nationality_id = 30

    def _var(value):
        v = _FakeVar()
        v.set(value)
        return v

    infos = []
    errors = []
    monkeypatch.setattr(gui, "SAVE_NAME_ONLY", False)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))

    editor = SimpleNamespace(
        current_record=(0x100, record),
        given_name_var=_var("Paul"),
        surname_var=_var("SCHOLES"),
        team_id_var=_var(7),
        squad_var=_var(18),
        position_var=_var("Midfielder"),
        nationality_var=_var(30),
        dob_day_var=_var(16),
        dob_month_var=_var(11),
        dob_year_var=_var(1974),
        height_var=_var(170),
        weight_var=_var("81"),
        attr_vars=[_var(value) for value in record.attributes],
        attr_labels=[f"Attr {idx}" for idx in range(len(record.attributes))],
        modified_records={},
        status_var=_FakeVar(),
    )

    gui.PM99DatabaseEditor.apply_changes(editor)

    assert errors == []
    assert record.weight == 81
    assert editor.modified_records[0x100] is record
    assert infos and "Weight: 68 → 81 kg" in infos[0][1]


def test_apply_changes_ignores_unresolved_attribute_slots(monkeypatch):
    record = PlayerRecord(
        given_name="Paul",
        surname="SCHOLES",
        name="Paul SCHOLES",
        team_id=7,
        squad_number=18,
        nationality=30,
        position_primary=2,
        birth_day=16,
        birth_month=11,
        birth_year=1974,
        height=170,
        skills=[50] * 10,
        version=700,
    )
    record.nationality_id = 30

    def _var(value):
        v = _FakeVar()
        v.set(value)
        return v

    infos = []
    errors = []
    monkeypatch.setattr(gui, "SAVE_NAME_ONLY", False)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))

    attr_values = list(record.attributes)
    attr_values[0] = 77
    attr_values[3] = 85

    editor = SimpleNamespace(
        current_record=(0x100, record),
        given_name_var=_var("Paul"),
        surname_var=_var("SCHOLES"),
        team_id_var=_var(7),
        squad_var=_var(18),
        position_var=_var("Midfielder"),
        nationality_var=_var(30),
        dob_day_var=_var(16),
        dob_month_var=_var(11),
        dob_year_var=_var(1974),
        height_var=_var(170),
        weight_var=_var(""),
        attr_vars=[_var(value) for value in attr_values],
        attr_labels=PlayerRecord.attribute_slot_labels(),
        attr_editable_indices=set(PlayerRecord.editable_attribute_indices()),
        modified_records={},
        status_var=_FakeVar(),
    )

    gui.PM99DatabaseEditor.apply_changes(editor)

    assert errors == []
    assert record.attributes[0] == 50
    assert record.attributes[3] == 85
    assert editor.modified_records[0x100] is record
    assert infos and "Attr 3 (Speed): 50 → 85" in infos[0][1]
    assert "Attr 0" not in infos[0][1]


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


def test_open_player_batch_edit_dialog_runs_dry_run_and_reports(monkeypatch):
    editor = _FakeEditor()
    editor.file_path = "DBDAT/JUG98030.FDI"
    infos = []
    errors = []

    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **kwargs: "/tmp/player_plan.csv")
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: True)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))

    calls = {}

    def fake_batch_edit_player_metadata_records(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(
            row_count=3,
            matched_row_count=2,
            changes=[
                SimpleNamespace(offset=0x20, changed_fields={"name": ("Paul SCHOLES", "Alan SMITH")}),
                SimpleNamespace(offset=0x30, changed_fields={"height": (170, 181)}),
            ],
            warnings=[SimpleNamespace(message="CSV row 4: no player matched 'Ghost PLAYER'")],
            backup_path=None,
        )

    monkeypatch.setattr(gui, "batch_edit_player_metadata_records", fake_batch_edit_player_metadata_records)

    gui.PM99DatabaseEditor.open_player_batch_edit_dialog(editor)

    assert calls == {
        "file_path": "DBDAT/JUG98030.FDI",
        "csv_path": "/tmp/player_plan.csv",
        "write_changes": False,
    }
    assert editor.root.update_calls == 1
    assert any("Running player batch edit" in v for v in editor.status_var.values)
    assert any("dry-run complete" in v for v in editor.status_var.values)
    assert errors == []
    assert infos and infos[0][0] == "Batch Edit Players from CSV"
    assert "Dry run complete" in infos[0][1]
    assert "Rows read: 3" in infos[0][1]
    assert "Matched rows: 2" in infos[0][1]
    assert "Records changed: 2" in infos[0][1]
    assert "Warnings: 1" in infos[0][1]
    assert "Ghost PLAYER" in infos[0][1]


def test_open_player_batch_edit_dialog_handles_exception(monkeypatch):
    editor = _FakeEditor()
    editor.file_path = "DBDAT/JUG98030.FDI"
    infos = []
    errors = []

    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **kwargs: "/tmp/player_plan.csv")
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: False)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))
    monkeypatch.setattr(
        gui,
        "batch_edit_player_metadata_records",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    gui.PM99DatabaseEditor.open_player_batch_edit_dialog(editor)

    assert any(v == "Player batch edit failed" for v in editor.status_var.values)
    assert infos == []
    assert errors and errors[0][0] == "Batch Edit Players from CSV"
    assert "boom" in errors[0][1]


def test_open_team_roster_batch_edit_dialog_runs_write_and_refreshes(monkeypatch):
    editor = _FakeEditor()
    editor.file_path = "DBDAT/JUG98030.FDI"
    editor.team_file_path = "DBDAT/EQ98030.FDI"
    refresh_calls = []
    editor.load_current_team_roster = lambda: refresh_calls.append(True)
    infos = []
    errors = []

    monkeypatch.setattr(gui.filedialog, "askopenfilename", lambda **kwargs: "/tmp/team_roster_plan.csv")
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: False)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))

    calls = {}

    def fake_batch_edit_team_roster_records(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(
            row_count=2,
            matched_row_count=2,
            linked_changes=[SimpleNamespace(slot_number=1)],
            same_entry_changes=[SimpleNamespace(slot_number=1)],
            warnings=[SimpleNamespace(message="CSV row 4: ignored duplicate target")],
            backup_path="/tmp/EQ98030.FDI.bak",
        )

    monkeypatch.setattr(gui, "batch_edit_team_roster_records", fake_batch_edit_team_roster_records)

    gui.PM99DatabaseEditor.open_team_roster_batch_edit_dialog(editor)

    assert calls == {
        "team_file": "DBDAT/EQ98030.FDI",
        "player_file": "DBDAT/JUG98030.FDI",
        "csv_path": "/tmp/team_roster_plan.csv",
        "write_changes": True,
    }
    assert refresh_calls == [True]
    assert editor.root.update_calls == 1
    assert any("Running team roster batch edit" in v for v in editor.status_var.values)
    assert any("complete (2 changed, 1 warning(s))" in v for v in editor.status_var.values)
    assert errors == []
    assert infos and infos[0][0] == "Batch Edit Team Roster from CSV"
    assert "Batch edit complete" in infos[0][1]
    assert "Linked rows changed: 1" in infos[0][1]
    assert "Same-entry rows changed: 1" in infos[0][1]
    assert "/tmp/EQ98030.FDI.bak" in infos[0][1]
    assert "ignored duplicate target" in infos[0][1]


def test_open_player_metadata_inspect_dialog_runs_and_reports(monkeypatch):
    editor = _FakeEditor()
    editor.file_path = "DBDAT/JUG98030.FDI"
    editor.current_record = (0x5A8EA, SimpleNamespace(given_name="Paul", surname="SCHOLES", name="Paul SCHOLES"))
    infos = []
    errors = []
    structured_views = []

    answers = iter(["Paul SCHOLES", "0x5A8EA"])
    monkeypatch.setattr(gui.simpledialog, "askstring", lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))
    monkeypatch.setattr(
        gui.PM99DatabaseEditor,
        "_show_player_metadata_inspect_dialog_view",
        lambda self, **kwargs: structured_views.append(dict(kwargs)),
    )

    calls = {}

    def fake_inspect_player_metadata_records(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(
            record_count=11479,
            matched_count=1,
            records=[
                SimpleNamespace(
                    record_id=3384,
                    offset=0x5A8EA,
                    name="Paul SCHOLES",
                    suffix_anchor=0x1F,
                    attribute_prefix=[77, 89, 107],
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
                    post_weight_byte=30,
                )
            ],
        )

    monkeypatch.setattr(gui, "inspect_player_metadata_records", fake_inspect_player_metadata_records)

    gui.PM99DatabaseEditor.open_player_metadata_inspect_dialog(editor)

    assert calls == {
        "file_path": "DBDAT/JUG98030.FDI",
        "target_name": "Paul SCHOLES",
        "target_offset": 0x5A8EA,
    }
    assert editor.root.update_calls == 1
    assert any("Inspecting player metadata" in v for v in editor.status_var.values)
    assert any("inspection complete" in v for v in editor.status_var.values)
    assert infos == []
    assert errors == []
    assert structured_views
    assert structured_views[0]["result"].matched_count == 1
    assert structured_views[0]["result"].records[0].name == "Paul SCHOLES"
    assert structured_views[0]["result"].records[0].attribute_prefix == [77, 89, 107]
    assert structured_views[0]["result"].records[0].post_weight_byte == 30
    assert structured_views[0]["result"].records[0].trailer_byte == 19
    assert structured_views[0]["result"].records[0].sidecar_byte == 13
    assert structured_views[0]["result"].records[0].weight == 68


def test_open_player_indexed_profiles_dialog_runs_and_reports(monkeypatch):
    editor = _FakeEditor()
    editor.file_path = "DBDAT/JUG98030.FDI"
    editor.current_record = (
        0x5A8EA,
        SimpleNamespace(
            nationality=30,
            position_primary=2,
            indexed_unknown_0=10,
            indexed_unknown_1=0,
            indexed_unknown_9=1,
            indexed_unknown_10=5,
        ),
    )
    infos = []
    errors = []
    structured_views = []

    answers = iter(["30", "2", "10", "0", "1", "5", "77", "89", "107", "30", "19", "13", "5"])
    monkeypatch.setattr(gui.simpledialog, "askstring", lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))
    monkeypatch.setattr(
        gui.PM99DatabaseEditor,
        "_show_player_indexed_profiles_dialog_view",
        lambda self, **kwargs: structured_views.append(dict(kwargs)),
    )

    suffix_calls = {}
    leading_calls = {}
    prefix_calls = {}
    legacy_calls = {}

    def fake_profile_indexed_player_suffix_bytes(**kwargs):
        suffix_calls.update(kwargs)
        return SimpleNamespace(
            record_count=11479,
            anchored_count=1954,
            filtered_count=4,
            nationality_filter=30,
            position_filter=2,
            buckets=[
                SimpleNamespace(
                    indexed_unknown_9=1,
                    indexed_unknown_10=5,
                    count=4,
                    sample_names=["Paul SCHOLES", "Demo PLAYER"],
                )
            ],
        )

    def fake_profile_indexed_player_leading_bytes(**kwargs):
        leading_calls.update(kwargs)
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
            position_counts=[(2, 4)],
            nationality_counts=[(30, 4)],
            buckets=[
                SimpleNamespace(
                    indexed_unknown_0=10,
                    indexed_unknown_1=0,
                    count=4,
                    sample_names=["Paul SCHOLES"],
                )
            ],
        )

    def fake_profile_indexed_player_attribute_prefixes(**kwargs):
        prefix_calls.update(kwargs)
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

    def fake_profile_player_legacy_weight_candidates(**kwargs):
        legacy_calls.update(kwargs)
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
                    top_values=[(30, 547)],
                )
            ],
        )

    monkeypatch.setattr(gui, "profile_indexed_player_suffix_bytes", fake_profile_indexed_player_suffix_bytes)
    monkeypatch.setattr(gui, "profile_indexed_player_leading_bytes", fake_profile_indexed_player_leading_bytes)
    monkeypatch.setattr(gui, "profile_indexed_player_attribute_prefixes", fake_profile_indexed_player_attribute_prefixes)
    monkeypatch.setattr(gui, "profile_player_legacy_weight_candidates", fake_profile_player_legacy_weight_candidates)

    gui.PM99DatabaseEditor.open_player_indexed_profiles_dialog(editor)

    assert suffix_calls == {
        "file_path": "DBDAT/JUG98030.FDI",
        "nationality": 30,
        "position": 2,
        "limit": 5,
    }
    assert leading_calls == {
        "file_path": "DBDAT/JUG98030.FDI",
        "nationality": 30,
        "position": 2,
        "indexed_unknown_0": 10,
        "indexed_unknown_1": 0,
        "indexed_unknown_9": 1,
        "indexed_unknown_10": 5,
        "attribute_0": 77,
        "attribute_1": 89,
        "attribute_2": 107,
        "post_weight_byte": 30,
        "trailer_byte": 19,
        "sidecar_byte": 13,
        "limit": 5,
    }
    assert prefix_calls == {
        "file_path": "DBDAT/JUG98030.FDI",
        "nationality": 30,
        "position": 2,
        "indexed_unknown_0": 10,
        "indexed_unknown_1": 0,
        "indexed_unknown_9": 1,
        "indexed_unknown_10": 5,
        "attribute_0": 77,
        "attribute_1": 89,
        "attribute_2": 107,
        "post_weight_byte": 30,
        "trailer_byte": 19,
        "sidecar_byte": 13,
        "limit": 5,
    }
    assert legacy_calls == {
        "file_path": "DBDAT/JUG98030.FDI",
    }
    assert editor.root.update_calls == 1
    assert infos == []
    assert errors == []
    assert structured_views
    assert structured_views[0]["player_file"] == "DBDAT/JUG98030.FDI"
    assert structured_views[0]["suffix_result"].buckets[0].count == 4
    assert structured_views[0]["leading_result"].buckets[0].indexed_unknown_0 == 10
    assert structured_views[0]["tail_prefix_result"].buckets[0].attribute_1 == 89
    assert structured_views[0]["tail_prefix_result"].signature_buckets[0].trailer_byte == 19
    assert structured_views[0]["tail_prefix_result"].signature_buckets[0].sidecar_byte == 13
    assert structured_views[0]["legacy_weight_result"].recommended_offset == 14


def test_open_team_roster_sources_dialog_runs_and_reports(monkeypatch):
    editor = _FakeEditor()
    editor.file_path = "DBDAT/JUG98030.FDI"
    editor.team_file_path = "DBDAT/EQ98030.FDI"
    editor.current_team = (0x10, SimpleNamespace(name="Stoke C."))
    infos = []
    errors = []
    structured_views = []

    monkeypatch.setattr(gui.simpledialog, "askstring", lambda *args, **kwargs: "Stoke C.")
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))
    monkeypatch.setattr(
        gui.PM99DatabaseEditor,
        "_show_team_roster_sources_dialog_view",
        lambda self, **kwargs: structured_views.append(dict(kwargs)),
    )

    linked_calls = {}
    overlap_calls = {}

    def fake_extract_team_rosters_eq_jug_linked(**kwargs):
        linked_calls.update(kwargs)
        return [
            {
                "team_name": "Stoke C.",
                "full_club_name": "Stoke City",
                "eq_record_id": 341,
                "mode_byte": 0,
                "ent_count": 1,
                "rows": [
                    {"pid": 9404, "flag": 0, "player_name": "Bryan SMALL"},
                    {"pid": 9412, "flag": 0, "player_name": "Peter THORNE"},
                ],
            }
        ]

    def fake_extract_team_rosters_eq_same_entry_overlap(**kwargs):
        overlap_calls.update(kwargs)
        return SimpleNamespace(
            preferred_roster_coverage={"covered_count": 514, "club_like_team_count": 530, "club_like_covered_count": 514},
            requested_team_results=[
                {
                    "team_name": "Stoke C.",
                    "full_club_name": "Stoke City",
                    "status": "strong_same_entry_run_overlap",
                    "team_offset": 0x29804,
                    "preferred_roster_match": {
                        "provenance": "same_entry_authoritative",
                        "source": {"entry_offset": 0x6D03},
                        "rows": [
                            {"is_empty_slot": False, "pid_candidate": 2510, "dd6361_name": "Demo PLAYER"},
                            {"is_empty_slot": False, "pid_candidate": 2683, "dd6361_name": None},
                        ],
                    },
                }
            ],
        )

    monkeypatch.setattr(gui, "extract_team_rosters_eq_jug_linked", fake_extract_team_rosters_eq_jug_linked)
    monkeypatch.setattr(gui, "extract_team_rosters_eq_same_entry_overlap", fake_extract_team_rosters_eq_same_entry_overlap)

    gui.PM99DatabaseEditor.open_team_roster_sources_dialog(editor)

    assert linked_calls == {
        "team_file": "DBDAT/EQ98030.FDI",
        "player_file": "DBDAT/JUG98030.FDI",
        "team_queries": ["Stoke C."],
    }
    assert overlap_calls == {
        "team_file": "DBDAT/EQ98030.FDI",
        "player_file": "DBDAT/JUG98030.FDI",
        "team_queries": ["Stoke C."],
        "top_examples": 5,
        "include_fallbacks": True,
    }
    assert editor.root.update_calls == 1
    assert infos == []
    assert errors == []
    assert structured_views
    assert structured_views[0]["team_file"] == "DBDAT/EQ98030.FDI"
    assert structured_views[0]["player_file"] == "DBDAT/JUG98030.FDI"
    assert structured_views[0]["team_query"] == "Stoke C."
    assert structured_views[0]["linked_rosters"][0]["team_name"] == "Stoke C."
    assert structured_views[0]["linked_rosters"][0]["rows"][0]["player_name"] == "Bryan SMALL"
    assert structured_views[0]["same_entry_result"].requested_team_results[0]["preferred_roster_match"]["provenance"] == "same_entry_authoritative"


def test_open_team_roster_edit_linked_dialog_runs_dry_run_and_reports(monkeypatch):
    editor = _FakeEditor()
    editor.file_path = "DBDAT/JUG98030.FDI"
    editor.team_file_path = "DBDAT/EQ98030.FDI"
    editor.current_team = (0x10, SimpleNamespace(name="Stoke C."))
    infos = []
    errors = []

    answers = iter(["1", "9404", "1"])
    monkeypatch.setattr(gui.simpledialog, "askstring", lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: True)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))

    calls = {}

    def fake_edit_team_roster_eq_jug_linked(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(
            changes=[
                SimpleNamespace(
                    team_name="Stoke C.",
                    old_player_record_id=9404,
                    new_player_record_id=9404,
                    old_flag=0,
                    new_flag=1,
                )
            ],
            warnings=[],
            backup_path=None,
        )

    monkeypatch.setattr(gui, "edit_team_roster_eq_jug_linked", fake_edit_team_roster_eq_jug_linked)

    gui.PM99DatabaseEditor.open_team_roster_edit_linked_dialog(editor)

    assert calls == {
        "team_file": "DBDAT/EQ98030.FDI",
        "player_file": "DBDAT/JUG98030.FDI",
        "team_query": "Stoke C.",
        "slot_number": 1,
        "player_record_id": 9404,
        "flag": 1,
        "write_changes": False,
    }
    assert editor.root.update_calls == 1
    assert any("Running linked team roster edit" in v for v in editor.status_var.values)
    assert any("dry-run complete" in v for v in editor.status_var.values)
    assert errors == []
    assert infos and infos[0][0] == "Edit Linked Team Roster Slot"
    assert "Dry run complete" in infos[0][1]
    assert "Rows changed: 1" in infos[0][1]
    assert "flag 0 -> 1" in infos[0][1]


def test_open_team_roster_edit_linked_dialog_handles_exception(monkeypatch):
    editor = _FakeEditor()
    editor.file_path = "DBDAT/JUG98030.FDI"
    editor.team_file_path = "DBDAT/EQ98030.FDI"
    editor.current_team = (0x10, SimpleNamespace(name="Stoke C."))
    infos = []
    errors = []

    answers = iter(["1", "", "1"])
    monkeypatch.setattr(gui.simpledialog, "askstring", lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: False)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))
    monkeypatch.setattr(
        gui,
        "edit_team_roster_eq_jug_linked",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    gui.PM99DatabaseEditor.open_team_roster_edit_linked_dialog(editor)

    assert any(v == "Linked team roster edit failed" for v in editor.status_var.values)
    assert infos == []
    assert errors and errors[0][0] == "Edit Linked Team Roster Slot"
    assert "boom" in errors[0][1]


def test_open_selected_team_roster_edit_dialog_runs_linked_write_and_refreshes(monkeypatch):
    editor = _FakeEditor()
    editor.file_path = "DBDAT/JUG98030.FDI"
    editor.team_file_path = "DBDAT/EQ98030.FDI"
    editor.team_roster_tree = _FakeTree()
    row_id = editor.team_roster_tree.insert("", "end", values=(1, "Demo PLAYER [pid 3937]"))
    editor.team_roster_tree.set_selection(row_id)
    editor.team_roster_row_meta = {
        row_id: {
            "mode": "linked",
            "team_query": "Milan",
            "team_name": "Milan",
            "slot_number": 1,
            "current_pid": 3937,
            "current_flag": 0,
        }
    }
    refresh_calls = []
    editor.load_current_team_roster = lambda: refresh_calls.append(True)

    infos = []
    errors = []
    answers = iter(["4100", "1"])
    monkeypatch.setattr(gui.simpledialog, "askstring", lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: False)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))

    calls = {}

    def fake_edit_team_roster_eq_jug_linked(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(
            changes=[
                SimpleNamespace(
                    team_name="Milan",
                    old_player_record_id=3937,
                    new_player_record_id=4100,
                    old_flag=0,
                    new_flag=1,
                )
            ],
            warnings=[],
            backup_path="/tmp/EQ98030.FDI.bak",
            applied_to_disk=True,
        )

    monkeypatch.setattr(gui, "edit_team_roster_eq_jug_linked", fake_edit_team_roster_eq_jug_linked)

    gui.PM99DatabaseEditor.open_selected_team_roster_edit_dialog(editor)

    assert calls == {
        "team_file": "DBDAT/EQ98030.FDI",
        "player_file": "DBDAT/JUG98030.FDI",
        "team_query": "Milan",
        "slot_number": 1,
        "player_record_id": 4100,
        "flag": 1,
        "write_changes": True,
    }
    assert refresh_calls == [True]
    assert editor.root.update_calls == 1
    assert any("Selected linked roster edit complete" in v for v in editor.status_var.values)
    assert errors == []
    assert infos and infos[0][0] == "Edit Selected Team Roster Slot"
    assert "Linked roster edit complete" in infos[0][1]
    assert "pid 3937 -> 4100" in infos[0][1]
    assert "/tmp/EQ98030.FDI.bak" in infos[0][1]


def test_open_selected_team_roster_edit_dialog_runs_same_entry_write_and_refreshes(monkeypatch):
    editor = _FakeEditor()
    editor.file_path = "DBDAT/JUG98030.FDI"
    editor.team_file_path = "DBDAT/EQ98030.FDI"
    editor.team_roster_tree = _FakeTree()
    row_id = editor.team_roster_tree.insert("", "end", values=(1, "Demo PLAYER [pid 2510]"))
    editor.team_roster_tree.set_selection(row_id)
    editor.team_roster_row_meta = {
        row_id: {
            "mode": "same_entry",
            "team_query": "Milan",
            "team_name": "Milan",
            "team_offset": 0x1111,
            "slot_number": 1,
            "current_pid": 2510,
        }
    }
    refresh_calls = []
    editor.load_current_team_roster = lambda: refresh_calls.append(True)

    infos = []
    errors = []
    answers = iter(["2683"])
    monkeypatch.setattr(gui.simpledialog, "askstring", lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: False)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))

    calls = {}

    def fake_edit_team_roster_same_entry_authoritative(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(
            changes=[
                SimpleNamespace(
                    team_name="Milan",
                    old_pid_candidate=2510,
                    new_pid_candidate=2683,
                    preserved_tail_bytes_hex="58595a",
                )
            ],
            warnings=[],
            backup_path=None,
            applied_to_disk=True,
        )

    monkeypatch.setattr(
        gui,
        "edit_team_roster_same_entry_authoritative",
        fake_edit_team_roster_same_entry_authoritative,
    )

    gui.PM99DatabaseEditor.open_selected_team_roster_edit_dialog(editor)

    assert calls == {
        "team_file": "DBDAT/EQ98030.FDI",
        "player_file": "DBDAT/JUG98030.FDI",
        "team_query": "Milan",
        "team_offset": 0x1111,
        "slot_number": 1,
        "pid_candidate": 2683,
        "write_changes": True,
    }
    assert refresh_calls == [True]
    assert editor.root.update_calls == 1
    assert any("Selected same-entry roster edit complete" in v for v in editor.status_var.values)
    assert errors == []
    assert infos and infos[0][0] == "Edit Selected Team Roster Slot"
    assert "Same-entry roster edit complete" in infos[0][1]
    assert "pid 2510 -> 2683" in infos[0][1]
    assert "preserved tail=58595a" in infos[0][1]


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

    monkeypatch.setattr(gui, "extract_team_rosters_eq_jug_linked", lambda **kwargs: [])
    monkeypatch.setattr(gui, "extract_team_rosters_eq_same_entry_overlap", fake_extract)
    monkeypatch.setattr(gui, "build_player_visible_skill_index_dd6361", fake_build_index)

    gui.PM99DatabaseEditor.load_current_team_roster(editor)

    assert len(editor.team_roster_tree.rows) == 2
    meta_rows = list(editor.team_roster_row_meta.values())
    assert len(meta_rows) == 2
    assert meta_rows[0]["mode"] == "same_entry"
    assert meta_rows[0]["slot_number"] == 1
    assert meta_rows[0]["current_pid"] == 3937
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
        == "Loaded supported same-entry roster rows for Milan: 2 (static SP/ST/AG/QU only; dynamic columns unresolved) [same_entry_authoritative]"
    )


def test_load_current_team_roster_accepts_known_lineup_anchor_assisted_rows(monkeypatch):
    editor = SimpleNamespace(
        team_roster_tree=_FakeTree(),
        current_team=(0x10, SimpleNamespace(name="Manchester Utd")),
        team_file_path="DBDAT/EQ98030.FDI",
        file_path="DBDAT/JUG98030.FDI",
        status_var=_FakeVar(),
    )

    def fake_extract(**kwargs):
        assert kwargs["include_fallbacks"] is True
        return SimpleNamespace(
            requested_team_results=[
                {
                    "team_name": "Manchester Utd",
                    "team_offset": 0x1234,
                    "preferred_roster_match": {
                        "provenance": "known_lineup_anchor_assisted",
                        "rows": [
                            {"is_empty_slot": False, "pid_candidate": 1852, "dd6361_name": "Henning BERG"},
                        ],
                    },
                }
            ]
        )

    monkeypatch.setattr(gui, "extract_team_rosters_eq_jug_linked", lambda **kwargs: [])
    monkeypatch.setattr(gui, "extract_team_rosters_eq_same_entry_overlap", fake_extract)
    monkeypatch.setattr(gui, "build_player_visible_skill_index_dd6361", lambda **kwargs: {})

    gui.PM99DatabaseEditor.load_current_team_roster(editor)

    assert len(editor.team_roster_tree.rows) == 1
    meta_rows = list(editor.team_roster_row_meta.values())
    assert meta_rows[0]["same_entry_provenance"] == "known_lineup_anchor_assisted"
    assert meta_rows[0]["current_pid"] == 1852
    assert (
        editor.status_var.get()
        == "Loaded supported same-entry roster rows for Manchester Utd: 1 (static SP/ST/AG/QU only; dynamic columns unresolved) [known_lineup_anchor_assisted]"
    )


def test_load_current_team_roster_prefers_eq_jug_linked_rows(monkeypatch):
    editor = SimpleNamespace(
        team_roster_tree=_FakeTree(),
        current_team=(0x10, SimpleNamespace(name="Milan")),
        team_file_path="DBDAT/EQ98030.FDI",
        file_path="DBDAT/JUG98030.FDI",
        status_var=_FakeVar(),
    )

    def fake_extract_linked(**kwargs):
        return [
            {
                "provenance": "eq_jug_linked_parser",
                "rows": [
                    {"slot_index": 0, "flag": 0, "pid": 3937, "player_name": "Demo PLAYER"},
                    {"slot_index": 1, "flag": 1, "pid": 4000, "player_name": ""},
                ],
            }
        ]

    def fake_build_index(**kwargs):
        assert kwargs == {"file_path": "DBDAT/JUG98030.FDI"}
        return {
            3937: {
                "pid": 3937,
                "resolved_bio_name": "Demo PLAYER",
                "mapped10": {"speed": 90, "stamina": 86, "aggression": 85, "quality": 90},
            }
        }

    def fail_overlap(**kwargs):
        raise AssertionError("same-entry fallback should not be called when linked rows exist")

    monkeypatch.setattr(gui, "extract_team_rosters_eq_jug_linked", fake_extract_linked)
    monkeypatch.setattr(gui, "extract_team_rosters_eq_same_entry_overlap", fail_overlap)
    monkeypatch.setattr(gui, "build_player_visible_skill_index_dd6361", fake_build_index)

    gui.PM99DatabaseEditor.load_current_team_roster(editor)

    assert len(editor.team_roster_tree.rows) == 2
    meta_rows = list(editor.team_roster_row_meta.values())
    assert len(meta_rows) == 2
    assert meta_rows[0]["mode"] == "linked"
    assert meta_rows[0]["slot_number"] == 1
    assert meta_rows[0]["current_pid"] == 3937
    assert meta_rows[0]["current_flag"] == 0
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
        == "Loaded parser-backed EQ->JUG roster rows for Milan: 2 (static SP/ST/AG/QU only; dynamic columns unresolved)"
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
    warnings = []
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *args, **kwargs: True)
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg: infos.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append((title, msg)))
    monkeypatch.setattr(gui.messagebox, "showwarning", lambda title, msg: warnings.append((title, msg)))

    calls = {}

    def fake_apply_staged(create_backups=False):
        calls["create_backups"] = create_backups
        editor.staged_visible_skill_patches.clear()
        return [SimpleNamespace(file_path=editor.file_path)]

    editor._apply_staged_visible_skill_patches = fake_apply_staged
    monkeypatch.setattr(
        gui,
        "validate_database_files",
        lambda **kwargs: SimpleNamespace(
            all_valid=True,
            files=[
                SimpleNamespace(
                    category="players",
                    file_path=kwargs["player_file"],
                    success=True,
                    valid_count=1,
                    uncertain_count=0,
                    detail="re-opened cleanly",
                )
            ],
        ),
    )

    gui.PM99DatabaseEditor.save_database(editor)

    assert calls["create_backups"] is False
    assert errors == []
    assert warnings == []
    assert infos and infos[0][0] == "Success"
    assert "Validation:" in infos[0][1]
    assert "players: OK" in infos[0][1]
    # Timestamped player backup should be created because staged visible-skill patches target the player file.
    backups = list(tmp_path.glob("JUG98030.FDI.backup_*"))
    assert backups
    assert any("revalidated" in str(v).lower() for v in editor.status_var.values)
