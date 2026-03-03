from __future__ import annotations

import copy
import csv
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app.editor_actions import (
    build_player_visible_skill_index_dd6361,
    edit_team_roster_eq_jug_linked,
    edit_team_roster_same_entry_authoritative,
    extract_team_rosters_eq_jug_linked,
    extract_team_rosters_eq_same_entry_overlap,
    inspect_player_metadata_records,
    inspect_player_visible_skills_dd6361,
    patch_player_visible_skills_dd6361,
    profile_indexed_player_attribute_prefixes,
    profile_indexed_player_leading_bytes,
    profile_indexed_player_suffix_bytes,
    validate_database_files,
    write_coach_staged_records,
    write_team_staged_records,
)
from app.editor_helpers import team_query_matches
from app.editor_sources import gather_player_records_from_fdi
from app.gui_state import (
    ClubListItemView,
    CoachProfileView,
    DirtyRecordState,
    EditorWorkspaceRoute,
    PlayerProfileView,
    RosterRowView,
    SearchResultItem,
    SelectionState,
    ValidationBannerState,
)
from app.io import FDIFile
from app.loaders import load_coaches, load_teams
from app.models import PlayerRecord
from app.settings import SAVE_NAME_ONLY


VISIBLE_SKILL_ORDER = [
    "speed",
    "stamina",
    "aggression",
    "quality",
    "handling",
    "passing",
    "dribbling",
    "heading",
    "tackling",
    "shooting",
]
VISIBLE_SKILL_LABELS = {
    "speed": "Speed",
    "stamina": "Stamina",
    "aggression": "Aggression",
    "quality": "Quality",
    "handling": "Handling",
    "passing": "Passing",
    "dribbling": "Dribbling",
    "heading": "Heading",
    "tackling": "Tackling",
    "shooting": "Shooting",
}
POSITION_OPTIONS = ["Goalkeeper", "Defender", "Midfielder", "Forward"]
POSITION_TO_CODE = {name: idx for idx, name in enumerate(POSITION_OPTIONS)}
ATTRIBUTE_LABELS = PlayerRecord.attribute_slot_labels()
TEAM_ROSTER_SUPPORTED_PROVENANCES = {"same_entry_authoritative", "known_lineup_anchor_assisted"}
UNSUPPORTED_COACH_LINK_TEXT = "Link not resolved by current parser"


def _normalize_spaces(value: str) -> str:
    return " ".join(str(value or "").split())


def _normalize_name(value: str) -> str:
    return _normalize_spaces(value).upper()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip() or default)
    except Exception:
        return int(default)


class PM99DatabaseEditor:
    """Refreshed editor-first shell for the PM99 database editor."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Premier Manager 99 - Database Editor")
        self._configure_window()

        self.file_path = "DBDAT/JUG98030.FDI"
        self.coach_file_path = "DBDAT/ENT98030.FDI"
        self.team_file_path = "DBDAT/EQ98030.FDI"

        self.file_data: bytes | None = None
        self.fdi_file: FDIFile | None = None

        self.all_records: list[tuple[int, PlayerRecord]] = []
        self.uncertain_player_records: list[tuple[int, PlayerRecord]] = []
        self.coach_records: list[tuple[int, Any]] = []
        self.team_records: list[tuple[int, Any]] = []

        self.player_index: dict[int, PlayerRecord] = {}
        self.uncertain_player_index: dict[int, PlayerRecord] = {}
        self.coach_index: dict[int, Any] = {}
        self.team_index: dict[int, Any] = {}
        self.team_lookup: dict[int, str] = {}
        self.team_alias_lookup: dict[int, tuple[str, str]] = {}
        self.player_name_lookup: dict[str, list[int]] = {}

        self.modified_records: dict[int, PlayerRecord] = {}
        self.modified_coach_records: dict[int, Any] = {}
        self.modified_team_records: dict[int, Any] = {}
        self.staged_visible_skill_patches: dict[tuple[str, str], dict[str, Any]] = {}

        self.selection_state = SelectionState()
        self.dirty_state = DirtyRecordState()
        self.validation_state = ValidationBannerState()
        self.current_route = EditorWorkspaceRoute.CLUBS

        self.current_club_offset: int | None = None
        self.current_record: tuple[int, PlayerRecord] | None = None
        self.current_coach: tuple[int, Any] | None = None
        self.current_team: tuple[int, Any] | None = None

        self.current_player_original: PlayerRecord | None = None
        self.current_visible_skill_baseline: dict[str, int] = {}
        self.current_visible_skill_target_name: str = ""
        self.current_visible_skill_source_query: str = ""
        self.current_roster_rows: list[RosterRowView] = []
        self.current_roster_meta_by_item: dict[str, RosterRowView] = {}
        self._dd6361_pid_stat_cache: dict[str, dict[int, dict[str, Any]]] = {}
        self._linked_roster_catalog_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._same_entry_overlap_cache: dict[tuple[str, str, str], Any] = {}
        self._player_catalog_loaded = False
        self._player_catalog_loading = False
        self._player_catalog_loading_mode = "idle"
        self._player_catalog_preload_after_id: str | None = None
        self._player_catalog_generation = 0
        self._search_item_map: dict[str, SearchResultItem] = {}
        self._club_item_map: dict[str, int] = {}
        self._player_result_map: dict[str, int] = {}
        self._coach_item_map: dict[str, int] = {}
        self._league_item_map: dict[str, int] = {}

        self._loading_player_form = False
        self._loading_team_form = False
        self._loading_coach_form = False
        self._provenance_visible = False
        self._left_rail_visible = True
        self._right_pane_visible = True
        self._companion_file_state = {
            "players": "not loaded",
            "teams": "not loaded",
            "coaches": "not loaded",
        }
        self._last_resolution_note = "No database set selected."

        self.setup_ui()
        self._show_empty_state()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _configure_window(self) -> None:
        desired_w, desired_h = 1500, 920
        try:
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            margin_w = 80
            margin_h = 120
            width = min(desired_w, max(480, screen_w - margin_w))
            height = min(desired_h, max(360, screen_h - margin_h))
            x = max((screen_w - width) // 2, 0)
            y = max((screen_h - height) // 2, 0)
            self.root.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            self.root.geometry("1500x920")

    def setup_ui(self) -> None:
        self._build_menu()

        if SAVE_NAME_ONLY:
            banner = tk.Label(
                self.root,
                text="SAFE MODE: only player names will be written; all other fields are view-only.",
                bg="#f8e7d6",
                fg="#6c2c00",
                padx=10,
                pady=4,
                anchor="w",
            )
            banner.pack(fill=tk.X)

        self.toolbar = ttk.Frame(self.root, padding=(8, 8, 8, 4))
        self.toolbar.pack(fill=tk.X)

        self.save_button = ttk.Button(self.toolbar, text="Save All", command=self.save_database)
        self.save_button.pack(side=tk.LEFT)

        self.toolbar_route_var = tk.StringVar(value="Clubs")
        ttk.Label(self.toolbar, textvariable=self.toolbar_route_var).pack(side=tk.LEFT, padx=(16, 0))

        self.toolbar_status_var = tk.StringVar(value="No database loaded")
        ttk.Label(self.toolbar, textvariable=self.toolbar_status_var).pack(side=tk.RIGHT)

        self.main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self.left_rail = ttk.Frame(self.main_paned, padding=8)
        self.main_paned.add(self.left_rail, weight=1)
        self._build_left_rail()

        self.center_and_right = ttk.PanedWindow(self.main_paned, orient=tk.HORIZONTAL)
        self.main_paned.add(self.center_and_right, weight=6)

        self.center_host = ttk.Frame(self.center_and_right, padding=(0, 0, 10, 0))
        self.center_and_right.add(self.center_host, weight=5)

        self.right_host = ttk.Frame(self.center_and_right)
        self.center_and_right.add(self.right_host, weight=2)

        self.center_view_stack = ttk.Frame(self.center_host)
        self.center_view_stack.pack(fill=tk.BOTH, expand=True)

        self.landing_frame = ttk.Frame(self.center_view_stack, padding=24)
        self.view_frames: dict[EditorWorkspaceRoute, ttk.Frame] = {
            EditorWorkspaceRoute.CLUBS: ttk.Frame(self.center_view_stack),
            EditorWorkspaceRoute.PLAYERS: ttk.Frame(self.center_view_stack),
            EditorWorkspaceRoute.COACHES: ttk.Frame(self.center_view_stack),
            EditorWorkspaceRoute.LEAGUES: ttk.Frame(self.center_view_stack),
        }

        for frame in [self.landing_frame, *self.view_frames.values()]:
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.player_load_overlay = ttk.Frame(self.center_view_stack, padding=24)
        overlay_inner = ttk.Frame(self.player_load_overlay, padding=18)
        overlay_inner.pack(expand=True)
        self.player_load_overlay_title_var = tk.StringVar(value="Loading Player Data")
        self.player_load_overlay_body_var = tk.StringVar(
            value="The editor is loading player records only because you requested a player-dependent view."
        )
        ttk.Label(
            overlay_inner,
            textvariable=self.player_load_overlay_title_var,
            font=("TkDefaultFont", 13, "bold"),
        ).pack(pady=(0, 8))
        ttk.Label(
            overlay_inner,
            textvariable=self.player_load_overlay_body_var,
            justify=tk.CENTER,
            wraplength=520,
        ).pack()
        self._player_load_overlay_visible = False

        self._build_landing_view()
        self._build_clubs_view()
        self._build_players_view()
        self._build_coaches_view()
        self._build_leagues_view()
        self._build_right_pane()

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(side=tk.BOTTOM, fill=tk.X)

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open Database Set...", command=self.open_file)
        file_menu.add_command(label="Save All", command=self.save_database, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Advanced Workspace", command=self.open_advanced_workspace)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        self.root.bind("<Control-s>", lambda _event: self.save_database())

    def _build_left_rail(self) -> None:
        ttk.Label(self.left_rail, text="Global Search").pack(anchor="w")
        self.global_search_var = tk.StringVar()
        self.global_search_var.trace_add("write", lambda *_: self.refresh_global_search())
        self.global_search_entry = tk.Entry(self.left_rail, textvariable=self.global_search_var, relief=tk.SOLID, bd=1)
        self.global_search_entry.pack(fill=tk.X, pady=(4, 2))
        self.global_search_hint_var = tk.StringVar(value="Load a database to search clubs, players, and coaches.")
        ttk.Label(self.left_rail, textvariable=self.global_search_hint_var, justify=tk.LEFT, wraplength=240).pack(
            anchor="w",
            fill=tk.X,
            pady=(0, 6),
        )

        self.global_search_results_host = ttk.Frame(self.left_rail)
        self.global_search_tree = ttk.Treeview(self.global_search_results_host, columns=("summary",), show="tree", height=6)
        self.global_search_tree.pack(fill=tk.BOTH, expand=True)
        self.global_search_tree.bind("<<TreeviewSelect>>", self._on_global_search_select)
        self._global_search_results_visible = True
        self._set_global_search_results_visible(False)

        ttk.Separator(self.left_rail).pack(fill=tk.X, pady=8)

        self.nav_buttons: dict[EditorWorkspaceRoute, ttk.Button] = {}
        self.nav_button_base_labels: dict[EditorWorkspaceRoute, str] = {}
        nav_section = ttk.LabelFrame(self.left_rail, text="Browse", padding=6)
        nav_section.pack(fill=tk.X)
        for route, label in (
            (EditorWorkspaceRoute.CLUBS, "Clubs"),
            (EditorWorkspaceRoute.PLAYERS, "Players"),
            (EditorWorkspaceRoute.COACHES, "Coaches"),
            (EditorWorkspaceRoute.LEAGUES, "Leagues"),
        ):
            index = len(self.nav_buttons)
            button = ttk.Button(
                nav_section,
                text=label,
                command=lambda selected_route=route: self.set_route(selected_route),
            )
            row = index // 2
            column = index % 2
            button.grid(row=row, column=column, sticky="ew", padx=2, pady=2)
            self.nav_buttons[route] = button
            self.nav_button_base_labels[route] = label
        nav_section.grid_columnconfigure(0, weight=1)
        nav_section.grid_columnconfigure(1, weight=1)

        ttk.Separator(self.left_rail).pack(fill=tk.X, pady=10)
        ttk.Label(self.left_rail, text="Database").pack(anchor="w")

        self.db_files_var = tk.StringVar(value="No files loaded")
        self.db_dirty_var = tk.StringVar(value="No staged changes")
        self.db_validation_var = tk.StringVar(value=self.validation_state.message)

        ttk.Label(self.left_rail, textvariable=self.db_files_var, justify=tk.LEFT, wraplength=240).pack(anchor="w", fill=tk.X, pady=(4, 2))
        ttk.Label(self.left_rail, textvariable=self.db_dirty_var, justify=tk.LEFT, wraplength=240).pack(anchor="w", fill=tk.X, pady=2)
        ttk.Label(self.left_rail, textvariable=self.db_validation_var, justify=tk.LEFT, wraplength=240).pack(anchor="w", fill=tk.X, pady=2)

    def _build_landing_view(self) -> None:
        container = ttk.Frame(self.landing_frame)
        container.pack(expand=True)
        self.landing_title_var = tk.StringVar(value="PM99 Database Editor")
        ttk.Label(container, textvariable=self.landing_title_var, font=("TkDefaultFont", 18, "bold")).pack(pady=(0, 8))
        self.landing_body_var = tk.StringVar(
            value=(
                "Load a PM99 database set to browse clubs, inspect rosters, "
                "edit players, and stage changes for one explicit Save All."
            )
        )
        ttk.Label(
            container,
            textvariable=self.landing_body_var,
            justify=tk.CENTER,
            wraplength=640,
        ).pack(pady=(0, 16))
        self.landing_progress_var = tk.StringVar(value="Waiting for a database.")
        ttk.Label(container, textvariable=self.landing_progress_var, justify=tk.CENTER).pack(pady=(0, 6))
        self.landing_detail_var = tk.StringVar(
            value="Select any one of JUG*.FDI, EQ*.FDI, or ENT*.FDI. The editor will resolve the full database set automatically."
        )
        ttk.Label(container, textvariable=self.landing_detail_var, justify=tk.CENTER, wraplength=700).pack(pady=(0, 14))
        ttk.Button(container, text="Load Database Set", command=self.open_file).pack()

    def _build_clubs_view(self) -> None:
        frame = self.view_frames[EditorWorkspaceRoute.CLUBS]

        ttk.Label(
            frame,
            text="Browse clubs first. Select a squad row to open a player in the editor pane.",
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(0, 6))

        toolbar = ttk.Frame(frame, padding=(0, 0, 0, 6))
        toolbar.pack(fill=tk.X)

        ttk.Label(toolbar, text="Club Search").pack(side=tk.LEFT)
        self.club_search_var = tk.StringVar()
        self.club_search_var.trace_add("write", lambda *_: self.refresh_club_view())
        tk.Entry(toolbar, textvariable=self.club_search_var, relief=tk.SOLID, bd=1, width=24).pack(side=tk.LEFT, padx=(6, 10))

        ttk.Label(toolbar, text="Country").pack(side=tk.LEFT)
        self.club_country_var = tk.StringVar(value="All")
        self.club_country_combo = ttk.Combobox(toolbar, textvariable=self.club_country_var, state="readonly", width=16)
        self.club_country_combo.pack(side=tk.LEFT, padx=(6, 10))
        self.club_country_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_club_view())

        ttk.Label(toolbar, text="League").pack(side=tk.LEFT)
        self.club_league_var = tk.StringVar(value="All")
        self.club_league_combo = ttk.Combobox(toolbar, textvariable=self.club_league_var, state="readonly", width=20)
        self.club_league_combo.pack(side=tk.LEFT, padx=(6, 10))
        self.club_league_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_club_view())

        self.club_sort_var = tk.StringVar(value="country")
        ttk.Checkbutton(
            toolbar,
            text="Group by country / league",
            variable=self.club_sort_var,
            onvalue="country",
            offvalue="flat",
            command=self.refresh_club_view,
        ).pack(side=tk.LEFT)

        content = ttk.PanedWindow(frame, orient=tk.HORIZONTAL)
        content.pack(fill=tk.BOTH, expand=True)

        left = ttk.LabelFrame(content, text="Club Browser", padding=6)
        right = ttk.Frame(content)
        content.add(left, weight=2)
        content.add(right, weight=5)

        self.club_tree = ttk.Treeview(left, columns=("team_id", "league"), show="tree headings")
        self.club_tree.heading("#0", text="Club")
        self.club_tree.heading("team_id", text="Team ID")
        self.club_tree.heading("league", text="League")
        self.club_tree.column("#0", width=200)
        self.club_tree.column("team_id", width=72, anchor=tk.CENTER)
        self.club_tree.column("league", width=150)
        self.club_tree.pack(fill=tk.BOTH, expand=True)
        self.club_tree.bind("<<TreeviewSelect>>", self._on_club_tree_select)

        summary = ttk.LabelFrame(right, text="Club Summary", padding=10)
        summary.pack(fill=tk.X)

        self.club_summary_name_var = tk.StringVar(value="No club selected")
        self.club_summary_context_var = tk.StringVar(
            value="Select a club to review team details. Player rosters load only when you request them."
        )
        self.club_summary_team_id_var = tk.StringVar(value="-")
        self.club_summary_league_var = tk.StringVar(value="-")
        self.club_summary_country_var = tk.StringVar(value="-")
        self.club_summary_coach_var = tk.StringVar(value="Coach link not resolved")
        self.club_summary_roster_var = tk.StringVar(value="-")
        self.club_summary_status_var = tk.StringVar(value="No roster loaded")
        ttk.Label(summary, textvariable=self.club_summary_name_var, font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
        ttk.Label(summary, textvariable=self.club_summary_context_var, justify=tk.LEFT, wraplength=460).pack(anchor="w", pady=(4, 8))

        metrics = ttk.Frame(summary)
        metrics.pack(fill=tk.X)
        self._build_summary_metric(metrics, 0, 0, "Team ID", self.club_summary_team_id_var)
        self._build_summary_metric(metrics, 0, 1, "League", self.club_summary_league_var)
        self._build_summary_metric(metrics, 1, 0, "Country", self.club_summary_country_var)
        self._build_summary_metric(metrics, 1, 1, "Coach", self.club_summary_coach_var)
        self._build_summary_metric(metrics, 2, 0, "Roster Count", self.club_summary_roster_var)
        self._build_summary_metric(metrics, 2, 1, "Roster Status", self.club_summary_status_var)

        action_row = ttk.Frame(right, padding=(0, 8, 0, 8))
        action_row.pack(fill=tk.X)
        self.club_load_players_button = ttk.Button(
            action_row,
            text="Load Player Data",
            command=self._load_player_data_for_current_context,
        )
        self.club_load_players_button.pack(side=tk.LEFT)
        self.club_rename_button = ttk.Button(action_row, text="Rename Club", command=lambda: self._show_editor_card("team"))
        self.club_rename_button.pack(side=tk.LEFT, padx=(6, 0))
        self.club_edit_coach_button = ttk.Button(action_row, text="Edit Coach", command=self._focus_current_coach)
        self.club_edit_coach_button.pack(side=tk.LEFT, padx=(6, 0))
        self.club_edit_slot_button = ttk.Button(action_row, text="Edit Selected Slot", command=lambda: self._open_roster_edit_dialog(None))
        self.club_edit_slot_button.pack(side=tk.LEFT, padx=(6, 0))
        self.club_export_button = ttk.Button(action_row, text="Export Roster CSV", command=self.export_current_roster_csv)
        self.club_export_button.pack(side=tk.LEFT, padx=(6, 0))
        self._set_club_action_state(has_club=False, has_roster=False, has_selected_slot=False)

        roster_frame = ttk.LabelFrame(right, text="Squad", padding=8)
        roster_frame.pack(fill=tk.BOTH, expand=True)

        roster_columns = ("slot", "name", "position", "nationality", "speed", "stamina", "aggression", "quality", "status")
        self.roster_tree = ttk.Treeview(roster_frame, columns=roster_columns, show="headings")
        headings = {
            "slot": "No.",
            "name": "Player",
            "position": "Position",
            "nationality": "Nationality",
            "speed": "SP",
            "stamina": "ST",
            "aggression": "AG",
            "quality": "QU",
            "status": "Status",
        }
        widths = {
            "slot": 48,
            "name": 220,
            "position": 90,
            "nationality": 88,
            "speed": 48,
            "stamina": 48,
            "aggression": 48,
            "quality": 48,
            "status": 160,
        }
        for column in roster_columns:
            self.roster_tree.heading(column, text=headings[column])
            self.roster_tree.column(column, width=widths[column], anchor=tk.CENTER if column in {"slot", "speed", "stamina", "aggression", "quality"} else tk.W)
        self.roster_tree.pack(fill=tk.BOTH, expand=True)
        self.roster_tree.bind("<<TreeviewSelect>>", self._on_roster_select)
        self.roster_tree.bind("<Double-1>", self._on_roster_double_click)

        self.roster_empty_var = tk.StringVar(value="Load a database to browse clubs.")
        ttk.Label(right, textvariable=self.roster_empty_var, justify=tk.LEFT).pack(anchor="w", pady=(6, 0))

    def _build_players_view(self) -> None:
        frame = self.view_frames[EditorWorkspaceRoute.PLAYERS]

        toolbar = ttk.Frame(frame, padding=(0, 0, 0, 6))
        toolbar.pack(fill=tk.X)

        ttk.Label(toolbar, text="Search").pack(side=tk.LEFT)
        self.player_search_var = tk.StringVar()
        self.player_search_var.trace_add("write", lambda *_: self.refresh_players_view())
        search_entry = tk.Entry(toolbar, textvariable=self.player_search_var, relief=tk.SOLID, bd=1, width=28)
        search_entry.pack(side=tk.LEFT, padx=(6, 10))
        search_entry.insert(0, "")

        self.players_view_hint_var = tk.StringVar(value="Searches player names, club names, and common aliases.")
        ttk.Label(
            frame,
            textvariable=self.players_view_hint_var,
            justify=tk.LEFT,
            wraplength=760,
        ).pack(anchor="w", pady=(0, 6))
        self.players_load_button = ttk.Button(
            frame,
            text="Load Player Data",
            command=self._load_player_data_for_current_context,
        )
        self.players_load_button.pack(anchor="w", pady=(0, 6))

        ttk.Label(toolbar, text="Club").pack(side=tk.LEFT)
        self.player_filter_club_var = tk.StringVar(value="All")
        self.player_filter_club_combo = ttk.Combobox(toolbar, textvariable=self.player_filter_club_var, state="readonly", width=18)
        self.player_filter_club_combo.pack(side=tk.LEFT, padx=(6, 10))
        self.player_filter_club_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_players_view())

        ttk.Label(toolbar, text="Position").pack(side=tk.LEFT)
        self.player_filter_position_var = tk.StringVar(value="All")
        self.player_filter_position_combo = ttk.Combobox(
            toolbar,
            textvariable=self.player_filter_position_var,
            state="readonly",
            values=["All", *POSITION_OPTIONS],
            width=12,
        )
        self.player_filter_position_combo.pack(side=tk.LEFT, padx=(6, 10))
        self.player_filter_position_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_players_view())

        ttk.Label(toolbar, text="Nationality").pack(side=tk.LEFT)
        self.player_filter_nationality_var = tk.StringVar()
        tk.Entry(toolbar, textvariable=self.player_filter_nationality_var, relief=tk.SOLID, bd=1, width=8).pack(side=tk.LEFT, padx=(6, 10))
        self.player_filter_nationality_var.trace_add("write", lambda *_: self.refresh_players_view())

        self.player_show_uncertain_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text="Show uncertain", variable=self.player_show_uncertain_var, command=self.refresh_players_view).pack(side=tk.LEFT)

        columns = ("name", "club", "position", "squad", "nationality")
        self.player_results_tree = ttk.Treeview(frame, columns=columns, show="headings")
        for name, heading, width in (
            ("name", "Player", 230),
            ("club", "Club", 180),
            ("position", "Position", 90),
            ("squad", "No.", 52),
            ("nationality", "Nationality", 88),
        ):
            self.player_results_tree.heading(name, text=heading)
            self.player_results_tree.column(name, width=width, anchor=tk.CENTER if name == "squad" else tk.W)
        self.player_results_tree.pack(fill=tk.BOTH, expand=True)
        self.player_results_tree.bind("<<TreeviewSelect>>", self._on_player_results_select)

    def _build_coaches_view(self) -> None:
        frame = self.view_frames[EditorWorkspaceRoute.COACHES]

        toolbar = ttk.Frame(frame, padding=(0, 0, 0, 6))
        toolbar.pack(fill=tk.X)

        ttk.Label(toolbar, text="Search").pack(side=tk.LEFT)
        self.coach_search_var = tk.StringVar()
        self.coach_search_var.trace_add("write", lambda *_: self.refresh_coaches_view())
        tk.Entry(toolbar, textvariable=self.coach_search_var, relief=tk.SOLID, bd=1, width=28).pack(side=tk.LEFT, padx=(6, 0))

        columns = ("name", "club", "team_id")
        self.coach_tree = ttk.Treeview(frame, columns=columns, show="headings")
        for name, heading, width in (
            ("name", "Coach", 220),
            ("club", "Club", 180),
            ("team_id", "Team ID", 72),
        ):
            self.coach_tree.heading(name, text=heading)
            self.coach_tree.column(name, width=width, anchor=tk.CENTER if name == "team_id" else tk.W)
        self.coach_tree.pack(fill=tk.BOTH, expand=True)
        self.coach_tree.bind("<<TreeviewSelect>>", self._on_coach_tree_select)

    def _build_leagues_view(self) -> None:
        frame = self.view_frames[EditorWorkspaceRoute.LEAGUES]

        ttk.Label(frame, text="Browse-only league navigator", font=("TkDefaultFont", 11, "bold")).pack(anchor="w", pady=(0, 6))

        self.league_tree = ttk.Treeview(frame, columns=("team_id",), show="tree headings")
        self.league_tree.heading("#0", text="Country / League / Club")
        self.league_tree.heading("team_id", text="Team ID")
        self.league_tree.column("#0", width=420)
        self.league_tree.column("team_id", width=72, anchor=tk.CENTER)
        self.league_tree.pack(fill=tk.BOTH, expand=True)
        self.league_tree.bind("<<TreeviewSelect>>", self._on_league_tree_select)

    def _build_right_pane(self) -> None:
        self.right_stack = ttk.Frame(self.right_host)
        self.right_stack.pack(fill=tk.BOTH, expand=True)

        self.editor_frames: dict[str, ttk.Frame] = {
            "empty": ttk.Frame(self.right_stack, padding=12),
            "player": ttk.Frame(self.right_stack, padding=12),
            "team": ttk.Frame(self.right_stack, padding=12),
            "coach": ttk.Frame(self.right_stack, padding=12),
        }
        for frame in self.editor_frames.values():
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._build_empty_editor()
        self._build_player_editor()
        self._build_team_editor()
        self._build_coach_editor()
        self._show_editor_card("empty")

    def _build_empty_editor(self) -> None:
        frame = self.editor_frames["empty"]
        ttk.Label(frame, text="No record selected", font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text="Select a club, player, or coach to open an editor card.",
            justify=tk.LEFT,
            wraplength=420,
        ).pack(anchor="w", pady=(6, 0))

    def _build_player_editor(self) -> None:
        frame = self.editor_frames["player"]

        header = ttk.Frame(frame)
        header.pack(fill=tk.X)

        self.player_header_name_var = tk.StringVar(value="Player")
        self.player_header_note_var = tk.StringVar(value="Select a player from a club roster or the Players browser.")
        self.player_header_club_var = tk.StringVar(value="-")
        self.player_header_squad_var = tk.StringVar(value="-")
        self.player_header_position_var = tk.StringVar(value="-")
        self.player_header_dirty_var = tk.StringVar(value="Clean")
        self.player_header_confidence_var = tk.StringVar(value="-")
        self.player_header_stage_var = tk.StringVar(value="No staged edits")
        ttk.Label(header, textvariable=self.player_header_name_var, font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
        ttk.Label(header, textvariable=self.player_header_note_var, justify=tk.LEFT, wraplength=430).pack(anchor="w", pady=(2, 8))

        header_metrics = ttk.Frame(frame)
        header_metrics.pack(fill=tk.X, pady=(0, 8))
        self._build_summary_metric(header_metrics, 0, 0, "Club", self.player_header_club_var)
        self._build_summary_metric(header_metrics, 0, 1, "Squad", self.player_header_squad_var)
        self._build_summary_metric(header_metrics, 1, 0, "Position", self.player_header_position_var)
        self._build_summary_metric(header_metrics, 1, 1, "Edit State", self.player_header_dirty_var)
        self._build_summary_metric(header_metrics, 2, 0, "Confidence", self.player_header_confidence_var)
        self._build_summary_metric(header_metrics, 2, 1, "Stage", self.player_header_stage_var)

        action_row = ttk.Frame(frame)
        action_row.pack(fill=tk.X, pady=(0, 8))
        self.player_revert_button = ttk.Button(action_row, text="Revert Changes", command=self.revert_player_changes)
        self.player_revert_button.pack(side=tk.LEFT)
        self.player_focus_club_button = ttk.Button(action_row, text="Focus Club", command=self.focus_player_club)
        self.player_focus_club_button.pack(side=tk.LEFT, padx=(6, 0))
        self.player_prev_button = ttk.Button(action_row, text="Previous Player", command=lambda: self.step_roster_player(-1))
        self.player_prev_button.pack(side=tk.LEFT, padx=(6, 0))
        self.player_next_button = ttk.Button(action_row, text="Next Player", command=lambda: self.step_roster_player(1))
        self.player_next_button.pack(side=tk.LEFT, padx=(6, 0))

        self.player_form_vars: dict[str, tk.Variable] = {
            "given_name": tk.StringVar(),
            "surname": tk.StringVar(),
            "team_id": tk.StringVar(),
            "squad_number": tk.StringVar(),
            "nationality": tk.StringVar(),
            "dob_day": tk.StringVar(),
            "dob_month": tk.StringVar(),
            "dob_year": tk.StringVar(),
            "position": tk.StringVar(),
            "height": tk.StringVar(),
            "weight": tk.StringVar(),
        }
        self.player_field_widgets: dict[str, tk.Widget] = {}
        self.player_field_labels: dict[str, ttk.Label] = {}

        identity = ttk.LabelFrame(frame, text="Identity & Registration", padding=8)
        identity.pack(fill=tk.X, pady=(0, 8))
        self._add_entry_row(identity, 0, "Given Name", "given_name")
        self._add_entry_row(identity, 1, "Surname", "surname")
        self._add_entry_row(identity, 2, "Team ID", "team_id", spin_range=(0, 65535))
        self._add_entry_row(identity, 3, "Squad Number", "squad_number", spin_range=(0, 255))
        self._add_entry_row(identity, 4, "Nationality", "nationality", spin_range=(0, 255))

        dob_row = ttk.Frame(identity)
        dob_row.grid(row=5, column=0, columnspan=2, sticky="ew", pady=2)
        label = ttk.Label(dob_row, text="DOB", width=18)
        label.pack(side=tk.LEFT)
        self.player_field_labels["dob"] = label
        for key, width, limit in (("dob_day", 4, 31), ("dob_month", 4, 12), ("dob_year", 6, 2100)):
            widget = tk.Spinbox(
                dob_row,
                from_=1 if key != "dob_year" else 1900,
                to=limit,
                textvariable=self.player_form_vars[key],
                width=width,
                relief=tk.SOLID,
                bd=1,
            )
            widget.pack(side=tk.LEFT, padx=(0, 4))
            self.player_field_widgets[key] = widget
            self.player_form_vars[key].trace_add("write", lambda *_args, group="dob": self._on_player_form_changed(group))

        football = ttk.LabelFrame(frame, text="Football Profile", padding=8)
        football.pack(fill=tk.X, pady=(0, 8))
        self.player_profile_hint_var = tk.StringVar(value="Core parser-backed football fields.")
        ttk.Label(football, textvariable=self.player_profile_hint_var, justify=tk.LEFT, wraplength=420).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )
        position_row = ttk.Frame(football)
        position_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=2)
        pos_label = ttk.Label(position_row, text="Position", width=18)
        pos_label.pack(side=tk.LEFT)
        self.player_field_labels["position"] = pos_label
        position_combo = ttk.Combobox(
            position_row,
            textvariable=self.player_form_vars["position"],
            state="readonly",
            values=POSITION_OPTIONS,
            width=20,
        )
        position_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        position_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_player_form_changed("position"))
        self.player_field_widgets["position"] = position_combo
        self._add_entry_row(football, 2, "Height (cm)", "height", spin_range=(50, 250))
        self._add_entry_row(football, 3, "Weight (kg)", "weight", spin_range=(40, 140))

        skills = ttk.LabelFrame(frame, text="Skills", padding=8)
        skills.pack(fill=tk.X, pady=(0, 8))
        self.player_skill_hint_var = tk.StringVar(
            value="Visible dd6361-backed skills. Changes are staged and validated on Save All."
        )
        ttk.Label(skills, textvariable=self.player_skill_hint_var, justify=tk.LEFT, wraplength=420).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 6)
        )
        self.player_skill_vars: dict[str, tk.StringVar] = {}
        self.player_skill_widgets: dict[str, tk.Spinbox] = {}
        for idx, field in enumerate(VISIBLE_SKILL_ORDER):
            row = 1 + (idx // 2)
            column = (idx % 2) * 2
            ttk.Label(skills, text=VISIBLE_SKILL_LABELS[field]).grid(row=row, column=column, sticky="w", padx=(0, 6), pady=2)
            var = tk.StringVar(value="0")
            widget = tk.Spinbox(skills, from_=0, to=255, textvariable=var, width=6, relief=tk.SOLID, bd=1)
            widget.grid(row=row, column=column + 1, sticky="w", pady=2)
            var.trace_add("write", lambda *_args, skill_field=field: self._on_player_skill_changed(skill_field))
            self.player_skill_vars[field] = var
            self.player_skill_widgets[field] = widget

        extra = ttk.LabelFrame(frame, text="Additional Attributes", padding=8)
        extra.pack(fill=tk.X, pady=(0, 8))
        self.player_additional_hint_var = tk.StringVar(value="Only stable, parser-backed summaries are shown here.")
        ttk.Label(extra, textvariable=self.player_additional_hint_var, justify=tk.LEFT, wraplength=420).pack(anchor="w", pady=(0, 8))
        extra_metrics = ttk.Frame(extra)
        extra_metrics.pack(fill=tk.X)
        self.player_additional_physical_var = tk.StringVar(value="-")
        self.player_additional_availability_var = tk.StringVar(value="-")
        self.player_additional_metadata_var = tk.StringVar(value="-")
        self.player_additional_structural_var = tk.StringVar(value="-")
        self._build_summary_metric(extra_metrics, 0, 0, "Physical", self.player_additional_physical_var)
        self._build_summary_metric(extra_metrics, 0, 1, "Write Support", self.player_additional_availability_var)
        self._build_summary_metric(extra_metrics, 1, 0, "Metadata", self.player_additional_metadata_var)
        self._build_summary_metric(extra_metrics, 1, 1, "Structure", self.player_additional_structural_var)

        self.player_provenance_preview_var = tk.StringVar(value="No warnings for the current record.")
        ttk.Label(frame, textvariable=self.player_provenance_preview_var, justify=tk.LEFT, wraplength=430).pack(anchor="w", pady=(0, 4))
        self.provenance_toggle_button = ttk.Button(frame, text="Show Provenance & Warnings", command=self.toggle_provenance_panel)
        self.provenance_toggle_button.pack(anchor="w")

        self.provenance_frame = ttk.LabelFrame(frame, text="Provenance & Warnings", padding=8)
        self.provenance_text = tk.Text(self.provenance_frame, height=7, wrap="word", relief=tk.SOLID, bd=1)
        self.provenance_text.pack(fill=tk.BOTH, expand=True)
        self._set_player_action_state(False, False, False)

    def _build_team_editor(self) -> None:
        frame = self.editor_frames["team"]

        self.team_header_var = tk.StringVar(value="Club / Team")
        self.team_header_note_var = tk.StringVar(value="Select a club to open its team editor.")
        self.team_header_team_id_var = tk.StringVar(value="-")
        self.team_header_league_var = tk.StringVar(value="-")
        self.team_header_country_var = tk.StringVar(value="-")
        self.team_header_dirty_var = tk.StringVar(value="Clean")
        self.team_header_roster_var = tk.StringVar(value="No roster loaded")
        ttk.Label(frame, textvariable=self.team_header_var, font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
        ttk.Label(frame, textvariable=self.team_header_note_var, justify=tk.LEFT, wraplength=430).pack(anchor="w", pady=(2, 8))

        header_metrics = ttk.Frame(frame)
        header_metrics.pack(fill=tk.X, pady=(0, 8))
        self._build_summary_metric(header_metrics, 0, 0, "Team ID", self.team_header_team_id_var)
        self._build_summary_metric(header_metrics, 0, 1, "League", self.team_header_league_var)
        self._build_summary_metric(header_metrics, 1, 0, "Country", self.team_header_country_var)
        self._build_summary_metric(header_metrics, 1, 1, "Edit State", self.team_header_dirty_var)
        self._build_summary_metric(header_metrics, 2, 0, "Roster", self.team_header_roster_var)

        self.team_form_vars: dict[str, tk.StringVar] = {
            "name": tk.StringVar(),
            "team_id": tk.StringVar(),
            "stadium": tk.StringVar(),
        }
        self.team_field_widgets: dict[str, tk.Widget] = {}

        details = ttk.LabelFrame(frame, text="Club Details", padding=8)
        details.pack(fill=tk.X, pady=(0, 8))
        self.team_detail_hint_var = tk.StringVar(value="Writable here: club name and team ID. Stadium stays read-only for reference.")
        ttk.Label(details, textvariable=self.team_detail_hint_var, justify=tk.LEFT, wraplength=420).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 6),
        )
        self._add_team_row(details, 1, "Club Name", "name")
        self._add_team_row(details, 2, "Team ID", "team_id", spin_range=(0, 65535))
        stadium_entry = self._add_team_row(details, 3, "Stadium", "stadium")
        stadium_entry.configure(state="disabled")

        coach_summary = ttk.LabelFrame(frame, text="Coach Summary", padding=8)
        coach_summary.pack(fill=tk.X, pady=(0, 8))
        self.team_coach_summary_var = tk.StringVar(value=UNSUPPORTED_COACH_LINK_TEXT)
        ttk.Label(coach_summary, textvariable=self.team_coach_summary_var, justify=tk.LEFT, wraplength=420).pack(anchor="w")
        self.team_edit_coach_button = ttk.Button(coach_summary, text="Edit Coach", command=self._focus_current_coach)
        self.team_edit_coach_button.pack(anchor="w", pady=(6, 0))
        self.team_edit_coach_button.state(["disabled"])

        roster_actions = ttk.LabelFrame(frame, text="Roster Actions", padding=8)
        roster_actions.pack(fill=tk.X, pady=(0, 8))
        self.team_roster_hint_var = tk.StringVar(
            value="Choose a squad row in the Clubs view to enable slot-specific roster tools."
        )
        ttk.Label(roster_actions, textvariable=self.team_roster_hint_var, justify=tk.LEFT, wraplength=420).pack(
            anchor="w",
            pady=(0, 6),
        )
        self.team_load_players_button = ttk.Button(
            roster_actions,
            text="Load Player Data",
            command=self._load_player_data_for_current_context,
        )
        self.team_load_players_button.pack(anchor="w", pady=(0, 6))
        roster_action_grid = ttk.Frame(roster_actions)
        roster_action_grid.pack(fill=tk.X)
        self.team_edit_slot_button = ttk.Button(
            roster_action_grid,
            text="Edit Selected Slot",
            command=lambda: self._open_roster_edit_dialog(None),
        )
        self.team_edit_slot_button.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=2)
        self.team_linked_edit_button = ttk.Button(
            roster_action_grid,
            text="Linked Source Edit",
            command=lambda: self._open_roster_edit_dialog("linked"),
        )
        self.team_linked_edit_button.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=2)
        self.team_same_entry_button = ttk.Button(
            roster_action_grid,
            text="Same-Entry Edit",
            command=lambda: self._open_roster_edit_dialog("same_entry"),
        )
        self.team_same_entry_button.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=2)
        self.team_batch_import_button = ttk.Button(
            roster_action_grid,
            text="Batch Import CSV",
            command=self._show_batch_roster_placeholder,
        )
        self.team_batch_import_button.grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=2)
        roster_action_grid.grid_columnconfigure(0, weight=1)
        roster_action_grid.grid_columnconfigure(1, weight=1)

        provenance = ttk.LabelFrame(frame, text="Data Provenance", padding=8)
        provenance.pack(fill=tk.BOTH, expand=True)
        self.team_provenance_var = tk.StringVar(value="")
        ttk.Label(provenance, textvariable=self.team_provenance_var, justify=tk.LEFT, wraplength=420).pack(anchor="w")

        action_row = ttk.Frame(frame)
        action_row.pack(fill=tk.X, pady=(8, 0))
        self.team_revert_button = ttk.Button(action_row, text="Revert Club Changes", command=self.revert_team_changes)
        self.team_revert_button.pack(side=tk.LEFT)
        self._set_team_editor_action_state(has_club=False, has_roster=False, has_selected_slot=False)

    def _build_coach_editor(self) -> None:
        frame = self.editor_frames["coach"]

        self.coach_header_var = tk.StringVar(value="Coach")
        self.coach_meta_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.coach_header_var, font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
        ttk.Label(frame, textvariable=self.coach_meta_var, justify=tk.LEFT).pack(anchor="w", pady=(2, 8))

        self.coach_form_vars: dict[str, tk.StringVar] = {
            "given_name": tk.StringVar(),
            "surname": tk.StringVar(),
        }
        self.coach_field_widgets: dict[str, tk.Widget] = {}

        details = ttk.LabelFrame(frame, text="Coach Details", padding=8)
        details.pack(fill=tk.X, pady=(0, 8))
        self._add_coach_row(details, 0, "Given Name", "given_name")
        self._add_coach_row(details, 1, "Surname", "surname")

        link_frame = ttk.LabelFrame(frame, text="Linked Club", padding=8)
        link_frame.pack(fill=tk.X, pady=(0, 8))
        self.coach_link_var = tk.StringVar(value=UNSUPPORTED_COACH_LINK_TEXT)
        ttk.Label(link_frame, textvariable=self.coach_link_var, justify=tk.LEFT).pack(anchor="w")

        action_row = ttk.Frame(frame)
        action_row.pack(fill=tk.X)
        ttk.Button(action_row, text="Revert Coach Changes", command=self.revert_coach_changes).pack(side=tk.LEFT)

    def _add_entry_row(
        self,
        parent: tk.Misc,
        row: int,
        label_text: str,
        field_name: str,
        *,
        spin_range: tuple[int, int] | None = None,
    ) -> tk.Widget:
        label = ttk.Label(parent, text=label_text, width=18)
        label.grid(row=row, column=0, sticky="w", pady=2)
        self.player_field_labels[field_name] = label

        variable = self.player_form_vars[field_name]
        if spin_range is None:
            widget: tk.Widget = tk.Entry(parent, textvariable=variable, relief=tk.SOLID, bd=1)
        else:
            widget = tk.Spinbox(
                parent,
                from_=spin_range[0],
                to=spin_range[1],
                textvariable=variable,
                relief=tk.SOLID,
                bd=1,
                width=8,
            )
        widget.grid(row=row, column=1, sticky="ew", pady=2)
        parent.grid_columnconfigure(1, weight=1)
        self.player_field_widgets[field_name] = widget
        variable.trace_add("write", lambda *_args, changed_field=field_name: self._on_player_form_changed(changed_field))
        return widget

    def _add_team_row(
        self,
        parent: tk.Misc,
        row: int,
        label_text: str,
        field_name: str,
        *,
        spin_range: tuple[int, int] | None = None,
    ) -> tk.Widget:
        ttk.Label(parent, text=label_text, width=18).grid(row=row, column=0, sticky="w", pady=2)
        variable = self.team_form_vars[field_name]
        if spin_range is None:
            widget: tk.Widget = tk.Entry(parent, textvariable=variable, relief=tk.SOLID, bd=1)
        else:
            widget = tk.Spinbox(
                parent,
                from_=spin_range[0],
                to=spin_range[1],
                textvariable=variable,
                relief=tk.SOLID,
                bd=1,
                width=8,
            )
        widget.grid(row=row, column=1, sticky="ew", pady=2)
        parent.grid_columnconfigure(1, weight=1)
        self.team_field_widgets[field_name] = widget
        variable.trace_add("write", lambda *_args, changed_field=field_name: self._on_team_form_changed(changed_field))
        return widget

    def _add_coach_row(self, parent: tk.Misc, row: int, label_text: str, field_name: str) -> tk.Widget:
        ttk.Label(parent, text=label_text, width=18).grid(row=row, column=0, sticky="w", pady=2)
        variable = self.coach_form_vars[field_name]
        widget = tk.Entry(parent, textvariable=variable, relief=tk.SOLID, bd=1)
        widget.grid(row=row, column=1, sticky="ew", pady=2)
        parent.grid_columnconfigure(1, weight=1)
        self.coach_field_widgets[field_name] = widget
        variable.trace_add("write", lambda *_args, changed_field=field_name: self._on_coach_form_changed(changed_field))
        return widget

    def _build_summary_metric(
        self,
        parent: tk.Misc,
        row: int,
        column: int,
        label_text: str,
        value_var: tk.StringVar,
    ) -> None:
        card = ttk.Frame(parent, padding=(0, 0, 12, 8))
        card.grid(row=row, column=column, sticky="ew")
        ttk.Label(card, text=label_text, font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
        ttk.Label(card, textvariable=value_var, justify=tk.LEFT, wraplength=240).pack(anchor="w")
        parent.grid_columnconfigure(column, weight=1)

    def _show_empty_state(self) -> None:
        self._companion_file_state = {
            "players": "not loaded",
            "teams": "not loaded",
            "coaches": "not loaded",
        }
        self._player_catalog_loaded = False
        self._player_catalog_loading = False
        self._hide_left_rail()
        self._hide_right_pane()
        self.landing_frame.lift()
        self._set_navigation_enabled(False)
        self.landing_title_var.set("PM99 Database Editor")
        self.landing_body_var.set(
            "Load a PM99 database set to browse clubs, inspect rosters, edit players, and stage changes for one explicit Save All."
        )
        self.landing_progress_var.set("Waiting for a database.")
        self.landing_detail_var.set(
            "Select any one of JUG*.FDI, EQ*.FDI, or ENT*.FDI. The editor will resolve the full database set automatically."
        )
        self._refresh_footer_state()
        self._update_route_label()

    def _show_editor_card(self, key: str) -> None:
        frame = self.editor_frames.get(key)
        if frame is not None:
            frame.lift()

    def _show_player_load_overlay(self, reason_label: str) -> None:
        self.player_load_overlay_title_var.set("Loading Player Data")
        self.player_load_overlay_body_var.set(
            "The editor is loading player records for {reason}. "
            "This only happens when you open a player-dependent view.".format(reason=reason_label)
        )
        if not self._player_load_overlay_visible:
            self.player_load_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
            self._player_load_overlay_visible = True
        self.player_load_overlay.lift()

    def _hide_player_load_overlay(self) -> None:
        if self._player_load_overlay_visible:
            self.player_load_overlay.place_forget()
            self._player_load_overlay_visible = False

    def _hide_left_rail(self) -> None:
        if self._left_rail_visible:
            try:
                self.main_paned.forget(self.left_rail)
            except Exception:
                pass
            self._left_rail_visible = False

    def _ensure_left_rail(self) -> None:
        if not self._left_rail_visible:
            self.main_paned.insert(0, self.left_rail, weight=1)
            self._left_rail_visible = True

    def _hide_right_pane(self) -> None:
        if self._right_pane_visible:
            try:
                self.center_and_right.forget(self.right_host)
            except Exception:
                pass
            self._right_pane_visible = False

    def _ensure_right_pane(self) -> None:
        if not self._right_pane_visible:
            self.center_and_right.add(self.right_host, weight=2)
            self._right_pane_visible = True

    def _set_navigation_enabled(self, enabled: bool) -> None:
        button_state = "!disabled" if enabled else "disabled"
        for button in self.nav_buttons.values():
            try:
                button.state([button_state] if enabled else ["disabled"])
            except Exception:
                pass
        try:
            self.global_search_entry.configure(state="normal" if enabled else "disabled")
        except Exception:
            pass
        try:
            self.global_search_tree.configure(selectmode="browse" if enabled else "none")
        except Exception:
            pass
        if enabled:
            active_query = _normalize_spaces(self.global_search_var.get())
            self.global_search_hint_var.set(
                "Select a result to jump directly into the editor."
                if active_query and self._search_item_map
                else (
                    "No matches for the current search."
                    if active_query
                    else "Type a club, player, or coach name to search."
                )
            )
        else:
            self.global_search_hint_var.set("Load a database to search clubs, players, and coaches.")
            self._set_global_search_results_visible(False)

    def _set_global_search_results_visible(self, visible: bool) -> None:
        if visible and not self._global_search_results_visible:
            self.global_search_results_host.pack(fill=tk.X, pady=(0, 6))
            self._global_search_results_visible = True
        elif not visible and self._global_search_results_visible:
            self.global_search_results_host.pack_forget()
            self._global_search_results_visible = False

    def _update_nav_button_labels(self) -> None:
        for route, button in self.nav_buttons.items():
            base_label = self.nav_button_base_labels.get(route, route.value.title())
            if route == EditorWorkspaceRoute.PLAYERS and not self._player_catalog_loaded and self.file_path:
                button.configure(text=f"{base_label} (on demand)")
                continue
            counts = {
                EditorWorkspaceRoute.CLUBS: len(self.team_index),
                EditorWorkspaceRoute.PLAYERS: len(self.player_index),
                EditorWorkspaceRoute.COACHES: len(self.coach_index),
                EditorWorkspaceRoute.LEAGUES: len(self.team_index),
            }
            count = counts.get(route, 0)
            button.configure(text=f"{base_label} ({count})" if count else base_label)

    def set_route(self, route: EditorWorkspaceRoute) -> None:
        if not self.player_index and not self.team_index and not self.coach_index:
            self.current_route = route
            self._update_route_label()
            self.landing_frame.lift()
            return
        self.current_route = route
        self._update_route_label()
        self._ensure_left_rail()
        self._ensure_right_pane()
        self.view_frames[route].lift()
        if route == EditorWorkspaceRoute.CLUBS:
            self.refresh_club_view()
        elif route == EditorWorkspaceRoute.PLAYERS:
            self.refresh_players_view()
        elif route == EditorWorkspaceRoute.COACHES:
            self.refresh_coaches_view()
        elif route == EditorWorkspaceRoute.LEAGUES:
            self.refresh_leagues_view()

    def _update_route_label(self) -> None:
        if not (self.player_index or self.team_index or self.coach_index):
            self.toolbar_route_var.set("Welcome")
            return
        self.toolbar_route_var.set(self.current_route.value.title())

    def _resolve_database_set_from_selection(self, selected: Path) -> tuple[Path | None, Path | None, Path | None, list[str]]:
        directory = selected.parent
        notes: list[str] = [f"Selected: {selected.name}"]
        try:
            candidates = [item for item in directory.iterdir() if item.is_file()]
        except Exception:
            candidates = []

        by_upper_name = {item.name.upper(): item for item in candidates}
        upper_stem = selected.stem.upper()
        suffix_digits = "".join(ch for ch in upper_stem if ch.isdigit())

        def _pick(prefix: str, default_name: str) -> Path | None:
            exact_with_suffix = f"{prefix}{suffix_digits}.FDI" if suffix_digits else None
            if exact_with_suffix and exact_with_suffix in by_upper_name:
                return by_upper_name[exact_with_suffix]
            if default_name.upper() in by_upper_name:
                return by_upper_name[default_name.upper()]
            if selected.name.upper().startswith(prefix) and selected.suffix.upper() == ".FDI":
                return selected
            prefix_matches = sorted(
                [
                    item
                    for item in candidates
                    if item.suffix.upper() == ".FDI" and item.name.upper().startswith(prefix)
                ],
                key=lambda item: (len(item.name), item.name.upper()),
            )
            return prefix_matches[0] if prefix_matches else None

        player_path = _pick("JUG", "JUG98030.FDI")
        team_path = _pick("EQ", "EQ98030.FDI")
        coach_path = _pick("ENT", "ENT98030.FDI")

        if player_path is None:
            notes.append("Player DB not found")
        if team_path is None:
            notes.append("Club DB not found")
        if coach_path is None:
            notes.append("Coach DB not found")

        resolved_bits = []
        if player_path is not None:
            resolved_bits.append(f"players={player_path.name}")
        if team_path is not None:
            resolved_bits.append(f"clubs={team_path.name}")
        if coach_path is not None:
            resolved_bits.append(f"coaches={coach_path.name}")
        if resolved_bits:
            notes.append("Resolved set: " + ", ".join(resolved_bits))

        return player_path, team_path, coach_path, notes

    def _cancel_player_preload_schedule(self) -> None:
        after_id = self._player_catalog_preload_after_id
        if after_id is None:
            return
        self._player_catalog_preload_after_id = None
        try:
            self.root.after_cancel(after_id)
        except Exception:
            pass

    def _schedule_background_player_preload(self, delay_ms: int = 1500) -> None:
        self._cancel_player_preload_schedule()
        if (
            self._player_catalog_loaded
            or self._player_catalog_loading
            or not self.file_path
            or self._companion_file_state.get("players") not in {"deferred", "loading"}
        ):
            return
        self._player_catalog_preload_after_id = self.root.after(delay_ms, self._begin_background_player_preload)

    def _begin_background_player_preload(self) -> None:
        self._player_catalog_preload_after_id = None
        if self._player_catalog_loaded or self._player_catalog_loading or not self.file_path:
            return

        path = Path(self.file_path)
        if not path.exists():
            return

        generation = self._player_catalog_generation
        self._player_catalog_loading = True
        self._player_catalog_loading_mode = "background"
        self._companion_file_state["players"] = "loading"
        self.validation_state = ValidationBannerState(status="loading", message="Warming player data in background")
        self.status_var.set("Warming player data in background...")
        self.toolbar_status_var.set("Background-loading players...")
        self._refresh_footer_state()

        worker = threading.Thread(
            target=self._background_player_preload_worker,
            args=(generation, path),
            daemon=True,
        )
        worker.start()

    def _background_player_preload_worker(self, generation: int, path: Path) -> None:
        try:
            fdi = FDIFile(str(path))
            fdi.load(include_scanner_fallback=True)
            valid_players, uncertain_players = gather_player_records_from_fdi(fdi)
            try:
                self.root.after(
                    0,
                    lambda: self._complete_background_player_preload(
                        generation,
                        fdi,
                        valid_players,
                        uncertain_players,
                        None,
                    ),
                )
            except Exception:
                pass
        except Exception as exc:
            try:
                self.root.after(
                    0,
                    lambda message=str(exc): self._complete_background_player_preload(
                        generation,
                        None,
                        [],
                        [],
                        message,
                    ),
                )
            except Exception:
                pass

    def _apply_loaded_player_catalog(
        self,
        fdi: FDIFile,
        valid_players: list[Any],
        uncertain_players: list[Any],
        *,
        status_prefix: str,
    ) -> None:
        self.file_data = bytes(getattr(fdi, "file_data", b"")) or self.file_data
        self.fdi_file = fdi
        self.all_records = [(entry.offset, entry.record) for entry in valid_players]
        self.uncertain_player_records = [(entry.offset, entry.record) for entry in uncertain_players]
        self._player_catalog_loaded = True
        self._companion_file_state["players"] = "loaded"

        missing_parts = []
        if self._companion_file_state.get("teams") != "loaded":
            missing_parts.append("club DB missing")
        if self._companion_file_state.get("coaches") != "loaded":
            missing_parts.append("coach DB missing")
        if missing_parts:
            self.validation_state = ValidationBannerState(
                status="warning",
                message="Ready for editing (" + ", ".join(missing_parts) + ")",
            )
        else:
            self.validation_state = ValidationBannerState(status="ok", message="Ready for editing")

        self._rebuild_indexes()
        self._refresh_filter_choices()
        self._refresh_all_views()
        self._refresh_footer_state()

        if self.current_club_offset is not None:
            self._select_club_by_offset(self.current_club_offset, focus_editor=False)
        if self.current_route == EditorWorkspaceRoute.PLAYERS:
            self.refresh_players_view()

        self.status_var.set(
            f"{status_prefix}: {len(self.all_records)} visible, {len(self.uncertain_player_records)} uncertain"
        )
        self.toolbar_status_var.set(
            f"{Path(self.file_path).name} | players {len(self.all_records)} | clubs {len(self.team_records)} | coaches {len(self.coach_records)}"
        )

    def _complete_background_player_preload(
        self,
        generation: int,
        fdi: FDIFile | None,
        valid_players: list[Any],
        uncertain_players: list[Any],
        error_message: str | None,
    ) -> None:
        if generation != self._player_catalog_generation:
            return

        self._player_catalog_loading = False
        self._player_catalog_loading_mode = "idle"

        if error_message:
            self._companion_file_state["players"] = "deferred"
            self.validation_state = ValidationBannerState(
                status="warning",
                message="Ready for browsing (player data still loads on demand)",
            )
            self.status_var.set("Background player warmup failed; player data is still available on demand")
            self.toolbar_status_var.set(
                f"{Path(self.file_path).name} | players on demand | clubs {len(self.team_records)} | coaches {len(self.coach_records)}"
            )
            self._refresh_footer_state()
            self._hide_player_load_overlay()
            return

        if fdi is None:
            return

        self._apply_loaded_player_catalog(
            fdi,
            valid_players,
            uncertain_players,
            status_prefix="Player data ready",
        )
        self._hide_player_load_overlay()

    def _ensure_player_catalog_loaded(self, reason_label: str) -> bool:
        if self._player_catalog_loaded:
            return True
        if self._player_catalog_loading:
            if self._player_catalog_loading_mode == "background":
                self._show_player_load_overlay(reason_label)
                self.player_load_overlay_body_var.set(
                    "Player data is already warming in the background. "
                    "The selected player-dependent view will refresh as soon as the load finishes."
                )
            return False

        self._cancel_player_preload_schedule()
        path = Path(self.file_path)
        if not path.exists():
            return False

        self._player_catalog_loading = True
        self._player_catalog_loading_mode = "manual"
        self._show_player_load_overlay(reason_label)
        self.status_var.set(f"Loading player data for {reason_label}...")
        self.toolbar_status_var.set("Loading players...")
        self.validation_state = ValidationBannerState(status="loading", message="Loading player data on demand")
        self._companion_file_state["players"] = "loading"
        self._refresh_footer_state()
        self.root.update()

        try:
            fdi = FDIFile(str(path))
            fdi.load(include_scanner_fallback=True)
            valid_players, uncertain_players = gather_player_records_from_fdi(fdi)
            self._apply_loaded_player_catalog(
                fdi,
                valid_players,
                uncertain_players,
                status_prefix="Player data loaded",
            )
            return True
        except Exception as exc:
            self._companion_file_state["players"] = "error"
            self.validation_state = ValidationBannerState(status="error", message="Player data load failed")
            self.status_var.set("Player data load failed")
            self.toolbar_status_var.set("Player load failed")
            self._refresh_footer_state()
            messagebox.showerror(
                "Player Data",
                f"Failed to load player records on demand:\n{exc}",
            )
            return False
        finally:
            self._player_catalog_loading = False
            self._player_catalog_loading_mode = "idle"
            self._hide_player_load_overlay()

    def _load_player_data_for_current_context(self) -> None:
        if self._player_catalog_loaded:
            return

        if self.current_route == EditorWorkspaceRoute.PLAYERS:
            reason_label = "the Players view"
        elif self.current_club_offset is not None and self.current_team is not None:
            reason_label = f"club roster for {self._team_name(self.current_team[1])}"
        else:
            reason_label = "player-dependent views"

        if self._player_catalog_loading:
            if self._player_catalog_loading_mode == "background":
                self._show_player_load_overlay(reason_label)
                self.player_load_overlay_body_var.set(
                    "Player data is already warming in the background. "
                    "The selected view will populate automatically when it is ready."
                )
            return

        if not self._ensure_player_catalog_loaded(reason_label):
            return

        if self.current_route == EditorWorkspaceRoute.PLAYERS:
            self.refresh_players_view()
        elif self.current_club_offset is not None:
            self._select_club_by_offset(self.current_club_offset, focus_editor=False)

    def open_file(self) -> None:
        if not self._confirm_navigation_away_from_dirty("load another database"):
            return

        filename = filedialog.askopenfilename(
            title="Select Any PM99 Database File (JUG / EQ / ENT)",
            filetypes=[("FDI files", "*.FDI"), ("All files", "*.*")],
            initialdir=str(Path(self.file_path).parent if self.file_path else "DBDAT"),
        )
        if not filename:
            return

        selected = Path(filename)
        player_path, team_path, coach_path, notes = self._resolve_database_set_from_selection(selected)
        self._last_resolution_note = " | ".join(notes)
        if player_path is None:
            messagebox.showerror(
                "Load Database Set",
                (
                    "Could not resolve a player database in the selected folder.\n\n"
                    "Select any one of JUG*.FDI, EQ*.FDI, or ENT*.FDI from a folder that contains the full PM99 database set."
                ),
            )
            return

        self.file_path = str(player_path)
        self.team_file_path = str(team_path) if team_path is not None else str(selected.parent / "EQ98030.FDI")
        self.coach_file_path = str(coach_path) if coach_path is not None else str(selected.parent / "ENT98030.FDI")
        self.load_database()

    def load_database(self) -> None:
        path = Path(self.file_path)
        if not path.exists():
            messagebox.showerror("Load Database Set", f"Player file not found:\n{path}")
            self.status_var.set("Player file not found")
            return

        self._player_catalog_generation += 1
        self._cancel_player_preload_schedule()

        team_path = Path(self.team_file_path)
        coach_path = Path(self.coach_file_path)

        self.landing_frame.lift()
        self.landing_title_var.set("Loading PM99 Databases")
        self.landing_body_var.set("Reading player, club, and coach data into the editor shell.")
        self.status_var.set("Loading database...")
        self.toolbar_status_var.set("Loading database...")
        self.landing_progress_var.set("Opening player database...")
        self.landing_detail_var.set(self._last_resolution_note)
        self.db_files_var.set(
            "Loading:\nPlayers: {players}\nTeams: {teams}\nCoaches: {coaches}".format(
                players=Path(self.file_path).name,
                teams=Path(self.team_file_path).name if self.team_file_path else "(missing)",
                coaches=Path(self.coach_file_path).name if self.coach_file_path else "(missing)",
            )
        )
        self.db_dirty_var.set("No staged changes")
        self.db_validation_var.set("Loading companion databases...")
        self.root.update_idletasks()

        try:
            self.file_data = path.read_bytes()
            self.fdi_file = None
            valid_players: list[Any] = []
            uncertain_players: list[Any] = []
            self._player_catalog_loaded = False
            self._player_catalog_loading = False
            self._player_catalog_loading_mode = "idle"
            self._dd6361_pid_stat_cache.clear()
            self._linked_roster_catalog_cache.clear()
            self._same_entry_overlap_cache.clear()
            self._companion_file_state["players"] = "deferred"

            self.landing_progress_var.set("Loading club database...")
            if team_path.exists():
                self.landing_detail_var.set(
                    self._last_resolution_note
                    + f"\nPlayer file: {path.name} | Club file: {team_path.name}"
                )
                self.root.update_idletasks()
                teams = load_teams(self.team_file_path)
                self._companion_file_state["teams"] = "loaded"
            else:
                teams = []
                self._companion_file_state["teams"] = "missing"

            self.landing_progress_var.set("Loading coach database...")
            if coach_path.exists():
                self.landing_detail_var.set(
                    self._last_resolution_note
                    + "\n"
                    + (
                        f"Player file: {path.name} | Club file: {team_path.name if team_path.exists() else 'missing'} | Coach file: {coach_path.name}"
                    )
                )
                self.root.update_idletasks()
                coaches = load_coaches(self.coach_file_path)
                self._companion_file_state["coaches"] = "loaded"
            else:
                coaches = []
                self._companion_file_state["coaches"] = "missing"
            self._companion_file_state["players"] = "deferred"

            self.fdi_file = None
            self.all_records = [(entry.offset, entry.record) for entry in valid_players]
            self.uncertain_player_records = [(entry.offset, entry.record) for entry in uncertain_players]
            self.team_records = list(teams)
            self.coach_records = list(coaches)

            self.modified_records.clear()
            self.modified_team_records.clear()
            self.modified_coach_records.clear()
            self.staged_visible_skill_patches.clear()
            self.dirty_state = DirtyRecordState()
            if not team_path.exists() or not coach_path.exists():
                missing_parts = []
                if not team_path.exists():
                    missing_parts.append("club DB missing")
                if not coach_path.exists():
                    missing_parts.append("coach DB missing")
                self.validation_state = ValidationBannerState(
                    status="warning",
                    message="Ready for browsing (" + ", ".join(missing_parts) + "; player data loads on demand)",
                )
            else:
                self.validation_state = ValidationBannerState(
                    status="ok",
                    message="Ready for browsing (player data loads on demand)",
                )

            self._rebuild_indexes()
            self._refresh_filter_choices()
            self._refresh_all_views()
            self._ensure_left_rail()
            self._ensure_right_pane()
            self._set_navigation_enabled(True)
            self._refresh_footer_state()
            self.set_route(EditorWorkspaceRoute.CLUBS)
            if self.team_records:
                self._show_editor_card("team")
                self._set_club_action_state(has_club=False, has_roster=False, has_selected_slot=False)
            else:
                self._show_editor_card("empty")

            total_players = len(self.all_records)
            total_teams = len(self.team_records)
            total_coaches = len(self.coach_records)
            hidden_uncertain = len(self.uncertain_player_records)
            self.status_var.set(
                f"Loaded {total_teams} clubs and {total_coaches} coaches | player data loads on demand"
            )
            self.toolbar_status_var.set(
                f"{Path(self.file_path).name} | players on demand | clubs {total_teams} | coaches {total_coaches}"
            )
            self.landing_title_var.set("Database Loaded")
            self.landing_body_var.set("The club-first editor shell is ready. Player records will load when you open a club roster or the Players view.")
            self.landing_progress_var.set(
                f"Loaded {total_teams} clubs and {total_coaches} coaches. Player records will load on demand."
            )
            self.landing_detail_var.set(
                self._last_resolution_note
                + "\n"
                + "Visible player records: on demand"
                "{uncertain} | Team DB: {team_state} | Coach DB: {coach_state}".format(
                    uncertain=(f" (+{hidden_uncertain} uncertain hidden once loaded)" if hidden_uncertain else ""),
                    team_state=("loaded" if team_path.exists() else "missing"),
                    coach_state=("loaded" if coach_path.exists() else "missing"),
                )
            )
            self._schedule_background_player_preload()
        except Exception as exc:
            self.validation_state = ValidationBannerState(status="error", message="Load failed")
            self._companion_file_state["players"] = "error"
            self._companion_file_state["teams"] = "error" if team_path.exists() else "missing"
            self._companion_file_state["coaches"] = "error" if coach_path.exists() else "missing"
            self._hide_left_rail()
            self._hide_right_pane()
            self._set_navigation_enabled(False)
            self.landing_frame.lift()
            self.landing_title_var.set("Load Failed")
            self.landing_body_var.set("The editor could not finish loading the selected databases.")
            self.landing_progress_var.set(str(exc))
            self.landing_detail_var.set(
                self._last_resolution_note
                + "\n"
                + f"Players: {path.name} | Teams: {team_path.name if team_path.exists() else 'missing'} | Coaches: {coach_path.name if coach_path.exists() else 'missing'}"
            )
            self._refresh_footer_state()
            self.status_var.set("Database load failed")
            self.toolbar_status_var.set("Load failed")
            messagebox.showerror("Load Database Set", f"Failed to load database set:\n{exc}")

    def _rebuild_indexes(self) -> None:
        self.player_index = {offset: record for offset, record in self.all_records}
        self.uncertain_player_index = {offset: record for offset, record in self.uncertain_player_records}
        self.team_index = {offset: record for offset, record in self.team_records}
        self.coach_index = {offset: record for offset, record in self.coach_records}

        self.player_name_lookup = defaultdict(list)
        for offset, record in [*self.all_records, *self.uncertain_player_records]:
            self.player_name_lookup[_normalize_name(self._player_display_name(record))].append(offset)

        self._rebuild_team_lookup()

    def _rebuild_team_lookup(self) -> None:
        self.team_lookup = {}
        self.team_alias_lookup = {}
        for offset, original in self.team_records:
            team = self.modified_team_records.get(offset, original)
            team_id = _safe_int(getattr(team, "team_id", 0), 0)
            short_name = _normalize_spaces(getattr(team, "name", "") or "")
            full_name = _normalize_spaces(getattr(team, "full_club_name", "") or "")
            if team_id:
                self.team_lookup[team_id] = short_name
                self.team_alias_lookup[team_id] = (short_name, full_name)

    def _refresh_filter_choices(self) -> None:
        countries = sorted({self._team_country(self._team_for_offset(offset)) for offset, _ in self.team_records if self._team_country(self._team_for_offset(offset))})
        leagues = sorted({self._team_league(self._team_for_offset(offset)) for offset, _ in self.team_records if self._team_league(self._team_for_offset(offset))})
        clubs = sorted({self._team_name(self._team_for_offset(offset)) for offset, _ in self.team_records if self._team_name(self._team_for_offset(offset))})

        self.club_country_combo["values"] = ["All", *countries]
        self.club_league_combo["values"] = ["All", *leagues]
        self.player_filter_club_combo["values"] = ["All", *clubs]

        if self.club_country_var.get() not in self.club_country_combo["values"]:
            self.club_country_var.set("All")
        if self.club_league_var.get() not in self.club_league_combo["values"]:
            self.club_league_var.set("All")
        if self.player_filter_club_var.get() not in self.player_filter_club_combo["values"]:
            self.player_filter_club_var.set("All")

    def _refresh_all_views(self) -> None:
        self.refresh_global_search()
        self.refresh_club_view()
        self.refresh_players_view()
        self.refresh_coaches_view()
        self.refresh_leagues_view()

    def _refresh_footer_state(self) -> None:
        if self.player_index or self.team_index or self.coach_index:
            if self.file_path and not self._player_catalog_loaded:
                player_line = f"Players: {Path(self.file_path).name} (on demand)"
            else:
                player_line = f"Players: {Path(self.file_path).name} ({len(self.player_index)})"
            self.db_files_var.set(
                "{player_line}\nClubs: {teams} ({team_count})\nCoaches: {coaches} ({coach_count})".format(
                    player_line=player_line,
                    teams=Path(self.team_file_path).name if self.team_file_path else "(missing)",
                    team_count=len(self.team_index),
                    coaches=Path(self.coach_file_path).name if self.coach_file_path else "(missing)",
                    coach_count=len(self.coach_index),
                )
            )
        else:
            self.db_files_var.set("No files loaded")

        if self.dirty_state.any_dirty() or self.staged_visible_skill_patches:
            parts = []
            if self.dirty_state.dirty_players:
                parts.append(f"{len(self.dirty_state.dirty_players)} player(s)")
            if self.dirty_state.dirty_teams:
                parts.append(f"{len(self.dirty_state.dirty_teams)} club(s)")
            if self.dirty_state.dirty_coaches:
                parts.append(f"{len(self.dirty_state.dirty_coaches)} coach(es)")
            if self.staged_visible_skill_patches:
                parts.append(f"{len(self.staged_visible_skill_patches)} skill patch(es)")
            self.db_dirty_var.set("Staged: " + ", ".join(parts))
        else:
            self.db_dirty_var.set("No staged changes")

        self.db_validation_var.set(
            "{message}\nFiles: players={players}, clubs={teams}, coaches={coaches}".format(
                message=self.validation_state.message,
                players=self._companion_file_state.get("players", "unknown"),
                teams=self._companion_file_state.get("teams", "unknown"),
                coaches=self._companion_file_state.get("coaches", "unknown"),
            )
        )
        self.save_button.state(["!disabled"] if self._has_staged_changes() else ["disabled"])
        self._update_nav_button_labels()

    def _has_staged_changes(self) -> bool:
        return bool(
            self.modified_records
            or self.modified_team_records
            or self.modified_coach_records
            or self.staged_visible_skill_patches
        )

    def refresh_global_search(self) -> None:
        tree = self.global_search_tree
        tree.delete(*tree.get_children())
        self._search_item_map = {}

        query = _normalize_spaces(self.global_search_var.get())
        if not query:
            if self.player_index or self.team_index or self.coach_index:
                self.global_search_hint_var.set(
                    "Type a club, player, or coach name to search."
                    if self._player_catalog_loaded
                    else "Type a club or coach name. Player results load on demand."
                )
            else:
                self.global_search_hint_var.set("Load a database to search clubs, players, and coaches.")
            self._set_global_search_results_visible(False)
            return
        lower_query = query.lower()

        parents = {
            "club": tree.insert("", tk.END, text="Clubs", open=True),
            "coach": tree.insert("", tk.END, text="Coaches", open=True),
        }
        counts = {"club": 0, "player": 0, "coach": 0}
        if self._player_catalog_loaded:
            parents["player"] = tree.insert("", tk.END, text="Players", open=True)

        for offset, _original in self.team_records:
            team = self._team_for_offset(offset)
            club_name = self._team_name(team)
            full_name = _normalize_spaces(getattr(team, "full_club_name", "") or "")
            if team_query_matches(query, club_name, full_name) or lower_query in str(getattr(team, "team_id", "")).lower():
                counts["club"] += 1
                item_id = tree.insert(
                    parents["club"],
                    tk.END,
                    text=f"{club_name} ({getattr(team, 'team_id', '')})",
                )
                self._search_item_map[item_id] = SearchResultItem(
                    result_type="club",
                    display_label=club_name,
                    backing_record_ref=("team", offset),
                    route_target=EditorWorkspaceRoute.CLUBS,
                    subtitle=full_name,
                )
                if counts["club"] >= 12:
                    break

        if self._player_catalog_loaded:
            combined_players = list(self.all_records)
            if self.player_show_uncertain_var.get():
                combined_players += list(self.uncertain_player_records)
            for offset, _original in combined_players:
                record = self._player_for_offset(offset)
                display_name = self._player_display_name(record)
                team_name = self.team_lookup.get(_safe_int(getattr(record, "team_id", 0), 0), "")
                if lower_query in display_name.lower() or lower_query in team_name.lower():
                    counts["player"] += 1
                    label = display_name
                    if team_name:
                        label += f" [{team_name}]"
                    item_id = tree.insert(parents["player"], tk.END, text=label)
                    self._search_item_map[item_id] = SearchResultItem(
                        result_type="player",
                        display_label=display_name,
                        backing_record_ref=("player", offset),
                        route_target=EditorWorkspaceRoute.PLAYERS,
                        subtitle=team_name,
                    )
                    if counts["player"] >= 18:
                        break

        for offset, _original in self.coach_records:
            coach = self._coach_for_offset(offset)
            display_name = self._coach_display_name(coach)
            if lower_query in display_name.lower():
                counts["coach"] += 1
                item_id = tree.insert(parents["coach"], tk.END, text=display_name)
                self._search_item_map[item_id] = SearchResultItem(
                    result_type="coach",
                    display_label=display_name,
                    backing_record_ref=("coach", offset),
                    route_target=EditorWorkspaceRoute.COACHES,
                    subtitle=UNSUPPORTED_COACH_LINK_TEXT,
                )
                if counts["coach"] >= 12:
                    break

        for key, parent_id in list(parents.items()):
            if counts[key] == 0:
                tree.delete(parent_id)

        total_results = sum(counts.values())
        self._set_global_search_results_visible(total_results > 0)
        if total_results:
            if self._player_catalog_loaded:
                self.global_search_hint_var.set("Select a result to jump directly into the editor.")
            else:
                self.global_search_hint_var.set("Select a result to jump directly into the editor. Player results load when needed.")
        else:
            self.global_search_hint_var.set(
                "No club or coach matches yet. Load player data if you want player results."
                if not self._player_catalog_loaded
                else "No matches for the current search."
            )

    def _on_global_search_select(self, _event: Any) -> None:
        selection = self.global_search_tree.selection()
        if not selection:
            return
        item = selection[0]
        result = self._search_item_map.get(item)
        if result is None:
            return

        self.set_route(result.route_target)
        kind, offset = result.backing_record_ref
        if kind == "team":
            self._select_club_by_offset(int(offset), focus_editor=False)
        elif kind == "player":
            self._select_player_by_offset(int(offset), route_if_needed=False)
        elif kind == "coach":
            self._select_coach_by_offset(int(offset), route_if_needed=False)

    def _filtered_clubs(self) -> list[ClubListItemView]:
        query = _normalize_spaces(self.club_search_var.get()).lower()
        selected_country = self.club_country_var.get()
        selected_league = self.club_league_var.get()
        player_team_counts = self._build_player_team_counts()

        out: list[ClubListItemView] = []
        for offset, _original in self.team_records:
            team = self._team_for_offset(offset)
            team_id = _safe_int(getattr(team, "team_id", 0), 0)
            club_name = self._team_name(team)
            full_name = _normalize_spaces(getattr(team, "full_club_name", "") or "")
            country = self._team_country(team)
            league = self._team_league(team)
            if selected_country not in ("", "All") and country != selected_country:
                continue
            if selected_league not in ("", "All") and league != selected_league:
                continue
            if query:
                if not (team_query_matches(query, club_name, full_name) or query in str(team_id)):
                    continue
            out.append(
                ClubListItemView(
                    offset=offset,
                    team_id=team_id,
                    club_name=club_name,
                    full_club_name=full_name,
                    league=league,
                    country=country,
                    coach_name=UNSUPPORTED_COACH_LINK_TEXT,
                    roster_count=player_team_counts.get(team_id, 0),
                    is_dirty=offset in self.dirty_state.dirty_teams,
                )
            )
        out.sort(key=lambda item: (item.country, item.league, item.club_name))
        return out

    def _build_player_team_counts(self) -> dict[int, int]:
        counts: dict[int, int] = defaultdict(int)
        for offset in self.player_index:
            record = self._player_for_offset(offset)
            team_id = _safe_int(getattr(record, "team_id", 0), 0)
            if team_id:
                counts[team_id] += 1
        return dict(counts)

    def refresh_club_view(self) -> None:
        tree = self.club_tree
        tree.delete(*tree.get_children())
        self._club_item_map = {}

        clubs = self._filtered_clubs()
        if not clubs:
            self.club_summary_name_var.set("No clubs match the current filters")
            self.club_summary_context_var.set("Adjust the filters or clear the search to see available clubs.")
            self.club_summary_team_id_var.set("-")
            self.club_summary_league_var.set("-")
            self.club_summary_country_var.set("-")
            self.club_summary_coach_var.set(UNSUPPORTED_COACH_LINK_TEXT)
            self.club_summary_roster_var.set("-")
            self.club_summary_status_var.set("No roster loaded")
            self.roster_tree.delete(*self.roster_tree.get_children())
            self.roster_empty_var.set("No club rows to display.")
            self._set_club_action_state(has_club=False, has_roster=False, has_selected_slot=False)
            return

        group_by_country = self.club_sort_var.get() == "country"
        group_nodes: dict[tuple[str, str], str] = {}
        for item in clubs:
            parent = ""
            if group_by_country:
                group_key = (item.country or "Unknown", item.league or "Unknown")
                if group_key not in group_nodes:
                    country_node = None
                    country_key = (group_key[0], "")
                    if country_key not in group_nodes:
                        country_node = tree.insert("", tk.END, text=group_key[0], open=True)
                        group_nodes[country_key] = country_node
                    parent = tree.insert(group_nodes[country_key], tk.END, text=group_key[1], open=True)
                    group_nodes[group_key] = parent
                else:
                    parent = group_nodes[group_key]
            item_id = tree.insert(
                parent,
                tk.END,
                text=item.club_name + (" *" if item.is_dirty else ""),
                values=(item.team_id, item.league),
            )
            self._club_item_map[item_id] = item.offset

        if self.current_club_offset is not None:
            self._select_tree_item_by_value(self.club_tree, self._club_item_map, self.current_club_offset)

    def _on_club_tree_select(self, _event: Any) -> None:
        selection = self.club_tree.selection()
        if not selection:
            return
        offset = self._club_item_map.get(selection[0])
        if offset is None:
            return
        self._select_club_by_offset(offset, focus_editor=True)

    def _select_club_by_offset(self, offset: int, *, focus_editor: bool) -> None:
        team = self._team_for_offset(offset)
        self.current_club_offset = offset
        self.current_team = (offset, team)
        self.selection_state.selected_club_id = _safe_int(getattr(team, "team_id", 0), 0) or None
        self.club_summary_name_var.set(self._team_name(team))
        self.club_summary_team_id_var.set(str(getattr(team, "team_id", "") or "-"))
        self.club_summary_league_var.set(self._team_league(team))
        self.club_summary_country_var.set(self._team_country(team))
        self.club_summary_coach_var.set(UNSUPPORTED_COACH_LINK_TEXT)

        if not self._player_catalog_loaded:
            self.club_summary_context_var.set(
                "Club selected. Team details are ready now. Load player data when you want to inspect the roster."
            )
            self.current_roster_rows = []
            self.current_roster_meta_by_item = {}
            self.selection_state.current_roster_context = []
            self.roster_tree.delete(*self.roster_tree.get_children())
            self.club_summary_roster_var.set("On demand")
            self.club_summary_status_var.set("Player data not loaded")
            self.roster_empty_var.set(
                "Player records are deferred. Use Load Player Data to open the selected club roster."
            )
            self._set_club_action_state(has_club=True, has_roster=False, has_selected_slot=False)
            self.display_team(team)
            if focus_editor:
                self._show_editor_card("team")
            return

        self.club_summary_context_var.set("Club selected. Review the roster below, then pick a player to edit.")

        rows, reason = self._build_roster_rows_for_team(team)
        self.current_roster_rows = rows
        self.selection_state.current_roster_context = [row.player_offset for row in rows if row.player_offset is not None]
        self._render_roster_rows(rows, reason)

        self.club_summary_roster_var.set(str(len(rows)) if rows else "Unavailable")
        self.club_summary_status_var.set(self._summarize_roster_status(rows, reason))
        self._set_club_action_state(has_club=True, has_roster=bool(rows), has_selected_slot=False)
        self.display_team(team)
        if focus_editor:
            self._show_editor_card("team")

    def _render_roster_rows(self, rows: list[RosterRowView], reason: str | None) -> None:
        tree = self.roster_tree
        tree.delete(*tree.get_children())
        self.current_roster_meta_by_item = {}
        if not rows:
            self.roster_empty_var.set(reason or "Roster unavailable for the selected club.")
            return

        self.roster_empty_var.set("Single-click to load a player. Double-click to keep player focus in the editor.")
        for row in rows:
            item_id = tree.insert(
                "",
                tk.END,
                values=(
                    row.slot_number,
                    row.player_name,
                    row.position_label,
                    row.nationality_label,
                    row.skills.get("speed", ""),
                    row.skills.get("stamina", ""),
                    row.skills.get("aggression", ""),
                    row.skills.get("quality", ""),
                    ", ".join(row.status_badges),
                ),
            )
            self.current_roster_meta_by_item[item_id] = row

    def _summarize_roster_status(self, rows: list[RosterRowView], reason: str | None) -> str:
        if not rows:
            return reason or "Roster unavailable"
        source_modes = {str((row.meta or {}).get("mode") or "") for row in rows}
        if "linked" in source_modes:
            return "Authoritative linked roster"
        if "same_entry" in source_modes:
            return "Authoritative same-entry roster"
        return "Roster loaded"

    def _set_club_action_state(self, *, has_club: bool, has_roster: bool, has_selected_slot: bool) -> None:
        try:
            self.club_load_players_button.state(
                ["!disabled"] if (has_club and not self._player_catalog_loaded and not self._player_catalog_loading) else ["disabled"]
            )
        except Exception:
            pass
        try:
            self.club_rename_button.state(["!disabled"] if has_club else ["disabled"])
        except Exception:
            pass
        try:
            self.club_export_button.state(["!disabled"] if has_roster else ["disabled"])
        except Exception:
            pass
        try:
            self.club_edit_slot_button.state(["!disabled"] if has_selected_slot else ["disabled"])
        except Exception:
            pass
        try:
            self.club_edit_coach_button.state(["disabled"])
        except Exception:
            pass
        self._set_team_editor_action_state(
            has_club=has_club,
            has_roster=has_roster,
            has_selected_slot=has_selected_slot,
        )

    def _selected_roster_row(self) -> RosterRowView | None:
        try:
            selection = self.roster_tree.selection()
        except Exception:
            selection = ()
        if not selection:
            return None
        return self.current_roster_meta_by_item.get(selection[0])

    def _set_team_editor_action_state(self, *, has_club: bool, has_roster: bool, has_selected_slot: bool) -> None:
        selected_row = self._selected_roster_row()
        selected_mode = str((selected_row.meta or {}).get("mode") or "") if selected_row is not None else ""
        team_dirty = bool(
            self.current_club_offset is not None and self.current_club_offset in self.dirty_state.dirty_teams
        )

        button_rules = (
            ("team_edit_slot_button", has_selected_slot),
            ("team_linked_edit_button", has_selected_slot and selected_mode == "linked"),
            ("team_same_entry_button", has_selected_slot and selected_mode == "same_entry"),
            ("team_batch_import_button", has_roster),
            ("team_revert_button", has_club and team_dirty),
            ("team_load_players_button", has_club and not self._player_catalog_loaded and not self._player_catalog_loading),
        )
        for attr_name, enabled in button_rules:
            button = getattr(self, attr_name, None)
            if button is None:
                continue
            try:
                button.state(["!disabled"] if enabled else ["disabled"])
            except Exception:
                pass

        if hasattr(self, "team_edit_coach_button"):
            try:
                self.team_edit_coach_button.state(["disabled"])
            except Exception:
                pass

        if hasattr(self, "team_roster_hint_var"):
            if not self._player_catalog_loaded:
                self.team_roster_hint_var.set(
                    "Player records are deferred. Load Player Data to enable roster tools for the selected club."
                )
            elif not has_roster:
                self.team_roster_hint_var.set("No roster tools available because the selected club has no authoritative roster.")
            elif selected_row is None:
                self.team_roster_hint_var.set("Choose a squad row in the Clubs view to enable slot-specific roster tools.")
            else:
                source_label = "linked source" if selected_mode == "linked" else "same-entry source" if selected_mode == "same_entry" else "available source"
                self.team_roster_hint_var.set(
                    f"Selected slot {selected_row.slot_number}: {selected_row.player_name}. "
                    f"Use the {source_label} edit path shown below."
                )

    def _resolve_player_file_for_roster(self) -> str:
        player_path = Path(self.file_path)
        if player_path.name.upper().startswith("JUG") and player_path.exists():
            return str(player_path)
        fallback = Path("DBDAT/JUG98030.FDI")
        return str(fallback if fallback.exists() else player_path)

    def _get_linked_roster_catalog(self, team_file: str, player_file: str) -> list[dict[str, Any]]:
        cache_key = (str(Path(team_file)), str(Path(player_file)))
        cached = self._linked_roster_catalog_cache.get(cache_key)
        if cached is None:
            cached = list(
                extract_team_rosters_eq_jug_linked(
                    team_file=team_file,
                    player_file=player_file,
                    team_queries=None,
                )
                or []
            )
            self._linked_roster_catalog_cache[cache_key] = cached
        return list(cached)

    def _get_same_entry_overlap_result(self, team_file: str, player_file: str, team_query: str | None = None) -> Any:
        normalized_query = str(team_query or "").strip().casefold()
        cache_key = (str(Path(team_file)), str(Path(player_file)), normalized_query)
        cached = self._same_entry_overlap_cache.get(cache_key)
        if cached is None:
            cached = extract_team_rosters_eq_same_entry_overlap(
                team_file=team_file,
                player_file=player_file,
                team_queries=[team_query] if team_query else None,
                top_examples=5,
                include_fallbacks=True,
            )
            self._same_entry_overlap_cache[cache_key] = cached
        return cached

    def _build_roster_rows_for_team(self, team: Any) -> tuple[list[RosterRowView], str | None]:
        team_name = self._team_name(team)
        if not team_name:
            return [], "Roster unavailable: club name missing"

        team_file = self.team_file_path
        if not Path(team_file).exists():
            return [], "Roster unavailable: team file missing"

        player_file = self._resolve_player_file_for_roster()
        pid_index = self._get_dd6361_pid_index(player_file)

        try:
            linked = [
                roster
                for roster in self._get_linked_roster_catalog(team_file, player_file)
                if team_query_matches(
                    team_name,
                    team_name=str(roster.get("team_name") or ""),
                    full_club_name=str(roster.get("full_club_name") or ""),
                )
            ]
        except Exception:
            linked = []

        rows: list[RosterRowView] = []
        if linked:
            selected = dict(linked[0] or {})
            for raw_row in list(selected.get("rows") or []):
                pid = _safe_int(raw_row.get("pid", 0), 0)
                stats_entry = dict(pid_index.get(pid) or {})
                display_name = _normalize_spaces(raw_row.get("player_name") or stats_entry.get("resolved_bio_name") or f"PID {pid}")
                player_offset = self._resolve_player_offset_for_roster_name(display_name, _safe_int(getattr(team, "team_id", 0), 0))
                player_record = self._record_from_any_player_offset(player_offset)
                rows.append(
                    RosterRowView(
                        slot_number=_safe_int(raw_row.get("slot_index", 0), 0) + 1,
                        player_name=display_name,
                        player_offset=player_offset,
                        position_label=player_record.get_position_name() if player_record is not None else "",
                        nationality_label=str(getattr(player_record, "nationality", "")) if player_record is not None else "",
                        skills={
                            "speed": (stats_entry.get("mapped10") or {}).get("speed", ""),
                            "stamina": (stats_entry.get("mapped10") or {}).get("stamina", ""),
                            "aggression": (stats_entry.get("mapped10") or {}).get("aggression", ""),
                            "quality": (stats_entry.get("mapped10") or {}).get("quality", ""),
                        },
                        status_badges=["linked source"] + ([] if player_offset is not None else ["player unresolved"]),
                        meta={
                            "mode": "linked",
                            "team_query": str(selected.get("team_name") or team_name),
                            "slot_number": _safe_int(raw_row.get("slot_index", 0), 0) + 1,
                            "current_pid": pid,
                            "current_flag": _safe_int(raw_row.get("flag", 0), 0),
                        },
                    )
                )
            return rows, None

        try:
            overlap = self._get_same_entry_overlap_result(
                team_file=team_file,
                player_file=player_file,
                team_query=team_name,
            )
        except Exception as exc:
            return [], f"Roster unavailable: {exc}"

        requested = list(getattr(overlap, "requested_team_results", []) or [])
        selected = dict(requested[0] or {}) if requested else {}
        preferred = dict(selected.get("preferred_roster_match") or {})
        provenance = str(preferred.get("provenance") or "")
        if provenance not in TEAM_ROSTER_SUPPORTED_PROVENANCES:
            return [], "Roster unavailable: no authoritative roster mapping found"

        for raw_row in list(preferred.get("rows") or []):
            if raw_row.get("is_empty_slot"):
                continue
            pid = _safe_int(raw_row.get("pid_candidate", 0), 0)
            stats_entry = dict(pid_index.get(pid) or {})
            display_name = _normalize_spaces(raw_row.get("dd6361_name") or stats_entry.get("resolved_bio_name") or f"PID {pid}")
            player_offset = self._resolve_player_offset_for_roster_name(display_name, _safe_int(getattr(team, "team_id", 0), 0))
            player_record = self._record_from_any_player_offset(player_offset)
            rows.append(
                RosterRowView(
                    slot_number=len(rows) + 1,
                    player_name=display_name,
                    player_offset=player_offset,
                    position_label=player_record.get_position_name() if player_record is not None else "",
                    nationality_label=str(getattr(player_record, "nationality", "")) if player_record is not None else "",
                    skills={
                        "speed": (stats_entry.get("mapped10") or {}).get("speed", ""),
                        "stamina": (stats_entry.get("mapped10") or {}).get("stamina", ""),
                        "aggression": (stats_entry.get("mapped10") or {}).get("aggression", ""),
                        "quality": (stats_entry.get("mapped10") or {}).get("quality", ""),
                    },
                    status_badges=[provenance or "same entry"] + ([] if player_offset is not None else ["player unresolved"]),
                    meta={
                        "mode": "same_entry",
                        "team_query": str(selected.get("team_name") or team_name),
                        "slot_number": len(rows) + 1,
                        "current_pid": pid,
                        "team_offset": _safe_int(selected.get("team_offset", 0), 0),
                        "same_entry_provenance": provenance,
                    },
                )
            )
        return rows, None if rows else "Roster unavailable: no usable rows"

    def _get_dd6361_pid_index(self, player_file: str) -> dict[int, dict[str, Any]]:
        index = self._dd6361_pid_stat_cache.get(player_file)
        if index is None:
            try:
                index = build_player_visible_skill_index_dd6361(file_path=player_file)
            except Exception:
                index = {}
            self._dd6361_pid_stat_cache[player_file] = index
        return index

    def _resolve_player_offset_for_roster_name(self, name: str, team_id: int) -> int | None:
        normalized = _normalize_name(name)
        offsets = list(self.player_name_lookup.get(normalized, []))
        if not offsets:
            return None
        for offset in offsets:
            record = self._player_for_offset(offset)
            if _safe_int(getattr(record, "team_id", 0), 0) == team_id:
                return offset
        return offsets[0]

    def _record_from_any_player_offset(self, offset: int | None) -> PlayerRecord | None:
        if offset is None:
            return None
        if offset in self.player_index:
            return self._player_for_offset(offset)
        if offset in self.uncertain_player_index:
            return self._player_for_offset(offset)
        return None

    def _on_roster_select(self, _event: Any) -> None:
        selection = self.roster_tree.selection()
        if not selection:
            self._set_club_action_state(
                has_club=self.current_club_offset is not None,
                has_roster=bool(self.current_roster_rows),
                has_selected_slot=False,
            )
            return
        row = self.current_roster_meta_by_item.get(selection[0])
        if row is None:
            self._set_club_action_state(
                has_club=self.current_club_offset is not None,
                has_roster=bool(self.current_roster_rows),
                has_selected_slot=False,
            )
            return
        self._set_club_action_state(
            has_club=self.current_club_offset is not None,
            has_roster=bool(self.current_roster_rows),
            has_selected_slot=True,
        )
        if row.player_offset is not None:
            self._select_player_by_offset(row.player_offset, route_if_needed=False)
        else:
            self.display_team(self.current_team[1] if self.current_team else None)

    def _on_roster_double_click(self, _event: Any) -> None:
        selection = self.roster_tree.selection()
        if not selection:
            return
        row = self.current_roster_meta_by_item.get(selection[0])
        if row and row.player_offset is not None:
            self._select_player_by_offset(row.player_offset, route_if_needed=False)

    def refresh_players_view(self) -> None:
        tree = self.player_results_tree
        tree.delete(*tree.get_children())
        self._player_result_map = {}

        if not self._player_catalog_loaded:
            if self._player_catalog_loading:
                self.players_view_hint_var.set("Loading player data now...")
            else:
                self.players_view_hint_var.set(
                    "Player records are deferred to keep startup fast. Load player data when you want the full player browser."
                )
            try:
                self.players_load_button.state(
                    ["disabled"] if self._player_catalog_loading or not self.file_path else ["!disabled"]
                )
            except Exception:
                pass
            return

        self.players_view_hint_var.set("Searches player names, club names, and common aliases.")
        try:
            self.players_load_button.state(["disabled"])
        except Exception:
            pass

        query = _normalize_spaces(self.player_search_var.get()).lower()
        selected_club = self.player_filter_club_var.get()
        selected_position = self.player_filter_position_var.get()
        nationality_filter = _normalize_spaces(self.player_filter_nationality_var.get())

        records = list(self.all_records)
        if self.player_show_uncertain_var.get():
            records.extend(self.uncertain_player_records)

        for offset, _original in records:
            record = self._player_for_offset(offset)
            display_name = self._player_display_name(record)
            team_name = self.team_lookup.get(_safe_int(getattr(record, "team_id", 0), 0), "")
            if query and query not in display_name.lower() and query not in team_name.lower():
                continue
            if selected_club not in ("", "All") and team_name != selected_club:
                continue
            position_label = record.get_position_name()
            if selected_position not in ("", "All") and position_label != selected_position:
                continue
            nationality_label = str(getattr(record, "nationality", getattr(record, "nationality_id", "")))
            if nationality_filter and nationality_filter != nationality_label:
                continue

            item_id = tree.insert(
                "",
                tk.END,
                values=(
                    display_name,
                    team_name,
                    position_label,
                    getattr(record, "squad_number", ""),
                    nationality_label,
                ),
            )
            self._player_result_map[item_id] = offset

    def _on_player_results_select(self, _event: Any) -> None:
        selection = self.player_results_tree.selection()
        if not selection:
            return
        offset = self._player_result_map.get(selection[0])
        if offset is None:
            return
        self._select_player_by_offset(offset, route_if_needed=False)

    def refresh_coaches_view(self) -> None:
        tree = self.coach_tree
        tree.delete(*tree.get_children())
        self._coach_item_map = {}
        query = _normalize_spaces(self.coach_search_var.get()).lower()

        for offset, _original in self.coach_records:
            coach = self._coach_for_offset(offset)
            display_name = self._coach_display_name(coach)
            if query and query not in display_name.lower():
                continue
            item_id = tree.insert("", tk.END, values=(display_name, UNSUPPORTED_COACH_LINK_TEXT, ""))
            self._coach_item_map[item_id] = offset

    def _on_coach_tree_select(self, _event: Any) -> None:
        selection = self.coach_tree.selection()
        if not selection:
            return
        offset = self._coach_item_map.get(selection[0])
        if offset is None:
            return
        self._select_coach_by_offset(offset, route_if_needed=False)

    def refresh_leagues_view(self) -> None:
        tree = self.league_tree
        tree.delete(*tree.get_children())
        self._league_item_map = {}

        countries: dict[str, dict[str, list[tuple[int, Any]]]] = defaultdict(lambda: defaultdict(list))
        for offset, _original in self.team_records:
            team = self._team_for_offset(offset)
            countries[self._team_country(team)][self._team_league(team)].append((offset, team))

        for country in sorted(countries):
            country_item = tree.insert("", tk.END, text=country, open=True)
            for league in sorted(countries[country]):
                league_item = tree.insert(country_item, tk.END, text=league, open=True)
                for offset, team in sorted(countries[country][league], key=lambda item: self._team_name(item[1])):
                    item_id = tree.insert(
                        league_item,
                        tk.END,
                        text=self._team_name(team),
                        values=(getattr(team, "team_id", ""),),
                    )
                    self._league_item_map[item_id] = offset

    def _on_league_tree_select(self, _event: Any) -> None:
        selection = self.league_tree.selection()
        if not selection:
            return
        offset = self._league_item_map.get(selection[0])
        if offset is None:
            return
        self.set_route(EditorWorkspaceRoute.CLUBS)
        self._select_club_by_offset(offset, focus_editor=False)

    def _select_first_club_if_available(self) -> None:
        if not self.team_records:
            self._show_editor_card("empty")
            return
        first_offset = self.team_records[0][0]
        self._select_club_by_offset(first_offset, focus_editor=True)
        self._select_tree_item_by_value(self.club_tree, self._club_item_map, first_offset)

    def _select_player_by_offset(self, offset: int, *, route_if_needed: bool) -> None:
        if route_if_needed:
            self.set_route(EditorWorkspaceRoute.PLAYERS)
        record = self._player_for_offset(offset)
        self.current_record = (offset, record)
        self.selection_state.selected_player_offset = offset
        self.display_player(offset)
        self._show_editor_card("player")
        self._select_tree_item_by_value(self.player_results_tree, self._player_result_map, offset)

    def _select_coach_by_offset(self, offset: int, *, route_if_needed: bool) -> None:
        if route_if_needed:
            self.set_route(EditorWorkspaceRoute.COACHES)
        coach = self._coach_for_offset(offset)
        self.current_coach = (offset, coach)
        self.selection_state.selected_coach_offset = offset
        self.display_coach(offset)
        self._show_editor_card("coach")
        self._select_tree_item_by_value(self.coach_tree, self._coach_item_map, offset)

    def display_player(self, offset: int) -> None:
        record = self._player_for_offset(offset)
        original = self.player_index.get(offset) or self.uncertain_player_index.get(offset)
        if original is None:
            return
        self.current_player_original = original

        is_uncertain = offset in self.uncertain_player_index
        club_name = self.team_lookup.get(_safe_int(getattr(record, "team_id", 0), 0), "")

        profile_view = self._build_player_profile_view(offset, record, original, club_name, is_uncertain)
        self.player_header_name_var.set(profile_view.full_name)
        self._refresh_player_header_widgets(offset, record, profile_view, is_uncertain)

        self._loading_player_form = True
        try:
            self.player_form_vars["given_name"].set(getattr(record, "given_name", "") or "")
            self.player_form_vars["surname"].set(getattr(record, "surname", "") or "")
            self.player_form_vars["team_id"].set(str(getattr(record, "team_id", 0) or 0))
            self.player_form_vars["squad_number"].set(str(getattr(record, "squad_number", 0) or 0))
            self.player_form_vars["nationality"].set(
                str(getattr(record, "nationality", getattr(record, "nationality_id", 0)) or 0)
            )
            dob = getattr(record, "dob", (1, 1, 1975))
            self.player_form_vars["dob_day"].set(str(dob[0]))
            self.player_form_vars["dob_month"].set(str(dob[1]))
            self.player_form_vars["dob_year"].set(str(dob[2]))
            self.player_form_vars["position"].set(record.get_position_name())
            self.player_form_vars["height"].set(str(getattr(record, "height", 175) or 175))
            weight_value = getattr(record, "weight", None)
            self.player_form_vars["weight"].set("" if weight_value is None else str(weight_value))
        finally:
            self._loading_player_form = False

        self._load_visible_skill_snapshot(record)
        additional_map = {group: label for group, label, _note in profile_view.additional_fields}
        self.player_additional_physical_var.set(additional_map.get("physical", "-"))
        self.player_additional_availability_var.set(additional_map.get("availability", "-"))
        self.player_additional_metadata_var.set(additional_map.get("metadata", "-"))
        self.player_additional_structural_var.set(additional_map.get("structural", "-"))
        self._set_provenance_lines(profile_view.provenance_lines)
        preview_line = next(
            (
                line
                for line in profile_view.provenance_lines
                if line.startswith("Dirty fields:")
                or line.startswith("Nationality-search hint:")
                or line.startswith("Record type:")
            ),
            profile_view.provenance_lines[0] if profile_view.provenance_lines else "No warnings for the current record.",
        )
        self.player_provenance_preview_var.set(preview_line)
        self._set_player_editor_enabled(enabled=not (SAVE_NAME_ONLY and not self._player_only_name_edit_allowed()))
        if is_uncertain:
            self._set_player_editor_enabled(enabled=False)
            self.player_profile_hint_var.set("View-only: this record is uncertain and is kept out of the write path.")
            self.player_skill_hint_var.set("Visible skills shown for reference only on uncertain records.")
        elif SAVE_NAME_ONLY:
            self.player_profile_hint_var.set(
                "Safe mode: only names will be written. The rest of the profile stays visible for review."
            )
            if self.current_visible_skill_baseline:
                self.player_skill_hint_var.set(
                    "Visible skill snapshot loaded for reference. Safe mode keeps skill edits out of the write path."
                )
            else:
                self.player_skill_hint_var.set(
                    "No visible skill snapshot resolved for this player. Skills stay view-only in this build."
                )
        else:
            self.player_profile_hint_var.set("Core parser-backed football fields.")
            if self.current_visible_skill_baseline:
                self.player_skill_hint_var.set(
                    "Visible dd6361-backed skills. Changes are staged and validated on Save All."
                )
            else:
                self.player_skill_hint_var.set("Visible skill snapshot not currently available for this player.")

        roster_context = list(self.selection_state.current_roster_context or [])
        can_step_prev = offset in roster_context and roster_context.index(offset) > 0
        can_step_next = offset in roster_context and roster_context.index(offset) < (len(roster_context) - 1)
        self._set_player_action_state(True, can_step_prev, can_step_next)

        self._sync_player_dirty_styles()

    def _build_player_profile_view(
        self,
        offset: int,
        record: PlayerRecord,
        original: PlayerRecord,
        club_name: str,
        is_uncertain: bool,
    ) -> PlayerProfileView:
        tail_prefix = list(getattr(record, "attributes", [])[:3])
        parsed_name = self._player_display_name(record)
        post_weight = None
        trailer_byte = None
        sidecar_byte = None
        provenance_lines = [
            f"Parser confidence: {getattr(record, 'confidence', 100)}",
            f"Suppressed flag: {'yes' if getattr(record, 'suppressed', False) else 'no'}",
            f"Record type: {'uncertain' if is_uncertain else 'authoritative'}",
        ]
        if getattr(record, "raw_data", None):
            post_weight = PlayerRecord._extract_indexed_post_weight_byte(bytes(record.raw_data), parsed_name)
            if post_weight is not None:
                nat = getattr(record, "nationality", getattr(record, "nationality_id", None))
                hint = "mirror" if nat == post_weight else "grouped key"
                provenance_lines.append(f"Nationality-search hint: post_weight_byte={post_weight} ({hint})")
            trailer_byte = PlayerRecord._extract_indexed_post_attribute_byte(bytes(record.raw_data), parsed_name)
            if trailer_byte is not None:
                provenance_lines.append(f"Post-attribute trailer byte: {trailer_byte}")
            sidecar_byte = PlayerRecord._extract_indexed_post_attribute_sidecar_byte(bytes(record.raw_data), parsed_name)
            if sidecar_byte is not None:
                provenance_lines.append(f"Post-attribute sidecar byte: {sidecar_byte}")
        if offset in self.dirty_state.dirty_players:
            dirty_fields = sorted(self.dirty_state.field_dirty_map.get(f"players:{offset}", set()))
            if dirty_fields:
                provenance_lines.append("Dirty fields: " + ", ".join(dirty_fields))

        height_text = f"{getattr(record, 'height', 0) or 0} cm"
        weight_value = getattr(record, "weight", None)
        weight_text = f"{weight_value} kg" if weight_value is not None else "not surfaced"
        physical_summary = f"Height {height_text} | Weight {weight_text}"

        if is_uncertain:
            availability_summary = "View only: uncertain parser result"
        elif SAVE_NAME_ONLY:
            availability_summary = "Safe mode: name edits only"
        elif bool(getattr(record, "supports_weight_write", lambda: False)()):
            availability_summary = "Weight supported | profile fields editable"
        else:
            availability_summary = "Core profile editable | weight read-only"

        metadata_summary = (
            "Nationality search mirror/group hint available in Provenance"
            if post_weight is not None
            else "Standard player metadata only"
        )

        structural_flags = []
        if tail_prefix:
            structural_flags.append("tail signature retained")
        if getattr(record, "indexed_unknown_0", None) is not None or getattr(record, "indexed_unknown_9", None) is not None:
            structural_flags.append("indexed suffix retained")
        if trailer_byte is not None or sidecar_byte is not None:
            structural_flags.append("sidecar bytes retained")
        structural_summary = ", ".join(structural_flags) if structural_flags else "No extra structural probes surfaced"

        additional_fields: list[tuple[str, str, str]] = [
            ("physical", physical_summary, ""),
            ("availability", availability_summary, ""),
            ("metadata", metadata_summary, ""),
            ("structural", structural_summary, ""),
        ]

        return PlayerProfileView(
            offset=offset,
            full_name=self._player_display_name(record),
            club_name=club_name,
            squad_number=_safe_int(getattr(record, "squad_number", 0), 0),
            position_label=record.get_position_name(),
            dirty=bool(self.dirty_state.field_dirty_map.get(f"players:{offset}", set())),
            confidence_label="Uncertain" if is_uncertain else f"Confidence {getattr(record, 'confidence', 100)}",
            supports_weight_write=bool(getattr(record, "supports_weight_write", lambda: False)()),
            visible_skills=dict(self.current_visible_skill_baseline),
            additional_fields=additional_fields,
            provenance_lines=provenance_lines,
        )

    def _refresh_player_header_widgets(
        self,
        offset: int,
        record: PlayerRecord,
        profile_view: PlayerProfileView,
        is_uncertain: bool,
    ) -> None:
        dirty_fields = set(self.dirty_state.field_dirty_map.get(f"players:{offset}", set()))
        profile_dirty_fields = sorted(field for field in dirty_fields if not str(field).startswith("skill:"))
        skill_dirty_fields = sorted(str(field).split(":", 1)[1] for field in dirty_fields if str(field).startswith("skill:"))

        club_name = profile_view.club_name or "No club"
        squad_number = _safe_int(getattr(record, "squad_number", profile_view.squad_number), 0)
        roster_context = list(self.selection_state.current_roster_context or [])
        roster_position = roster_context.index(offset) + 1 if offset in roster_context else None

        self.player_header_name_var.set(profile_view.full_name)
        self.player_header_club_var.set(club_name)

        squad_label = f"No. {squad_number}" if squad_number else "Unassigned"
        if roster_position is not None:
            squad_label = f"{squad_label} | {roster_position}/{len(roster_context)} in roster"
        self.player_header_squad_var.set(squad_label)
        self.player_header_position_var.set(profile_view.position_label or record.get_position_name())

        if is_uncertain:
            self.player_header_dirty_var.set("View only")
        elif dirty_fields:
            self.player_header_dirty_var.set("Staged")
        else:
            self.player_header_dirty_var.set("Clean")
        self.player_header_confidence_var.set(profile_view.confidence_label)

        stage_parts: list[str] = []
        if profile_dirty_fields:
            stage_parts.append(f"{len(profile_dirty_fields)} field(s)")
        if skill_dirty_fields:
            stage_parts.append(f"{len(skill_dirty_fields)} skill tweak(s)")
        self.player_header_stage_var.set(" + ".join(stage_parts) if stage_parts else "No staged edits")

        if is_uncertain:
            note = "Uncertain parser result. Review the profile and provenance, but this record stays outside Save All."
        elif dirty_fields:
            preview_fields = [name.replace("_", " ").title() for name in profile_dirty_fields]
            preview_fields.extend(
                VISIBLE_SKILL_LABELS.get(skill_name, skill_name.replace("_", " ").title())
                for skill_name in skill_dirty_fields
            )
            preview_text = ", ".join(preview_fields[:3])
            if len(preview_fields) > 3:
                preview_text += ", ..."
            note = f"Staged for the next Save All. Current changes: {preview_text}."
        elif roster_position is not None:
            note = (
                f"Browsing the current roster for {club_name}. Use Previous / Next Player to step through "
                f"the squad without leaving the editor."
            )
        elif self.current_route == EditorWorkspaceRoute.PLAYERS:
            note = "Loaded from the Players browser. Use Focus Club to jump back into the club-first flow."
        else:
            note = "Player ready for review. Nothing is written until you choose Save All."

        if SAVE_NAME_ONLY and not is_uncertain:
            note += " Safe mode is active: only player names will be written in this build."
        self.player_header_note_var.set(note)

    def _player_only_name_edit_allowed(self) -> bool:
        return True

    def _set_player_action_state(self, has_player: bool, can_step_prev: bool, can_step_next: bool) -> None:
        offset = self.selection_state.selected_player_offset
        is_uncertain = offset in self.uncertain_player_index if offset is not None else False
        is_dirty = bool(self.dirty_state.field_dirty_map.get(f"players:{offset}", set())) if offset is not None else False

        can_focus_club = False
        if has_player and offset is not None:
            record = self._player_for_offset(offset)
            team_id = _safe_int(getattr(record, "team_id", 0), 0)
            if team_id:
                can_focus_club = any(
                    _safe_int(getattr(self._team_for_offset(team_offset), "team_id", 0), 0) == team_id
                    for team_offset, _original in self.team_records
                )

        revert_enabled = bool(has_player and is_dirty and not is_uncertain)
        focus_enabled = bool(has_player and can_focus_club)
        prev_enabled = bool(has_player and can_step_prev and not is_uncertain)
        next_enabled = bool(has_player and can_step_next and not is_uncertain)

        try:
            self.player_revert_button.state(["!disabled"] if revert_enabled else ["disabled"])
        except Exception:
            pass
        try:
            self.player_focus_club_button.state(["!disabled"] if focus_enabled else ["disabled"])
        except Exception:
            pass
        try:
            self.player_prev_button.state(["!disabled"] if prev_enabled else ["disabled"])
        except Exception:
            pass
        try:
            self.player_next_button.state(["!disabled"] if next_enabled else ["disabled"])
        except Exception:
            pass

    def _set_player_editor_enabled(self, *, enabled: bool) -> None:
        normal_state = "normal" if enabled else "disabled"
        name_state = "normal"
        if SAVE_NAME_ONLY:
            allowed = {"given_name", "surname"}
        else:
            allowed = set(self.player_field_widgets)
        for field, widget in self.player_field_widgets.items():
            desired_state = normal_state if field in allowed else "disabled"
            if field in {"given_name", "surname"}:
                desired_state = name_state if enabled else "disabled"
            elif field == "position":
                desired_state = "readonly" if (enabled and field in allowed and not SAVE_NAME_ONLY) else "disabled"
            try:
                widget.configure(state=desired_state)
            except Exception:
                pass
        for field, widget in self.player_skill_widgets.items():
            try:
                widget.configure(state="disabled" if (not enabled or SAVE_NAME_ONLY) else "normal")
            except Exception:
                pass

    def _set_provenance_lines(self, lines: list[str]) -> None:
        self.provenance_text.configure(state="normal")
        self.provenance_text.delete("1.0", tk.END)
        self.provenance_text.insert("1.0", "\n".join(lines))
        self.provenance_text.configure(state="disabled")

    def toggle_provenance_panel(self) -> None:
        self._provenance_visible = not self._provenance_visible
        if self._provenance_visible:
            self.provenance_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
            self.provenance_toggle_button.configure(text="Hide Provenance & Warnings")
        else:
            self.provenance_frame.pack_forget()
            self.provenance_toggle_button.configure(text="Show Provenance & Warnings")

    def _load_visible_skill_snapshot(self, record: PlayerRecord) -> None:
        self.current_visible_skill_baseline = {}
        self.current_visible_skill_target_name = ""
        self.current_visible_skill_source_query = self._player_display_name(record)
        query = self.current_visible_skill_source_query
        loaded_values: dict[str, int] = {}

        try:
            snapshot = inspect_player_visible_skills_dd6361(
                file_path=self._resolve_player_file_for_roster(),
                player_name=query,
            )
            target_name = str(getattr(snapshot, "resolved_bio_name", query))
            self.current_visible_skill_target_name = target_name
            self.current_visible_skill_baseline = {
                field: _safe_int((snapshot.mapped10 or {}).get(field, 0), 0)
                for field in VISIBLE_SKILL_ORDER
            }
            loaded_values = dict(self.current_visible_skill_baseline)
        except Exception:
            self.current_visible_skill_target_name = query
            self.current_visible_skill_baseline = {}
            loaded_values = {}

        staged = self._current_visible_skill_patch_for_player()
        if staged:
            loaded_values.update({field: int(value) for field, value in dict(staged.get("updates") or {}).items()})

        for field in VISIBLE_SKILL_ORDER:
            self.player_skill_vars[field].set(str(loaded_values.get(field, 0)))

        self._sync_player_dirty_styles()

    def _current_visible_skill_patch_for_player(self) -> dict[str, Any] | None:
        if self.selection_state.selected_player_offset is None:
            return None
        key = self._visible_skill_stage_key()
        if key is None:
            return None
        return self.staged_visible_skill_patches.get(key)

    def _visible_skill_stage_key(self) -> tuple[str, str] | None:
        if not self.current_visible_skill_target_name:
            return None
        return (str(Path(self._resolve_player_file_for_roster())), str(self.current_visible_skill_target_name))

    def _on_player_form_changed(self, _field_name: str) -> None:
        if self._loading_player_form:
            return
        if self.selection_state.selected_player_offset is None:
            return
        if self.selection_state.selected_player_offset in self.uncertain_player_index:
            return
        self._restage_current_player()

    def _on_player_skill_changed(self, _field_name: str) -> None:
        if self._loading_player_form:
            return
        if self.selection_state.selected_player_offset is None:
            return
        if self.selection_state.selected_player_offset in self.uncertain_player_index:
            return
        self._restage_current_player(update_skills_only=True)

    def _restage_current_player(self, *, update_skills_only: bool = False) -> None:
        offset = self.selection_state.selected_player_offset
        original = self.current_player_original
        if offset is None or original is None:
            return

        skill_dirty_fields = self._restage_current_visible_skill_patch()
        if SAVE_NAME_ONLY and not update_skills_only:
            staged = self._build_player_stage_from_form(original, names_only=True)
        else:
            staged = self._build_player_stage_from_form(original, names_only=False)

        if staged is None:
            self.modified_records.pop(offset, None)
            player_dirty_fields: set[str] = set()
        else:
            self.modified_records[offset] = staged
            player_dirty_fields = self._diff_player_fields(original, staged)

        combined_dirty = set(player_dirty_fields) | set(skill_dirty_fields)
        self.dirty_state.set_record_fields("players", offset, combined_dirty)
        self._rebuild_indexes()
        self._refresh_all_views()
        self._refresh_footer_state()

        if offset in self.modified_records:
            self.current_record = (offset, self.modified_records[offset])
        else:
            self.current_record = (offset, self.player_index.get(offset) or original)

        self._sync_player_dirty_styles()

    def _build_player_stage_from_form(self, original: PlayerRecord, *, names_only: bool) -> PlayerRecord | None:
        staged = copy.deepcopy(original)
        dirty = False

        new_given = _normalize_spaces(self.player_form_vars["given_name"].get())
        new_surname = _normalize_spaces(self.player_form_vars["surname"].get())
        if new_given != (getattr(original, "given_name", "") or ""):
            if not new_given:
                return None
            staged.set_given_name(new_given)
            dirty = True
        if new_surname != (getattr(original, "surname", "") or ""):
            if not new_surname:
                return None
            staged.set_surname(new_surname)
            dirty = True

        if names_only:
            return staged if dirty else None

        new_team_id = _safe_int(self.player_form_vars["team_id"].get(), getattr(original, "team_id", 0))
        if new_team_id != _safe_int(getattr(original, "team_id", 0), 0):
            staged.set_team_id(new_team_id)
            dirty = True

        new_squad = _safe_int(self.player_form_vars["squad_number"].get(), getattr(original, "squad_number", 0))
        if new_squad != _safe_int(getattr(original, "squad_number", 0), 0):
            staged.set_squad_number(new_squad)
            dirty = True

        new_nat = _safe_int(
            self.player_form_vars["nationality"].get(),
            getattr(original, "nationality", getattr(original, "nationality_id", 0)),
        )
        old_nat = _safe_int(getattr(original, "nationality", getattr(original, "nationality_id", 0)), 0)
        if new_nat != old_nat:
            staged.set_nationality(new_nat)
            dirty = True

        new_position_name = self.player_form_vars["position"].get() or original.get_position_name()
        new_position = POSITION_TO_CODE.get(new_position_name, getattr(original, "position_primary", 0))
        if new_position != _safe_int(getattr(original, "position_primary", 0), 0):
            staged.set_position(new_position)
            dirty = True

        day = _safe_int(self.player_form_vars["dob_day"].get(), getattr(original, "birth_day", 1))
        month = _safe_int(self.player_form_vars["dob_month"].get(), getattr(original, "birth_month", 1))
        year = _safe_int(self.player_form_vars["dob_year"].get(), getattr(original, "birth_year", 1975))
        old_dob = tuple(getattr(original, "dob", (1, 1, 1975)))
        if (day, month, year) != old_dob:
            staged.set_dob(day, month, year)
            dirty = True

        new_height = _safe_int(self.player_form_vars["height"].get(), getattr(original, "height", 175))
        if new_height != _safe_int(getattr(original, "height", 175), 175):
            staged.set_height(new_height)
            dirty = True

        if getattr(original, "supports_weight_write", lambda: False)():
            weight_text = _normalize_spaces(self.player_form_vars["weight"].get())
            if weight_text:
                new_weight = _safe_int(weight_text, getattr(original, "weight", 0) or 0)
                old_weight = getattr(original, "weight", None)
                if old_weight is None or new_weight != int(old_weight):
                    staged.set_weight(new_weight)
                    dirty = True
            elif getattr(original, "weight", None) is not None:
                staged.weight = getattr(original, "weight", None)

        return staged if dirty else None

    def _restage_current_visible_skill_patch(self) -> set[str]:
        key = self._visible_skill_stage_key()
        dirty_fields: set[str] = set()
        if key is None or not self.current_visible_skill_baseline:
            return dirty_fields

        updates: dict[str, int] = {}
        for field in VISIBLE_SKILL_ORDER:
            current_value = _safe_int(self.player_skill_vars[field].get(), self.current_visible_skill_baseline.get(field, 0))
            baseline = self.current_visible_skill_baseline.get(field)
            if baseline is None:
                continue
            if current_value != baseline:
                updates[field] = current_value
                dirty_fields.add(f"skill:{field}")

        if updates:
            self.staged_visible_skill_patches[key] = {
                "file_path": str(key[0]),
                "player_name": str(key[1]),
                "updates": dict(updates),
                "target_query": self.current_visible_skill_source_query or str(key[1]),
            }
        else:
            self.staged_visible_skill_patches.pop(key, None)
        return dirty_fields

    def _diff_player_fields(self, original: PlayerRecord, staged: PlayerRecord) -> set[str]:
        changed: set[str] = set()
        fields = [
            ("given_name", getattr(original, "given_name", ""), getattr(staged, "given_name", "")),
            ("surname", getattr(original, "surname", ""), getattr(staged, "surname", "")),
            ("team_id", getattr(original, "team_id", 0), getattr(staged, "team_id", 0)),
            ("squad_number", getattr(original, "squad_number", 0), getattr(staged, "squad_number", 0)),
            ("nationality", getattr(original, "nationality", getattr(original, "nationality_id", 0)), getattr(staged, "nationality", getattr(staged, "nationality_id", 0))),
            ("position", getattr(original, "position_primary", 0), getattr(staged, "position_primary", 0)),
            ("dob", tuple(getattr(original, "dob", (1, 1, 1975))), tuple(getattr(staged, "dob", (1, 1, 1975)))),
            ("height", getattr(original, "height", 175), getattr(staged, "height", 175)),
            ("weight", getattr(original, "weight", None), getattr(staged, "weight", None)),
        ]
        for field, before, after in fields:
            if before != after:
                changed.add(field)
        return changed

    def _sync_player_dirty_styles(self) -> None:
        original = self.current_player_original
        offset = self.selection_state.selected_player_offset
        if original is None or offset is None:
            return

        dirty_fields = set(self.dirty_state.field_dirty_map.get(f"players:{offset}", set()))
        direct_fields = {
            "given_name": _normalize_spaces(self.player_form_vars["given_name"].get()) != _normalize_spaces(getattr(original, "given_name", "")),
            "surname": _normalize_spaces(self.player_form_vars["surname"].get()) != _normalize_spaces(getattr(original, "surname", "")),
            "team_id": _safe_int(self.player_form_vars["team_id"].get(), 0) != _safe_int(getattr(original, "team_id", 0), 0),
            "squad_number": _safe_int(self.player_form_vars["squad_number"].get(), 0) != _safe_int(getattr(original, "squad_number", 0), 0),
            "nationality": _safe_int(self.player_form_vars["nationality"].get(), 0) != _safe_int(getattr(original, "nationality", getattr(original, "nationality_id", 0)), 0),
            "position": (self.player_form_vars["position"].get() or original.get_position_name()) != original.get_position_name(),
            "height": _safe_int(self.player_form_vars["height"].get(), 0) != _safe_int(getattr(original, "height", 175), 175),
            "weight": (
                _normalize_spaces(self.player_form_vars["weight"].get()) != ""
                and _safe_int(self.player_form_vars["weight"].get(), getattr(original, "weight", 0) or 0) != int(getattr(original, "weight", 0) or 0)
            ),
        }
        current_dob = (
            _safe_int(self.player_form_vars["dob_day"].get(), 1),
            _safe_int(self.player_form_vars["dob_month"].get(), 1),
            _safe_int(self.player_form_vars["dob_year"].get(), 1975),
        )
        direct_fields["dob"] = current_dob != tuple(getattr(original, "dob", (1, 1, 1975)))

        for field, widget in self.player_field_widgets.items():
            is_dirty = direct_fields.get(field, False)
            self._set_widget_dirty(widget, is_dirty)
            label = self.player_field_labels.get(field)
            if label is not None:
                label.configure(foreground="#9a3c12" if is_dirty else "")

        dob_dirty = direct_fields["dob"]
        if "dob" in self.player_field_labels:
            self.player_field_labels["dob"].configure(foreground="#9a3c12" if dob_dirty else "")
        for key in ("dob_day", "dob_month", "dob_year"):
            self._set_widget_dirty(self.player_field_widgets[key], dob_dirty)

        position_label = self.player_field_labels.get("position")
        if position_label is not None:
            position_label.configure(foreground="#9a3c12" if direct_fields["position"] else "")

        for field, widget in self.player_skill_widgets.items():
            baseline = self.current_visible_skill_baseline.get(field)
            if baseline is None:
                self._set_widget_dirty(widget, False)
                continue
            current_value = _safe_int(self.player_skill_vars[field].get(), baseline)
            self._set_widget_dirty(widget, current_value != baseline)

        record = self._player_for_offset(offset)
        club_name = self.team_lookup.get(_safe_int(getattr(record, "team_id", 0), 0), "")
        is_uncertain = offset in self.uncertain_player_index
        profile_view = self._build_player_profile_view(
            offset,
            record,
            original,
            club_name,
            is_uncertain,
        )
        self._refresh_player_header_widgets(offset, record, profile_view, is_uncertain)

    def _set_widget_dirty(self, widget: tk.Widget, is_dirty: bool) -> None:
        try:
            widget.configure(bg="#fff1db" if is_dirty else "white")
        except Exception:
            pass

    def revert_player_changes(self) -> None:
        offset = self.selection_state.selected_player_offset
        if offset is None:
            return
        self.modified_records.pop(offset, None)
        key = self._visible_skill_stage_key()
        if key is not None:
            self.staged_visible_skill_patches.pop(key, None)
        self.dirty_state.clear_record("players", offset)
        self._rebuild_indexes()
        self._refresh_all_views()
        self._refresh_footer_state()
        self.display_player(offset)
        self.status_var.set("Reverted staged player changes")

    def focus_player_club(self) -> None:
        offset = self.selection_state.selected_player_offset
        if offset is None:
            return
        record = self._player_for_offset(offset)
        team_id = _safe_int(getattr(record, "team_id", 0), 0)
        for team_offset, _original in self.team_records:
            team = self._team_for_offset(team_offset)
            if _safe_int(getattr(team, "team_id", 0), 0) == team_id:
                self.set_route(EditorWorkspaceRoute.CLUBS)
                self._select_club_by_offset(team_offset, focus_editor=False)
                self._select_tree_item_by_value(self.club_tree, self._club_item_map, team_offset)
                return

    def step_roster_player(self, direction: int) -> None:
        context = list(self.selection_state.current_roster_context or [])
        current = self.selection_state.selected_player_offset
        if not context or current not in context:
            return
        idx = context.index(current)
        next_idx = idx + int(direction)
        if 0 <= next_idx < len(context):
            self._select_player_by_offset(context[next_idx], route_if_needed=False)

    def _refresh_team_header_widgets(self, team: Any, offset: int) -> None:
        self.team_header_var.set(self._team_name(team))
        self.team_header_team_id_var.set(str(getattr(team, "team_id", "") or "-"))
        self.team_header_league_var.set(self._team_league(team))
        self.team_header_country_var.set(self._team_country(team))
        self.team_header_dirty_var.set("Staged" if offset in self.dirty_state.dirty_teams else "Clean")

        roster_count = len(self.current_roster_rows)
        roster_status = self.club_summary_status_var.get() or ("Roster loaded" if roster_count else "No roster loaded")
        if roster_count:
            self.team_header_roster_var.set(f"{roster_count} players | {roster_status}")
        else:
            self.team_header_roster_var.set(roster_status)

        selected_row = self._selected_roster_row()
        if selected_row is not None:
            self.team_header_note_var.set(
                f"Club ready. Slot {selected_row.slot_number} is selected in the squad list for roster tools."
            )
        elif not self._player_catalog_loaded:
            self.team_header_note_var.set(
                "Club ready for editing. Load player data when you want roster tools and player profiles."
            )
        elif offset in self.dirty_state.dirty_teams:
            self.team_header_note_var.set("Club changes are staged. Review the details below, then use Save All to write them.")
        else:
            self.team_header_note_var.set("Club ready for editing. Rename the club or use roster tools from the current squad.")

    def display_team(self, team: Any | None) -> None:
        if team is None:
            return
        offset = self.current_club_offset
        if offset is None:
            return
        original = self.team_index.get(offset)
        if original is None:
            return

        self._refresh_team_header_widgets(team, offset)
        self.team_coach_summary_var.set(
            "Linked coach editing is not available yet. Coach data is still surfaced separately in the Coaches browser."
        )
        self.team_provenance_var.set(
            "Writable here: club name and team ID.\n"
            "Roster slot tools operate on the selected squad row from the Clubs view.\n"
            "Stadium stays visible for context only while coach links remain unresolved."
        )
        try:
            self.team_edit_coach_button.state(["disabled"])
        except Exception:
            pass

        self._loading_team_form = True
        try:
            self.team_form_vars["name"].set(self._team_name(team))
            self.team_form_vars["team_id"].set(str(getattr(team, "team_id", 0) or 0))
            self.team_form_vars["stadium"].set(_normalize_spaces(getattr(team, "stadium", "") or ""))
        finally:
            self._loading_team_form = False

        self._set_team_editor_action_state(
            has_club=True,
            has_roster=bool(self.current_roster_rows),
            has_selected_slot=self._selected_roster_row() is not None,
        )
        self._sync_team_dirty_styles(original, team, offset)

    def _on_team_form_changed(self, _field_name: str) -> None:
        if self._loading_team_form:
            return
        offset = self.current_club_offset
        if offset is None:
            return
        original = self.team_index.get(offset)
        if original is None:
            return

        staged = copy.deepcopy(original)
        dirty_fields: set[str] = set()

        new_name = _normalize_spaces(self.team_form_vars["name"].get())
        if new_name and new_name != self._team_name(original):
            if hasattr(staged, "set_name"):
                staged.set_name(new_name)
            else:
                setattr(staged, "name", new_name)
            dirty_fields.add("name")

        new_team_id = _safe_int(self.team_form_vars["team_id"].get(), getattr(original, "team_id", 0))
        if new_team_id != _safe_int(getattr(original, "team_id", 0), 0):
            if hasattr(staged, "set_team_id"):
                staged.set_team_id(new_team_id)
            else:
                setattr(staged, "team_id", new_team_id)
            dirty_fields.add("team_id")

        if dirty_fields:
            self.modified_team_records[offset] = staged
            self.current_team = (offset, staged)
        else:
            self.modified_team_records.pop(offset, None)
            self.current_team = (offset, original)

        self.dirty_state.set_record_fields("teams", offset, dirty_fields)
        self._rebuild_team_lookup()
        self._refresh_all_views()
        self._refresh_footer_state()
        self.display_team(self._team_for_offset(offset))
        self.status_var.set("Club changes staged")

    def _sync_team_dirty_styles(self, original: Any, current: Any, offset: int) -> None:
        name_dirty = self._team_name(original) != self._team_name(current)
        id_dirty = _safe_int(getattr(original, "team_id", 0), 0) != _safe_int(getattr(current, "team_id", 0), 0)
        self._set_widget_dirty(self.team_field_widgets["name"], name_dirty)
        self._set_widget_dirty(self.team_field_widgets["team_id"], id_dirty)
        self._refresh_team_header_widgets(current, offset)
        self._set_team_editor_action_state(
            has_club=True,
            has_roster=bool(self.current_roster_rows),
            has_selected_slot=self._selected_roster_row() is not None,
        )

    def revert_team_changes(self) -> None:
        offset = self.current_club_offset
        if offset is None:
            return
        self.modified_team_records.pop(offset, None)
        self.dirty_state.clear_record("teams", offset)
        self._rebuild_team_lookup()
        self._refresh_all_views()
        self._refresh_footer_state()
        self.display_team(self._team_for_offset(offset))
        self.status_var.set("Reverted staged club changes")

    def display_coach(self, offset: int) -> None:
        coach = self._coach_for_offset(offset)
        original = self.coach_index.get(offset)
        if original is None:
            return

        view = CoachProfileView(
            offset=offset,
            full_name=self._coach_display_name(coach),
            club_name=UNSUPPORTED_COACH_LINK_TEXT,
            team_id_label="",
            dirty=offset in self.dirty_state.dirty_coaches,
            notes=["Current coach editing supports name changes only."],
        )
        self.coach_header_var.set(view.full_name)
        self.coach_meta_var.set(f"{'Dirty' if view.dirty else 'Clean'}   |   {view.club_name}")
        self.coach_link_var.set(view.club_name)

        self._loading_coach_form = True
        try:
            self.coach_form_vars["given_name"].set(getattr(coach, "given_name", "") or "")
            self.coach_form_vars["surname"].set(getattr(coach, "surname", "") or "")
        finally:
            self._loading_coach_form = False

        self._set_widget_dirty(
            self.coach_field_widgets["given_name"],
            _normalize_spaces(self.coach_form_vars["given_name"].get()) != _normalize_spaces(getattr(original, "given_name", "")),
        )
        self._set_widget_dirty(
            self.coach_field_widgets["surname"],
            _normalize_spaces(self.coach_form_vars["surname"].get()) != _normalize_spaces(getattr(original, "surname", "")),
        )

    def _on_coach_form_changed(self, _field_name: str) -> None:
        if self._loading_coach_form:
            return
        offset = self.selection_state.selected_coach_offset
        if offset is None:
            return
        original = self.coach_index.get(offset)
        if original is None:
            return

        given = _normalize_spaces(self.coach_form_vars["given_name"].get())
        surname = _normalize_spaces(self.coach_form_vars["surname"].get())
        dirty_fields: set[str] = set()
        staged = copy.deepcopy(original)

        if given != _normalize_spaces(getattr(original, "given_name", "")):
            dirty_fields.add("given_name")
        if surname != _normalize_spaces(getattr(original, "surname", "")):
            dirty_fields.add("surname")

        if dirty_fields and given and surname:
            if hasattr(staged, "set_name"):
                staged.set_name(given, surname)
            else:
                setattr(staged, "given_name", given)
                setattr(staged, "surname", surname)
                setattr(staged, "full_name", f"{given} {surname}".strip())
            self.modified_coach_records[offset] = staged
            self.current_coach = (offset, staged)
        else:
            self.modified_coach_records.pop(offset, None)
            self.current_coach = (offset, original)
            if not (given and surname) and dirty_fields:
                dirty_fields = set()

        self.dirty_state.set_record_fields("coaches", offset, dirty_fields)
        self._refresh_all_views()
        self._refresh_footer_state()
        self.display_coach(offset)
        self.status_var.set("Coach changes staged")

    def revert_coach_changes(self) -> None:
        offset = self.selection_state.selected_coach_offset
        if offset is None:
            return
        self.modified_coach_records.pop(offset, None)
        self.dirty_state.clear_record("coaches", offset)
        self._refresh_all_views()
        self._refresh_footer_state()
        self.display_coach(offset)
        self.status_var.set("Reverted staged coach changes")

    def _focus_current_coach(self) -> None:
        if self.coach_records:
            self.set_route(EditorWorkspaceRoute.COACHES)
            self._select_coach_by_offset(self.coach_records[0][0], route_if_needed=False)
        else:
            messagebox.showinfo("Coach Editor", UNSUPPORTED_COACH_LINK_TEXT)

    def _open_roster_edit_dialog(self, required_mode: str | None) -> None:
        selection = self.roster_tree.selection()
        if not selection:
            messagebox.showinfo("Roster Slot Editor", "Select a roster row first.")
            return
        row = self.current_roster_meta_by_item.get(selection[0])
        if row is None:
            messagebox.showinfo("Roster Slot Editor", "The selected row does not have editable roster metadata.")
            return
        mode = str(row.meta.get("mode") or "")
        if required_mode and mode != required_mode:
            messagebox.showinfo(
                "Roster Slot Editor",
                f"The selected row is a {mode or 'non-editable'} source, not a {required_mode} source.",
            )
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Roster Slot")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text=f"{row.player_name} (slot {row.slot_number})", font=("TkDefaultFont", 11, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        ttk.Label(dialog, text=f"Source: {mode}").pack(anchor="w", padx=12)

        pid_var = tk.StringVar(value=str(row.meta.get("current_pid", "")))
        flag_var = tk.StringVar(value=str(row.meta.get("current_flag", "")))
        dry_run_var = tk.BooleanVar(value=True)

        form = ttk.Frame(dialog, padding=12)
        form.pack(fill=tk.BOTH, expand=True)
        ttk.Label(form, text="Player ID", width=16).grid(row=0, column=0, sticky="w", pady=2)
        tk.Entry(form, textvariable=pid_var, relief=tk.SOLID, bd=1).grid(row=0, column=1, sticky="ew", pady=2)
        if mode == "linked":
            ttk.Label(form, text="Flag", width=16).grid(row=1, column=0, sticky="w", pady=2)
            tk.Entry(form, textvariable=flag_var, relief=tk.SOLID, bd=1).grid(row=1, column=1, sticky="ew", pady=2)
            next_row = 2
        else:
            next_row = 1
        form.grid_columnconfigure(1, weight=1)
        ttk.Checkbutton(form, text="Dry run (stage only)", variable=dry_run_var).grid(row=next_row, column=0, columnspan=2, sticky="w", pady=(6, 0))

        button_row = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        button_row.pack(fill=tk.X)

        def _apply() -> None:
            try:
                pid = _safe_int(pid_var.get(), _safe_int(row.meta.get("current_pid", 0), 0))
                flag = _safe_int(flag_var.get(), _safe_int(row.meta.get("current_flag", 0), 0))
                result_lines = self._apply_roster_slot_edit(row, pid=pid, flag=flag, dry_run=bool(dry_run_var.get()))
                dialog.destroy()
                messagebox.showinfo("Roster Slot Editor", "\n".join(result_lines))
            except Exception as exc:
                messagebox.showerror("Roster Slot Editor", f"Roster slot edit failed:\n{exc}")

        ttk.Button(button_row, text="Apply", command=_apply).pack(side=tk.LEFT)
        ttk.Button(button_row, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=(6, 0))

    def _apply_roster_slot_edit(
        self,
        row: RosterRowView,
        *,
        pid: int,
        flag: int,
        dry_run: bool,
    ) -> list[str]:
        if self.current_team is None:
            raise ValueError("No team selected")

        mode = str(row.meta.get("mode") or "")
        team_query = str(row.meta.get("team_query") or self._team_name(self.current_team[1]))
        team_file = self.team_file_path
        player_file = self._resolve_player_file_for_roster()

        self.status_var.set("Applying roster slot edit...")
        self.root.update_idletasks()

        if mode == "linked":
            result = edit_team_roster_eq_jug_linked(
                team_file=team_file,
                player_file=player_file,
                team_query=team_query,
                slot_number=_safe_int(row.meta.get("slot_number", row.slot_number), row.slot_number),
                player_record_id=pid,
                flag=flag,
                write_changes=not dry_run,
            )
        elif mode == "same_entry":
            result = edit_team_roster_same_entry_authoritative(
                team_file=team_file,
                player_file=player_file,
                team_query=team_query,
                team_offset=_safe_int(row.meta.get("team_offset", 0), 0),
                slot_number=_safe_int(row.meta.get("slot_number", row.slot_number), row.slot_number),
                pid_candidate=pid,
                write_changes=not dry_run,
            )
        else:
            raise ValueError(f"Unsupported roster edit mode: {mode}")

        if not dry_run and getattr(result, "applied_to_disk", False):
            self._select_club_by_offset(self.current_club_offset, focus_editor=False)

        warning_count = len(getattr(result, "warnings", []) or [])
        self.status_var.set(
            f"Roster slot edit complete ({len(getattr(result, 'changes', []) or [])} changed, {warning_count} warning(s))"
        )
        lines = [
            "Dry run complete" if dry_run else "Roster edit complete",
            f"Club: {team_query}",
            f"Player: {row.player_name}",
            f"Rows changed: {len(getattr(result, 'changes', []) or [])}",
            f"Warnings: {warning_count}",
        ]
        backup = getattr(result, "backup_path", None)
        if backup:
            lines.append(f"Backup: {backup}")
        return lines

    def _show_batch_roster_placeholder(self) -> None:
        messagebox.showinfo(
            "Roster Tools",
            "Batch roster CSV import has not been migrated into the refreshed shell yet.\n"
            "Use the Advanced Workspace for research and keep Save All for staged editor changes.",
        )

    def export_current_roster_csv(self) -> None:
        if not self.current_roster_rows:
            messagebox.showinfo("Export Roster CSV", "No roster is available for the selected club.")
            return
        filename = filedialog.asksaveasfilename(
            title="Export Club Roster",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not filename:
            return
        with open(filename, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["slot", "player", "position", "nationality", "speed", "stamina", "aggression", "quality", "status"])
            for row in self.current_roster_rows:
                writer.writerow(
                    [
                        row.slot_number,
                        row.player_name,
                        row.position_label,
                        row.nationality_label,
                        row.skills.get("speed", ""),
                        row.skills.get("stamina", ""),
                        row.skills.get("aggression", ""),
                        row.skills.get("quality", ""),
                        ", ".join(row.status_badges),
                    ]
                )
        self.status_var.set(f"Exported roster CSV to {filename}")

    def save_database(self) -> bool:
        if not self._has_staged_changes():
            messagebox.showinfo("Save All", "No staged changes to save.")
            return False

        if not messagebox.askyesno(
            "Save All",
            "Write all staged player, club, coach, and visible-skill changes now?\n\n"
            "The save runs once and then re-opens the written files for validation.",
        ):
            return False

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_lines: list[str] = []

        try:
            self.status_var.set("Saving staged changes...")
            self.toolbar_status_var.set("Saving...")
            self.root.update_idletasks()
            had_player_related_changes = bool(changed_players or self.staged_visible_skill_patches)

            if self.modified_records or self.staged_visible_skill_patches:
                player_backup = Path(self.file_path + f".backup_{timestamp}")
                if self.file_data is not None:
                    player_backup.write_bytes(self.file_data)
                else:
                    player_backup.write_bytes(Path(self.file_path).read_bytes())
                summary_lines.append(f"Players backup: {player_backup}")

            changed_players = dict(self.modified_records)
            changed_teams = dict(self.modified_team_records)
            changed_coaches = dict(self.modified_coach_records)

            if changed_players:
                fdi = FDIFile(self.file_path)
                fdi.file_data = self.file_data
                fdi.modified_records = dict(changed_players)
                fdi.save()
                self.file_data = Path(self.file_path).read_bytes()

            if self.staged_visible_skill_patches:
                self._apply_staged_visible_skill_patches()
                self.file_data = Path(self.file_path).read_bytes()

            if changed_coaches:
                coach_backup = write_coach_staged_records(self.coach_file_path, list(changed_coaches.items()))
                if coach_backup:
                    summary_lines.append(f"Coaches backup: {coach_backup}")

            if changed_teams:
                team_backup = write_team_staged_records(self.team_file_path, list(changed_teams.items()))
                if team_backup:
                    summary_lines.append(f"Teams backup: {team_backup}")

            self._commit_staged_records_to_loaded_state(changed_players, changed_teams, changed_coaches)

            validation = validate_database_files(
                player_file=self.file_path if had_player_related_changes else None,
                team_file=self.team_file_path if changed_teams else None,
                coach_file=self.coach_file_path if changed_coaches else None,
            )

            details = []
            for item in list(getattr(validation, "files", []) or []):
                status = "OK" if getattr(item, "success", False) else "FAIL"
                details.append(
                    f"{getattr(item, 'category', 'file')}: {status} "
                    f"(valid={int(getattr(item, 'valid_count', 0) or 0)}, "
                    f"uncertain={int(getattr(item, 'uncertain_count', 0) or 0)})"
                )
                detail = _normalize_spaces(getattr(item, "detail", "") or "")
                if detail:
                    details.append(f"  {detail}")

            if validation.all_valid:
                self.validation_state = ValidationBannerState(status="ok", message="Validation passed after save")
                self.status_var.set("Database saved and validated")
                self.toolbar_status_var.set("Saved")
                self._refresh_footer_state()
                messagebox.showinfo("Save All", "\n".join(["Save complete", *summary_lines, "", *details]))
                return True

            self.validation_state = ValidationBannerState(status="warning", message="Write succeeded but validation reported issues")
            self.status_var.set("Database saved, validation reported issues")
            self.toolbar_status_var.set("Saved with warning")
            self._refresh_footer_state()
            messagebox.showwarning("Save All", "\n".join(["Save complete with validation warnings", *summary_lines, "", *details]))
            return True
        except Exception as exc:
            self.validation_state = ValidationBannerState(status="error", message="Save failed")
            self.status_var.set("Save failed")
            self.toolbar_status_var.set("Save failed")
            self._refresh_footer_state()
            messagebox.showerror("Save All", f"Save failed:\n{exc}")
            return False

    def _apply_staged_visible_skill_patches(self) -> None:
        staged_items = list(self.staged_visible_skill_patches.values())
        for item in staged_items:
            patch_player_visible_skills_dd6361(
                file_path=str(item["file_path"]),
                player_name=str(item["player_name"]),
                updates=dict(item.get("updates") or {}),
                output_file=None,
                in_place=True,
                create_backup_before_write=False,
                json_output=None,
            )

    def _commit_staged_records_to_loaded_state(
        self,
        changed_players: dict[int, PlayerRecord],
        changed_teams: dict[int, Any],
        changed_coaches: dict[int, Any],
    ) -> None:
        if changed_players:
            for offset, record in changed_players.items():
                if offset in self.player_index:
                    self.player_index[offset] = record
            self.all_records = [(offset, self.player_index[offset]) for offset in self.player_index]

        if changed_teams:
            for offset, record in changed_teams.items():
                if offset in self.team_index:
                    self.team_index[offset] = record
            self.team_records = [(offset, self.team_index[offset]) for offset in self.team_index]

        if changed_coaches:
            for offset, record in changed_coaches.items():
                if offset in self.coach_index:
                    self.coach_index[offset] = record
            self.coach_records = [(offset, self.coach_index[offset]) for offset in self.coach_index]

        self.modified_records.clear()
        self.modified_team_records.clear()
        self.modified_coach_records.clear()
        self.staged_visible_skill_patches.clear()
        if changed_players or changed_teams:
            self._dd6361_pid_stat_cache.clear()
            self._linked_roster_catalog_cache.clear()
            self._same_entry_overlap_cache.clear()
        self.dirty_state = DirtyRecordState()
        self._rebuild_indexes()
        self._refresh_filter_choices()
        self._refresh_all_views()
        self._refresh_footer_state()

        if self.current_club_offset is not None:
            self._select_club_by_offset(self.current_club_offset, focus_editor=False)
        if self.selection_state.selected_player_offset is not None:
            self.display_player(self.selection_state.selected_player_offset)
        if self.selection_state.selected_coach_offset is not None:
            self.display_coach(self.selection_state.selected_coach_offset)

    def _confirm_navigation_away_from_dirty(self, action_label: str) -> bool:
        if not self._has_staged_changes():
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved Changes",
            f"You have staged changes. Save them before you {action_label}?",
        )
        if answer is None:
            return False
        if answer is True:
            return self.save_database()
        return True

    def on_close(self) -> None:
        if not self._confirm_navigation_away_from_dirty("close the editor"):
            return
        self.root.destroy()

    def open_advanced_workspace(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Advanced Workspace")
        window.geometry("900x620")

        ttk.Label(window, text="Advanced Workspace", font=("TkDefaultFont", 14, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        ttk.Label(
            window,
            text=(
                "Research-only tools live here. They are intentionally separate from the main editor shell.\n"
                "These views surface parser-backed inspection data, indexed byte profiles, and roster-source diagnostics."
            ),
            justify=tk.LEFT,
        ).pack(anchor="w", padx=12, pady=(0, 8))

        filter_row = ttk.LabelFrame(window, text="Advanced Filters", padding=(12, 8))
        filter_row.pack(fill=tk.X, padx=12, pady=(0, 8))

        advanced_nationality_var = tk.StringVar()
        advanced_position_var = tk.StringVar(value="Any")

        ttk.Label(filter_row, text="Nationality").pack(side=tk.LEFT)
        tk.Entry(filter_row, textvariable=advanced_nationality_var, relief=tk.SOLID, bd=1, width=8).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Label(filter_row, text="Position").pack(side=tk.LEFT)
        ttk.Combobox(
            filter_row,
            textvariable=advanced_position_var,
            state="readonly",
            values=["Any", *POSITION_OPTIONS],
            width=12,
        ).pack(side=tk.LEFT, padx=(6, 0))

        button_row = ttk.Frame(window, padding=(12, 0, 12, 8))
        button_row.pack(fill=tk.X)

        output = tk.Text(window, wrap="word", relief=tk.SOLID, bd=1)
        output.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        def _write_lines(lines: list[str]) -> None:
            output.configure(state="normal")
            output.delete("1.0", tk.END)
            output.insert("1.0", "\n".join(lines))
            output.configure(state="disabled")

        def _read_advanced_filters() -> tuple[int | None, int | None, list[str]]:
            nationality_text = _normalize_spaces(advanced_nationality_var.get())
            position_text = advanced_position_var.get()
            if nationality_text:
                try:
                    nationality_value = int(nationality_text, 0)
                except Exception as exc:
                    raise ValueError("Nationality filter must be an integer.") from exc
            else:
                nationality_value = None
            position_value = POSITION_TO_CODE.get(position_text) if position_text in POSITION_TO_CODE else None
            header_lines = [
                "Advanced Filters",
                f"nationality={nationality_value if nationality_value is not None else 'any'}",
                f"position={position_text if position_value is not None else 'Any'}",
                "",
            ]
            return nationality_value, position_value, header_lines

        def _inspect_selected_player() -> None:
            offset = self.selection_state.selected_player_offset
            if offset is None:
                _write_lines(["No player is selected."])
                return
            try:
                _nat_value, _pos_value, header_lines = _read_advanced_filters()
                record = self._player_for_offset(offset)
                result = inspect_player_metadata_records(
                    file_path=self._resolve_player_file_for_roster(),
                    target_name=self._player_display_name(record),
                    target_offset=offset,
                )
                lines = [
                    *header_lines,
                    f"Matches: {getattr(result, 'matched_count', 0)}",
                    f"Storage mode: {getattr(result, 'storage_mode', 'unknown')}",
                ]
                for snapshot in list(getattr(result, "records", []) or [])[:8]:
                    lines.extend(
                        [
                            "",
                            f"{snapshot.name} @ 0x{int(snapshot.offset):08X}",
                            f"team_id={snapshot.team_id} position={snapshot.position} nationality={snapshot.nationality}",
                            f"dob={snapshot.birth_day}/{snapshot.birth_month}/{snapshot.birth_year} height={snapshot.height} weight={snapshot.weight}",
                            f"tail_prefix={list(snapshot.attribute_prefix or [])} post_weight={snapshot.post_weight_byte} trailer={snapshot.trailer_byte} sidecar={snapshot.sidecar_byte}",
                        ]
                    )
                _write_lines(lines)
            except Exception as exc:
                _write_lines([f"Player metadata inspection failed: {exc}"])

        def _inspect_indexed_profiles() -> None:
            try:
                nationality_value, position_value, header_lines = _read_advanced_filters()
                player_file = self._resolve_player_file_for_roster()
                suffix_result = profile_indexed_player_suffix_bytes(
                    player_file,
                    nationality=nationality_value,
                    position=position_value,
                    limit=5,
                    sample_size=3,
                )
                leading_result = profile_indexed_player_leading_bytes(
                    player_file,
                    nationality=nationality_value,
                    position=position_value,
                    limit=5,
                    sample_size=3,
                )
                tail_result = profile_indexed_player_attribute_prefixes(
                    player_file,
                    nationality=nationality_value,
                    position=position_value,
                    limit=5,
                    sample_size=3,
                )

                lines = [
                    *header_lines,
                    f"Indexed Player File: {player_file}",
                    f"Anchored records: suffix={suffix_result.anchored_count}, leading={leading_result.anchored_count}, tail={tail_result.anchored_count}",
                    f"Filtered records: suffix={suffix_result.filtered_count}, leading={leading_result.filtered_count}, tail={tail_result.filtered_count}",
                    "",
                    "Suffix u9/u10 Buckets",
                ]
                for bucket in list(suffix_result.buckets or [])[:5]:
                    lines.append(
                        f"u9/u10={bucket.indexed_unknown_9}/{bucket.indexed_unknown_10} "
                        f"count={bucket.count} samples={', '.join(bucket.sample_names or [])}"
                    )

                lines.extend(["", "Leading u0/u1 Buckets"])
                for bucket in list(leading_result.buckets or [])[:5]:
                    lines.append(
                        f"u0/u1={bucket.indexed_unknown_0}/{bucket.indexed_unknown_1} "
                        f"count={bucket.count} samples={', '.join(bucket.sample_names or [])}"
                    )

                lines.extend(
                    [
                        "",
                        "Tail Prefix Buckets",
                        f"Layout verified={tail_result.layout_verified_count} mismatch={tail_result.layout_mismatch_count}",
                        (
                            "post_weight mirror ratio="
                            f"{tail_result.post_weight_nationality_match_ratio:.2%} "
                            f"({tail_result.post_weight_nationality_match_count}/{tail_result.post_weight_nationality_eligible_count})"
                        ),
                    ]
                )
                for bucket in list(tail_result.buckets or [])[:5]:
                    lines.append(
                        f"tail={bucket.attribute_0}/{bucket.attribute_1}/{bucket.attribute_2} "
                        f"count={bucket.count} samples={', '.join(bucket.sample_names or [])}"
                    )

                if getattr(tail_result, "post_weight_group_clusters", None):
                    lines.extend(["", "Grouped Post-Weight Cohorts"])
                    for cluster in list(tail_result.post_weight_group_clusters or [])[:5]:
                        nat_counts = ", ".join(
                            f"{nat}({count})" for nat, count in list(cluster.nationality_counts or [])[:4]
                        )
                        lines.append(
                            f"postwt={cluster.post_weight_byte} total={cluster.total_count} "
                            f"nationalities={nat_counts}"
                        )
                _write_lines(lines)
            except Exception as exc:
                _write_lines([f"Indexed byte profile analysis failed: {exc}"])

        def _inspect_current_roster_sources() -> None:
            if self.current_team is None:
                _write_lines(["No club is selected."])
                return
            try:
                _nat_value, _pos_value, header_lines = _read_advanced_filters()
                team = self.current_team[1]
                team_name = self._team_name(team)
                player_file = self._resolve_player_file_for_roster()
                lines = [*header_lines, f"Club: {team_name}", ""]
                try:
                    linked = [
                        roster
                        for roster in self._get_linked_roster_catalog(self.team_file_path, player_file)
                        if team_query_matches(
                            team_name,
                            team_name=str(roster.get("team_name") or ""),
                            full_club_name=str(roster.get("full_club_name") or ""),
                        )
                    ]
                except Exception as exc:
                    linked = []
                    lines.append(f"Linked source error: {exc}")
                if linked:
                    first = dict(linked[0] or {})
                    lines.append(f"Linked rows: {len(list(first.get('rows') or []))} (shared GUI cache)")
                else:
                    lines.append("Linked rows: none")

                try:
                    overlap = self._get_same_entry_overlap_result(
                        team_file=self.team_file_path,
                        player_file=player_file,
                        team_query=team_name,
                    )
                    requested = list(getattr(overlap, "requested_team_results", []) or [])
                    first = dict(requested[0] or {}) if requested else {}
                    preferred = dict(first.get("preferred_roster_match") or {})
                    lines.extend(
                        [
                            "",
                            "Same-entry overlap:",
                            "shared GUI cache reused",
                            f"preferred provenance={preferred.get('provenance') or 'none'}",
                            f"rows={len(list(preferred.get('rows') or []))}",
                        ]
                    )
                except Exception as exc:
                    lines.extend(["", f"Same-entry overlap error: {exc}"])
                _write_lines(lines)
            except Exception as exc:
                _write_lines([f"Roster source inspection failed: {exc}"])

        def _inspect_bitmap_references() -> None:
            lines = [
                "Bitmap / Asset Reference Probe",
                "Scanning the currently selected PM99 database set for .BMP / .TGA string markers.",
                "",
            ]
            targets = [
                ("Players", self.file_path),
                ("Clubs", self.team_file_path),
                ("Coaches", self.coach_file_path),
            ]

            for label, file_name in targets:
                path = Path(str(file_name or ""))
                if not path.exists():
                    lines.extend([f"{label}: file missing", ""])
                    continue

                try:
                    data = path.read_bytes()
                except Exception as exc:
                    lines.extend([f"{label}: read failed ({exc})", ""])
                    continue

                data_upper = data.upper()
                hits: list[tuple[int, str, str]] = []
                for marker in (b".BMP", b".TGA"):
                    search_at = 0
                    while len(hits) < 8:
                        found_at = data_upper.find(marker, search_at)
                        if found_at < 0:
                            break
                        snippet_start = max(0, found_at - 24)
                        snippet_end = min(len(data), found_at + 32)
                        snippet = "".join(
                            chr(byte) if 32 <= byte <= 126 else "."
                            for byte in data[snippet_start:snippet_end]
                        )
                        hits.append((found_at, marker.decode("ascii"), snippet))
                        search_at = found_at + len(marker)

                lines.append(f"{label}: {path.name}")
                if hits:
                    for found_at, marker_name, snippet in hits:
                        lines.append(f"  0x{found_at:08X} {marker_name} {snippet}")
                else:
                    lines.append("  no .BMP or .TGA markers found")
                lines.append("")

            lines.append(
                "This is a read-only string probe. It helps locate likely image-reference contracts before any bitmap-aware editor surface is added."
            )
            _write_lines(lines)

        ttk.Button(button_row, text="Inspect Selected Player Metadata", command=_inspect_selected_player).pack(side=tk.LEFT)
        ttk.Button(button_row, text="Indexed Byte Profiles", command=_inspect_indexed_profiles).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(button_row, text="Inspect Current Club Roster Sources", command=_inspect_current_roster_sources).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(button_row, text="Inspect Bitmap References", command=_inspect_bitmap_references).pack(side=tk.LEFT, padx=(6, 0))

    def _select_tree_item_by_value(self, tree: ttk.Treeview, mapping: dict[str, int], target_value: int) -> None:
        for item_id, mapped_value in mapping.items():
            if int(mapped_value) == int(target_value):
                tree.selection_set(item_id)
                tree.see(item_id)
                return

    def _player_display_name(self, record: PlayerRecord) -> str:
        display = _normalize_spaces(getattr(record, "name", "") or "")
        if display:
            return display
        return _normalize_spaces(
            f"{getattr(record, 'given_name', '') or ''} {getattr(record, 'surname', '') or ''}"
        ) or "Unknown Player"

    def _coach_display_name(self, coach: Any) -> str:
        display = _normalize_spaces(
            getattr(coach, "full_name", None)
            or getattr(coach, "name", None)
            or f"{getattr(coach, 'given_name', '') or ''} {getattr(coach, 'surname', '') or ''}"
        )
        return display or "Unknown Coach"

    def _player_for_offset(self, offset: int) -> PlayerRecord:
        return (
            self.modified_records.get(offset)
            or self.player_index.get(offset)
            or self.uncertain_player_index.get(offset)
        )

    def _team_for_offset(self, offset: int) -> Any:
        return self.modified_team_records.get(offset) or self.team_index.get(offset)

    def _coach_for_offset(self, offset: int) -> Any:
        return self.modified_coach_records.get(offset) or self.coach_index.get(offset)

    def _team_name(self, team: Any) -> str:
        return _normalize_spaces(getattr(team, "name", "") or "") or "Unknown Club"

    def _team_country(self, team: Any) -> str:
        try:
            value = team.get_country()
        except Exception:
            value = getattr(team, "country", "") or ""
        return _normalize_spaces(value) or "Unknown"

    def _team_league(self, team: Any) -> str:
        return _normalize_spaces(getattr(team, "league", "") or "") or "Unknown League"
