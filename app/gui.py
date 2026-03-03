# Make gui.py runnable either as a package (python -m app.gui) or directly (python app/gui.py)
# This tries relative imports first; if that fails (no package context), it adjusts sys.path
import os, sys
try:
    # When executed as a package: python -m app.gui
    from .models import PlayerRecord, TeamRecord, CoachRecord
    from .io import FDIFile
    from .file_writer import save_modified_records
    from .xor import xor_decode
    from .loaders import load_teams, load_coaches
    from .pkf import PKFDecoderError, PKFFile
    from .pkf_searcher import PKFSearcher, SearchResult
except Exception:
    # When executed directly: python app/gui.py
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from app.models import PlayerRecord, TeamRecord, CoachRecord
    from app.io import FDIFile
    from app.file_writer import save_modified_records
    from app.xor import xor_decode
    from app.loaders import load_teams, load_coaches
    from app.pkf import PKFDecoderError, PKFFile

# Ensure common helpers are available when run as a script
from pathlib import Path

"""
Modern GUI application for Premier Manager 99 Database Editor
Uses the modular package structure
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from app.bulk_rename import bulk_rename_players, revert_player_renames
from app.editor_actions import (
    batch_edit_player_metadata_records,
    batch_edit_team_roster_records,
    build_player_visible_skill_index_dd6361,
    edit_team_roster_eq_jug_linked,
    edit_team_roster_same_entry_authoritative,
    extract_team_rosters_eq_jug_linked,
    extract_team_rosters_eq_same_entry_overlap,
    inspect_player_metadata_records,
    inspect_player_visible_skills_dd6361,
    patch_player_visible_skills_dd6361,
    parse_player_skill_patch_assignments,
    profile_indexed_player_leading_bytes,
    profile_indexed_player_suffix_bytes,
    profile_indexed_player_attribute_prefixes,
    profile_player_legacy_weight_candidates,
    rename_coach_records,
    rename_team_records,
    validate_database_files,
    write_coach_staged_records,
    write_team_staged_records,
)
from app.editor_helpers import team_query_matches
from app.editor_sources import gather_player_records
from app.models import PlayerRecord, TeamRecord, CoachRecord
from app.io import FDIFile
from app.file_writer import save_modified_records
from app.xor import xor_decode
from app.loaders import load_teams, load_coaches
from app.pkf import PKFDecoderError, PKFFile
from app.pkf_searcher import PKFSearcher, SearchResult
from app.settings import SAVE_NAME_ONLY
from datetime import datetime
import re
from collections import defaultdict
import threading

TEAM_PANEL_PROVENANCE_TEXT = (
    "Authoritative save fields: Team name, Team ID, Stadium. "
    "Capacity, Car Park, and Pitch quality are display-only until parser-backed save support exists."
)
TEAM_ROSTER_PROVENANCE_TEXT = (
    "Authoritative roster rows where available. Static SP/ST/AG/QU are parser-backed. "
    "EN/FI/MO/AV/ROL./POS remain unresolved."
)
TEAM_ROSTER_SHOW_TEXT = "Show partial squad roster"
TEAM_ROSTER_HIDE_TEXT = "Hide partial squad roster"
TEAM_ROSTER_STATUS_SUFFIX = " (static SP/ST/AG/QU only; dynamic columns unresolved)"
TEAM_ROSTER_UNRESOLVED_VALUE = "?"


def _format_hex_preview(data: bytes, width: int = 16, start_offset: int = 0, max_lines: int = 1000) -> tuple[str, bool]:
    """Return a hex dump for ``data`` suitable for text display with pagination support.

    Args:
        data: The data to format
        width: Bytes per line
        start_offset: Starting offset in data
        max_lines: Maximum lines to display

    Returns:
        Tuple of (formatted_text, has_more_data)
    """
    if not data:
        return "(empty payload)", False

    lines = []
    total_lines = (len(data) + width - 1) // width
    end_offset = min(len(data), start_offset + max_lines * width)

    for offset in range(start_offset, end_offset, width):
        if offset >= len(data):
            break
        chunk = data[offset : offset + width]
        hex_part = " ".join(f"{byte:02X}" for byte in chunk)
        ascii_part = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
        lines.append(f"{offset:08X}  {hex_part:<{width * 3 - 1}}  {ascii_part}")

    has_more = end_offset < len(data)
    if has_more:
        lines.append(f"… ({len(data) - end_offset} more bytes)")

    return "\n".join(lines), has_more

class PM99DatabaseEditor:
    """Modern GUI application for editing Premier Manager 99 database files"""
    def __init__(self, root):
        self.root = root
        self.root.title("Premier Manager 99 - Database Editor")
        # Preferred window size (target); will be clamped to fit the physical screen
        # to avoid oversized windows on laptops.
        desired_w, desired_h = 1400, 850
        try:
            # Query actual screen size (logical pixels)
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            # Reserve a small margin so the window doesn't overlap taskbars or go edge-to-edge
            margin_w = 80
            margin_h = 120
            max_w = max(200, screen_w - margin_w)
            max_h = max(200, screen_h - margin_h)
            w = min(desired_w, max_w)
            h = min(desired_h, max_h)
            # Center the window on screen
            x = max((screen_w - w) // 2, 0)
            y = max((screen_h - h) // 2, 0)
            self.root.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            # Fallback to original fixed geometry if anything goes wrong
            self.root.geometry("1400x850")
        
        self.file_path = 'DBDAT/JUG98030.FDI'
        self.file_data = None
        self.fdi_file = None
        self.all_records = []
        self.filtered_records = []
        self.current_record = None
        self.modified_records = {}  # offset -> PlayerRecord
        self.modified_coach_records = {}  # offset -> CoachRecord
        self.modified_team_records = {}   # offset -> TeamRecord
        self.team_roster_row_meta = {}    # tree item id -> authoritative roster row metadata

        # Coaches loading state (lazy-loaded)
        self.coach_file_path = 'DBDAT/ENT98030.FDI'
        self.coaches_loaded = False
        self.coach_records = []            # list of (offset, Coach)
        self.filtered_coach_records = []   # filtered view for search

        # Teams loading state (lazy-loaded)
        self.team_file_path = 'DBDAT/EQ98030.FDI'
        self.teams_loaded = False
        self.team_records = []             # list of (offset, TeamRecord)
        self.filtered_team_records = []    # filtered view for search
        self.team_lookup = {}              # team_id -> team_name mapping (built after teams parsed)
        self.team_alias_lookup = {}        # team_id -> (short_name, full_club_name)
        self.player_uncertain_count = 0

        default_pkf_dir = Path("SIMULDAT") if Path("SIMULDAT").exists() else Path(".")
        self._pkf_last_dir = default_pkf_dir.resolve()

        self.setup_ui()
        self.load_database()
    
    def setup_ui(self):
        """Create the UI"""
        # Menu
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open Database...", command=self.open_file)
        file_menu.add_command(label="Save Database", command=self.save_database, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)

        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Open PKF Viewer...", command=self.open_pkf_viewer)
        tools_menu.add_command(label="PKF String Searcher...", command=self.open_pkf_searcher)
        tools_menu.add_command(label="Load PKF and Count Records...", command=self.load_pkf_and_count)
        tools_menu.add_separator()
        tools_menu.add_command(label="Bulk Rename Players (M1)...", command=self.open_bulk_player_rename_dialog)
        tools_menu.add_command(label="Revert Bulk Player Rename (M1)...", command=self.open_bulk_player_revert_dialog)
        tools_menu.add_command(label="Batch Edit Players from CSV...", command=self.open_player_batch_edit_dialog)
        tools_menu.add_command(label="Batch Edit Team Roster from CSV...", command=self.open_team_roster_batch_edit_dialog)
        tools_menu.add_command(label="Inspect Player Metadata...", command=self.open_player_metadata_inspect_dialog)
        tools_menu.add_command(label="Inspect Indexed Player Byte Profiles...", command=self.open_player_indexed_profiles_dialog)
        tools_menu.add_command(label="Inspect Team Roster Sources...", command=self.open_team_roster_sources_dialog)
        tools_menu.add_command(label="Edit Selected Team Roster Slot...", command=self.open_selected_team_roster_edit_dialog)
        tools_menu.add_command(label="Edit Linked Team Roster Slot...", command=self.open_team_roster_edit_linked_dialog)
        tools_menu.add_separator()
        tools_menu.add_command(
            label="Patch Player Visible Skills (dd6361)...",
            command=self.open_player_skill_patch_dialog,
        )

        self.root.bind('<Control-s>', lambda e: self.save_database())
        if SAVE_NAME_ONLY:
            try:
                banner = ttk.Label(self.root, text="SAFE MODE: Only player names will be saved. Other edits are disabled.", foreground='darkred')
                banner.pack(fill=tk.X)
            except Exception:
                pass
        
        # Main layout
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left: Notebook with tabs for Players, Coaches, Teams
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=1)
        
        self.notebook = ttk.Notebook(left_frame)
        notebook = self.notebook
        self.notebook.pack(fill=tk.BOTH, expand=True)
        self.notebook.bind('<<NotebookTabChanged>>', self.on_tab_changed)
        
        # Players tab
        player_tab = ttk.Frame(notebook)
        notebook.add(player_tab, text="Players")
        
        # Search (Players)
        search_frame = ttk.LabelFrame(player_tab, text="Search", padding="5")
        search_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(
            search_frame,
            text="Search by player name or team (examples: Beckham, Man Utd, Manchester United)",
            font=("TkDefaultFont", 8),
        ).pack(fill=tk.X, anchor=tk.W, pady=(0, 4))
        
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.filter_records)
        ttk.Entry(search_frame, textvariable=self.search_var).pack(fill=tk.X)

        player_actions = ttk.Frame(player_tab)
        player_actions.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(
            player_actions,
            text="Inspect Selected Player",
            command=self.inspect_selected_player_metadata,
        ).pack(side=tk.LEFT)
        ttk.Button(
            player_actions,
            text="Advanced Research...",
            command=self.open_player_indexed_profiles_dialog,
        ).pack(side=tk.LEFT, padx=(6, 0))
        
        # Player tree
        tree_frame = ttk.LabelFrame(player_tab, text="Players", padding="5")
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ('name', 'team', 'squad', 'pos')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings', selectmode='browse')
        
        self.tree.heading('name', text='Name')
        self.tree.heading('team', text='Team ID')
        self.tree.heading('squad', text='Squad #')
        self.tree.heading('pos', text='Position')
        
        self.tree.column('name', width=200)
        self.tree.column('team', width=80)
        self.tree.column('squad', width=70)
        self.tree.column('pos', width=100)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree.bind('<<TreeviewSelect>>', self.on_select)
        
        # Count label
        self.count_label = ttk.Label(player_tab, text="Players: 0")
        self.count_label.pack(pady=(5, 0))
        
        # Coaches tab (read-only, populated lazily)
        coach_tab = ttk.Frame(notebook)
        notebook.add(coach_tab, text="Coaches")
        coach_search_frame = ttk.LabelFrame(coach_tab, text="Search", padding="5")
        coach_search_frame.pack(fill=tk.X, pady=(0,5))
        self.coach_search_var = tk.StringVar()
        self.coach_search_var.trace('w', self.filter_coaches)
        ttk.Entry(coach_search_frame, textvariable=self.coach_search_var).pack(fill=tk.X)
        coach_list_frame = ttk.LabelFrame(coach_tab, text="Coaches", padding="5")
        coach_list_frame.pack(fill=tk.BOTH, expand=True)

        coach_columns = ('name', 'offset')
        self.coach_tree = ttk.Treeview(coach_list_frame, columns=coach_columns, show='headings', selectmode='browse')
        self.coach_tree.heading('name', text='Name')
        self.coach_tree.heading('offset', text='Offset')
        self.coach_tree.column('name', width=220)
        self.coach_tree.column('offset', width=90, anchor=tk.CENTER)

        coach_scroll = ttk.Scrollbar(coach_list_frame, orient=tk.VERTICAL, command=self.coach_tree.yview)
        self.coach_tree.configure(yscrollcommand=coach_scroll.set)

        self.coach_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        coach_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.coach_tree.bind('<<TreeviewSelect>>', self.on_select_coach)
        self.coach_tree.bind('<Double-1>', self._on_coach_double)

        # Export button for coaches
        export_coach_btn = ttk.Button(coach_tab, text="Export Coaches", command=self.export_coaches)
        export_coach_btn.pack(pady=(5,0))

        self.coach_count_label = ttk.Label(coach_tab, text="Coaches: 0")
        self.coach_count_label.pack(pady=(5,0))
        
        # Teams tab (read-only, populated asynchronously)
        team_tab = ttk.Frame(notebook)
        notebook.add(team_tab, text="Teams")
        team_search_frame = ttk.LabelFrame(team_tab, text="Search", padding="5")
        team_search_frame.pack(fill=tk.X, pady=(0,5))
        self.team_search_var = tk.StringVar()
        self.team_search_var.trace('w', self.filter_teams)
        ttk.Entry(team_search_frame, textvariable=self.team_search_var).pack(fill=tk.X)
        team_list_frame = ttk.LabelFrame(team_tab, text="Teams", padding="5")
        team_list_frame.pack(fill=tk.BOTH, expand=True)

        team_columns = ('name', 'team_id', 'offset')
        self.team_tree = ttk.Treeview(team_list_frame, columns=team_columns, show='headings', selectmode='browse')
        self.team_tree.heading('name', text='Team Name')
        self.team_tree.heading('team_id', text='Team ID')
        self.team_tree.heading('offset', text='Offset')
        self.team_tree.column('name', width=260)
        self.team_tree.column('team_id', width=90, anchor=tk.CENTER)
        self.team_tree.column('offset', width=90, anchor=tk.CENTER)

        team_scroll = ttk.Scrollbar(team_list_frame, orient=tk.VERTICAL, command=self.team_tree.yview)
        self.team_tree.configure(yscrollcommand=team_scroll.set)

        self.team_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        team_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.team_tree.bind('<<TreeviewSelect>>', self.on_select_team)
        self.team_tree.bind('<Double-1>', self._on_team_double)

        # Export button for teams
        export_team_btn = ttk.Button(team_tab, text="Export Teams", command=self.export_teams)
        export_team_btn.pack(pady=(5,0))

        self.team_count_label = ttk.Label(team_tab, text="Teams: 0")
        self.team_count_label.pack(pady=(5,0))

        # Leagues tab (hierarchical: Country -> League -> Teams)
        league_tab = ttk.Frame(notebook)
        notebook.add(league_tab, text="⚽ Leagues")
        
        # Country filter
        filter_frame = ttk.Frame(league_tab)
        filter_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(filter_frame, text="Country:").pack(side=tk.LEFT, padx=5)
        self.league_country_var = tk.StringVar(value="All")
        
        try:
            from app.league_definitions import get_all_countries
            countries = ["All"] + get_all_countries()
        except:
            countries = ["All"]
        
        self.league_country_combo = ttk.Combobox(filter_frame, textvariable=self.league_country_var,
                                                  values=countries, state="readonly", width=15)
        self.league_country_combo.pack(side=tk.LEFT, padx=5)
        self.league_country_combo.bind("<<ComboboxSelected>>", lambda e: self.populate_league_tree())
        
        # Search
        ttk.Label(filter_frame, text="Search:").pack(side=tk.LEFT, padx=(20,5))
        self.league_search_var = tk.StringVar()
        self.league_search_var.trace('w', self.filter_leagues)
        search_entry = ttk.Entry(filter_frame, textvariable=self.league_search_var, width=20)
        search_entry.pack(side=tk.LEFT, padx=5)
        
        # Hierarchical TreeView
        league_list_frame = ttk.LabelFrame(league_tab, text="Leagues & Teams", padding="5")
        league_list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        league_columns = ('team_id', 'stadium', 'capacity')
        self.league_tree = ttk.Treeview(league_list_frame, columns=league_columns, show='tree headings', selectmode='browse')
        self.league_tree.heading('#0', text='Country / League / Team')
        self.league_tree.heading('team_id', text='Team ID')
        self.league_tree.heading('stadium', text='Stadium')
        self.league_tree.heading('capacity', text='Capacity')
        
        self.league_tree.column('#0', width=350, minwidth=200)
        self.league_tree.column('team_id', width=80, minwidth=60)
        self.league_tree.column('stadium', width=250, minwidth=150)
        self.league_tree.column('capacity', width=100, minwidth=80)

        league_scroll_v = ttk.Scrollbar(league_list_frame, orient=tk.VERTICAL, command=self.league_tree.yview)
        league_scroll_h = ttk.Scrollbar(league_list_frame, orient=tk.HORIZONTAL, command=self.league_tree.xview)
        self.league_tree.configure(yscrollcommand=league_scroll_v.set, xscrollcommand=league_scroll_h.set)

        self.league_tree.grid(row=0, column=0, sticky='nsew')
        league_scroll_v.grid(row=0, column=1, sticky='ns')
        league_scroll_h.grid(row=1, column=0, sticky='ew')
        
        league_list_frame.rowconfigure(0, weight=1)
        league_list_frame.columnconfigure(0, weight=1)

        self.league_tree.bind('<<TreeviewSelect>>', self.on_select_league)
        self.league_tree.bind('<Double-1>', self.on_league_doubleclick)

        self.league_count_label = ttk.Label(league_tab, text="Leagues: 0")
        self.league_count_label.pack(pady=(5,0), padx=5)

        # Analysis tab (persistent home for confirmed inspection/reporting surfaces)
        analysis_tab = ttk.Frame(notebook)
        notebook.add(analysis_tab, text="Analysis")
        self.analysis_tab = analysis_tab

        analysis_controls = ttk.LabelFrame(
            analysis_tab,
            text="Confirmed Analysis",
            padding="8",
        )
        analysis_controls.pack(fill=tk.X, padx=5, pady=(5, 0))
        ttk.Label(
            analysis_controls,
            text=(
                "Parser-backed inspection/reporting surfaces render here. "
                "These views mirror the stable read contracts shared with the CLI."
            ),
            justify=tk.LEFT,
            wraplength=860,
        ).pack(fill=tk.X, anchor=tk.W)

        analysis_btn_row = ttk.Frame(analysis_controls)
        analysis_btn_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(
            analysis_btn_row,
            text="Player Metadata",
            command=self.open_player_metadata_inspect_dialog,
        ).pack(side=tk.LEFT)
        ttk.Button(
            analysis_btn_row,
            text="Indexed Byte Profiles",
            command=self.open_player_indexed_profiles_dialog,
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            analysis_btn_row,
            text="Team Roster Sources",
            command=self.open_team_roster_sources_dialog,
        ).pack(side=tk.LEFT, padx=(6, 0))

        self.analysis_report_title_var = tk.StringVar(value="No analysis loaded")
        ttk.Label(
            analysis_tab,
            textvariable=self.analysis_report_title_var,
            font=("TkDefaultFont", 10, "bold"),
        ).pack(fill=tk.X, padx=8, pady=(8, 2))

        self.analysis_report_hint_var = tk.StringVar(
            value="Run one of the confirmed inspection actions to populate this workspace."
        )
        ttk.Label(
            analysis_tab,
            textvariable=self.analysis_report_hint_var,
            font=("TkDefaultFont", 8),
            justify=tk.LEFT,
            wraplength=900,
        ).pack(fill=tk.X, padx=8, pady=(0, 6))

        self.analysis_report_container = ttk.Frame(analysis_tab)
        self.analysis_report_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        # End of restored local GUI file
        # Right: Editor
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=2)
        
        # Player info
        info_frame = ttk.LabelFrame(right_frame, text="Player Information", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Name (editable - given name and surname)
        ttk.Label(info_frame, text="Given Name:", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, pady=5)
        self.given_name_var = tk.StringVar()
        # store widget reference so we can enable/disable in safe mode
        self.given_entry = ttk.Entry(info_frame, textvariable=self.given_name_var, width=20)
        self.given_entry.grid(row=0, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(info_frame, text="(max 12 chars)", font=('TkDefaultFont', 8)).grid(row=0, column=2, sticky=tk.W)
        
        ttk.Label(info_frame, text="Surname:", font=('TkDefaultFont', 10, 'bold')).grid(row=1, column=0, sticky=tk.W, pady=5)
        self.surname_var = tk.StringVar()
        # store widget reference so we can enable/disable in safe mode
        self.surname_entry = ttk.Entry(info_frame, textvariable=self.surname_var, width=20)
        self.surname_entry.grid(row=1, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(info_frame, text="(max 12 chars)", font=('TkDefaultFont', 8)).grid(row=1, column=2, sticky=tk.W)
        
        # Team ID
        ttk.Label(info_frame, text="Team ID:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.team_id_var = tk.IntVar()
        self.team_id_spinbox = ttk.Spinbox(info_frame, from_=0, to=65535, textvariable=self.team_id_var, width=10)
        self.team_id_spinbox.grid(row=2, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(info_frame, text="(0-65535)", font=('TkDefaultFont', 8)).grid(row=2, column=2, sticky=tk.W)
        
        # Squad Number
        ttk.Label(info_frame, text="Squad #:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.squad_var = tk.IntVar()
        self.squad_spinbox = ttk.Spinbox(info_frame, from_=0, to=255, textvariable=self.squad_var, width=10)
        self.squad_spinbox.grid(row=3, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(info_frame, text="(0-255)", font=('TkDefaultFont', 8)).grid(row=3, column=2, sticky=tk.W)
        
        # Position
        ttk.Label(info_frame, text="Position:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.position_var = tk.StringVar()
        pos_combo = ttk.Combobox(info_frame, textvariable=self.position_var, state='readonly', width=15)
        pos_combo['values'] = ['Goalkeeper', 'Defender', 'Midfielder', 'Forward']
        pos_combo.grid(row=4, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(info_frame, text="✓ Confirmed field", font=('TkDefaultFont', 8), foreground='green').grid(row=4, column=2, sticky=tk.W)
        
        # Nationality (editor uses numeric ID mapping - mapping TBD)
        ttk.Label(info_frame, text="Nationality ID:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.nationality_var = tk.IntVar()
        self.nationality_spinbox = ttk.Spinbox(info_frame, from_=0, to=255, textvariable=self.nationality_var, width=8)
        self.nationality_spinbox.grid(row=5, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(info_frame, text="(ID, mapping TBD)", font=('TkDefaultFont', 8)).grid(row=5, column=2, sticky=tk.W)
        
        # Date of Birth (day/month/year)
        ttk.Label(info_frame, text="DOB:").grid(row=6, column=0, sticky=tk.W, pady=5)
        self.dob_day_var = tk.IntVar()
        self.dob_month_var = tk.IntVar()
        self.dob_year_var = tk.IntVar()
        dob_frame = ttk.Frame(info_frame)
        dob_frame.grid(row=6, column=1, sticky=tk.W, padx=10, pady=5)
        self.dob_day_spinbox = ttk.Spinbox(dob_frame, from_=1, to=31, width=4, textvariable=self.dob_day_var)
        self.dob_day_spinbox.pack(side=tk.LEFT)
        ttk.Label(dob_frame, text="/").pack(side=tk.LEFT)
        self.dob_month_spinbox = ttk.Spinbox(dob_frame, from_=1, to=12, width=4, textvariable=self.dob_month_var)
        self.dob_month_spinbox.pack(side=tk.LEFT)
        ttk.Label(dob_frame, text="/").pack(side=tk.LEFT)
        self.dob_year_spinbox = ttk.Spinbox(dob_frame, from_=1900, to=2100, width=6, textvariable=self.dob_year_var)
        self.dob_year_spinbox.pack(side=tk.LEFT)
        ttk.Label(info_frame, text="(day/month/year)", font=('TkDefaultFont', 8)).grid(row=6, column=2, sticky=tk.W)
        
        # Height
        ttk.Label(info_frame, text="Height (cm):").grid(row=7, column=0, sticky=tk.W, pady=5)
        self.height_var = tk.IntVar()
        self.height_spinbox = ttk.Spinbox(info_frame, from_=50, to=250, textvariable=self.height_var, width=8)
        self.height_spinbox.grid(row=7, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(info_frame, text="cm", font=('TkDefaultFont', 8)).grid(row=7, column=2, sticky=tk.W)

        # Weight (only when the selected record exposes a parser-backed slot)
        ttk.Label(info_frame, text="Weight (kg):").grid(row=8, column=0, sticky=tk.W, pady=5)
        self.weight_var = tk.StringVar()
        self.weight_spinbox = ttk.Spinbox(info_frame, from_=40, to=140, textvariable=self.weight_var, width=8)
        self.weight_spinbox.grid(row=8, column=1, sticky=tk.W, padx=10, pady=5)
        self.weight_hint_var = tk.StringVar(value="(available when parser-backed)")
        ttk.Label(info_frame, textvariable=self.weight_hint_var, font=('TkDefaultFont', 8)).grid(row=8, column=2, sticky=tk.W)

        # Attributes
        attr_frame = ttk.LabelFrame(right_frame, text="Attributes (Candidate Fields - Double-XOR Encoded)", padding="10")
        attr_frame.pack(fill=tk.BOTH, expand=True)
        
        # Scrollable attributes
        canvas = tk.Canvas(attr_frame)
        scrollbar = ttk.Scrollbar(attr_frame, orient=tk.VERTICAL, command=canvas.yview)
        self.attr_container = ttk.Frame(canvas)
        
        self.attr_container.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=self.attr_container, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.attr_vars = []
        
        self.attr_labels = PlayerRecord.attribute_slot_labels()
        self.attr_editable_indices = set(PlayerRecord.editable_attribute_indices())

        # Verified dd6361 visible-skill panel state (separate from legacy generic attributes)
        self.visible_skill_snapshot = None
        self.staged_visible_skill_patches = {}
        self.visible_skill_field_order = [
            "speed", "stamina", "aggression", "quality",
            "handling", "passing", "dribbling", "heading", "tackling", "shooting",
        ]
        self.visible_skill_baseline = {}
        self.visible_skill_vars = {field: tk.IntVar(value=0) for field in self.visible_skill_field_order}
        self.visible_skill_status_var = tk.StringVar(
            value="dd6361 visible skills: authoritative parser-backed panel (not loaded)"
        )

        visible_skill_frame = ttk.LabelFrame(
            right_frame,
            text="Verified Visible Skills (dd6361, Authoritative)",
            padding="10",
        )
        visible_skill_frame.pack(fill=tk.X, pady=(0, 5))

        visible_grid = ttk.Frame(visible_skill_frame)
        visible_grid.pack(fill=tk.X)

        for idx, field in enumerate(self.visible_skill_field_order):
            row = idx // 2
            col_group = idx % 2
            col = col_group * 3
            label = field.replace("_", " ").title()
            ttk.Label(visible_grid, text=label + ":").grid(row=row, column=col, sticky=tk.W, padx=(0, 4), pady=2)
            spin = ttk.Spinbox(visible_grid, from_=0, to=255, textvariable=self.visible_skill_vars[field], width=6)
            spin.grid(row=row, column=col + 1, sticky=tk.W, padx=(0, 10), pady=2)

        visible_btns = ttk.Frame(visible_skill_frame)
        visible_btns.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(
            visible_btns,
            text="Refresh dd6361",
            command=lambda: self.refresh_visible_skill_panel(show_dialog_errors=True),
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            visible_btns,
            text="Stage for Save Database",
            command=self.stage_visible_skill_panel_changes,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            visible_btns,
            text="Discard Staged",
            command=self.discard_visible_skill_panel_staged_changes,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            visible_btns,
            text="Review Staged...",
            command=self.review_staged_visible_skill_patches,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            visible_btns,
            text="Patch Visible Skills (In-Place + Backup)",
            command=self.patch_visible_skill_panel_in_place,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            visible_btns,
            text="Advanced Patch Dialog...",
            command=self.open_player_skill_patch_dialog,
        ).pack(side=tk.LEFT)
        ttk.Label(
            visible_skill_frame,
            textvariable=self.visible_skill_status_var,
            font=("TkDefaultFont", 8),
        ).pack(fill=tk.X, pady=(6, 0))

        # Buttons
        button_frame = ttk.Frame(right_frame, padding="10")
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="💾 Apply Changes", command=self.apply_changes,
                  style='Accent.TButton').pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="🔄 Reset", command=self.reset_current).pack(side=tk.LEFT, padx=5)
 
        # Team overlay panel (hidden by default) - will replace the right-hand editor when the Teams tab is active
        # Parent is the same right_frame used by the player editor; we will place() this overlay to sit on top.
        self.team_overlay = ttk.Frame(right_frame)
        self.team_overlay_active = False
        
        # Team panel variables (overlay)
        self.team_panel_name_var = tk.StringVar()
        self.team_panel_id_var = tk.IntVar()
        self.team_panel_stadium_var = tk.StringVar()
        self.team_panel_capacity_var = tk.IntVar()
        self.team_panel_car_var = tk.IntVar()
        self.team_panel_pitch_var = tk.StringVar()
 
        team_panel = ttk.LabelFrame(self.team_overlay, text="Team Details", padding="10")
        team_panel.pack(fill=tk.X, pady=(0,5))
 
        ttk.Label(team_panel, text="Team Name:", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(team_panel, textvariable=self.team_panel_name_var, width=40).grid(row=0, column=1, columnspan=2, sticky=tk.W, padx=10, pady=5)
 
        ttk.Label(team_panel, text="Team ID:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(team_panel, from_=0, to=65535, textvariable=self.team_panel_id_var, width=10).grid(row=1, column=1, sticky=tk.W, padx=10, pady=5)
 
        ttk.Label(team_panel, text="Stadium:").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Entry(team_panel, textvariable=self.team_panel_stadium_var, width=60).grid(row=2, column=1, columnspan=2, sticky=tk.W, padx=10, pady=5)
 
        ttk.Label(team_panel, text="Capacity:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.team_panel_capacity_spin = ttk.Spinbox(
            team_panel,
            from_=0,
            to=1000000,
            textvariable=self.team_panel_capacity_var,
            width=14,
            state='disabled',
        )
        self.team_panel_capacity_spin.grid(row=3, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(team_panel, text="display-only", font=('TkDefaultFont', 8)).grid(row=3, column=2, sticky=tk.W, pady=5)
 
        ttk.Label(team_panel, text="Car Park:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.team_panel_car_spin = ttk.Spinbox(
            team_panel,
            from_=0,
            to=200000,
            textvariable=self.team_panel_car_var,
            width=14,
            state='disabled',
        )
        self.team_panel_car_spin.grid(row=4, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(team_panel, text="display-only", font=('TkDefaultFont', 8)).grid(row=4, column=2, sticky=tk.W, pady=5)
 
        ttk.Label(team_panel, text="Pitch quality:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.team_panel_pitch_combo = ttk.Combobox(
            team_panel,
            textvariable=self.team_panel_pitch_var,
            state='disabled',
            width=16,
        )
        self.team_panel_pitch_combo['values'] = ['GOOD', 'EXCELLENT', 'AVERAGE', 'POOR', 'UNKNOWN']
        self.team_panel_pitch_combo.grid(row=5, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(team_panel, text="display-only", font=('TkDefaultFont', 8)).grid(row=5, column=2, sticky=tk.W, pady=5)
        ttk.Label(
            team_panel,
            text=TEAM_PANEL_PROVENANCE_TEXT,
            justify=tk.LEFT,
            font=('TkDefaultFont', 8),
            wraplength=520,
        ).grid(row=6, column=0, columnspan=3, sticky=tk.W, pady=(8, 0))
 
        # Roster toggle + frame (collapsible)
        roster_toggle_frame = ttk.Frame(self.team_overlay)
        roster_toggle_frame.pack(fill=tk.X)
        self.team_panel_roster_visible = False
        self.team_panel_roster_toggle_btn = ttk.Button(
            roster_toggle_frame,
            text=TEAM_ROSTER_SHOW_TEXT,
            command=self._toggle_roster,
        )
        self.team_panel_roster_toggle_btn.pack(side=tk.LEFT, padx=5, pady=5)
 
        self.team_panel_roster_frame = ttk.LabelFrame(
            self.team_overlay,
            text="Squad Roster (Authoritative / Partial)",
            padding="5",
        )
        # roster is not packed initially (collapsed)
        ttk.Label(
            self.team_panel_roster_frame,
            text=TEAM_ROSTER_PROVENANCE_TEXT,
            justify=tk.LEFT,
            font=('TkDefaultFont', 8),
            wraplength=720,
        ).pack(fill=tk.X, pady=(0, 4))

        roster_actions = ttk.Frame(self.team_panel_roster_frame)
        roster_actions.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(
            roster_actions,
            text="Edit Selected Slot...",
            command=self.open_selected_team_roster_edit_dialog,
        ).pack(side=tk.LEFT)
        ttk.Button(
            roster_actions,
            text="Refresh Roster",
            command=self.load_current_team_roster,
        ).pack(side=tk.LEFT, padx=(5, 0))

        # Enhanced roster tree with all attributes (PM99 style)
        roster_cols = ('num', 'name', 'en', 'sp', 'st', 'ag', 'qu', 'fi', 'mo', 'av', 'role', 'pos')
        self.team_roster_tree = ttk.Treeview(self.team_panel_roster_frame, columns=roster_cols, show='headings', selectmode='browse', height=20)
        self.team_roster_tree.bind('<Double-1>', self._on_team_roster_double)
        
        # Configure columns with PM99-style headers
        self.team_roster_tree.heading('num', text='N.')
        self.team_roster_tree.heading('name', text='PLAYER')
        self.team_roster_tree.heading('en', text='EN?')  # Unresolved
        self.team_roster_tree.heading('sp', text='SP')  # Speed
        self.team_roster_tree.heading('st', text='ST')  # Stamina
        self.team_roster_tree.heading('ag', text='AG')  # Agility
        self.team_roster_tree.heading('qu', text='QU')  # Quality
        self.team_roster_tree.heading('fi', text='FI?')  # Unresolved
        self.team_roster_tree.heading('mo', text='MO?')  # Unresolved
        self.team_roster_tree.heading('av', text='AV?')  # Unresolved
        self.team_roster_tree.heading('role', text='ROL.?')
        self.team_roster_tree.heading('pos', text='POS?')
        
        # Set column widths
        self.team_roster_tree.column('num', width=35, anchor=tk.CENTER)
        self.team_roster_tree.column('name', width=180, anchor=tk.W)
        self.team_roster_tree.column('en', width=35, anchor=tk.CENTER)
        self.team_roster_tree.column('sp', width=35, anchor=tk.CENTER)
        self.team_roster_tree.column('st', width=35, anchor=tk.CENTER)
        self.team_roster_tree.column('ag', width=35, anchor=tk.CENTER)
        self.team_roster_tree.column('qu', width=35, anchor=tk.CENTER)
        self.team_roster_tree.column('fi', width=35, anchor=tk.CENTER)
        self.team_roster_tree.column('mo', width=35, anchor=tk.CENTER)
        self.team_roster_tree.column('av', width=35, anchor=tk.CENTER)
        self.team_roster_tree.column('role', width=60, anchor=tk.CENTER)
        self.team_roster_tree.column('pos', width=50, anchor=tk.CENTER)
        
        roster_scroll = ttk.Scrollbar(self.team_panel_roster_frame, orient=tk.VERTICAL, command=self.team_roster_tree.yview)
        self.team_roster_tree.configure(yscrollcommand=roster_scroll.set)
        self.team_roster_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        roster_scroll.pack(side=tk.RIGHT, fill=tk.Y)
 
        # Team action buttons (overlay)
        team_btn_frame = ttk.Frame(self.team_overlay, padding="10")
        team_btn_frame.pack(fill=tk.X)
        ttk.Button(team_btn_frame, text="💾 Save Team", command=self.apply_team_changes, style='Accent.TButton').pack(side=tk.LEFT, padx=5)
        ttk.Button(team_btn_frame, text="🔄 Reset Team", command=self.reset_team_editor).pack(side=tk.LEFT, padx=5)
 
        # Start hidden (we use .place() to show/hide so player editor remains intact beneath)
        self.team_overlay.place_forget()
 
        # Coach overlay panel (hidden by default) - will replace the right-hand editor when the Coaches tab is active
        # Parent is the same right_frame used by the player editor; we will place() this overlay to sit on top.
        self.coach_overlay = ttk.Frame(right_frame)
        self.coach_overlay_active = False
 
        # Coach panel variables (overlay)
        self.coach_panel_given_var = tk.StringVar()
        self.coach_panel_surname_var = tk.StringVar()
        self.coach_panel_full_var = tk.StringVar()
 
        coach_panel = ttk.LabelFrame(self.coach_overlay, text="Coach Information", padding="10")
        coach_panel.pack(fill=tk.X, pady=(0,5))
 
        ttk.Label(coach_panel, text="Given Name:", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(coach_panel, textvariable=self.coach_panel_given_var, width=30).grid(row=0, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(coach_panel, text="(max 12 chars)", font=('TkDefaultFont', 8)).grid(row=0, column=2, sticky=tk.W)
 
        ttk.Label(coach_panel, text="Surname:", font=('TkDefaultFont', 10, 'bold')).grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(coach_panel, textvariable=self.coach_panel_surname_var, width=30).grid(row=1, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(coach_panel, text="(max 12 chars)", font=('TkDefaultFont', 8)).grid(row=1, column=2, sticky=tk.W)
 
        ttk.Label(coach_panel, text="Full Name:", font=('TkDefaultFont', 10)).grid(row=2, column=0, sticky=tk.W, pady=5)
        full_name_entry = ttk.Entry(coach_panel, textvariable=self.coach_panel_full_var, width=30, state='readonly')
        full_name_entry.grid(row=2, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(coach_panel, text="(auto-generated)", font=('TkDefaultFont', 8)).grid(row=2, column=2, sticky=tk.W)
 
        # Link given name and surname to update full name
        def update_coach_full_name(*args):
            given = self.coach_panel_given_var.get().strip()
            surname = self.coach_panel_surname_var.get().strip()
            self.coach_panel_full_var.set(f"{given} {surname}".strip())
        
        self.coach_panel_given_var.trace('w', update_coach_full_name)
        self.coach_panel_surname_var.trace('w', update_coach_full_name)
 
        # Coach attributes info frame (placeholder for future attributes)
        coach_attr_frame = ttk.LabelFrame(self.coach_overlay, text="Coach Details", padding="10")
        coach_attr_frame.pack(fill=tk.BOTH, expand=True, pady=(5,0))
 
        info_text = ttk.Label(coach_attr_frame, text="Coach attributes are not yet available in this editor.\nCurrently only name editing is supported.",
                             justify=tk.LEFT, font=('TkDefaultFont', 9))
        info_text.pack(pady=20)
 
        # Coach action buttons (overlay)
        coach_btn_frame = ttk.Frame(self.coach_overlay, padding="10")
        coach_btn_frame.pack(fill=tk.X)
        ttk.Button(coach_btn_frame, text="💾 Save Coach", command=self.apply_coach_changes, style='Accent.TButton').pack(side=tk.LEFT, padx=5)
        ttk.Button(coach_btn_frame, text="🔄 Reset Coach", command=self.reset_coach_editor).pack(side=tk.LEFT, padx=5)
 
        # Start hidden (we use .place() to show/hide so player editor remains intact beneath)
        self.coach_overlay.place_forget()
 
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(side=tk.BOTTOM, fill=tk.X)
 
    def filter_coaches(self, *args):
        """Filter coaches by search string and repopulate coach tree."""
        query = self.coach_search_var.get().strip().lower()
        if not getattr(self, 'coach_records', None):
            self.filtered_coach_records = []
        elif not query:
            self.filtered_coach_records = self.coach_records.copy()
        else:
            out = []
            for o, c in self.coach_records:
                name = getattr(c, 'name', None) or f"{getattr(c, 'given_name', '')} {getattr(c, 'surname', '')}".strip()
                if query in name.lower():
                    out.append((o, c))
            self.filtered_coach_records = out
        try:
            self.populate_coach_tree()
        except Exception:
            pass

    def populate_coach_tree(self):
        """Populate coach tree view from filtered_coach_records."""
        self.coach_tree.delete(*self.coach_tree.get_children())
        for offset, coach in getattr(self, 'filtered_coach_records', []) or []:
            name = getattr(coach, 'name', None) or f"{getattr(coach, 'given_name', '')} {getattr(coach, 'surname', '')}".strip()
            try:
                display_offset = f"0x{offset:08X}"
            except Exception:
                display_offset = str(offset)
            self.coach_tree.insert('', tk.END, values=(name, display_offset), tags=(str(offset),))
        try:
            self.coach_count_label.config(text=f"Coaches: {len(getattr(self, 'filtered_coach_records', []))}")
        except Exception:
            pass

    def on_select_coach(self, event):
        """Handle coach selection from coach tree."""
        sel = self.coach_tree.selection()
        if not sel:
            return
        item = self.coach_tree.item(sel[0])
        try:
            offset = int(item['tags'][0])
        except Exception:
            # Fallback: try parse hex string in values
            try:
                val = item['values'][1]
                offset = int(val, 16) if isinstance(val, str) and val.startswith("0x") else None
            except Exception:
                offset = None
        if offset is None:
            return
        for o, c in getattr(self, 'coach_records', []):
            if o == offset:
                self.current_coach = (o, c)
                self.coach_panel_given_var.set(getattr(c, 'given_name', '') or '')
                self.coach_panel_surname_var.set(getattr(c, 'surname', '') or '')
                full = getattr(c, 'name', '') or f"{getattr(c, 'given_name','') or ''} {getattr(c, 'surname','') or ''}".strip()
                self.coach_panel_full_var.set(full)
                self._show_coach_overlay()
                break

    def _on_coach_double(self, event):
        """Double-click coach => open coach overlay for editing."""
        self.on_select_coach(event)
        self._show_coach_overlay()

    def export_coaches(self):
        """Export coaches to CSV."""
        if not getattr(self, 'coach_records', None):
            messagebox.showinfo("Export Coaches", "No coaches to export")
            return
        filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not filename:
            return
        try:
            import csv
            with open(filename, 'w', newline='', encoding='utf-8') as fh:
                writer = csv.writer(fh)
                writer.writerow(['Offset', 'Given Name', 'Surname', 'Full Name'])
                for offset, coach in self.coach_records:
                    writer.writerow([f"0x{offset:08X}", getattr(coach, 'given_name', ''), getattr(coach, 'surname', ''), getattr(coach, 'name', '')])
            messagebox.showinfo("Export Coaches", f"Exported {len(self.coach_records)} coaches to {filename}")
        except Exception as e:
            messagebox.showerror("Export Coaches", f"Export failed:\n{e}")

    def filter_teams(self, *args):
        """Filter teams by search string and repopulate team tree."""
        query = self.team_search_var.get().strip()
        if not getattr(self, 'team_records', None):
            self.filtered_team_records = []
        elif not query:
            self.filtered_team_records = self.team_records.copy()
        else:
            out = []
            for o, t in self.team_records:
                name = getattr(t, 'name', '') or ''
                full_name = getattr(t, 'full_club_name', '') or ''
                tid = str(getattr(t, 'team_id', ''))
                if (
                    team_query_matches(query, team_name=name, full_club_name=full_name)
                    or query.lower() in tid.lower()
                ):
                    out.append((o, t))
            self.filtered_team_records = out
        try:
            self.populate_team_tree()
        except Exception:
            pass

    def populate_team_tree(self):
        """Populate the team tree view from filtered_team_records."""
        self.team_tree.delete(*self.team_tree.get_children())
        for offset, team in getattr(self, 'filtered_team_records', []) or []:
            name = getattr(team, 'name', '') or ''
            team_id = getattr(team, 'team_id', '')
            try:
                display_offset = f"0x{offset:08X}"
            except Exception:
                display_offset = str(offset)
            self.team_tree.insert('', tk.END, values=(name, team_id, display_offset), tags=(str(offset),))
        try:
            self.team_count_label.config(text=f"Teams: {len(getattr(self, 'filtered_team_records', []))}")
        except Exception:
            pass
    def filter_leagues(self, *args):
        """Filter leagues by the league search box and repopulate the league tree."""
        try:
            query = self.league_search_var.get().strip().lower()
        except Exception:
            query = ""
        # Store last query for possible use by populate_league_tree (non-breaking)
        self._league_search_query = query
        try:
            self.populate_league_tree()
        except Exception:
            # Swallow UI update errors; they will be visible when interacting with the app
            pass

    def on_select_team(self, event):
        """Handle team selection from team tree."""
        sel = self.team_tree.selection()
        if not sel:
            return
        item = self.team_tree.item(sel[0])
        try:
            offset = int(item['tags'][0])
        except Exception:
            try:
                val = item['values'][2]
                offset = int(val, 16) if isinstance(val, str) and val.startswith("0x") else None
            except Exception:
                offset = None
        if offset is None:
            return
        for o, team in getattr(self, 'team_records', []):
            if o == offset:
                self.current_team = (o, team)
                self.team_panel_name_var.set(getattr(team, 'name', '') or '')
                self.team_panel_id_var.set(getattr(team, 'team_id', 0) or 0)
                self.team_panel_stadium_var.set(getattr(team, 'stadium', '') or '')
                self.team_panel_capacity_var.set(getattr(team, 'capacity', 0) or 0)
                self.team_panel_car_var.set(getattr(team, 'car_park', 0) or 0)
                self.team_panel_pitch_var.set(getattr(team, 'pitch_quality', 'UNKNOWN') or 'UNKNOWN')
                # clear roster display
                self.team_roster_tree.delete(*self.team_roster_tree.get_children())
                if getattr(self, 'team_panel_roster_visible', False):
                    self.load_current_team_roster()
                self._show_team_overlay()
                break

    def _on_team_double(self, event):
        """Double-click team => open team overlay."""
        self.on_select_team(event)
        self._show_team_overlay()

    def export_teams(self):
        """Export teams to CSV."""
        if not getattr(self, 'team_records', None):
            messagebox.showinfo("Export Teams", "No teams to export")
            return
        filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not filename:
            return
        try:
            import csv
            with open(filename, 'w', newline='', encoding='utf-8') as fh:
                writer = csv.writer(fh)
                writer.writerow(['Offset', 'Team ID', 'Team Name', 'Stadium', 'Capacity'])
                for offset, team in self.team_records:
                    writer.writerow([f"0x{offset:08X}", getattr(team, 'team_id', ''), getattr(team, 'name', ''), getattr(team, 'stadium', ''), getattr(team, 'capacity', '')])
            messagebox.showinfo("Export Teams", f"Exported {len(self.team_records)} teams to {filename}")
        except Exception as e:
            messagebox.showerror("Export Teams", f"Export failed:\n{e}")

    def on_select_league(self, event):
        """Handle selection in league tree (basic placeholder)."""
        sel = self.league_tree.selection()
        if not sel:
            return
        item = self.league_tree.item(sel[0])
        # Simple feedback: show selected node text
        text = item.get('text') or (item.get('values') or [''])[0]
        self.status_var.set(f"Selected: {text}")

    def on_league_doubleclick(self, event):
        """Double-click league node - placeholder action."""
        self.on_select_league(event)
        messagebox.showinfo("League", "Double-clicked league/team node (placeholder)")

    def _toggle_roster(self):
        """Show/hide the team roster frame in the team overlay."""
        try:
            if self.team_panel_roster_visible:
                self.team_panel_roster_frame.pack_forget()
                self.team_panel_roster_visible = False
                self.team_panel_roster_toggle_btn.config(text=TEAM_ROSTER_SHOW_TEXT)
            else:
                self.team_panel_roster_frame.pack(fill=tk.BOTH, expand=True)
                self.team_panel_roster_visible = True
                self.team_panel_roster_toggle_btn.config(text=TEAM_ROSTER_HIDE_TEXT)
                self.load_current_team_roster()
        except Exception:
            pass

    @staticmethod
    def _unresolved_roster_values():
        return (TEAM_ROSTER_UNRESOLVED_VALUE,) * 6

    def _resolve_team_roster_player_file(self):
        """Return the player file used for roster lookups, preferring the active JUG file."""
        player_file = getattr(self, 'file_path', '') or 'DBDAT/JUG98030.FDI'
        try:
            if Path(str(player_file)).name.upper().startswith("JUG") is False:
                player_file = 'DBDAT/JUG98030.FDI'
        except Exception:
            player_file = 'DBDAT/JUG98030.FDI'
        return str(player_file)

    def _on_team_roster_double(self, _event):
        """Double-click a roster row to open the safe selected-slot editor."""
        self.open_selected_team_roster_edit_dialog()

    def load_current_team_roster(self):
        """Populate the team roster overlay using authoritative EQ roster extraction."""
        tree = getattr(self, 'team_roster_tree', None)
        if tree is None:
            return
        self.team_roster_row_meta = {}
        try:
            tree.delete(*tree.get_children())
        except Exception:
            pass
        current_team = getattr(self, 'current_team', None)
        if not current_team:
            return

        _offset, team = current_team
        team_name = str(getattr(team, 'name', '') or '').strip()
        if not team_name:
            return

        player_file = PM99DatabaseEditor._resolve_team_roster_player_file(self)

        try:
            linked = extract_team_rosters_eq_jug_linked(
                team_file=str(getattr(self, 'team_file_path', 'DBDAT/EQ98030.FDI') or 'DBDAT/EQ98030.FDI'),
                player_file=str(player_file),
                team_queries=[team_name],
            )
        except Exception:
            linked = []

        cache_by_file = getattr(self, '_dd6361_pid_stat_cache', None)
        if not isinstance(cache_by_file, dict):
            cache_by_file = {}
        pid_stat_index = cache_by_file.get(str(player_file))
        if pid_stat_index is None:
            try:
                pid_stat_index = build_player_visible_skill_index_dd6361(file_path=str(player_file))
            except Exception:
                pid_stat_index = {}
            cache_by_file[str(player_file)] = pid_stat_index
            self._dd6361_pid_stat_cache = cache_by_file

        if linked:
            item = linked[0]
            rows = list(item.get("rows") or [])
            visible_rows = 0
            for row in rows:
                pid = int(row.get("pid", 0) or 0)
                parser_name = str(row.get("player_name") or "").strip()
                stats_entry = dict((pid_stat_index or {}).get(pid) or {})
                resolved_name = str(stats_entry.get("resolved_bio_name") or "").strip()
                display_label = parser_name or resolved_name
                display_name = f"{display_label} [pid {pid}]" if display_label else f"PID {pid} (name unresolved)"
                sp = st = ag = qu = ""
                if stats_entry:
                    mapped10 = dict(stats_entry.get("mapped10") or {})
                    sp = mapped10.get("speed", "")
                    st = mapped10.get("stamina", "")
                    ag = mapped10.get("aggression", "")
                    qu = mapped10.get("quality", "")
                en, fi, mo, av, role, pos = PM99DatabaseEditor._unresolved_roster_values()
                visible_rows += 1
                item_id = tree.insert(
                    '',
                    tk.END,
                    values=(visible_rows, display_name, en, sp, st, ag, qu, fi, mo, av, role, pos),
                )
                self.team_roster_row_meta[str(item_id)] = {
                    "mode": "linked",
                    "team_query": str(item.get("team_name") or team_name),
                    "team_name": str(item.get("team_name") or team_name),
                    "full_club_name": str(item.get("full_club_name") or ""),
                    "slot_number": int(row.get("slot_index", 0) or 0) + 1,
                    "current_pid": pid,
                    "current_flag": int(row.get("flag", 0) or 0),
                }
            self.status_var.set(
                f"Loaded parser-backed EQ->JUG roster rows for {team_name}: {visible_rows}{TEAM_ROSTER_STATUS_SUFFIX}"
            )
            return

        try:
            supported_same_entry_provenances = {"same_entry_authoritative", "known_lineup_anchor_assisted"}
            result = extract_team_rosters_eq_same_entry_overlap(
                team_file=str(getattr(self, 'team_file_path', 'DBDAT/EQ98030.FDI') or 'DBDAT/EQ98030.FDI'),
                player_file=str(player_file),
                team_queries=[team_name],
                top_examples=5,
                include_fallbacks=True,
            )
        except Exception as exc:
            self.status_var.set(f"Team roster load failed: {exc}")
            return

        requested = list(getattr(result, 'requested_team_results', []) or [])
        item = requested[0] if requested else {}
        preferred = dict(item.get("preferred_roster_match") or {})
        preferred_provenance = str(preferred.get("provenance") or "")
        if preferred_provenance not in supported_same_entry_provenances:
            self.status_var.set(f"No supported same-entry overlay mapping yet for {team_name}")
            return

        rows = list(preferred.get("rows") or [])
        visible_rows = 0
        for row in rows:
            if row.get("is_empty_slot"):
                continue
            pid = int(row.get("pid_candidate", 0) or 0)
            dd_name = str(row.get("dd6361_name") or "").strip()
            stats_entry = dict((pid_stat_index or {}).get(pid) or {})
            resolved_name = str(stats_entry.get("resolved_bio_name") or "").strip()
            display_label = dd_name or resolved_name
            display_name = f"{display_label} [pid {pid}]" if display_label else f"PID {pid} (name unresolved)"
            sp = st = ag = qu = ""
            if stats_entry:
                mapped10 = dict(stats_entry.get("mapped10") or {})
                sp = mapped10.get("speed", "")
                st = mapped10.get("stamina", "")
                ag = mapped10.get("aggression", "")
                qu = mapped10.get("quality", "")
            en, fi, mo, av, role, pos = PM99DatabaseEditor._unresolved_roster_values()
            visible_rows += 1
            item_id = tree.insert(
                '',
                tk.END,
                values=(visible_rows, display_name, en, sp, st, ag, qu, fi, mo, av, role, pos),
            )
            self.team_roster_row_meta[str(item_id)] = {
                "mode": "same_entry",
                "team_query": str(item.get("team_name") or team_name),
                "team_name": str(item.get("team_name") or team_name),
                "full_club_name": str(item.get("full_club_name") or ""),
                "team_offset": int(item.get("team_offset", 0) or 0),
                "slot_number": visible_rows,
                "current_pid": pid,
                "same_entry_provenance": preferred_provenance,
            }
        provenance_suffix = f" [{preferred_provenance}]" if preferred_provenance else ""
        self.status_var.set(
            f"Loaded supported same-entry roster rows for {team_name}: {visible_rows}{TEAM_ROSTER_STATUS_SUFFIX}{provenance_suffix}"
        )

    def open_selected_team_roster_edit_dialog(self):
        """Edit the selected authoritative roster row from the team overlay."""
        tree = getattr(self, "team_roster_tree", None)
        if tree is None:
            return
        selection = list(tree.selection() or [])
        if not selection:
            messagebox.showinfo("Edit Selected Team Roster Slot", "Select a roster row first.")
            return

        item_id = str(selection[0])
        row_meta = dict((getattr(self, "team_roster_row_meta", {}) or {}).get(item_id) or {})
        if not row_meta:
            messagebox.showinfo(
                "Edit Selected Team Roster Slot",
                "The selected row does not have an authoritative writable mapping.",
            )
            return

        item = tree.item(item_id)
        values = list(item.get("values") or [])
        row_label = str(values[1] if len(values) > 1 else row_meta.get("team_name") or "").strip()
        mode = str(row_meta.get("mode") or "").strip()
        team_file = getattr(self, "team_file_path", None) or "DBDAT/EQ98030.FDI"
        player_file = PM99DatabaseEditor._resolve_team_roster_player_file(self)
        team_query = str(row_meta.get("team_query") or row_meta.get("team_name") or "").strip()
        slot_number = int(row_meta.get("slot_number", 0) or 0)
        if not team_query or slot_number < 1:
            messagebox.showinfo(
                "Edit Selected Team Roster Slot",
                "The selected row is missing required team roster metadata.",
            )
            return

        try:
            if mode == "linked":
                current_pid = int(row_meta.get("current_pid", 0) or 0)
                current_flag = int(row_meta.get("current_flag", 0) or 0)
                player_id_text = simpledialog.askstring(
                    "Edit Selected Team Roster Slot",
                    "Player record ID:",
                    initialvalue=str(current_pid),
                )
                if player_id_text is None:
                    return
                flag_text = simpledialog.askstring(
                    "Edit Selected Team Roster Slot",
                    "Flag byte:",
                    initialvalue=str(current_flag),
                )
                if flag_text is None:
                    return
                player_record_id = int(str(player_id_text).strip() or current_pid, 0)
                flag = int(str(flag_text).strip() or current_flag, 0)
                if player_record_id == current_pid and flag == current_flag:
                    messagebox.showinfo("Edit Selected Team Roster Slot", "No changes requested.")
                    return

                dry_run = messagebox.askyesno(
                    "Edit Selected Team Roster Slot",
                    (
                        f"Patch linked roster row:\n{row_label or team_query}\n\n"
                        "Run in dry-run mode?\n\n"
                        "Yes = validate and stage only\n"
                        "No = write changes immediately"
                    ),
                )
                self.status_var.set("Running selected linked team roster edit...")
                self.root.update_idletasks()
                result = edit_team_roster_eq_jug_linked(
                    team_file=team_file,
                    player_file=player_file,
                    team_query=team_query,
                    slot_number=slot_number,
                    player_record_id=player_record_id,
                    flag=flag,
                    write_changes=not dry_run,
                )
                if not dry_run and getattr(result, "applied_to_disk", False):
                    self.load_current_team_roster()

                warning_count = len(getattr(result, "warnings", []) or [])
                status_suffix = "dry-run " if dry_run else ""
                self.status_var.set(
                    f"✓ Selected linked roster edit {status_suffix}complete "
                    f"({len(getattr(result, 'changes', []) or [])} changed, {warning_count} warning(s))"
                )
                summary_lines = [
                    f"{'Dry run complete' if dry_run else 'Linked roster edit complete'}",
                    "",
                    f"Row: {row_label or team_query}",
                    f"Slot: {slot_number}",
                    f"Rows changed: {len(getattr(result, 'changes', []) or [])}",
                    f"Warnings: {warning_count}",
                ]
                if getattr(result, "changes", None):
                    change = result.changes[0]
                    summary_lines.extend(
                        [
                            "",
                            f"{getattr(change, 'team_name', '') or team_query}: "
                            f"pid {getattr(change, 'old_player_record_id', '')} -> {getattr(change, 'new_player_record_id', '')}, "
                            f"flag {getattr(change, 'old_flag', '')} -> {getattr(change, 'new_flag', '')}",
                        ]
                    )
                backup_path = getattr(result, "backup_path", None)
                if backup_path:
                    summary_lines.append(f"Backup: {backup_path}")
                if warning_count and getattr(result, "warnings", None):
                    summary_lines.extend(
                        [
                            "",
                            "First warning:",
                            str(getattr(result.warnings[0], "message", result.warnings[0])),
                        ]
                    )
                messagebox.showinfo("Edit Selected Team Roster Slot", "\n".join(summary_lines))
                return

            if mode == "same_entry":
                current_pid = int(row_meta.get("current_pid", 0) or 0)
                team_offset = int(row_meta.get("team_offset", 0) or 0)
                pid_text = simpledialog.askstring(
                    "Edit Selected Team Roster Slot",
                    "Player ID (16-bit same-entry PID):",
                    initialvalue=str(current_pid),
                )
                if pid_text is None:
                    return
                new_pid = int(str(pid_text).strip() or current_pid, 0)
                if new_pid == current_pid:
                    messagebox.showinfo("Edit Selected Team Roster Slot", "No changes requested.")
                    return

                dry_run = messagebox.askyesno(
                    "Edit Selected Team Roster Slot",
                    (
                        f"Patch same-entry roster row:\n{row_label or team_query}\n\n"
                        "Run in dry-run mode?\n\n"
                        "Yes = validate and stage only\n"
                        "No = write changes immediately"
                    ),
                )
                self.status_var.set("Running selected same-entry team roster edit...")
                self.root.update_idletasks()
                result = edit_team_roster_same_entry_authoritative(
                    team_file=team_file,
                    player_file=player_file,
                    team_query=team_query,
                    team_offset=team_offset,
                    slot_number=slot_number,
                    pid_candidate=new_pid,
                    write_changes=not dry_run,
                )
                if not dry_run and getattr(result, "applied_to_disk", False):
                    self.load_current_team_roster()

                warning_count = len(getattr(result, "warnings", []) or [])
                status_suffix = "dry-run " if dry_run else ""
                self.status_var.set(
                    f"✓ Selected same-entry roster edit {status_suffix}complete "
                    f"({len(getattr(result, 'changes', []) or [])} changed, {warning_count} warning(s))"
                )
                summary_lines = [
                    f"{'Dry run complete' if dry_run else 'Same-entry roster edit complete'}",
                    "",
                    f"Row: {row_label or team_query}",
                    f"Slot: {slot_number}",
                    f"Rows changed: {len(getattr(result, 'changes', []) or [])}",
                    f"Warnings: {warning_count}",
                ]
                if getattr(result, "changes", None):
                    change = result.changes[0]
                    provenance = str(getattr(change, "provenance", "") or row_meta.get("same_entry_provenance") or "")
                    provenance_suffix = f" [{provenance}]" if provenance else ""
                    tail_suffix = (
                        f" (preserved tail={getattr(change, 'preserved_tail_bytes_hex', '')})"
                        if str(getattr(change, "preserved_tail_bytes_hex", "") or "")
                        else ""
                    )
                    summary_lines.extend(
                        [
                            "",
                            f"{getattr(change, 'team_name', '') or team_query}: "
                            f"pid {getattr(change, 'old_pid_candidate', '')} -> {getattr(change, 'new_pid_candidate', '')}{provenance_suffix}{tail_suffix}",
                        ]
                    )
                backup_path = getattr(result, "backup_path", None)
                if backup_path:
                    summary_lines.append(f"Backup: {backup_path}")
                if warning_count and getattr(result, "warnings", None):
                    summary_lines.extend(
                        [
                            "",
                            "First warning:",
                            str(getattr(result.warnings[0], "message", result.warnings[0])),
                        ]
                    )
                messagebox.showinfo("Edit Selected Team Roster Slot", "\n".join(summary_lines))
                return

            messagebox.showinfo(
                "Edit Selected Team Roster Slot",
                f"The selected roster source is not writable yet ({mode or 'unknown'}).",
            )
        except Exception as exc:
            self.status_var.set("Selected team roster edit failed")
            messagebox.showerror("Edit Selected Team Roster Slot", f"Selected team roster edit failed:\n{exc}")

    def apply_team_changes(self):
        """Apply/stage team name edits using shared editor actions."""
        if not getattr(self, 'current_team', None):
            return
        offset, team = self.current_team
        try:
            # If this record is already staged, mutate the in-memory staged object directly
            # so repeated edits before Save do not reload stale on-disk state.
            if offset in self.modified_team_records:
                staged_team = self.modified_team_records[offset]
                change_lines = []
                new_name = self.team_panel_name_var.get().strip()
                new_stadium = self.team_panel_stadium_var.get().strip()
                if new_name and new_name != (getattr(staged_team, 'name', '') or '') and hasattr(staged_team, 'set_name'):
                    old_name = getattr(staged_team, 'name', '') or ''
                    staged_team.set_name(new_name)
                    change_lines.append(f"Team: {old_name} -> {getattr(staged_team, 'name', '') or new_name}")
                if new_stadium != (getattr(staged_team, 'stadium', '') or '') and hasattr(staged_team, 'set_stadium_name'):
                    old_stadium = getattr(staged_team, 'stadium', '') or ''
                    staged_team.set_stadium_name(new_stadium)
                    change_lines.append(f"Stadium: {old_stadium} -> {getattr(staged_team, 'stadium', '') or new_stadium}")
                try:
                    new_team_id = int(self.team_panel_id_var.get() or 0)
                except Exception:
                    new_team_id = getattr(staged_team, 'team_id', 0)
                if new_team_id != getattr(staged_team, 'team_id', 0) and hasattr(staged_team, 'set_team_id'):
                    staged_team.set_team_id(new_team_id)
                    change_lines.append(f"Team ID -> {new_team_id}")
                if not change_lines:
                    messagebox.showinfo("Team Editor", "No changes to apply")
                    return
                team = staged_team
                self.current_team = (offset, staged_team)
                for record_list_name in ('team_records', 'filtered_team_records'):
                    record_list = getattr(self, record_list_name, None) or []
                    for idx, (o, rec) in enumerate(record_list):
                        if o == offset:
                            record_list[idx] = (offset, staged_team)
                            break
                try:
                    self.build_team_lookup()
                    self.populate_tree()
                    self.populate_team_tree()
                except Exception:
                    pass
                self.status_var.set("✓ Team changes staged (save to persist)")
                messagebox.showinfo(
                    "Team Editor",
                    "Team changes staged. Use Save Database to persist.\n\n" + "\n".join(change_lines[:10]),
                )
                return

            old_name = getattr(team, 'name', '') or ''
            old_stadium = getattr(team, 'stadium', '') or ''
            new_name = self.team_panel_name_var.get().strip()
            new_stadium = self.team_panel_stadium_var.get().strip()

            result = rename_team_records(
                self.team_file_path,
                old_name,
                new_name or old_name,
                old_stadium=old_stadium if old_stadium else None,
                new_stadium=(new_stadium if new_stadium != old_stadium else None),
                include_uncertain=True,
                target_offsets=[offset],
                write_changes=False,
            )

            staged_team = team
            change_lines = []
            if result.staged_records:
                staged_team = result.staged_records[0][1]
                for change in result.changes:
                    if change.name_change and change.name_change[0] != change.name_change[1]:
                        change_lines.append(f"Team: {change.name_change[0]} -> {change.name_change[1]}")
                    if change.stadium_change and change.stadium_change[0] != change.stadium_change[1]:
                        change_lines.append(f"Stadium: {change.stadium_change[0]} -> {change.stadium_change[1]}")

            # Preserve direct Team ID edits in the staged record.
            try:
                new_team_id = int(self.team_panel_id_var.get() or 0)
            except Exception:
                new_team_id = getattr(staged_team, 'team_id', 0)
            if new_team_id != getattr(staged_team, 'team_id', 0) and hasattr(staged_team, 'set_team_id'):
                staged_team.set_team_id(new_team_id)
                change_lines.append(f"Team ID -> {new_team_id}")

            if not change_lines:
                messagebox.showinfo("Team Editor", "No changes to apply")
                return

            self.modified_team_records[offset] = staged_team
            self.current_team = (offset, staged_team)

            for record_list_name in ('team_records', 'filtered_team_records'):
                record_list = getattr(self, record_list_name, None) or []
                for idx, (o, rec) in enumerate(record_list):
                    if o == offset:
                        record_list[idx] = (offset, staged_team)
                        break

            try:
                self.build_team_lookup()
                self.populate_tree()
                self.populate_team_tree()
                self.team_panel_name_var.set(getattr(staged_team, 'name', '') or '')
                self.team_panel_stadium_var.set(getattr(staged_team, 'stadium', '') or '')
            except Exception:
                pass

            self.status_var.set("✓ Team changes staged (save to persist)")
            messagebox.showinfo(
                "Team Editor",
                "Team changes staged. Use Save Database to persist.\n\n" + "\n".join(change_lines[:10]),
            )
        except Exception as e:
            messagebox.showerror("Team Editor", f"Failed to apply team changes: {e}")

    def reset_team_editor(self):
        """Reset team editor overlay to original team values."""
        if getattr(self, 'current_team', None):
            self.team_panel_name_var.set(getattr(self.current_team[1], 'name', '') or '')
            self.team_panel_id_var.set(getattr(self.current_team[1], 'team_id', 0) or 0)
            self.team_panel_stadium_var.set(getattr(self.current_team[1], 'stadium', '') or '')
            self.team_panel_capacity_var.set(getattr(self.current_team[1], 'capacity', 0) or 0)
            self.team_panel_car_var.set(getattr(self.current_team[1], 'car_park', 0) or 0)
            self.team_panel_pitch_var.set(getattr(self.current_team[1], 'pitch_quality', 'UNKNOWN') or 'UNKNOWN')
            self.status_var.set("Team editor reset to original values")

    def apply_coach_changes(self):
        """Apply/stage coach name edits using shared editor actions."""
        if not getattr(self, 'current_coach', None):
            return
        offset, coach = self.current_coach
        try:
            if offset in self.modified_coach_records:
                staged_coach = self.modified_coach_records[offset]
                new_given = self.coach_panel_given_var.get().strip()
                new_surname = self.coach_panel_surname_var.get().strip()
                old_full = (
                    getattr(staged_coach, 'full_name', None)
                    or getattr(staged_coach, 'name', None)
                    or f"{getattr(staged_coach, 'given_name', '')} {getattr(staged_coach, 'surname', '')}".strip()
                )
                new_full = f"{new_given} {new_surname}".strip()
                if new_full == old_full:
                    messagebox.showinfo("Coach Editor", "No changes to apply")
                    return
                if hasattr(staged_coach, 'set_name'):
                    staged_coach.set_name(new_given, new_surname)
                else:
                    setattr(staged_coach, 'given_name', new_given)
                    setattr(staged_coach, 'surname', new_surname)
                    setattr(staged_coach, 'full_name', new_full)
                self.current_coach = (offset, staged_coach)
                for record_list_name in ('coach_records', 'filtered_coach_records'):
                    record_list = getattr(self, record_list_name, None) or []
                    for idx, (o, rec) in enumerate(record_list):
                        if o == offset:
                            record_list[idx] = (offset, staged_coach)
                            break
                try:
                    self.populate_coach_tree()
                except Exception:
                    pass
                self.coach_panel_full_var.set(
                    getattr(staged_coach, 'full_name', None)
                    or getattr(staged_coach, 'name', None)
                    or new_full
                )
                self.status_var.set("✓ Coach changes staged (save to persist)")
                messagebox.showinfo("Coach Editor", "Coach changes staged. Use Save Database to persist.")
                return

            old_name = (
                getattr(coach, 'full_name', None)
                or getattr(coach, 'name', None)
                or f"{getattr(coach, 'given_name', '')} {getattr(coach, 'surname', '')}".strip()
            )
            new_name = f"{self.coach_panel_given_var.get().strip()} {self.coach_panel_surname_var.get().strip()}".strip()
            result = rename_coach_records(
                self.coach_file_path,
                old_name,
                new_name,
                include_uncertain=True,
                target_offset=offset,
                write_changes=False,
            )
            if not result.staged_records:
                messagebox.showinfo("Coach Editor", "No changes to apply")
                return

            staged_coach = result.staged_records[0][1]
            self.modified_coach_records[offset] = staged_coach
            self.current_coach = (offset, staged_coach)
            for record_list_name in ('coach_records', 'filtered_coach_records'):
                record_list = getattr(self, record_list_name, None) or []
                for idx, (o, rec) in enumerate(record_list):
                    if o == offset:
                        record_list[idx] = (offset, staged_coach)
                        break
            try:
                self.populate_coach_tree()
            except Exception:
                pass
            full = (
                getattr(staged_coach, 'full_name', None)
                or getattr(staged_coach, 'name', None)
                or f"{getattr(staged_coach, 'given_name', '')} {getattr(staged_coach, 'surname', '')}".strip()
            )
            self.coach_panel_full_var.set(full)
            self.status_var.set("✓ Coach changes staged (save to persist)")
            messagebox.showinfo("Coach Editor", "Coach changes staged. Use Save Database to persist.")
        except Exception as e:
            messagebox.showerror("Coach Editor", f"Failed to apply coach changes: {e}")

    def reset_coach_editor(self):
        """Reset coach editor overlay to original values."""
        if getattr(self, 'current_coach', None):
            self.coach_panel_given_var.set(getattr(self.current_coach[1], 'given_name', '') or '')
            self.coach_panel_surname_var.set(getattr(self.current_coach[1], 'surname', '') or '')
            self.coach_panel_full_var.set(getattr(self.current_coach[1], 'name', '') or '')
            self.status_var.set("Coach editor reset to original values")

    def _show_team_overlay(self):
        """Show the team overlay UI on the editor pane."""
        try:
            if not self.team_overlay_active:
                self.team_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
                self.team_overlay_active = True
        except Exception:
            pass

    def _hide_team_overlay(self):
        """Hide the team overlay UI."""
        try:
            if self.team_overlay_active:
                self.team_overlay.place_forget()
                self.team_overlay_active = False
        except Exception:
            pass

    def _show_coach_overlay(self):
        """Show the coach overlay UI."""
        try:
            if not self.coach_overlay_active:
                self.coach_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
                self.coach_overlay_active = True
        except Exception:
            pass

    def _hide_coach_overlay(self):
        """Hide the coach overlay UI."""
        try:
            if self.coach_overlay_active:
                self.coach_overlay.place_forget()
                self.coach_overlay_active = False
        except Exception:
            pass

    def _clear_coach_overlay(self):
        """Clear coach overlay fields and hide it."""
        try:
            self.coach_panel_given_var.set('')
            self.coach_panel_surname_var.set('')
            self.coach_panel_full_var.set('')
            self._hide_coach_overlay()
        except Exception:
            pass

    def load_coaches(self):
        """Lazy-load coach records (called when switching to Coaches tab)."""
        try:
            self.status_var.set("Loading coaches...")
            self.root.update_idletasks()
            parsed = load_coaches(self.coach_file_path)
            self.coach_records = parsed
            self.coaches_loaded = True
            self.filtered_coach_records = self.coach_records.copy()
            self.populate_coach_tree()
            self.coach_count_label.config(text=f"Coaches: {len(self.coach_records)}")
            self.status_var.set("Coaches loaded")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load coaches:\n{e}")
            self.status_var.set("Error loading coaches")

    def build_team_lookup(self):
        """Build team id -> name mapping for displaying team names in player list."""
        self.team_lookup = {}
        self.team_alias_lookup = {}
        try:
            for offset, t in getattr(self, 'team_records', []):
                tid = getattr(t, 'team_id', None)
                if tid is not None:
                    team_id = int(tid)
                    short_name = str(getattr(t, 'name', '') or '')
                    full_club_name = str(getattr(t, 'full_club_name', '') or '')
                    self.team_lookup[team_id] = short_name
                    self.team_alias_lookup[team_id] = (short_name, full_club_name)
        except Exception:
            self.team_lookup = {}
            self.team_alias_lookup = {}

    def populate_league_tree(self):
        """Populate a simple leagues/teams hierarchy for the Leagues tab."""
        self.league_tree.delete(*self.league_tree.get_children())
        country = self.league_country_var.get()
        for offset, team in getattr(self, 'team_records', []):
            team_country = getattr(team, 'country', 'Unknown')
            if country != "All" and team_country != country:
                continue
            node = self.league_tree.insert('', tk.END, text=getattr(team, 'name', ''), values=(getattr(team, 'team_id', ''), getattr(team, 'stadium', ''), getattr(team, 'capacity', '')))
        try:
            self.league_count_label.config(text=f"Leagues: {len(self.team_records)}")
        except Exception:
            pass

    def _format_bulk_summary_lines(self, result):
        lines = []
        for file_result in getattr(result, 'file_results', [])[:12]:
            changed = getattr(file_result, 'changed_players', 0)
            total = getattr(file_result, 'total_players', 0)
            rows = getattr(file_result, 'rows_written', 0)
            lines.append(f"{file_result.file}: changed={changed}, total={total}, rows={rows}")
        extra = len(getattr(result, 'file_results', [])) - len(lines)
        if extra > 0:
            lines.append(f"... and {extra} more file(s)")
        return lines

    @staticmethod
    def _parse_optional_dialog_int(value):
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return int(text, 0)

    @staticmethod
    def _format_profile_count_summary(entries, *, label: str, limit: int = 4):
        summary_parts = []
        for raw_value, raw_count in list(entries or [])[: max(1, int(limit or 4))]:
            summary_parts.append(f"{label}={raw_value}({raw_count})")
        return ", ".join(summary_parts)

    @staticmethod
    def _format_post_weight_group_cluster_summary(entries, *, limit: int = 3, per_cluster_limit: int = 4):
        summary_parts = []
        for cluster in list(entries or [])[: max(1, int(limit or 3))]:
            post_weight_value = getattr(cluster, "post_weight_byte", None)
            total_count = int(getattr(cluster, "total_count", 0) or 0)
            nationality_counts = list(getattr(cluster, "nationality_counts", []) or [])[: max(1, int(per_cluster_limit or 4))]
            nationality_text = ", ".join(
                f"nat={nat_value}({count})" for nat_value, count in nationality_counts
            )
            if nationality_text:
                summary_parts.append(f"postwt={post_weight_value}[{total_count}]: {nationality_text}")
            else:
                summary_parts.append(f"postwt={post_weight_value}[{total_count}]")
        return "; ".join(summary_parts)

    @staticmethod
    def _player_suffix_pair_hint(indexed_unknown_9, indexed_unknown_10):
        tone_hint_map = {
            1: "light-skin?",
            2: "medium/dark-skin?",
            3: "dark-skin?",
        }
        hair_hint_map = {
            1: "fair/blond?",
            3: "black/very-dark?",
            5: "red/auburn?",
            6: "brown/dark-brown?",
        }
        tone_hint = tone_hint_map.get(indexed_unknown_9)
        hair_hint = hair_hint_map.get(indexed_unknown_10)
        if tone_hint and hair_hint:
            return f"{tone_hint}+{hair_hint}"
        if tone_hint:
            return tone_hint
        if hair_hint:
            return hair_hint
        return ""

    @staticmethod
    def _player_u1_display_hint(indexed_unknown_1):
        hint_map = {
            0: "ui-grey",
            1: "ui-green",
            2: "ui-red",
            4: "ui-green(alias)",
        }
        return hint_map.get(indexed_unknown_1, "")

    @staticmethod
    def _player_leading_guard_hint(indexed_unknown_0, indexed_unknown_1):
        parts = []
        if isinstance(indexed_unknown_0, int) and indexed_unknown_0 >= 0x62:
            parts.append("u0-reserved?")
        if indexed_unknown_1 == 3:
            parts.append("u1-excluded?")
        return "+".join(parts)

    def _show_text_report_dialog(self, title, body, *, width: int = 112, height: int = 30):
        """Show a scrollable read-only text report in a modal-ish toplevel."""
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        try:
            dialog.transient(self.root)
        except Exception:
            pass
        dialog.geometry("980x640")

        outer = ttk.Frame(dialog, padding="8")
        outer.pack(fill=tk.BOTH, expand=True)

        text_frame = ttk.Frame(outer)
        text_frame.pack(fill=tk.BOTH, expand=True)

        text_widget = tk.Text(text_frame, wrap=tk.NONE, width=width, height=height)
        y_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
        x_scroll = ttk.Scrollbar(outer, orient=tk.HORIZONTAL, command=text_widget.xview)
        text_widget.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        x_scroll.pack(fill=tk.X, pady=(6, 0))

        text_widget.insert("1.0", body if str(body or "").strip() else "(no data)")
        text_widget.configure(state=tk.DISABLED)

        btn_row = ttk.Frame(outer)
        btn_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btn_row, text="Close", command=dialog.destroy).pack(side=tk.RIGHT)

    def _start_analysis_notebook(self, title):
        """Prepare the persistent Analysis tab for a new structured report."""
        host = getattr(self, "analysis_report_container", None)
        if host is None:
            return None
        try:
            for child in list(host.winfo_children()):
                try:
                    child.destroy()
                except Exception:
                    pass
        except Exception:
            return None
        try:
            self.analysis_report_title_var.set(str(title or "Analysis"))
        except Exception:
            pass
        try:
            self.analysis_report_hint_var.set(
                "Showing the latest confirmed parser-backed inspection output."
            )
        except Exception:
            pass
        try:
            notebook = ttk.Notebook(host)
            notebook.pack(fill=tk.BOTH, expand=True)
        except Exception:
            return None
        try:
            main_notebook = getattr(self, "notebook", None)
            analysis_tab = getattr(self, "analysis_tab", None)
            if main_notebook is not None and analysis_tab is not None:
                main_notebook.select(analysis_tab)
        except Exception:
            pass
        return notebook

    def _add_report_tree(self, parent, *, columns, headings, rows, empty_message, widths=None):
        """Render a simple scrollable tree report inside `parent`."""
        frame = ttk.Frame(parent, padding="8")
        frame.pack(fill=tk.BOTH, expand=True)

        if not list(rows or []):
            ttk.Label(frame, text=empty_message, justify=tk.LEFT, wraplength=720).pack(
                fill=tk.BOTH,
                expand=True,
                anchor=tk.W,
            )
            return

        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        tree = ttk.Treeview(tree_frame, columns=tuple(columns), show="headings", selectmode="browse")
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        y_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        x_scroll = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=tree.xview)
        x_scroll.pack(fill=tk.X, pady=(6, 0))
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        width_map = dict(widths or {})
        for column in columns:
            heading = str(dict(headings or {}).get(column, column))
            tree.heading(column, text=heading)
            anchor = tk.W if width_map.get(column, 120) >= 120 else tk.CENTER
            tree.column(column, width=int(width_map.get(column, 120)), anchor=anchor)

        for row in list(rows or []):
            tree.insert("", tk.END, values=tuple(row))

    def _show_team_roster_sources_dialog_view(
        self,
        *,
        team_file,
        player_file,
        team_query,
        linked_rosters,
        same_entry_result,
    ):
        """Show a structured dialog for confirmed team roster source coverage."""
        notebook = PM99DatabaseEditor._start_analysis_notebook(self, "Inspect Team Roster Sources")
        outer = None
        if notebook is None:
            dialog = tk.Toplevel(self.root)
            dialog.title("Inspect Team Roster Sources")
            try:
                dialog.transient(self.root)
            except Exception:
                pass
            dialog.geometry("1100x720")

            outer = ttk.Frame(dialog, padding="8")
            outer.pack(fill=tk.BOTH, expand=True)

            notebook = ttk.Notebook(outer)
            notebook.pack(fill=tk.BOTH, expand=True)

        query_text = str(team_query or "").strip()
        linked_list = list(linked_rosters or [])
        requested = list(getattr(same_entry_result, "requested_team_results", []) or [])
        preferred_coverage = dict(getattr(same_entry_result, "preferred_roster_coverage", {}) or {})
        same_entry_coverage = dict(getattr(same_entry_result, "same_entry_overlap_coverage", {}) or {})
        final_coverage = dict(getattr(same_entry_result, "final_extraction_coverage", {}) or {})

        summary_rows = [
            ("Team file", str(team_file)),
            ("Player file", str(player_file)),
            ("Team query", query_text if query_text else "(coverage summary)"),
            ("Linked roster matches", len(linked_list)),
        ]
        if query_text:
            summary_rows.append(("Same-entry requested matches", len(requested)))
        for key in ("covered_count", "club_like_team_count", "club_like_covered_count"):
            if key in preferred_coverage:
                summary_rows.append((f"preferred_roster_coverage.{key}", preferred_coverage.get(key)))

        summary_tab = ttk.Frame(notebook)
        notebook.add(summary_tab, text="Summary")
        self._add_report_tree(
            summary_tab,
            columns=("metric", "value"),
            headings={"metric": "Metric", "value": "Value"},
            rows=summary_rows,
            empty_message="No roster coverage data available.",
            widths={"metric": 280, "value": 420},
        )

        linked_tab = ttk.Frame(notebook)
        notebook.add(linked_tab, text="Linked EQ->JUG")
        if query_text:
            linked_rows = []
            for item in linked_list:
                team_name = str(item.get("team_name") or "")
                full_club_name = str(item.get("full_club_name") or "")
                display = f"{team_name} ({full_club_name})" if full_club_name and full_club_name != team_name else team_name
                eq_record_id = int(item.get("eq_record_id") or 0)
                for index, row in enumerate(list(item.get("rows") or []), start=1):
                    linked_rows.append(
                        (
                            display,
                            eq_record_id,
                            index,
                            int(row.get("pid") or 0),
                            int(row.get("flag") or 0),
                            str(row.get("player_name") or "").strip() or "(name unresolved)",
                        )
                    )
            self._add_report_tree(
                linked_tab,
                columns=("team", "eq_record_id", "slot", "pid", "flag", "player"),
                headings={
                    "team": "Team",
                    "eq_record_id": "EQ Record",
                    "slot": "Slot",
                    "pid": "PID",
                    "flag": "Flag",
                    "player": "Player",
                },
                rows=linked_rows,
                empty_message="No parser-backed EQ->JUG linked roster matched the requested team.",
                widths={"team": 260, "eq_record_id": 90, "slot": 70, "pid": 80, "flag": 70, "player": 260},
            )
        else:
            linked_rows = []
            for item in linked_list:
                team_name = str(item.get("team_name") or "")
                full_club_name = str(item.get("full_club_name") or "")
                display = f"{team_name} ({full_club_name})" if full_club_name and full_club_name != team_name else team_name
                linked_rows.append(
                    (
                        display,
                        int(item.get("eq_record_id") or 0),
                        len(list(item.get("rows") or [])),
                        int(item.get("mode_byte") or 0),
                        int(item.get("ent_count") or 0),
                    )
                )
            self._add_report_tree(
                linked_tab,
                columns=("team", "eq_record_id", "rows", "mode", "ent_count"),
                headings={
                    "team": "Team",
                    "eq_record_id": "EQ Record",
                    "rows": "Rows",
                    "mode": "Mode",
                    "ent_count": "ENT Count",
                },
                rows=linked_rows,
                empty_message="No parser-backed EQ->JUG linked rosters were found.",
                widths={"team": 320, "eq_record_id": 90, "rows": 80, "mode": 80, "ent_count": 90},
            )

        same_entry_tab = ttk.Frame(notebook)
        notebook.add(same_entry_tab, text="Same-Entry")
        if query_text:
            same_entry_rows = []
            for item in requested:
                team_name = str(item.get("team_name") or "")
                full_club_name = str(item.get("full_club_name") or "")
                display = f"{team_name} ({full_club_name})" if full_club_name and full_club_name != team_name else team_name
                status = str(item.get("status") or "")
                team_offset = item.get("team_offset")
                preferred = dict(item.get("preferred_roster_match") or {})
                preferred_provenance = str(preferred.get("provenance") or "")
                if preferred_provenance:
                    source = dict(preferred.get("source") or {})
                    entry_offset = source.get("entry_offset")
                    rows = [row for row in list(preferred.get("rows") or []) if not bool(row.get("is_empty_slot"))]
                    for index, row in enumerate(rows, start=1):
                        tail_hex = str(row.get("tail_bytes_hex") or "").strip().lower()
                        if not tail_hex:
                            row5_raw_hex = str(row.get("row5_raw_hex") or "").strip().lower()
                            if len(row5_raw_hex) == 10:
                                tail_hex = row5_raw_hex[4:10]
                        same_entry_rows.append(
                            (
                                f"{display} [{preferred_provenance}]",
                                status,
                                f"0x{int(team_offset):08X}" if isinstance(team_offset, int) else "",
                                f"0x{int(entry_offset):08X}" if isinstance(entry_offset, int) else "",
                                index,
                                int(row.get("pid_candidate", 0) or 0),
                                tail_hex,
                                row.get("tail_byte_2"),
                                row.get("tail_byte_3"),
                                row.get("tail_byte_4"),
                                str(row.get("dd6361_name") or "").strip() or "(name unresolved)",
                            )
                        )
                else:
                    same_entry_rows.append(
                        (
                            display,
                            status,
                            f"0x{int(team_offset):08X}" if isinstance(team_offset, int) else "",
                            "",
                            "-",
                            "",
                            "",
                            "",
                            "",
                            "",
                            "(no preferred same-entry roster mapping)",
                        )
                    )
            self._add_report_tree(
                same_entry_tab,
                columns=("team", "status", "team_offset", "entry_offset", "slot", "pid", "tail", "b2", "b3", "b4", "player"),
                headings={
                    "team": "Team",
                    "status": "Status",
                    "team_offset": "Team Offset",
                    "entry_offset": "Entry",
                    "slot": "Slot",
                    "pid": "PID",
                    "tail": "Tail",
                    "b2": "B2",
                    "b3": "B3",
                    "b4": "B4",
                    "player": "Player",
                },
                rows=same_entry_rows,
                empty_message="No same-entry team results matched the requested team.",
                widths={
                    "team": 260,
                    "status": 190,
                    "team_offset": 110,
                    "entry_offset": 110,
                    "slot": 70,
                    "pid": 80,
                    "tail": 90,
                    "b2": 55,
                    "b3": 55,
                    "b4": 55,
                    "player": 220,
                },
            )
        else:
            coverage_rows = []
            for section_name, payload in (
                ("same_entry_overlap_coverage", same_entry_coverage),
                ("final_extraction_coverage", final_coverage),
                ("preferred_roster_coverage", preferred_coverage),
            ):
                for key, value in dict(payload or {}).items():
                    coverage_rows.append((f"{section_name}.{key}", value))
            coverage_rows.append(("note", "Use a team query to inspect authoritative row-level same-entry mappings."))
            self._add_report_tree(
                same_entry_tab,
                columns=("metric", "value"),
                headings={"metric": "Coverage Metric", "value": "Value"},
                rows=coverage_rows,
                empty_message="No same-entry coverage metrics are available.",
                widths={"metric": 320, "value": 420},
            )

        if outer is not None:
            btn_row = ttk.Frame(outer)
            btn_row.pack(fill=tk.X, pady=(8, 0))
            ttk.Button(btn_row, text="Close", command=dialog.destroy).pack(side=tk.RIGHT)

    @staticmethod
    def _normalize_name_lookup_key(text):
        return "".join(ch.lower() for ch in str(text or "") if ch.isalnum())

    def _find_local_player_still_path(self, player_name):
        """Return a matching local player still from .local/PlayerStills when available."""
        still_dir = Path(".local/PlayerStills")
        if not still_dir.exists():
            return None
        target_key = PM99DatabaseEditor._normalize_name_lookup_key(player_name)
        if not target_key:
            return None
        for path in sorted(still_dir.glob("*.png")):
            if PM99DatabaseEditor._normalize_name_lookup_key(path.stem) == target_key:
                return path
        return None

    def _show_local_player_still_panel(self, parent, *, player_name, still_path):
        """Render a best-effort local still preview when a matching asset exists."""
        frame = ttk.Frame(parent, padding="8")
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            frame,
            text=f"Matched local still for {player_name}",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor=tk.W, pady=(0, 4))
        ttk.Label(frame, text=str(still_path), justify=tk.LEFT, wraplength=880).pack(anchor=tk.W, pady=(0, 8))

        try:
            image = tk.PhotoImage(file=str(still_path))
            max_dim = max(int(image.width()), int(image.height()))
            factor = max(1, (max_dim + 359) // 360)
            preview = image.subsample(factor, factor) if factor > 1 else image
            image_label = ttk.Label(frame, image=preview)
            image_label.image = preview
            image_label.pack(anchor=tk.W)
        except Exception:
            ttk.Label(
                frame,
                text="Preview unavailable in this environment, but the local still path resolved correctly.",
                justify=tk.LEFT,
                wraplength=880,
            ).pack(anchor=tk.W)

    def _show_player_metadata_inspect_dialog_view(self, *, result):
        """Show structured player metadata inspection output for the stable parser-backed contract."""
        notebook = PM99DatabaseEditor._start_analysis_notebook(self, "Inspect Player Metadata")
        outer = None
        if notebook is None:
            dialog = tk.Toplevel(self.root)
            dialog.title("Inspect Player Metadata")
            try:
                dialog.transient(self.root)
            except Exception:
                pass
            dialog.geometry("1120x720")

            outer = ttk.Frame(dialog, padding="8")
            outer.pack(fill=tk.BOTH, expand=True)

            notebook = ttk.Notebook(outer)
            notebook.pack(fill=tk.BOTH, expand=True)

        records = list(getattr(result, "records", []) or [])
        first_record = records[0] if records else None
        still_path = None
        if first_record is not None:
            still_path = PM99DatabaseEditor._find_local_player_still_path(self, getattr(first_record, "name", ""))

        storage_mode = str(getattr(result, "storage_mode", "indexed") or "indexed")
        count_label = "Indexed entries" if storage_mode == "indexed" else "Parsed records"
        post_weight_counts = {}
        trailer_counts = {}
        sidecar_counts = {}
        for row in records:
            post_weight_value = getattr(row, "post_weight_byte", None)
            if post_weight_value is not None:
                post_weight_counts[post_weight_value] = int(post_weight_counts.get(post_weight_value, 0) or 0) + 1
            trailer_value = getattr(row, "trailer_byte", None)
            if trailer_value is not None:
                trailer_counts[trailer_value] = int(trailer_counts.get(trailer_value, 0) or 0) + 1
            sidecar_value = getattr(row, "sidecar_byte", None)
            if sidecar_value is not None:
                sidecar_counts[sidecar_value] = int(sidecar_counts.get(sidecar_value, 0) or 0) + 1
        summary_rows = [
            ("Storage mode", storage_mode),
            ("Player file", str(getattr(result, "file_path", ""))),
            (count_label, int(getattr(result, "record_count", 0) or 0)),
            ("Matched records", int(getattr(result, "matched_count", 0) or 0)),
            (
                "Top post-weight byte",
                PM99DatabaseEditor._format_profile_count_summary(
                    sorted(post_weight_counts.items(), key=lambda item: (-item[1], item[0])),
                    label="postwt",
                    limit=1,
                ) if post_weight_counts else "",
            ),
            (
                "Top trailer byte",
                PM99DatabaseEditor._format_profile_count_summary(
                    sorted(trailer_counts.items(), key=lambda item: (-item[1], item[0])),
                    label="trail",
                    limit=1,
                ) if trailer_counts else "",
            ),
            (
                "Top sidecar byte",
                PM99DatabaseEditor._format_profile_count_summary(
                    sorted(sidecar_counts.items(), key=lambda item: (-item[1], item[0])),
                    label="sidecar",
                    limit=1,
                ) if sidecar_counts else "",
            ),
            ("Local still", str(still_path) if still_path else "not found"),
        ]
        summary_tab = ttk.Frame(notebook)
        notebook.add(summary_tab, text="Summary")
        self._add_report_tree(
            summary_tab,
            columns=("metric", "value"),
            headings={"metric": "Metric", "value": "Value"},
            rows=summary_rows,
            empty_message="No player metadata records matched.",
            widths={"metric": 220, "value": 620},
        )

        rows_tab = ttk.Frame(notebook)
        notebook.add(rows_tab, text="Records")
        record_rows = []
        for row in records:
            dob_text = (
                f"{int(row.birth_day or 0):02d}/{int(row.birth_month or 0):02d}/{int(row.birth_year or 0):04d}"
                if row.birth_day is not None and row.birth_month is not None and row.birth_year is not None
                else "n/a"
            )
            anchor_text = f"0x{row.suffix_anchor:02X}" if isinstance(row.suffix_anchor, int) else "n/a"
            hint_parts = []
            u1_hint = PM99DatabaseEditor._player_u1_display_hint(getattr(row, "indexed_unknown_1", None))
            if u1_hint:
                hint_parts.append(u1_hint)
            guard_hint = PM99DatabaseEditor._player_leading_guard_hint(
                getattr(row, "indexed_unknown_0", None),
                getattr(row, "indexed_unknown_1", None),
            )
            if guard_hint:
                hint_parts.append(guard_hint)
            suffix_hint = PM99DatabaseEditor._player_suffix_pair_hint(
                getattr(row, "indexed_unknown_9", None),
                getattr(row, "indexed_unknown_10", None),
            )
            if suffix_hint:
                hint_parts.append(suffix_hint)
            if (
                getattr(row, "post_weight_byte", None) is not None
                and getattr(row, "nationality", None) is not None
            ):
                if getattr(row, "post_weight_byte", None) == getattr(row, "nationality", None):
                    hint_parts.append("postwt=nat-search")
                else:
                    hint_parts.append("postwt=nat-group")
            face_text = ", ".join(str(v) for v in list(getattr(row, "face_components", []) or []))
            prefix_text = ", ".join(str(v) for v in list(getattr(row, "attribute_prefix", []) or []))
            record_rows.append(
                (
                    f"0x{int(getattr(row, 'offset', 0) or 0):08X}",
                    int(getattr(row, "record_id", 0) or 0),
                    str(getattr(row, "name", "") or ""),
                    getattr(row, "nationality", None),
                    getattr(row, "position", None),
                    dob_text,
                    getattr(row, "height", None),
                    getattr(row, "weight", None),
                    anchor_text,
                    prefix_text,
                    getattr(row, "post_weight_byte", None),
                    getattr(row, "trailer_byte", None),
                    getattr(row, "sidecar_byte", None),
                    getattr(row, "indexed_unknown_0", None),
                    getattr(row, "indexed_unknown_1", None),
                    getattr(row, "indexed_unknown_9", None),
                    getattr(row, "indexed_unknown_10", None),
                    face_text,
                    " | ".join(hint_parts),
                )
            )
        self._add_report_tree(
            rows_tab,
            columns=("offset", "record_id", "name", "nat", "pos", "dob", "height", "weight", "anchor", "tail_prefix", "postwt", "trail", "sidecar", "u0", "u1", "u9", "u10", "face", "hints"),
            headings={
                "offset": "Offset",
                "record_id": "RID",
                "name": "Name",
                "nat": "Nat",
                "pos": "Pos",
                "dob": "DOB",
                "height": "Ht",
                "weight": "Wt",
                "anchor": "Anchor",
                "tail_prefix": "Tail Prefix",
                "postwt": "PostWt",
                "trail": "Trail",
                "sidecar": "Sidecar",
                "u0": "U0",
                "u1": "U1",
                "u9": "U9",
                "u10": "U10",
                "face": "Face",
                "hints": "Hints",
            },
            rows=record_rows,
            empty_message="No player metadata records matched.",
            widths={
                "offset": 110,
                "record_id": 70,
                "name": 200,
                "nat": 60,
                "pos": 60,
                "dob": 100,
                "height": 60,
                "weight": 60,
                "anchor": 80,
                "tail_prefix": 120,
                "postwt": 70,
                "trail": 60,
                "sidecar": 70,
                "u0": 55,
                "u1": 55,
                "u9": 55,
                "u10": 60,
                "face": 120,
                "hints": 260,
            },
        )

        if first_record is not None and still_path:
            still_tab = ttk.Frame(notebook)
            notebook.add(still_tab, text="Local Still")
            self._show_local_player_still_panel(
                still_tab,
                player_name=str(getattr(first_record, "name", "") or ""),
                still_path=still_path,
            )

        if outer is not None:
            btn_row = ttk.Frame(outer)
            btn_row.pack(fill=tk.X, pady=(8, 0))
            ttk.Button(btn_row, text="Close", command=dialog.destroy).pack(side=tk.RIGHT)

    def _show_player_indexed_profiles_dialog_view(
        self,
        *,
        player_file,
        suffix_result,
        leading_result,
        tail_prefix_result=None,
        legacy_weight_result=None,
    ):
        """Show structured indexed byte profile output for the stable read-side probes."""
        notebook = PM99DatabaseEditor._start_analysis_notebook(self, "Inspect Indexed Player Byte Profiles")
        outer = None
        if notebook is None:
            dialog = tk.Toplevel(self.root)
            dialog.title("Inspect Indexed Player Byte Profiles")
            try:
                dialog.transient(self.root)
            except Exception:
                pass
            dialog.geometry("1120x720")

            outer = ttk.Frame(dialog, padding="8")
            outer.pack(fill=tk.BOTH, expand=True)

            notebook = ttk.Notebook(outer)
            notebook.pack(fill=tk.BOTH, expand=True)

        summary_rows = [
            ("Player file", str(player_file)),
            ("Anchored records", int(getattr(leading_result, "anchored_count", 0) or 0)),
            ("Filtered records", int(getattr(leading_result, "filtered_count", 0) or 0)),
            ("Nationality filter", getattr(leading_result, "nationality_filter", None)),
            ("Position filter", getattr(leading_result, "position_filter", None)),
            ("U0 filter", getattr(leading_result, "indexed_unknown_0_filter", None)),
            ("U1 filter", getattr(leading_result, "indexed_unknown_1_filter", None)),
            ("U9 filter", getattr(leading_result, "indexed_unknown_9_filter", None)),
            ("U10 filter", getattr(leading_result, "indexed_unknown_10_filter", None)),
            ("Attr 0 filter", getattr(tail_prefix_result, "attribute_0_filter", None) if tail_prefix_result is not None else None),
            ("Attr 1 filter", getattr(tail_prefix_result, "attribute_1_filter", None) if tail_prefix_result is not None else None),
            ("Attr 2 filter", getattr(tail_prefix_result, "attribute_2_filter", None) if tail_prefix_result is not None else None),
            ("Post-weight byte filter", getattr(tail_prefix_result, "post_weight_byte_filter", None) if tail_prefix_result is not None else None),
            ("Trailer byte filter", getattr(tail_prefix_result, "trailer_byte_filter", None) if tail_prefix_result is not None else None),
            ("Sidecar byte filter", getattr(tail_prefix_result, "sidecar_byte_filter", None) if tail_prefix_result is not None else None),
        ]
        if legacy_weight_result is not None:
            summary_rows.extend(
                [
                    ("Legacy weight offset", getattr(legacy_weight_result, "recommended_offset", None)),
                    (
                        "Legacy exact ratio",
                        f"{float(getattr(legacy_weight_result, 'legacy_exact_match_ratio', 0.0) or 0.0):.4f}",
                    ),
                ]
            )
        if getattr(tail_prefix_result, "buckets", None):
            top_prefix = tail_prefix_result.buckets[0]
            summary_rows.append(
                (
                    "Top tail prefix",
                    f"[{getattr(top_prefix, 'attribute_0', None)}, "
                    f"{getattr(top_prefix, 'attribute_1', None)}, "
                    f"{getattr(top_prefix, 'attribute_2', None)}]",
                )
            )
        if getattr(tail_prefix_result, "signature_buckets", None):
            top_signature = tail_prefix_result.signature_buckets[0]
            summary_rows.append(
                (
                    "Top tail signature",
                    f"[{getattr(top_signature, 'attribute_0', None)}, "
                    f"{getattr(top_signature, 'attribute_1', None)}, "
                    f"{getattr(top_signature, 'attribute_2', None)} | "
                    f"trail={getattr(top_signature, 'trailer_byte', None)} "
                    f"sidecar={getattr(top_signature, 'sidecar_byte', None)}]",
                )
            )
        if tail_prefix_result is not None:
            summary_rows.extend(
                [
                    (
                        "Tail layout verification",
                        f"verified={int(getattr(tail_prefix_result, 'layout_verified_count', 0) or 0)} "
                        f"mismatch={int(getattr(tail_prefix_result, 'layout_mismatch_count', 0) or 0)}",
                    ),
                    (
                        "Top Attr 0 values",
                        PM99DatabaseEditor._format_profile_count_summary(
                            getattr(tail_prefix_result, "attribute_0_counts", []),
                            label="a0",
                        ),
                    ),
                    (
                        "Top Attr 1 values",
                        PM99DatabaseEditor._format_profile_count_summary(
                            getattr(tail_prefix_result, "attribute_1_counts", []),
                            label="a1",
                        ),
                    ),
                    (
                        "Top Attr 2 values",
                        PM99DatabaseEditor._format_profile_count_summary(
                            getattr(tail_prefix_result, "attribute_2_counts", []),
                            label="a2",
                        ),
                    ),
                    (
                        "Top post-weight bytes",
                        PM99DatabaseEditor._format_profile_count_summary(
                            getattr(tail_prefix_result, "post_weight_byte_counts", []),
                            label="postwt",
                        ),
                    ),
                    (
                        "Post-weight vs nationality",
                        (
                            f"match={int(getattr(tail_prefix_result, 'post_weight_nationality_match_count', 0) or 0)}"
                            + "/"
                            + f"{int(getattr(tail_prefix_result, 'post_weight_nationality_eligible_count', 0) or 0)} "
                            + f"ratio={float(getattr(tail_prefix_result, 'post_weight_nationality_match_ratio', 0.0) or 0.0):.4f}"
                        )
                        if int(getattr(tail_prefix_result, "post_weight_nationality_eligible_count", 0) or 0)
                        else "",
                    ),
                    (
                        "Top divergent post-weight keys",
                        PM99DatabaseEditor._format_profile_count_summary(
                            getattr(tail_prefix_result, "post_weight_divergent_counts", []),
                            label="postwt",
                            limit=5,
                        ),
                    ),
                    (
                        "Top post-weight mismatches",
                        ", ".join(
                            f"postwt={post_value}->nat={nat_value}({count})"
                            for post_value, nat_value, count in list(
                                getattr(tail_prefix_result, "post_weight_nationality_mismatch_pairs", []) or []
                            )[:5]
                        ),
                    ),
                    (
                        "Grouped post-weight cohorts",
                        PM99DatabaseEditor._format_post_weight_group_cluster_summary(
                            getattr(tail_prefix_result, "post_weight_group_clusters", []),
                            limit=3,
                            per_cluster_limit=4,
                        ),
                    ),
                    (
                        "Top trailer bytes",
                        PM99DatabaseEditor._format_profile_count_summary(
                            getattr(tail_prefix_result, "trailer_byte_counts", []),
                            label="trail",
                        ),
                    ),
                    (
                        "Top sidecar bytes",
                        PM99DatabaseEditor._format_profile_count_summary(
                            getattr(tail_prefix_result, "sidecar_byte_counts", []),
                            label="sidecar",
                        ),
                    ),
                ]
            )
            summary_rows.append(
                (
                    "Tail prefix status",
                    "read-only structural signature / sidecar block "
                    "(the post-weight byte is fixed at [player+0x48] and acts as a secondary nationality/search key: "
                    "FUN_0043d960 is called from the search-options builder against the same 0x4B2E90 nationality table "
                    "used by the player-view nationality label, "
                    "two post-attribute bytes are discrete and rendered separately in DBASEPRE UI paths, "
                    "then the remainder is copied in bulk; "
                    "no fixed named offsets proven)",
                )
            )
        summary_tab = ttk.Frame(notebook)
        notebook.add(summary_tab, text="Summary")
        self._add_report_tree(
            summary_tab,
            columns=("metric", "value"),
            headings={"metric": "Metric", "value": "Value"},
            rows=summary_rows,
            empty_message="No indexed profile data is available.",
            widths={"metric": 220, "value": 620},
        )

        suffix_tab = ttk.Frame(notebook)
        notebook.add(suffix_tab, text="Suffix Bytes")
        suffix_rows = []
        reference_rows = []
        seen_reference_paths = set()
        for bucket in list(getattr(suffix_result, "buckets", []) or []):
            sample_names = list(getattr(bucket, "sample_names", []) or [])
            hint = PM99DatabaseEditor._player_suffix_pair_hint(
                getattr(bucket, "indexed_unknown_9", None),
                getattr(bucket, "indexed_unknown_10", None),
            )
            still_count = 0
            for sample_name in sample_names:
                path = PM99DatabaseEditor._find_local_player_still_path(self, sample_name)
                if path:
                    still_count += 1
                    path_key = str(path)
                    if path_key not in seen_reference_paths:
                        seen_reference_paths.add(path_key)
                        reference_rows.append((sample_name, path_key))
            suffix_rows.append(
                (
                    getattr(bucket, "indexed_unknown_9", None),
                    getattr(bucket, "indexed_unknown_10", None),
                    getattr(bucket, "count", None),
                    hint,
                    ", ".join(sample_names),
                    still_count,
                )
            )
        self._add_report_tree(
            suffix_tab,
            columns=("u9", "u10", "count", "hint", "examples", "local_stills"),
            headings={
                "u9": "U9",
                "u10": "U10",
                "count": "Count",
                "hint": "Hint",
                "examples": "Examples",
                "local_stills": "Local Stills",
            },
            rows=suffix_rows,
            empty_message="No indexed suffix profile buckets matched.",
            widths={"u9": 60, "u10": 60, "count": 70, "hint": 180, "examples": 360, "local_stills": 90},
        )

        leading_tab = ttk.Frame(notebook)
        notebook.add(leading_tab, text="Leading Bytes")
        leading_rows = []
        for bucket in list(getattr(leading_result, "buckets", []) or []):
            sample_names = list(getattr(bucket, "sample_names", []) or [])
            hint = PM99DatabaseEditor._player_u1_display_hint(getattr(bucket, "indexed_unknown_1", None))
            guard = PM99DatabaseEditor._player_leading_guard_hint(
                getattr(bucket, "indexed_unknown_0", None),
                getattr(bucket, "indexed_unknown_1", None),
            )
            still_count = 0
            for sample_name in sample_names:
                path = PM99DatabaseEditor._find_local_player_still_path(self, sample_name)
                if path:
                    still_count += 1
                    path_key = str(path)
                    if path_key not in seen_reference_paths:
                        seen_reference_paths.add(path_key)
                        reference_rows.append((sample_name, path_key))
            leading_rows.append(
                (
                    getattr(bucket, "indexed_unknown_0", None),
                    getattr(bucket, "indexed_unknown_1", None),
                    getattr(bucket, "count", None),
                    hint,
                    guard,
                    ", ".join(sample_names),
                    still_count,
                )
            )
        self._add_report_tree(
            leading_tab,
            columns=("u0", "u1", "count", "hint", "guard", "examples", "local_stills"),
            headings={
                "u0": "U0",
                "u1": "U1",
                "count": "Count",
                "hint": "Hint",
                "guard": "Guard",
                "examples": "Examples",
                "local_stills": "Local Stills",
            },
            rows=leading_rows,
            empty_message="No indexed leading-byte profile buckets matched.",
            widths={"u0": 60, "u1": 60, "count": 70, "hint": 130, "guard": 130, "examples": 320, "local_stills": 90},
        )

        prefix_tab = ttk.Frame(notebook)
        notebook.add(prefix_tab, text="Tail Prefix")
        prefix_rows = []
        for bucket in list(getattr(tail_prefix_result, "buckets", []) or []):
            sample_names = list(getattr(bucket, "sample_names", []) or [])
            still_count = 0
            for sample_name in sample_names:
                path = PM99DatabaseEditor._find_local_player_still_path(self, sample_name)
                if path:
                    still_count += 1
                    path_key = str(path)
                    if path_key not in seen_reference_paths:
                        seen_reference_paths.add(path_key)
                        reference_rows.append((sample_name, path_key))
            prefix_rows.append(
                (
                    getattr(bucket, "attribute_0", None),
                    getattr(bucket, "attribute_1", None),
                    getattr(bucket, "attribute_2", None),
                    getattr(bucket, "count", None),
                    ", ".join(sample_names),
                    still_count,
                )
            )
        self._add_report_tree(
            prefix_tab,
            columns=("a0", "a1", "a2", "count", "examples", "local_stills"),
            headings={
                "a0": "Attr 0",
                "a1": "Attr 1",
                "a2": "Attr 2",
                "count": "Count",
                "examples": "Examples",
                "local_stills": "Local Stills",
            },
            rows=prefix_rows,
            empty_message="No indexed tail-prefix profile buckets matched.",
            widths={"a0": 70, "a1": 70, "a2": 70, "count": 70, "examples": 420, "local_stills": 90},
        )

        signature_tab = ttk.Frame(notebook)
        notebook.add(signature_tab, text="Tail Signatures")
        signature_rows = []
        for bucket in list(getattr(tail_prefix_result, "signature_buckets", []) or []):
            sample_names = list(getattr(bucket, "sample_names", []) or [])
            still_count = 0
            for sample_name in sample_names:
                path = PM99DatabaseEditor._find_local_player_still_path(self, sample_name)
                if path:
                    still_count += 1
                    path_key = str(path)
                    if path_key not in seen_reference_paths:
                        seen_reference_paths.add(path_key)
                        reference_rows.append((sample_name, path_key))
            signature_rows.append(
                (
                    getattr(bucket, "attribute_0", None),
                    getattr(bucket, "attribute_1", None),
                    getattr(bucket, "attribute_2", None),
                    getattr(bucket, "trailer_byte", None),
                    getattr(bucket, "sidecar_byte", None),
                    getattr(bucket, "count", None),
                    ", ".join(sample_names),
                    still_count,
                )
            )
        self._add_report_tree(
            signature_tab,
            columns=("a0", "a1", "a2", "trail", "sidecar", "count", "examples", "local_stills"),
            headings={
                "a0": "Attr 0",
                "a1": "Attr 1",
                "a2": "Attr 2",
                "trail": "Trail",
                "sidecar": "Sidecar",
                "count": "Count",
                "examples": "Examples",
                "local_stills": "Local Stills",
            },
            rows=signature_rows,
            empty_message="No indexed tail-signature profile buckets matched.",
            widths={
                "a0": 70,
                "a1": 70,
                "a2": 70,
                "trail": 70,
                "sidecar": 80,
                "count": 70,
                "examples": 360,
                "local_stills": 90,
            },
        )

        counts_tab = ttk.Frame(notebook)
        notebook.add(counts_tab, text="Cohorts")
        cohort_rows = []
        for value, count in list(getattr(leading_result, "position_counts", []) or []):
            cohort_rows.append(("Position", value, count))
        for value, count in list(getattr(leading_result, "nationality_counts", []) or []):
            cohort_rows.append(("Nationality", value, count))
        self._add_report_tree(
            counts_tab,
            columns=("group", "value", "count"),
            headings={"group": "Group", "value": "Value", "count": "Count"},
            rows=cohort_rows,
            empty_message="No cohort count data is available.",
            widths={"group": 140, "value": 100, "count": 100},
        )

        if legacy_weight_result is not None:
            legacy_tab = ttk.Frame(notebook)
            notebook.add(legacy_tab, text="Legacy Weight")

            legacy_summary_box = ttk.LabelFrame(legacy_tab, text="Control Set + Name-Only Validation")
            legacy_summary_box.pack(fill=tk.X, expand=False, padx=8, pady=(8, 0))
            legacy_summary_rows = [
                ("Recommended offset", getattr(legacy_weight_result, "recommended_offset", None)),
                ("Indexed entries", int(getattr(legacy_weight_result, "record_count", 0) or 0)),
                ("Control records", int(getattr(legacy_weight_result, "candidate_record_count", 0) or 0)),
                (
                    "Height baseline exact ratio",
                    f"{float(getattr(legacy_weight_result, 'height_baseline_exact_ratio', 0.0) or 0.0):.4f}",
                ),
                ("Name-only valid records", int(getattr(legacy_weight_result, "legacy_valid_record_count", 0) or 0)),
                ("Name-only slot records", int(getattr(legacy_weight_result, "legacy_slot_record_count", 0) or 0)),
                ("Name-only uniquely matched", int(getattr(legacy_weight_result, "legacy_matched_record_count", 0) or 0)),
                ("Name-only exact matches", int(getattr(legacy_weight_result, "legacy_exact_match_count", 0) or 0)),
                (
                    "Name-only exact ratio",
                    f"{float(getattr(legacy_weight_result, 'legacy_exact_match_ratio', 0.0) or 0.0):.4f}",
                ),
            ]
            self._add_report_tree(
                legacy_summary_box,
                columns=("metric", "value"),
                headings={"metric": "Metric", "value": "Value"},
                rows=legacy_summary_rows,
                empty_message="No legacy weight validation data is available.",
                widths={"metric": 240, "value": 220},
            )

            legacy_offsets_box = ttk.LabelFrame(legacy_tab, text="Marker-Relative Candidates")
            legacy_offsets_box.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 8))
            legacy_offset_rows = []
            for row in list(getattr(legacy_weight_result, "offsets", []) or []):
                top_values = ", ".join(
                    f"{value}({count})"
                    for value, count in list(getattr(row, "top_values", []) or [])
                )
                legacy_offset_rows.append(
                    (
                        f"marker+{int(getattr(row, 'relative_offset', 0) or 0)}",
                        int(getattr(row, "eligible_count", 0) or 0),
                        int(getattr(row, "exact_match_count", 0) or 0),
                        f"{float(getattr(row, 'exact_match_ratio', 0.0) or 0.0):.4f}",
                        f"{float(getattr(row, 'mean_abs_error', 0.0) or 0.0):.2f}",
                        top_values,
                    )
                )
            self._add_report_tree(
                legacy_offsets_box,
                columns=("offset", "eligible", "exact", "ratio", "mae", "top"),
                headings={
                    "offset": "Offset",
                    "eligible": "Eligible",
                    "exact": "Exact",
                    "ratio": "Exact Ratio",
                    "mae": "MAE",
                    "top": "Top Values",
                },
                rows=legacy_offset_rows,
                empty_message="No legacy weight candidate offsets were profiled.",
                widths={"offset": 90, "eligible": 80, "exact": 80, "ratio": 90, "mae": 70, "top": 360},
            )

        if reference_rows:
            still_tab = ttk.Frame(notebook)
            notebook.add(still_tab, text="Local Still Matches")
            self._add_report_tree(
                still_tab,
                columns=("name", "path"),
                headings={"name": "Sample Name", "path": "Local Still Path"},
                rows=reference_rows,
                empty_message="No local still assets matched the current sample names.",
                widths={"name": 220, "path": 620},
            )

        if outer is not None:
            btn_row = ttk.Frame(outer)
            btn_row.pack(fill=tk.X, pady=(8, 0))
            ttk.Button(btn_row, text="Close", command=dialog.destroy).pack(side=tk.RIGHT)

    def _format_player_metadata_inspect_report(self, result):
        if not getattr(result, "records", None):
            return "No player metadata records matched."
        storage_mode = str(getattr(result, "storage_mode", "indexed") or "indexed")
        count_label = "indexed_entries" if storage_mode == "indexed" else "parsed_records"
        lines = [
            f"Matched {len(result.records)} player record(s) ({count_label}={getattr(result, 'record_count', 0)})",
            "",
        ]
        for row in list(result.records or [])[:20]:
            anchor_text = f"0x{row.suffix_anchor:02X}" if isinstance(row.suffix_anchor, int) else "n/a"
            dob_text = (
                f"{int(row.birth_day or 0):02d}/{int(row.birth_month or 0):02d}/{int(row.birth_year or 0):04d}"
                if row.birth_day is not None and row.birth_month is not None and row.birth_year is not None
                else "n/a"
            )
            lines.append(f"0x{row.offset:08X} rid={row.record_id:5d}: {row.name}")
            lines.append(
                "  "
                + f"nat={row.nationality} pos={row.position} dob={dob_text} ht={row.height} wt={row.weight} anchor={anchor_text}"
            )
            lines.append(
                "  "
                + f"u0={row.indexed_unknown_0} u1={row.indexed_unknown_1} "
                + f"u9={row.indexed_unknown_9} u10={row.indexed_unknown_10}"
            )
            if list(getattr(row, "attribute_prefix", []) or []):
                lines.append(
                    "  "
                    + f"tail_prefix={list(getattr(row, 'attribute_prefix', []) or [])} "
                    + "(read-only non-stat prefix)"
                )
            if getattr(row, "post_weight_byte", None) is not None:
                lines.append("  " + f"post_weight_byte={getattr(row, 'post_weight_byte', None)}")
                if getattr(row, "nationality", None) is not None:
                    if getattr(row, "post_weight_byte", None) == getattr(row, "nationality", None):
                        lines.append("  post_weight_hint=mirrors nationality search key")
                    else:
                        lines.append("  post_weight_hint=grouped nationality search key")
            if getattr(row, "trailer_byte", None) is not None:
                lines.append("  " + f"trailer_byte={getattr(row, 'trailer_byte', None)}")
            if getattr(row, "sidecar_byte", None) is not None:
                lines.append("  " + f"sidecar_byte={getattr(row, 'sidecar_byte', None)}")
            if row.face_components:
                lines.append(f"  face={list(row.face_components)}")
            u1_hint = PM99DatabaseEditor._player_u1_display_hint(row.indexed_unknown_1)
            if u1_hint:
                lines.append(f"  u1_hint={u1_hint}")
            guard_hint = PM99DatabaseEditor._player_leading_guard_hint(row.indexed_unknown_0, row.indexed_unknown_1)
            if guard_hint:
                lines.append(f"  guard_hint={guard_hint}")
            suffix_hint = PM99DatabaseEditor._player_suffix_pair_hint(row.indexed_unknown_9, row.indexed_unknown_10)
            if suffix_hint:
                lines.append(f"  suffix_hint={suffix_hint}")
            lines.append("")
        extra = len(list(result.records or [])) - min(len(list(result.records or [])), 20)
        if extra > 0:
            lines.append(f"... and {extra} more record(s)")
        return "\n".join(lines).rstrip()

    def _format_player_suffix_profile_report(self, result):
        if not getattr(result, "buckets", None):
            return "No indexed suffix profile buckets matched."
        filter_bits = []
        if getattr(result, "nationality_filter", None) is not None:
            filter_bits.append(f"nat={result.nationality_filter}")
        if getattr(result, "position_filter", None) is not None:
            filter_bits.append(f"pos={result.position_filter}")
        filter_text = f" [{' '.join(filter_bits)}]" if filter_bits else ""
        lines = [
            f"Indexed suffix profile{filter_text}: anchored={result.anchored_count}, filtered={result.filtered_count}, indexed_entries={result.record_count}",
        ]
        for bucket in list(result.buckets or []):
            names = ", ".join(list(bucket.sample_names or []))
            line = (
                f"  u9={bucket.indexed_unknown_9} u10={bucket.indexed_unknown_10}: "
                f"count={bucket.count}"
            )
            hint = PM99DatabaseEditor._player_suffix_pair_hint(
                bucket.indexed_unknown_9,
                bucket.indexed_unknown_10,
            )
            if hint:
                line += f" hint={hint}"
            if names:
                line += f" examples={names}"
            lines.append(line)
        return "\n".join(lines)

    def _format_player_leading_profile_report(self, result):
        if not getattr(result, "buckets", None):
            return "No indexed leading-byte profile buckets matched."
        filter_bits = []
        if getattr(result, "nationality_filter", None) is not None:
            filter_bits.append(f"nat={result.nationality_filter}")
        if getattr(result, "position_filter", None) is not None:
            filter_bits.append(f"pos={result.position_filter}")
        if getattr(result, "indexed_unknown_0_filter", None) is not None:
            filter_bits.append(f"u0={result.indexed_unknown_0_filter}")
        if getattr(result, "indexed_unknown_1_filter", None) is not None:
            filter_bits.append(f"u1={result.indexed_unknown_1_filter}")
        if getattr(result, "indexed_unknown_9_filter", None) is not None:
            filter_bits.append(f"u9={result.indexed_unknown_9_filter}")
        if getattr(result, "indexed_unknown_10_filter", None) is not None:
            filter_bits.append(f"u10={result.indexed_unknown_10_filter}")
        filter_text = f" [{' '.join(filter_bits)}]" if filter_bits else ""
        lines = [
            f"Indexed leading-byte profile{filter_text}: anchored={result.anchored_count}, filtered={result.filtered_count}, indexed_entries={result.record_count}",
        ]
        position_text = PM99DatabaseEditor._format_profile_count_summary(
            getattr(result, "position_counts", []),
            label="pos",
        )
        if position_text:
            lines.append(f"  positions={position_text}")
        nationality_text = PM99DatabaseEditor._format_profile_count_summary(
            getattr(result, "nationality_counts", []),
            label="nat",
        )
        if nationality_text:
            lines.append(f"  nationalities={nationality_text}")
        for bucket in list(result.buckets or []):
            names = ", ".join(list(bucket.sample_names or []))
            line = f"  u0={bucket.indexed_unknown_0} u1={bucket.indexed_unknown_1}: count={bucket.count}"
            hint = PM99DatabaseEditor._player_u1_display_hint(bucket.indexed_unknown_1)
            if hint:
                line += f" hint={hint}"
            guard_hint = PM99DatabaseEditor._player_leading_guard_hint(
                bucket.indexed_unknown_0,
                bucket.indexed_unknown_1,
            )
            if guard_hint:
                line += f" guard={guard_hint}"
            if names:
                line += f" examples={names}"
            lines.append(line)
        return "\n".join(lines)

    def _format_team_roster_sources_report(self, *, team_file, player_file, team_query, linked_rosters, same_entry_result):
        query_text = str(team_query or "").strip()
        lines = [
            "Team Roster Sources",
            "",
            f"Team file: {team_file}",
            f"Player file: {player_file}",
            f"Team query: {query_text if query_text else '(coverage summary)'}",
            "",
        ]

        if not query_text:
            linked_count = len(list(linked_rosters or []))
            lines.append(f"Parser-backed EQ->JUG linked coverage: {linked_count} linked team record(s)")
            preferred = dict(getattr(same_entry_result, "preferred_roster_coverage", {}) or {})
            covered_count = preferred.get("covered_count")
            club_like_team_count = preferred.get("club_like_team_count")
            club_like_covered_count = preferred.get("club_like_covered_count")
            lines.append(
                "Authoritative same-entry preferred coverage: "
                + ", ".join(
                    part
                    for part in (
                        f"covered={covered_count}" if covered_count is not None else "",
                        f"club_like_total={club_like_team_count}" if club_like_team_count is not None else "",
                        f"club_like_covered={club_like_covered_count}" if club_like_covered_count is not None else "",
                    )
                    if part
                )
            )
            return "\n".join(lines)

        if not list(linked_rosters or []):
            lines.append("No parser-backed EQ->JUG linked roster matched the requested team.")
        else:
            lines.append(f"Parser-backed EQ->JUG linked matches: {len(list(linked_rosters or []))}")
            for item in list(linked_rosters or []):
                team_name = str(item.get("team_name") or "")
                full_club_name = str(item.get("full_club_name") or "")
                eq_record_id = int(item.get("eq_record_id") or 0)
                ent_count = int(item.get("ent_count") or 0)
                mode_byte = int(item.get("mode_byte") or 0)
                rows = list(item.get("rows") or [])
                display = team_name
                if full_club_name and full_club_name != team_name:
                    display = f"{team_name} ({full_club_name})"
                lines.append(
                    f"  {display}: eq_record_id={eq_record_id} mode={mode_byte} ent_count={ent_count} rows={len(rows)}"
                )
                for idx, row in enumerate(rows, start=1):
                    pid = int(row.get("pid") or 0)
                    flag = int(row.get("flag") or 0)
                    player_name = str(row.get("player_name") or "").strip() or "(name unresolved)"
                    lines.append(f"    slot={idx:02d} pid={pid:5d} flag={flag} {player_name}")

        lines.append("")
        requested = list(getattr(same_entry_result, "requested_team_results", []) or [])
        if not requested:
            lines.append("No same-entry team results matched the requested team.")
            return "\n".join(lines)

        lines.append(f"Same-entry extraction matches: {len(requested)}")
        for item in requested:
            team_name = str(item.get("team_name") or "")
            full_club_name = str(item.get("full_club_name") or "")
            display = team_name
            if full_club_name and full_club_name != team_name:
                display = f"{team_name} ({full_club_name})"
            status = str(item.get("status") or "")
            team_offset = item.get("team_offset")
            lines.append(
                "  "
                + display
                + (
                    f" status={status}"
                    + (f", team_offset=0x{int(team_offset):08X}" if isinstance(team_offset, int) else "")
                )
            )

            preferred = dict(item.get("preferred_roster_match") or {})
            preferred_provenance = str(preferred.get("provenance") or "")
            if not preferred_provenance:
                lines.append("    No preferred same-entry roster mapping.")
                continue

            source = dict(preferred.get("source") or {})
            entry_offset = source.get("entry_offset")
            rows = [row for row in list(preferred.get("rows") or []) if not bool(row.get("is_empty_slot"))]
            lines.append(
                "    "
                + f"preferred_roster={preferred_provenance} rows={len(rows)}"
                + (f", entry=0x{int(entry_offset):08X}" if isinstance(entry_offset, int) else "")
            )
            for index, row in enumerate(rows, start=1):
                pid = int(row.get("pid_candidate", 0) or 0)
                dd_name = str(row.get("dd6361_name") or "").strip() or "(name unresolved)"
                lines.append(f"      slot={index:02d} pid={pid:5d} {dd_name}")

        return "\n".join(lines)

    def open_player_metadata_inspect_dialog(self):
        """Show the parser-backed indexed player metadata snapshot for a selected player."""
        try:
            player_file = getattr(self, "file_path", None) or "DBDAT/JUG98030.FDI"
            initial_name = PM99DatabaseEditor._current_player_visible_skill_query(self)
            current = getattr(self, "current_record", None)
            initial_offset = ""
            if isinstance(current, tuple) and len(current) >= 1 and isinstance(current[0], int):
                initial_offset = f"0x{int(current[0]):X}"

            target_name = str(
                simpledialog.askstring(
                    "Inspect Player Metadata",
                    "Player name:",
                    initialvalue=initial_name,
                )
                or ""
            ).strip()
            if not target_name:
                return
            offset_text = simpledialog.askstring(
                "Inspect Player Metadata",
                "Offset (optional, hex or decimal):",
                initialvalue=initial_offset,
            )
            if offset_text is None:
                return
            target_offset = PM99DatabaseEditor._parse_optional_dialog_int(offset_text)

            self.status_var.set("Inspecting player metadata...")
            self.root.update_idletasks()
            result = inspect_player_metadata_records(
                file_path=player_file,
                target_name=target_name,
                target_offset=target_offset,
            )
            self.status_var.set(
                f"✓ Player metadata inspection complete ({getattr(result, 'matched_count', 0)} matched)"
            )
            PM99DatabaseEditor._show_player_metadata_inspect_dialog_view(self, result=result)
        except Exception as exc:
            self.status_var.set("Player metadata inspection failed")
            messagebox.showerror("Inspect Player Metadata", f"Player metadata inspection failed:\n{exc}")

    def open_player_indexed_profiles_dialog(self):
        """Show indexed suffix/leading-byte profiles using the current stable read contracts."""
        try:
            player_file = getattr(self, "file_path", None) or "DBDAT/JUG98030.FDI"
            current = getattr(self, "current_record", None)
            record = current[1] if isinstance(current, tuple) and len(current) >= 2 else None
            nat_default = "" if getattr(record, "nationality", None) is None else str(getattr(record, "nationality"))
            pos_default = "" if getattr(record, "position_primary", None) is None else str(getattr(record, "position_primary"))
            u0_default = "" if getattr(record, "indexed_unknown_0", None) is None else str(getattr(record, "indexed_unknown_0"))
            u1_default = "" if getattr(record, "indexed_unknown_1", None) is None else str(getattr(record, "indexed_unknown_1"))
            u9_default = "" if getattr(record, "indexed_unknown_9", None) is None else str(getattr(record, "indexed_unknown_9"))
            u10_default = "" if getattr(record, "indexed_unknown_10", None) is None else str(getattr(record, "indexed_unknown_10"))
            attrs_default = list(getattr(record, "attributes", []) or [])
            a0_default = "" if len(attrs_default) < 1 else str(attrs_default[0])
            a1_default = "" if len(attrs_default) < 2 else str(attrs_default[1])
            a2_default = "" if len(attrs_default) < 3 else str(attrs_default[2])
            post_weight_default = ""
            trail_default = ""
            sidecar_default = ""

            nat_text = simpledialog.askstring(
                "Inspect Indexed Player Byte Profiles",
                "Nationality filter (optional):",
                initialvalue=nat_default,
            )
            if nat_text is None:
                return
            pos_text = simpledialog.askstring(
                "Inspect Indexed Player Byte Profiles",
                "Position filter (optional):",
                initialvalue=pos_default,
            )
            if pos_text is None:
                return
            u0_text = simpledialog.askstring(
                "Inspect Indexed Player Byte Profiles",
                "Leading byte u0 filter (optional):",
                initialvalue=u0_default,
            )
            if u0_text is None:
                return
            u1_text = simpledialog.askstring(
                "Inspect Indexed Player Byte Profiles",
                "Leading byte u1 filter (optional):",
                initialvalue=u1_default,
            )
            if u1_text is None:
                return
            u9_text = simpledialog.askstring(
                "Inspect Indexed Player Byte Profiles",
                "Suffix byte u9 filter (optional):",
                initialvalue=u9_default,
            )
            if u9_text is None:
                return
            u10_text = simpledialog.askstring(
                "Inspect Indexed Player Byte Profiles",
                "Suffix byte u10 filter (optional):",
                initialvalue=u10_default,
            )
            if u10_text is None:
                return
            a0_text = simpledialog.askstring(
                "Inspect Indexed Player Byte Profiles",
                "Tail-prefix Attr 0 filter (optional):",
                initialvalue=a0_default,
            )
            if a0_text is None:
                return
            a1_text = simpledialog.askstring(
                "Inspect Indexed Player Byte Profiles",
                "Tail-prefix Attr 1 filter (optional):",
                initialvalue=a1_default,
            )
            if a1_text is None:
                return
            a2_text = simpledialog.askstring(
                "Inspect Indexed Player Byte Profiles",
                "Tail-prefix Attr 2 filter (optional):",
                initialvalue=a2_default,
            )
            if a2_text is None:
                return
            post_weight_text = simpledialog.askstring(
                "Inspect Indexed Player Byte Profiles",
                "Indexed post-weight byte filter (optional):",
                initialvalue=post_weight_default,
            )
            if post_weight_text is None:
                return
            trail_text = simpledialog.askstring(
                "Inspect Indexed Player Byte Profiles",
                "Fixed trailer byte filter (optional):",
                initialvalue=trail_default,
            )
            if trail_text is None:
                return
            sidecar_text = simpledialog.askstring(
                "Inspect Indexed Player Byte Profiles",
                "First post-trailer sidecar byte filter (optional):",
                initialvalue=sidecar_default,
            )
            if sidecar_text is None:
                return
            limit_text = simpledialog.askstring(
                "Inspect Indexed Player Byte Profiles",
                "Max buckets to show:",
                initialvalue="10",
            )
            if limit_text is None:
                return

            nationality = PM99DatabaseEditor._parse_optional_dialog_int(nat_text)
            position = PM99DatabaseEditor._parse_optional_dialog_int(pos_text)
            indexed_unknown_0 = PM99DatabaseEditor._parse_optional_dialog_int(u0_text)
            indexed_unknown_1 = PM99DatabaseEditor._parse_optional_dialog_int(u1_text)
            indexed_unknown_9 = PM99DatabaseEditor._parse_optional_dialog_int(u9_text)
            indexed_unknown_10 = PM99DatabaseEditor._parse_optional_dialog_int(u10_text)
            attribute_0 = PM99DatabaseEditor._parse_optional_dialog_int(a0_text)
            attribute_1 = PM99DatabaseEditor._parse_optional_dialog_int(a1_text)
            attribute_2 = PM99DatabaseEditor._parse_optional_dialog_int(a2_text)
            post_weight_byte = PM99DatabaseEditor._parse_optional_dialog_int(post_weight_text)
            trailer_byte = PM99DatabaseEditor._parse_optional_dialog_int(trail_text)
            sidecar_byte = PM99DatabaseEditor._parse_optional_dialog_int(sidecar_text)
            limit_value = PM99DatabaseEditor._parse_optional_dialog_int(limit_text)
            limit = max(1, int(limit_value or 10))

            self.status_var.set("Profiling indexed player bytes...")
            self.root.update_idletasks()
            suffix_result = profile_indexed_player_suffix_bytes(
                file_path=player_file,
                nationality=nationality,
                position=position,
                limit=limit,
            )
            leading_result = profile_indexed_player_leading_bytes(
                file_path=player_file,
                nationality=nationality,
                position=position,
                indexed_unknown_0=indexed_unknown_0,
                indexed_unknown_1=indexed_unknown_1,
                indexed_unknown_9=indexed_unknown_9,
                indexed_unknown_10=indexed_unknown_10,
                attribute_0=attribute_0,
                attribute_1=attribute_1,
                attribute_2=attribute_2,
                post_weight_byte=post_weight_byte,
                trailer_byte=trailer_byte,
                sidecar_byte=sidecar_byte,
                limit=limit,
            )
            tail_prefix_result = profile_indexed_player_attribute_prefixes(
                file_path=player_file,
                nationality=nationality,
                position=position,
                indexed_unknown_0=indexed_unknown_0,
                indexed_unknown_1=indexed_unknown_1,
                indexed_unknown_9=indexed_unknown_9,
                indexed_unknown_10=indexed_unknown_10,
                attribute_0=attribute_0,
                attribute_1=attribute_1,
                attribute_2=attribute_2,
                post_weight_byte=post_weight_byte,
                trailer_byte=trailer_byte,
                sidecar_byte=sidecar_byte,
                limit=limit,
            )
            legacy_weight_result = profile_player_legacy_weight_candidates(
                file_path=player_file,
            )
            self.status_var.set(
                "✓ Indexed player byte profiles complete "
                + f"(anchored={getattr(leading_result, 'anchored_count', 0)}, "
                + f"legacy_offset={getattr(legacy_weight_result, 'recommended_offset', None)}, "
                + f"tail_prefixes={len(list(getattr(tail_prefix_result, 'buckets', []) or []))})"
            )
            PM99DatabaseEditor._show_player_indexed_profiles_dialog_view(
                self,
                player_file=player_file,
                suffix_result=suffix_result,
                leading_result=leading_result,
                tail_prefix_result=tail_prefix_result,
                legacy_weight_result=legacy_weight_result,
            )
        except Exception as exc:
            self.status_var.set("Indexed player byte profiling failed")
            messagebox.showerror(
                "Inspect Indexed Player Byte Profiles",
                f"Indexed player byte profiling failed:\n{exc}",
            )

    def open_team_roster_sources_dialog(self):
        """Show the same confirmed team roster sources the CLI exposes today."""
        try:
            team_file = getattr(self, "team_file_path", None) or "DBDAT/EQ98030.FDI"
            player_file = PM99DatabaseEditor._resolve_team_roster_player_file(self)
            current_team = getattr(self, "current_team", None)
            initial_team_query = ""
            if isinstance(current_team, tuple) and len(current_team) >= 2:
                initial_team_query = str(getattr(current_team[1], "name", "") or "").strip()
            team_query = simpledialog.askstring(
                "Inspect Team Roster Sources",
                "Team query (optional; blank = coverage summary):",
                initialvalue=initial_team_query,
            )
            if team_query is None:
                return
            team_query = str(team_query or "").strip()
            team_queries = [team_query] if team_query else []

            self.status_var.set("Inspecting team roster sources...")
            self.root.update_idletasks()
            linked_rosters = extract_team_rosters_eq_jug_linked(
                team_file=team_file,
                player_file=player_file,
                team_queries=team_queries,
            )
            same_entry_result = extract_team_rosters_eq_same_entry_overlap(
                team_file=team_file,
                player_file=player_file,
                team_queries=team_queries,
                top_examples=5,
                include_fallbacks=True,
            )
            PM99DatabaseEditor._show_team_roster_sources_dialog_view(
                self,
                team_file=team_file,
                player_file=player_file,
                team_query=team_query,
                linked_rosters=linked_rosters,
                same_entry_result=same_entry_result,
            )
            self.status_var.set("✓ Team roster source inspection complete")
        except Exception as exc:
            self.status_var.set("Team roster source inspection failed")
            messagebox.showerror("Inspect Team Roster Sources", f"Team roster source inspection failed:\n{exc}")

    def open_bulk_player_rename_dialog(self):
        """Run deterministic bulk player rename via shared bulk-rename helpers."""
        try:
            data_dir = filedialog.askdirectory(
                title="Select DBDAT directory",
                initialdir=str(Path("DBDAT") if Path("DBDAT").exists() else Path(".")),
            )
            if not data_dir:
                return

            map_output = filedialog.asksaveasfilename(
                title="Save rename mapping CSV",
                defaultextension=".csv",
                initialfile="rename_map.csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            )
            if not map_output:
                return

            dry_run = messagebox.askyesno(
                "Bulk Rename Players",
                "Run in dry-run mode?\n\nYes = write mapping CSV only\nNo = rename players and write mapping",
            )
            self.status_var.set("Running bulk player rename...")
            self.root.update_idletasks()
            result = bulk_rename_players(data_dir, map_output, dry_run=dry_run)
            summary_lines = self._format_bulk_summary_lines(result)
            self.status_var.set(
                f"✓ Bulk player rename {'dry-run ' if dry_run else ''}complete ({result.rows_written} rows)"
            )
            messagebox.showinfo(
                "Bulk Rename Players",
                (
                    f"{'Dry run complete' if dry_run else 'Bulk rename complete'}\n\n"
                    f"Files processed: {result.files_processed}\n"
                    f"Rows written: {result.rows_written}\n"
                    f"Mapping: {result.map_output}\n\n"
                    + "\n".join(summary_lines)
                ),
            )
        except Exception as exc:
            self.status_var.set("Bulk player rename failed")
            messagebox.showerror("Bulk Rename Players", f"Bulk rename failed:\n{exc}")

    def open_bulk_player_revert_dialog(self):
        """Revert deterministic bulk player rename using a mapping CSV."""
        try:
            data_dir = filedialog.askdirectory(
                title="Select DBDAT directory",
                initialdir=str(Path("DBDAT") if Path("DBDAT").exists() else Path(".")),
            )
            if not data_dir:
                return

            map_input = filedialog.askopenfilename(
                title="Select rename mapping CSV",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                initialdir=str(Path(".")),
            )
            if not map_input:
                return

            dry_run = messagebox.askyesno(
                "Revert Bulk Player Rename",
                "Run in dry-run mode?\n\nYes = validate only\nNo = revert player names",
            )
            self.status_var.set("Running bulk player rename revert...")
            self.root.update_idletasks()
            result = revert_player_renames(data_dir, map_input, dry_run=dry_run)
            summary_lines = self._format_bulk_summary_lines(result)
            self.status_var.set(
                f"✓ Bulk player revert {'dry-run ' if dry_run else ''}complete ({result.rows_processed} rows)"
            )
            messagebox.showinfo(
                "Revert Bulk Player Rename",
                (
                    f"{'Dry run complete' if dry_run else 'Bulk revert complete'}\n\n"
                    f"Files processed: {result.files_processed}\n"
                    f"Rows processed: {result.rows_processed}\n"
                    f"Mapping: {result.map_input}\n\n"
                    + "\n".join(summary_lines)
                ),
            )
        except Exception as exc:
            self.status_var.set("Bulk player revert failed")
            messagebox.showerror("Revert Bulk Player Rename", f"Bulk revert failed:\n{exc}")

    def open_player_batch_edit_dialog(self):
        """Apply the shared CSV-driven player edit plan against the current player file."""
        try:
            player_file = getattr(self, "file_path", None) or "DBDAT/JUG98030.FDI"
            csv_path = filedialog.askopenfilename(
                title="Select player batch-edit CSV",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                initialdir=str(Path(".")),
            )
            if not csv_path:
                return

            dry_run = messagebox.askyesno(
                "Batch Edit Players from CSV",
                (
                    f"Apply plan to:\n{player_file}\n\n"
                    "Run in dry-run mode?\n\n"
                    "Yes = validate and stage only\n"
                    "No = write changes immediately"
                ),
            )
            self.status_var.set("Running player batch edit...")
            self.root.update_idletasks()
            result = batch_edit_player_metadata_records(
                file_path=player_file,
                csv_path=csv_path,
                write_changes=not dry_run,
            )
            warning_count = len(getattr(result, "warnings", []) or [])
            status_suffix = "dry-run " if dry_run else ""
            self.status_var.set(
                f"✓ Player batch edit {status_suffix}complete ({len(getattr(result, 'changes', []) or [])} changed, {warning_count} warning(s))"
            )

            summary_lines = [
                f"{'Dry run complete' if dry_run else 'Batch edit complete'}",
                "",
                f"Player file: {player_file}",
                f"Plan: {csv_path}",
                f"Rows read: {getattr(result, 'row_count', 0)}",
                f"Matched rows: {getattr(result, 'matched_row_count', 0)}",
                f"Records changed: {len(getattr(result, 'changes', []) or [])}",
                f"Warnings: {warning_count}",
            ]
            backup_path = getattr(result, "backup_path", None)
            if backup_path:
                summary_lines.append(f"Backup: {backup_path}")
            if warning_count:
                first_warning = getattr(result, "warnings", [None])[0]
                if first_warning is not None:
                    summary_lines.extend(
                        [
                            "",
                            "First warning:",
                            str(getattr(first_warning, "message", first_warning)),
                        ]
                    )
            if not dry_run:
                summary_lines.extend(
                    [
                        "",
                        "Reload the database view to refresh the player list if needed.",
                    ]
                )

            messagebox.showinfo("Batch Edit Players from CSV", "\n".join(summary_lines))
        except Exception as exc:
            self.status_var.set("Player batch edit failed")
            messagebox.showerror("Batch Edit Players from CSV", f"Player batch edit failed:\n{exc}")

    def open_team_roster_batch_edit_dialog(self):
        """Apply a shared CSV-driven batch plan against the current team roster file."""
        try:
            team_file = getattr(self, "team_file_path", None) or "DBDAT/EQ98030.FDI"
            player_file = getattr(self, "file_path", None) or "DBDAT/JUG98030.FDI"
            csv_path = filedialog.askopenfilename(
                title="Select team roster batch-edit CSV",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                initialdir=str(Path(".")),
            )
            if not csv_path:
                return

            dry_run = messagebox.askyesno(
                "Batch Edit Team Roster from CSV",
                (
                    f"Apply roster plan to:\n{team_file}\n\n"
                    "Run in dry-run mode?\n\n"
                    "Yes = validate and stage only\n"
                    "No = write changes immediately"
                ),
            )
            self.status_var.set("Running team roster batch edit...")
            self.root.update_idletasks()
            result = batch_edit_team_roster_records(
                team_file=team_file,
                player_file=player_file,
                csv_path=csv_path,
                write_changes=not dry_run,
            )
            linked_count = len(getattr(result, "linked_changes", []) or [])
            same_entry_count = len(getattr(result, "same_entry_changes", []) or [])
            warning_count = len(getattr(result, "warnings", []) or [])
            total_changes = linked_count + same_entry_count
            status_suffix = "dry-run " if dry_run else ""
            self.status_var.set(
                f"✓ Team roster batch edit {status_suffix}complete "
                f"({total_changes} changed, {warning_count} warning(s))"
            )

            if not dry_run and hasattr(self, "load_current_team_roster"):
                try:
                    self.load_current_team_roster()
                except Exception:
                    pass

            summary_lines = [
                f"{'Dry run complete' if dry_run else 'Batch edit complete'}",
                "",
                f"Team file: {team_file}",
                f"Player file: {player_file}",
                f"Plan: {csv_path}",
                f"Rows read: {getattr(result, 'row_count', 0)}",
                f"Matched rows: {getattr(result, 'matched_row_count', 0)}",
                f"Linked rows changed: {linked_count}",
                f"Same-entry rows changed: {same_entry_count}",
                f"Warnings: {warning_count}",
            ]
            backup_path = getattr(result, "backup_path", None)
            if backup_path:
                summary_lines.append(f"Backup: {backup_path}")
            if warning_count:
                first_warning = getattr(result, "warnings", [None])[0]
                if first_warning is not None:
                    summary_lines.extend(
                        [
                            "",
                            "First warning:",
                            str(getattr(first_warning, "message", first_warning)),
                        ]
                    )
            if not dry_run:
                summary_lines.extend(
                    [
                        "",
                        "Reload or switch teams if you need to inspect a different updated roster immediately.",
                    ]
                )

            messagebox.showinfo("Batch Edit Team Roster from CSV", "\n".join(summary_lines))
        except Exception as exc:
            self.status_var.set("Team roster batch edit failed")
            messagebox.showerror("Batch Edit Team Roster from CSV", f"Team roster batch edit failed:\n{exc}")

    def open_team_roster_edit_linked_dialog(self):
        """Patch one parser-backed linked EQ->JUG roster slot via the GUI."""
        try:
            team_file = getattr(self, "team_file_path", None) or "DBDAT/EQ98030.FDI"
            player_file = getattr(self, "file_path", None) or "DBDAT/JUG98030.FDI"
            current_team = getattr(self, "current_team", None)
            team_query = ""
            if isinstance(current_team, tuple) and len(current_team) >= 2:
                team_query = str(getattr(current_team[1], "name", "") or "").strip()
            if not team_query:
                team_query = str(
                    simpledialog.askstring(
                        "Edit Linked Team Roster Slot",
                        "Team query:",
                        initialvalue="",
                    )
                    or ""
                ).strip()
            if not team_query:
                return

            slot_text = simpledialog.askstring(
                "Edit Linked Team Roster Slot",
                "Slot number (1-based):",
                initialvalue="1",
            )
            if slot_text is None:
                return
            slot_text = str(slot_text).strip()
            if not slot_text:
                messagebox.showerror("Edit Linked Team Roster Slot", "Slot number is required.")
                return
            slot_number = int(slot_text, 0)

            player_id_text = simpledialog.askstring(
                "Edit Linked Team Roster Slot",
                "New player record ID (optional):",
                initialvalue="",
            )
            if player_id_text is None:
                return
            player_id_text = str(player_id_text).strip()
            player_record_id = int(player_id_text, 0) if player_id_text else None

            flag_text = simpledialog.askstring(
                "Edit Linked Team Roster Slot",
                "New flag byte (optional):",
                initialvalue="",
            )
            if flag_text is None:
                return
            flag_text = str(flag_text).strip()
            flag = int(flag_text, 0) if flag_text else None

            if player_record_id is None and flag is None:
                messagebox.showinfo("Edit Linked Team Roster Slot", "No changes requested.")
                return

            dry_run = messagebox.askyesno(
                "Edit Linked Team Roster Slot",
                (
                    f"Patch linked roster slot for:\n{team_query}\n\n"
                    "Run in dry-run mode?\n\n"
                    "Yes = validate and stage only\n"
                    "No = write changes immediately"
                ),
            )
            self.status_var.set("Running linked team roster edit...")
            self.root.update_idletasks()
            result = edit_team_roster_eq_jug_linked(
                team_file=team_file,
                player_file=player_file,
                team_query=team_query,
                slot_number=slot_number,
                player_record_id=player_record_id,
                flag=flag,
                write_changes=not dry_run,
            )
            warning_count = len(getattr(result, "warnings", []) or [])
            status_suffix = "dry-run " if dry_run else ""
            self.status_var.set(
                f"✓ Linked team roster edit {status_suffix}complete ({len(getattr(result, 'changes', []) or [])} changed, {warning_count} warning(s))"
            )

            summary_lines = [
                f"{'Dry run complete' if dry_run else 'Linked roster edit complete'}",
                "",
                f"Team file: {team_file}",
                f"Player file: {player_file}",
                f"Team query: {team_query}",
                f"Slot: {slot_number}",
                f"Rows changed: {len(getattr(result, 'changes', []) or [])}",
                f"Warnings: {warning_count}",
            ]
            if getattr(result, "changes", None):
                change = result.changes[0]
                summary_lines.extend(
                    [
                        "",
                        f"{getattr(change, 'team_name', '') or team_query}: "
                        f"pid {getattr(change, 'old_player_record_id', '')} -> {getattr(change, 'new_player_record_id', '')}, "
                        f"flag {getattr(change, 'old_flag', '')} -> {getattr(change, 'new_flag', '')}",
                    ]
                )
            backup_path = getattr(result, "backup_path", None)
            if backup_path:
                summary_lines.append(f"Backup: {backup_path}")
            if warning_count and getattr(result, "warnings", None):
                summary_lines.extend(
                    [
                        "",
                        "First warning:",
                        str(getattr(result.warnings[0], "message", result.warnings[0])),
                    ]
                )

            messagebox.showinfo("Edit Linked Team Roster Slot", "\n".join(summary_lines))
        except Exception as exc:
            self.status_var.set("Linked team roster edit failed")
            messagebox.showerror("Edit Linked Team Roster Slot", f"Linked team roster edit failed:\n{exc}")

    def _current_player_visible_skill_query(self):
        current = getattr(self, "current_record", None)
        if not (isinstance(current, tuple) and len(current) >= 2):
            return ""
        record = current[1]
        given = (getattr(record, "given_name", None) or "").strip()
        surname = (getattr(record, "surname", None) or "").strip()
        full = " ".join(part for part in (given, surname) if part).strip()
        if full:
            return full
        return (getattr(record, "name", "") or "").strip()

    def _visible_skill_stage_key(self, file_path: str, resolved_bio_name: str):
        return (str(Path(file_path)), str(resolved_bio_name).strip().upper())

    def _current_visible_skill_stage_entry(self):
        """Return staged dd6361 patch entry for the current visible-skill snapshot, if any."""
        snapshot = getattr(self, "visible_skill_snapshot", None)
        if snapshot is None:
            return None
        file_path = getattr(self, "file_path", None) or "DBDAT/JUG98030.FDI"
        if not str(file_path).lower().endswith(".fdi"):
            file_path = "DBDAT/JUG98030.FDI"
        key = self._visible_skill_stage_key(file_path, getattr(snapshot, "resolved_bio_name", ""))
        staged = getattr(self, "staged_visible_skill_patches", None)
        if not isinstance(staged, dict):
            return None
        return staged.get(key)

    def _visible_skill_status_text(self, snapshot=None):
        """Build a compact status line for the dd6361 visible-skill panel."""
        snapshot = snapshot if snapshot is not None else getattr(self, "visible_skill_snapshot", None)
        staged = getattr(self, "staged_visible_skill_patches", None)
        staged_count = len(staged) if isinstance(staged, dict) else 0
        if snapshot is None:
            if staged_count:
                return f"dd6361 visible skills: not loaded | {staged_count} staged patch(es)"
            return "dd6361 visible skills: not loaded"
        base = f"dd6361 visible skills loaded: {getattr(snapshot, 'resolved_bio_name', '')}"
        current_stage = self._current_visible_skill_stage_entry()
        if current_stage:
            return base + f" | staged patch pending ({len(current_stage.get('updates', {}))} field(s))"
        if staged_count:
            return base + f" | {staged_count} staged patch(es)"
        return base

    def _set_visible_skill_panel_unavailable(self, reason: str = "unavailable"):
        try:
            self.visible_skill_snapshot = None
            self.visible_skill_baseline = {}
            for field, var in getattr(self, "visible_skill_vars", {}).items():
                try:
                    var.set(0)
                except Exception:
                    pass
            if hasattr(self, "visible_skill_status_var"):
                status = f"dd6361 visible skills: {reason}"
                staged = getattr(self, "staged_visible_skill_patches", None)
                if isinstance(staged, dict) and staged:
                    status += f" | {len(staged)} staged patch(es)"
                self.visible_skill_status_var.set(status)
        except Exception:
            pass

    def refresh_visible_skill_panel(self, show_dialog_errors: bool = False):
        """Load verified dd6361 mapped10 visible stats for the currently selected player."""
        try:
            file_path = getattr(self, "file_path", None) or "DBDAT/JUG98030.FDI"
            if not str(file_path).lower().endswith(".fdi"):
                file_path = "DBDAT/JUG98030.FDI"
            query = self._current_player_visible_skill_query()
            if not query:
                self._set_visible_skill_panel_unavailable("no player selected")
                return None

            snapshot = inspect_player_visible_skills_dd6361(
                file_path=file_path,
                player_name=query,
            )
            self.visible_skill_snapshot = snapshot
            self.visible_skill_baseline = {
                field: int(snapshot.mapped10.get(field, 0))
                for field in getattr(self, "visible_skill_field_order", snapshot.mapped10_order)
            }
            for field in getattr(self, "visible_skill_field_order", snapshot.mapped10_order):
                if field in getattr(self, "visible_skill_vars", {}):
                    self.visible_skill_vars[field].set(int(snapshot.mapped10.get(field, 0)))
            if hasattr(self, "visible_skill_status_var"):
                self.visible_skill_status_var.set(self._visible_skill_status_text(snapshot))
            return snapshot
        except Exception as exc:
            self._set_visible_skill_panel_unavailable(f"error ({exc})")
            if show_dialog_errors:
                messagebox.showerror("Visible Skills (dd6361)", f"Failed to load visible skills:\n{exc}")
            return None

    def _collect_visible_skill_panel_updates(self):
        """Return changed mapped10 fields from the dd6361 visible-skill panel."""
        snapshot = getattr(self, "visible_skill_snapshot", None)
        if snapshot is None:
            return None, "No dd6361 visible-skill snapshot is loaded"

        updates = {}
        field_order = getattr(self, "visible_skill_field_order", getattr(snapshot, "mapped10_order", []))
        baseline = getattr(self, "visible_skill_baseline", {}) or {}
        for field in field_order:
            if field not in getattr(self, "visible_skill_vars", {}):
                continue
            try:
                new_val = int(self.visible_skill_vars[field].get())
            except Exception as exc:
                return None, f"Invalid value for {field}: {exc}"
            old_val = int(baseline.get(field, snapshot.mapped10.get(field, 0)))
            if new_val != old_val:
                updates[field] = new_val
        return updates, None

    def stage_visible_skill_panel_changes(self):
        """Stage panel-visible dd6361 mapped10 edits for the next Save Database run."""
        snapshot = getattr(self, "visible_skill_snapshot", None)
        if snapshot is None:
            snapshot = self.refresh_visible_skill_panel(show_dialog_errors=True)
            if snapshot is None:
                return

        updates, err = self._collect_visible_skill_panel_updates()
        if err:
            messagebox.showerror("Visible Skills (dd6361)", err)
            return
        if not updates:
            messagebox.showinfo("Visible Skills (dd6361)", "No visible skill changes to stage.")
            return

        file_path = getattr(self, "file_path", None) or "DBDAT/JUG98030.FDI"
        if not str(file_path).lower().endswith(".fdi"):
            file_path = "DBDAT/JUG98030.FDI"

        key = self._visible_skill_stage_key(file_path, snapshot.resolved_bio_name)
        staged = getattr(self, "staged_visible_skill_patches", None)
        if not isinstance(staged, dict):
            self.staged_visible_skill_patches = {}
            staged = self.staged_visible_skill_patches
        staged[key] = {
            "file_path": str(file_path),
            "player_name": str(snapshot.resolved_bio_name),
            "updates": dict(updates),
            "target_query": str(getattr(snapshot, "target_query", snapshot.resolved_bio_name)),
        }

        changed_lines = [
            f"{field}: {self.visible_skill_baseline.get(field, snapshot.mapped10.get(field))} -> {value}"
            for field, value in updates.items()
        ]
        self.status_var.set(
            f"✓ Staged dd6361 visible skills for {snapshot.resolved_bio_name} (save database to persist)"
        )
        try:
            self.visible_skill_status_var.set(self._visible_skill_status_text(snapshot))
        except Exception:
            pass
        messagebox.showinfo(
            "Visible Skills (dd6361)",
            (
                "Visible skill changes staged for Save Database.\n\n"
                f"Player: {snapshot.resolved_bio_name}\n"
                f"File: {file_path}\n\n"
                "Changed fields:\n"
                + "\n".join(changed_lines[:10])
                + (f"\n... and {len(changed_lines) - 10} more" if len(changed_lines) > 10 else "")
            ),
        )

    def discard_visible_skill_panel_staged_changes(self):
        """Discard the staged dd6361 visible-skill patch for the currently loaded player snapshot."""
        snapshot = getattr(self, "visible_skill_snapshot", None)
        if snapshot is None:
            messagebox.showinfo("Visible Skills (dd6361)", "No dd6361 visible-skill snapshot is loaded.")
            return

        file_path = getattr(self, "file_path", None) or "DBDAT/JUG98030.FDI"
        if not str(file_path).lower().endswith(".fdi"):
            file_path = "DBDAT/JUG98030.FDI"
        key = self._visible_skill_stage_key(file_path, getattr(snapshot, "resolved_bio_name", ""))
        staged = getattr(self, "staged_visible_skill_patches", None)
        if not isinstance(staged, dict) or key not in staged:
            messagebox.showinfo("Visible Skills (dd6361)", "No staged visible-skill patch exists for this player.")
            return

        staged_item = staged.pop(key)
        self.status_var.set(f"Discarded staged dd6361 visible-skill patch for {snapshot.resolved_bio_name}")
        try:
            self.visible_skill_status_var.set(self._visible_skill_status_text(snapshot))
        except Exception:
            pass

        # Reset UI values back to baseline for the current snapshot.
        for field, baseline_val in (getattr(self, "visible_skill_baseline", {}) or {}).items():
            if field in getattr(self, "visible_skill_vars", {}):
                try:
                    self.visible_skill_vars[field].set(int(baseline_val))
                except Exception:
                    pass

        changed_fields = ", ".join(sorted((staged_item.get("updates") or {}).keys()))
        messagebox.showinfo(
            "Visible Skills (dd6361)",
            f"Discarded staged patch for {snapshot.resolved_bio_name}."
            + (f"\nFields: {changed_fields}" if changed_fields else ""),
        )

    def review_staged_visible_skill_patches(self):
        """Show a summary of staged dd6361 visible-skill patches pending Save Database."""
        staged = getattr(self, "staged_visible_skill_patches", None)
        if not isinstance(staged, dict) or not staged:
            messagebox.showinfo("Visible Skills (dd6361)", "No staged dd6361 visible-skill patches.")
            return

        current_key = None
        snapshot = getattr(self, "visible_skill_snapshot", None)
        if snapshot is not None:
            try:
                file_path = getattr(self, "file_path", None) or "DBDAT/JUG98030.FDI"
                if not str(file_path).lower().endswith(".fdi"):
                    file_path = "DBDAT/JUG98030.FDI"
                current_key = self._visible_skill_stage_key(file_path, getattr(snapshot, "resolved_bio_name", ""))
            except Exception:
                current_key = None

        lines = []
        for idx, (_key, item) in enumerate(
            sorted(staged.items(), key=lambda kv: (kv[1].get("file_path", ""), kv[1].get("player_name", "")))
        ):
            if idx >= 20:
                lines.append(f"... and {len(staged) - 20} more staged patch(es)")
                break
            updates = item.get("updates") or {}
            update_preview = ", ".join(f"{k}={v}" for k, v in sorted(updates.items())[:6])
            if len(updates) > 6:
                update_preview += f", ... (+{len(updates) - 6} more)"
            line = (
                f"{item.get('player_name')} [{Path(str(item.get('file_path'))).name}]"
                + (f": {update_preview}" if update_preview else "")
            )
            if current_key is not None and _key == current_key:
                line += " [current]"
            lines.append(line)

        messagebox.showinfo(
            "Visible Skills (dd6361)",
            (
                f"Staged dd6361 visible-skill patches pending Save Database ({len(staged)} total):\n\n"
                + "\n".join(lines)
            ),
        )

    def _apply_staged_visible_skill_patches(self, create_backups: bool = False):
        """
        Apply staged dd6361 visible-skill patches immediately.

        Intended for Save Database integration. Returns a list of backend patch results.
        """
        staged = getattr(self, "staged_visible_skill_patches", None)
        if not isinstance(staged, dict) or not staged:
            return []

        results = []
        # Apply in a stable order for reproducibility.
        for _key, item in sorted(staged.items(), key=lambda kv: (kv[1].get("file_path", ""), kv[1].get("player_name", ""))):
            result = patch_player_visible_skills_dd6361(
                file_path=str(item["file_path"]),
                player_name=str(item["player_name"]),
                updates=dict(item.get("updates") or {}),
                output_file=None,
                in_place=True,
                create_backup_before_write=create_backups,
                json_output=None,
            )
            results.append(result)

        # Refresh current player file bytes/panel if we touched the open player file.
        try:
            current_file = str(getattr(self, "file_path", "") or "")
            if current_file and any(str(getattr(r, "file_path", "")) == current_file for r in results):
                self.file_data = Path(current_file).read_bytes()
                self.refresh_visible_skill_panel(show_dialog_errors=False)
        except Exception:
            pass

        self.staged_visible_skill_patches.clear()
        try:
            self.visible_skill_status_var.set(self._visible_skill_status_text(getattr(self, "visible_skill_snapshot", None)))
        except Exception:
            pass
        return results

    def patch_visible_skill_panel_in_place(self):
        """Patch current panel changes in-place via dd6361 backend (with backup)."""
        snapshot = getattr(self, "visible_skill_snapshot", None)
        if snapshot is None:
            snapshot = self.refresh_visible_skill_panel(show_dialog_errors=True)
            if snapshot is None:
                return

        updates, err = self._collect_visible_skill_panel_updates()
        if err:
            messagebox.showerror("Visible Skills (dd6361)", err)
            return
        if not updates:
            messagebox.showinfo("Visible Skills (dd6361)", "No visible skill changes to patch.")
            return

        file_path = getattr(self, "file_path", None) or "DBDAT/JUG98030.FDI"
        if not str(file_path).lower().endswith(".fdi"):
            file_path = "DBDAT/JUG98030.FDI"

        changed_lines = [
            f"{field}: {self.visible_skill_baseline.get(field, snapshot.mapped10.get(field))} -> {value}"
            for field, value in updates.items()
        ]
        if not messagebox.askyesno(
            "Visible Skills (dd6361)",
            (
                "Patch visible skills in place for the currently selected player?\n\n"
                f"Player: {snapshot.resolved_bio_name}\n"
                f"File: {file_path}\n"
                "A backup will be created automatically.\n\n"
                + "\n".join(changed_lines[:10])
            ),
        ):
            return

        try:
            self.status_var.set("Patching dd6361 visible skills (in-place)...")
            self.root.update_idletasks()
            result = patch_player_visible_skills_dd6361(
                file_path=file_path,
                player_name=snapshot.resolved_bio_name,
                updates=updates,
                output_file=None,
                in_place=True,
                create_backup_before_write=True,
                json_output=None,
            )
            try:
                key = self._visible_skill_stage_key(file_path, result.resolved_bio_name)
                if isinstance(getattr(self, "staged_visible_skill_patches", None), dict):
                    self.staged_visible_skill_patches.pop(key, None)
            except Exception:
                pass
            try:
                if Path(file_path).resolve() == Path(getattr(self, "file_path", "")).resolve():
                    self.file_data = Path(file_path).read_bytes()
            except Exception:
                pass
            # Re-read to refresh baseline/current values.
            refreshed = self.refresh_visible_skill_panel(show_dialog_errors=False)
            self.status_var.set(f"✓ dd6361 visible skills patched for {result.resolved_bio_name}")
            info_lines = [
                f"Player: {result.resolved_bio_name}",
                f"File: {result.output_file}",
            ]
            if result.backup_path:
                info_lines.append(f"Backup: {result.backup_path}")
            info_lines.extend(["", "Patched fields:"] + changed_lines[:10])
            if len(changed_lines) > 10:
                info_lines.append(f"... and {len(changed_lines) - 10} more")
            if refreshed is not None and getattr(refreshed, "resolved_bio_name", None):
                info_lines.append("")
                info_lines.append(f"Reloaded snapshot: {refreshed.resolved_bio_name}")
            messagebox.showinfo("Visible Skills (dd6361)", "\n".join(info_lines))
        except Exception as exc:
            self.status_var.set("dd6361 visible skill patch failed")
            messagebox.showerror("Visible Skills (dd6361)", f"Failed to patch visible skills:\n{exc}")

    def _prompt_visible_skill_patch_assignments(self, snapshot):
        """
        Prompt for dd6361 mapped10 visible-skill edits.

        Returns a list of FIELD=VALUE assignments, an empty list for "no changes",
        or None when the user cancels. Falls back to a simple text prompt in
        headless/test contexts where a real modal dialog cannot be shown.
        """
        # Headless/test fallback (e.g. unit tests using a fake root object)
        if not hasattr(self.root, "wait_window"):
            assignment_text = simpledialog.askstring(
                "Patch Player Visible Skills",
                (
                    "Enter visible stat assignments as FIELD=VALUE.\n"
                    "Use commas or new lines to provide multiple values.\n\n"
                    "Supported fields: speed, stamina, aggression, quality,\n"
                    "handling, passing, dribbling, heading, tackling, shooting"
                ),
                initialvalue="\n".join(
                    f"{field}={snapshot.mapped10.get(field, 0)}"
                    for field in getattr(snapshot, "mapped10_order", [])
                ),
            )
            if assignment_text is None:
                return None
            return [
                item.strip()
                for item in re.split(r"[\n,]+", assignment_text)
                if item and item.strip()
            ]

        dialog = tk.Toplevel(self.root)
        dialog.title("Patch Player Visible Skills (dd6361)")
        try:
            dialog.transient(self.root)
            dialog.grab_set()
        except Exception:
            pass
        dialog.resizable(False, False)

        result = {"assignments": None}
        vars_by_field = {}
        initial_values = {field: int(snapshot.mapped10.get(field, 0)) for field in snapshot.mapped10_order}

        body = ttk.Frame(dialog, padding=10)
        body.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            body,
            text=f"Player: {getattr(snapshot, 'resolved_bio_name', '')}",
            font=("TkDefaultFont", 10, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 4))
        ttk.Label(
            body,
            text="Edit verified visible stats (dd6361 mapped10). Only changed fields will be patched.",
        ).grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(0, 8))

        for idx, field in enumerate(snapshot.mapped10_order):
            row = 2 + idx
            label = field.replace("_", " ").title()
            ttk.Label(body, text=label + ":").grid(row=row, column=0, sticky=tk.W, padx=(0, 8), pady=2)
            var = tk.IntVar(value=initial_values[field])
            vars_by_field[field] = var
            spin = ttk.Spinbox(body, from_=0, to=255, textvariable=var, width=8)
            spin.grid(row=row, column=1, sticky=tk.W, pady=2)
            ttk.Label(body, text=f"(current {initial_values[field]})").grid(
                row=row, column=2, sticky=tk.W, padx=(8, 0), pady=2
            )
            if idx == 0:
                try:
                    spin.focus_set()
                    spin.selection_range(0, tk.END)
                except Exception:
                    pass

        button_row = 2 + len(snapshot.mapped10_order)
        button_frame = ttk.Frame(body)
        button_frame.grid(row=button_row, column=0, columnspan=3, sticky=tk.EW, pady=(10, 0))

        def _collect_assignments():
            assignments = []
            for field in snapshot.mapped10_order:
                try:
                    value = int(vars_by_field[field].get())
                except Exception as exc:
                    messagebox.showerror(
                        "Patch Player Visible Skills",
                        f"Invalid value for {field}: {exc}",
                        parent=dialog,
                    )
                    return None
                if value != initial_values[field]:
                    assignments.append(f"{field}={value}")
            return assignments

        def _on_apply():
            assignments = _collect_assignments()
            if assignments is None:
                return
            result["assignments"] = assignments
            dialog.destroy()

        def _on_cancel():
            result["assignments"] = None
            dialog.destroy()

        ttk.Button(button_frame, text="Cancel", command=_on_cancel).pack(side=tk.RIGHT)
        ttk.Button(button_frame, text="Patch", command=_on_apply).pack(side=tk.RIGHT, padx=(0, 6))

        try:
            dialog.bind("<Return>", lambda _e: _on_apply())
            dialog.bind("<Escape>", lambda _e: _on_cancel())
            dialog.protocol("WM_DELETE_WINDOW", _on_cancel)
        except Exception:
            pass

        self.root.wait_window(dialog)
        return result["assignments"]

    def open_player_skill_patch_dialog(self):
        """
        Patch verified visible player stats (dd6361 mapped10) using the shared backend action.

        This is intentionally separate from the legacy player attribute editor because the
        current on-screen PM99 stat mapping is only verified for the dd6361 biography trailer
        path (core4 + 6 technical skills).
        """
        try:
            default_query = ""
            current = getattr(self, "current_record", None)
            if isinstance(current, tuple) and len(current) >= 2:
                record = current[1]
                default_query = " ".join(
                    part for part in [getattr(record, "given_name", None), getattr(record, "surname", None)] if part
                ).strip()
                if not default_query:
                    default_query = (getattr(record, "name", "") or "").strip()

            player_file = getattr(self, "file_path", None) or "DBDAT/JUG98030.FDI"
            if not str(player_file).lower().endswith(".fdi"):
                player_file = "DBDAT/JUG98030.FDI"

            player_file = filedialog.askopenfilename(
                title="Select player database (JUG*.FDI)",
                filetypes=[("FDI files", "*.FDI"), ("All files", "*.*")],
                initialdir=str(Path(player_file).parent if player_file else Path("DBDAT")),
                initialfile=Path(player_file).name if player_file else "JUG98030.FDI",
            )
            if not player_file:
                return

            name_query = simpledialog.askstring(
                "Patch Player Visible Skills",
                "Player name query (dd6361 bio name):",
                initialvalue=default_query or "",
            )
            if not name_query:
                return

            # Prefill with the current verified mapped10 values for the selected/player query.
            snapshot = inspect_player_visible_skills_dd6361(
                file_path=player_file,
                player_name=name_query,
            )
            prompt_assignments = getattr(self, "_prompt_visible_skill_patch_assignments", None)
            if not callable(prompt_assignments):
                prompt_assignments = lambda snap: PM99DatabaseEditor._prompt_visible_skill_patch_assignments(self, snap)
            assignment_items = prompt_assignments(snapshot)
            if assignment_items is None:
                return
            if not assignment_items:
                messagebox.showinfo("Patch Player Visible Skills", "No visible skill changes were selected.")
                return

            in_place = messagebox.askyesno(
                "Patch Player Visible Skills",
                (
                    "Patch in place?\n\n"
                    "Yes = patch the selected JUG*.FDI directly and create a backup\n"
                    "No = write a patched copy (recommended)"
                ),
            )

            output_file = None
            if not in_place:
                default_out = Path(player_file).with_name(Path(player_file).stem + ".dd6361_patched.FDI")
                output_file = filedialog.asksaveasfilename(
                    title="Save patched player database copy",
                    defaultextension=".FDI",
                    initialfile=default_out.name,
                    initialdir=str(default_out.parent),
                    filetypes=[("FDI files", "*.FDI"), ("All files", "*.*")],
                )
                if not output_file:
                    return

            self.status_var.set("Running dd6361 visible skill patch...")
            self.root.update_idletasks()

            updates = parse_player_skill_patch_assignments(assignment_items)
            result = patch_player_visible_skills_dd6361(
                file_path=player_file,
                player_name=name_query,
                updates=updates,
                output_file=output_file,
                in_place=in_place,
                create_backup_before_write=in_place,
                json_output=None,
            )

            # Refresh cached bytes if we patched the currently open player file in-place.
            try:
                if result.in_place and Path(player_file).resolve() == Path(getattr(self, "file_path", "")).resolve():
                    self.file_data = Path(player_file).read_bytes()
            except Exception:
                pass

            changed_lines = []
            for field in result.mapped10_order:
                if field in result.updates_requested:
                    changed_lines.append(
                        f"{field}: {result.mapped10_before.get(field)} -> {result.mapped10_after.get(field)}"
                    )
            if len(changed_lines) > 10:
                changed_lines = changed_lines[:10] + [f"... and {len(result.updates_requested) - 10} more"]

            self.status_var.set(
                f"✓ Visible skill patch {'applied' if result.in_place else 'copy written'} for {result.resolved_bio_name}"
            )
            summary = [
                f"Player: {result.resolved_bio_name}",
                f"Resolved from query: {snapshot.target_query}",
                f"File: {result.output_file}",
            ]
            if result.backup_path:
                summary.append(f"Backup: {result.backup_path}")
            if result.touched_entry_offsets:
                touched_preview = ", ".join(f"0x{off:08X}" for off in result.touched_entry_offsets[:5])
                summary.append(f"Touched entry offsets: {touched_preview}")
            if changed_lines:
                summary.extend(["", "Changed fields:"] + changed_lines)
            messagebox.showinfo("Patch Player Visible Skills", "\n".join(summary))
        except Exception as exc:
            self.status_var.set("Visible skill patch failed")
            messagebox.showerror("Patch Player Visible Skills", f"Visible skill patch failed:\n{exc}")

    def open_pkf_viewer(self) -> None:
        """Open a PKF archive in a lightweight inspection window."""
 
        initial_dir = str(self._pkf_last_dir)
        file_path = filedialog.askopenfilename(
            title="Select PKF file",
            initialdir=initial_dir,
            filetypes=(("PKF archives", "*.pkf"), ("All files", "*.*")),
        )
        if not file_path:
            return
 
        chosen_path = Path(file_path)
        try:
            data = chosen_path.read_bytes()
        except Exception as exc:
            messagebox.showerror("PKF Viewer", f"Failed to read file:\n{exc}")
            self.status_var.set("Error reading PKF file")
            return
 
        try:
            pkf_file = PKFFile.from_bytes(chosen_path.name, data)
        except Exception as exc:
            messagebox.showerror("PKF Viewer", f"Failed to parse PKF file:\n{exc}")
            self.status_var.set("Error parsing PKF file")
            return
 
        self._pkf_last_dir = chosen_path.parent
        self._show_pkf_viewer_window(chosen_path, pkf_file, data)
        self.status_var.set(f"Opened PKF viewer for {chosen_path.name} ({len(pkf_file)} entries)")
 
    def _show_pkf_viewer_window(self, file_path: Path, pkf_file: PKFFile, raw_bytes: bytes) -> None:
        """Render the PKF inspection window."""
 
        viewer = tk.Toplevel(self.root)
        viewer.title(f"PKF Viewer — {file_path.name}")
        viewer.geometry("1000x700")
        viewer.minsize(800, 500)
 
        header = ttk.Frame(viewer, padding=(10, 10, 10, 0))
        header.pack(fill=tk.X)
        ttk.Label(header, text=str(file_path), font=("TkDefaultFont", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(
            header,
            text=f"{len(pkf_file)} entries · format: {pkf_file.format_hint} · {len(raw_bytes)} bytes",
        ).pack(anchor=tk.W)
 
        # Controls frame
        controls_frame = ttk.Frame(viewer, padding=(10, 5, 10, 10))
        controls_frame.pack(fill=tk.X)
 
        # Data transformation controls
        transform_frame = ttk.LabelFrame(controls_frame, text="Data Transformation", padding="5")
        transform_frame.pack(side=tk.LEFT, padx=(0, 10))
 
        # XOR controls
        ttk.Label(transform_frame, text="XOR Key:").grid(row=0, column=0, sticky=tk.W, padx=5)
        xor_key_var = tk.StringVar(value="0x00")
        xor_key_entry = ttk.Entry(transform_frame, textvariable=xor_key_var, width=10)
        xor_key_entry.grid(row=0, column=1, padx=5)
 
        xor_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(transform_frame, text="Apply XOR", variable=xor_enabled_var,
                       command=lambda: update_preview(tree.selection()[0] if tree.selection() else None)).grid(row=0, column=2, padx=5)
 
        # Additional transformations
        ttk.Label(transform_frame, text="Encoding:").grid(row=1, column=0, sticky=tk.W, padx=5)
        encoding_var = tk.StringVar(value="raw")
        encoding_combo = ttk.Combobox(transform_frame, textvariable=encoding_var,
                                     values=["raw", "utf-8", "cp1252", "latin1"], width=8, state="readonly")
        encoding_combo.grid(row=1, column=1, padx=5)
        encoding_combo.bind("<<ComboboxSelected>>", lambda e: update_preview(tree.selection()[0] if tree.selection() else None))
 
        bit_ops_var = tk.StringVar(value="none")
        ttk.Label(transform_frame, text="Bit Ops:").grid(row=1, column=2, sticky=tk.W, padx=5)
        bit_ops_combo = ttk.Combobox(transform_frame, textvariable=bit_ops_var,
                                    values=["none", "reverse_bits", "swap_endian"], width=12, state="readonly")
        bit_ops_combo.grid(row=1, column=3, padx=5)
        bit_ops_combo.bind("<<ComboboxSelected>>", lambda e: update_preview(tree.selection()[0] if tree.selection() else None))
 
        # Pagination controls
        pagination_frame = ttk.LabelFrame(controls_frame, text="View Options", padding="5")
        pagination_frame.pack(side=tk.LEFT, padx=(0, 10))
 
        ttk.Label(pagination_frame, text="Lines per page:").grid(row=0, column=0, sticky=tk.W, padx=5)
        lines_per_page_var = tk.IntVar(value=50)
        lines_spinbox = ttk.Spinbox(pagination_frame, from_=10, to=1000, textvariable=lines_per_page_var, width=8)
        lines_spinbox.grid(row=0, column=1, padx=5)
 
        current_page_var = tk.IntVar(value=1)
        ttk.Label(pagination_frame, text="Page:").grid(row=0, column=2, sticky=tk.W, padx=5)
        page_spinbox = ttk.Spinbox(pagination_frame, from_=1, to=9999, textvariable=current_page_var, width=6)
        page_spinbox.grid(row=0, column=3, padx=5)
 
        ttk.Button(pagination_frame, text="Go", command=lambda: update_preview(tree.selection()[0] if tree.selection() else None)).grid(row=0, column=4, padx=5)
 
        paned = ttk.PanedWindow(viewer, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
 
        # Left: entry listing
        list_frame = ttk.Frame(paned)
        paned.add(list_frame, weight=1)
 
        columns = ("offset", "length")
        tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        tree.heading("offset", text="Offset")
        tree.heading("length", text="Length")
        tree.column("offset", width=110, anchor=tk.W)
        tree.column("length", width=80, anchor=tk.E)
 
        tree_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=tree_scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
 
        entries = pkf_file.list_entries()
        entry_map = {str(entry.index): entry for entry in entries}
        for entry in entries:
            tree.insert(
                "",
                tk.END,
                iid=str(entry.index),
                values=(f"0x{entry.offset:08X}", f"{entry.length} bytes"),
            )
 
        # Right: preview pane
        preview_frame = ttk.Frame(paned)
        paned.add(preview_frame, weight=2)
 
        info_label = ttk.Label(preview_frame, text="Select an entry to preview", padding=(0, 0, 0, 5))
        info_label.pack(anchor=tk.W)
 
        text_container = ttk.Frame(preview_frame)
        text_container.pack(fill=tk.BOTH, expand=True)
 
        preview = tk.Text(text_container, wrap="none", font=("Courier New", 10))
        preview.grid(row=0, column=0, sticky="nsew")
        y_scroll = ttk.Scrollbar(text_container, orient=tk.VERTICAL, command=preview.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(text_container, orient=tk.HORIZONTAL, command=preview.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        preview.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        preview.insert("1.0", "Select an entry to view its hex preview.")
        preview.configure(state="disabled")
 
        text_container.rowconfigure(0, weight=1)
        text_container.columnconfigure(0, weight=1)
 
        def get_transformed_data(raw_data: bytes) -> bytes:
            """Apply transformations to the data."""
            data = raw_data
 
            # Apply XOR if enabled
            if xor_enabled_var.get():
                try:
                    key_str = xor_key_var.get().strip()
                    if key_str.startswith('0x'):
                        key = int(key_str, 16)
                    else:
                        key = int(key_str, 10)
                    data = xor_decode(data, key)
                except (ValueError, TypeError):
                    # Invalid key, show original data
                    pass
 
            # Apply bit operations
            bit_op = bit_ops_var.get()
            if bit_op == "reverse_bits":
                data = bytes(self._reverse_bits_byte(b) for b in data)
            elif bit_op == "swap_endian":
                # Swap endianness of 16-bit words
                if len(data) % 2 == 0:
                    data = b''.join(data[i+1:i+2] + data[i:i+1] for i in range(0, len(data), 2))
 
            return data
 
        def _reverse_bits_byte(self, byte: int) -> int:
            """Reverse the bits in a byte."""
            return int('{:08b}'.format(byte)[::-1], 2)
 
        def update_preview(selected_entry_id: str) -> None:
            if not selected_entry_id:
                return
 
            entry = entry_map.get(selected_entry_id)
            if entry is None:
                return
 
            # Apply transformations
            transformed_data = get_transformed_data(entry.raw_bytes)
 
            label = f"Entry {entry.index}"
            if entry.name:
                label += f" ({entry.name})"
            transform_info = []
            if xor_enabled_var.get():
                transform_info.append(f"XOR: {xor_key_var.get()}")
            transform_str = f" · {' · '.join(transform_info)}" if transform_info else ""
            info_label.configure(
                text=f"{label} · offset 0x{entry.offset:08X} · {len(transformed_data)} bytes{transform_str}"
            )
 
            # Calculate pagination
            lines_per_page = lines_per_page_var.get()
            bytes_per_line = 16
            current_page = max(1, current_page_var.get())
            start_offset = (current_page - 1) * lines_per_page * bytes_per_line
 
            # Format with pagination
            formatted_text, has_more = _format_hex_preview(
                transformed_data,
                width=16,
                start_offset=start_offset,
                max_lines=lines_per_page
            )
 
            lines = [formatted_text]
 
            # Add page info
            total_pages = max(1, (len(transformed_data) + bytes_per_line * lines_per_page - 1) // (bytes_per_line * lines_per_page))
            current_page_var.set(min(current_page, total_pages))
            lines.append(f"\nPage {current_page_var.get()} of {total_pages}")
 
            # Try to decode with selected encoding
            encoding = encoding_var.get()
            if encoding != "raw":
                try:
                    decoded_text = transformed_data.decode(encoding)
                    lines.extend(["", f"Decoded as {encoding}:", decoded_text])
                except UnicodeDecodeError as exc:
                    lines.extend(["", f"Decoding error ({encoding}): {exc}"])
                except Exception as exc:
                    lines.extend(["", f"Error: {exc}"])
 
            try:
                decoded = pkf_file.decode_payload(transformed_data)
            except PKFDecoderError as exc:
                if encoding == "raw":  # Only show decoder error if not showing encoding
                    lines.extend(["", f"Decoder error: {exc}"])
            else:
                if not isinstance(decoded, (bytes, bytearray)):
                    lines.extend(["", "Decoded payload:", str(decoded)])
 
            preview.configure(state="normal")
            preview.delete("1.0", tk.END)
            preview.insert("1.0", "\n".join(lines))
            preview.configure(state="disabled")
 
        def on_tree_select(event) -> None:  # pragma: no cover - UI interaction
            selection = tree.selection()
            if not selection:
                return
            current_page_var.set(1)  # Reset to first page on selection change
            update_preview(selection[0])
 
        tree.bind("<<TreeviewSelect>>", on_tree_select)
 
        # Auto-select first entry if available
        children = tree.get_children()
        if children:
            first = children[0]
            tree.selection_set(first)
            tree.focus(first)
            update_preview(first)
 
    def open_pkf_searcher(self) -> None:
        """Open PKF String Searcher tool window."""
        searcher_window = tk.Toplevel(self.root)
        searcher_window.title("PKF String Searcher")
        searcher_window.geometry("1200x800")
        searcher_window.minsize(900, 600)
        
        # Directory selection
        dir_frame = ttk.LabelFrame(searcher_window, text="Search Location", padding="10")
        dir_frame.pack(fill=tk.X, padx=10, pady=10)
        
        dir_var = tk.StringVar(value=str(self._pkf_last_dir))
        ttk.Label(dir_frame, text="Directory:").pack(side=tk.LEFT, padx=5)
        dir_entry = ttk.Entry(dir_frame, textvariable=dir_var, width=50)
        dir_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        def browse_dir():
            from tkinter import filedialog
            directory = filedialog.askdirectory(initialdir=dir_var.get())
            if directory:
                dir_var.set(directory)
        
        ttk.Button(dir_frame, text="Browse...", command=browse_dir).pack(side=tk.LEFT, padx=5)
        
        # Search controls
        search_frame = ttk.LabelFrame(searcher_window, text="Search Parameters", padding="10")
        search_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        # Query input
        query_frame = ttk.Frame(search_frame)
        query_frame.pack(fill=tk.X, pady=5)
        ttk.Label(query_frame, text="Search Query:").pack(side=tk.LEFT, padx=5)
        query_var = tk.StringVar()
        query_entry = ttk.Entry(query_frame, textvariable=query_var, width=40)
        query_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Search mode
        mode_frame = ttk.Frame(search_frame)
        mode_frame.pack(fill=tk.X, pady=5)
        ttk.Label(mode_frame, text="Mode:").pack(side=tk.LEFT, padx=5)
        mode_var = tk.StringVar(value="text")
        ttk.Radiobutton(mode_frame, text="Text", variable=mode_var, value="text").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(mode_frame, text="Regex", variable=mode_var, value="regex").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(mode_frame, text="Hex", variable=mode_var, value="hex").pack(side=tk.LEFT, padx=5)
        
        # Options row 1
        opts1_frame = ttk.Frame(search_frame)
        opts1_frame.pack(fill=tk.X, pady=5)
        
        case_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts1_frame, text="Case sensitive", variable=case_var).pack(side=tk.LEFT, padx=5)
        
        recursive_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts1_frame, text="Recursive", variable=recursive_var).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(opts1_frame, text="Encoding:").pack(side=tk.LEFT, padx=(20, 5))
        encoding_var = tk.StringVar(value="utf-8")
        encoding_combo = ttk.Combobox(opts1_frame, textvariable=encoding_var,
                                     values=["utf-8", "cp1252", "latin1", "raw"], width=10, state="readonly")
        encoding_combo.pack(side=tk.LEFT, padx=5)
        
        # Options row 2 (XOR and context)
        opts2_frame = ttk.Frame(search_frame)
        opts2_frame.pack(fill=tk.X, pady=5)
        
        xor_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts2_frame, text="XOR decode:", variable=xor_enabled_var).pack(side=tk.LEFT, padx=5)
        xor_key_var = tk.StringVar(value="0x00")
        xor_entry = ttk.Entry(opts2_frame, textvariable=xor_key_var, width=8)
        xor_entry.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(opts2_frame, text="Context bytes:").pack(side=tk.LEFT, padx=(20, 5))
        context_var = tk.IntVar(value=32)
        ttk.Spinbox(opts2_frame, from_=8, to=256, textvariable=context_var, width=8).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(opts2_frame, text="Max results:").pack(side=tk.LEFT, padx=(20, 5))
        limit_var = tk.IntVar(value=1000)
        ttk.Spinbox(opts2_frame, from_=10, to=10000, textvariable=limit_var, width=8).pack(side=tk.LEFT, padx=5)
        
        # Search button
        btn_frame = ttk.Frame(search_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        
        search_status_var = tk.StringVar(value="Ready")
        ttk.Label(btn_frame, textvariable=search_status_var).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_frame, text="🔍 Search", command=lambda: perform_search(),
                  style='Accent.TButton').pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Export CSV", command=lambda: export_results('csv')).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Clear", command=lambda: clear_results()).pack(side=tk.RIGHT, padx=5)
        
        # Results pane
        results_paned = ttk.PanedWindow(searcher_window, orient=tk.VERTICAL)
        results_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # Results list (top)
        results_list_frame = ttk.LabelFrame(results_paned, text="Results", padding="5")
        results_paned.add(results_list_frame, weight=2)
        
        results_columns = ("file", "entry", "offset", "preview")
        results_tree = ttk.Treeview(results_list_frame, columns=results_columns, show='headings', selectmode='browse')
        results_tree.heading("file", text="File")
        results_tree.heading("entry", text="Entry")
        results_tree.heading("offset", text="Offset")
        results_tree.heading("preview", text="Preview")
        
        results_tree.column("file", width=200)
        results_tree.column("entry", width=60, anchor=tk.CENTER)
        results_tree.column("offset", width=100, anchor=tk.CENTER)
        results_tree.column("preview", width=400)
        
        results_scroll = ttk.Scrollbar(results_list_frame, orient=tk.VERTICAL, command=results_tree.yview)
        results_tree.configure(yscrollcommand=results_scroll.set)
        results_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        results_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Detail pane (bottom)
        detail_frame = ttk.LabelFrame(results_paned, text="Match Details", padding="5")
        results_paned.add(detail_frame, weight=1)
        
        detail_text = tk.Text(detail_frame, wrap="none", font=("Courier New", 9), height=15)
        detail_scroll_y = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL, command=detail_text.yview)
        detail_scroll_x = ttk.Scrollbar(detail_frame, orient=tk.HORIZONTAL, command=detail_text.xview)
        detail_text.configure(yscrollcommand=detail_scroll_y.set, xscrollcommand=detail_scroll_x.set)
        
        detail_text.grid(row=0, column=0, sticky='nsew')
        detail_scroll_y.grid(row=0, column=1, sticky='ns')
        detail_scroll_x.grid(row=1, column=0, sticky='ew')
        
        detail_frame.rowconfigure(0, weight=1)
        detail_frame.columnconfigure(0, weight=1)
        
        # Store search results
        current_results = []
        
        def clear_results():
            """Clear all results."""
            nonlocal current_results
            current_results = []
            for item in results_tree.get_children():
                results_tree.delete(item)
            detail_text.delete("1.0", tk.END)
            search_status_var.set("Ready")
        
        def perform_search():
            """Execute the search."""
            nonlocal current_results
            
            directory = Path(dir_var.get())
            query = query_var.get().strip()
            
            if not query:
                messagebox.showwarning("Search", "Please enter a search query")
                return
            
            if not directory.exists():
                messagebox.showerror("Search", f"Directory not found: {directory}")
                return
            
            # Clear previous results
            clear_results()
            search_status_var.set("Searching...")
            searcher_window.update()
            
            try:
                # Create searcher
                searcher = PKFSearcher(
                    directory=directory,
                    recursive=recursive_var.get(),
                    file_pattern="*.pkf",
                    max_results=limit_var.get(),
                    context_size=context_var.get(),
                )
                
                # Check for PKF files
                pkf_files = searcher.find_pkf_files()
                if not pkf_files:
                    messagebox.showinfo("Search", f"No PKF files found in {directory}")
                    search_status_var.set("No PKF files found")
                    return
                
                # Perform search
                mode = mode_var.get()
                if mode == "hex":
                    results = searcher.search_hex(query, use_parallel=True)
                elif mode == "regex":
                    results = searcher.search_regex(query, encoding=encoding_var.get(), use_parallel=True)
                elif xor_enabled_var.get():
                    try:
                        key_str = xor_key_var.get().strip()
                        xor_key = int(key_str, 16) if key_str.startswith('0x') else int(key_str)
                        results = searcher.search_with_xor(query, xor_key, encoding=encoding_var.get(), use_parallel=True)
                    except ValueError as e:
                        messagebox.showerror("Search", f"Invalid XOR key: {e}")
                        search_status_var.set("Error: Invalid XOR key")
                        return
                else:
                    results = searcher.search_text(query, case_sensitive=case_var.get(),
                                                  encoding=encoding_var.get(), use_parallel=True)
                
                current_results = results
                
                # Display results
                if not results:
                    search_status_var.set("No matches found")
                    messagebox.showinfo("Search", "No matches found")
                    return
                
                for idx, result in enumerate(results):
                    rel_path = result.file_path.relative_to(directory) if result.file_path.is_relative_to(directory) else result.file_path.name
                    preview_text = result.get_match_text(encoding_var.get())[:60]
                    if len(preview_text) > 60:
                        preview_text = preview_text[:57] + "..."
                    
                    results_tree.insert("", tk.END, iid=str(idx), values=(
                        str(rel_path),
                        result.entry_index,
                        f"0x{result.absolute_offset:08X}",
                        preview_text
                    ))
                
                search_status_var.set(f"Found {len(results)} match(es) in {len(pkf_files)} file(s)")
                
            except Exception as e:
                messagebox.showerror("Search Error", f"Search failed:\n{str(e)}")
                search_status_var.set(f"Error: {str(e)}")
        
        def on_result_select(event):
            """Show details when a result is selected."""
            selection = results_tree.selection()
            if not selection:
                return
            
            try:
                idx = int(selection[0])
                result = current_results[idx]
                
                # Format detailed view
                detail_text.delete("1.0", tk.END)
                
                details = []
                details.append(f"File: {result.file_path}")
                details.append(f"Entry: {result.entry_index}")
                details.append(f"Entry Offset: 0x{result.entry_offset:08X}")
                details.append(f"Match Offset (in entry): 0x{result.match_offset:04X}")
                details.append(f"Absolute Offset: 0x{result.absolute_offset:08X}")
                if result.encoding:
                    details.append(f"Encoding: {result.encoding}")
                if result.xor_key is not None:
                    details.append(f"XOR Key: 0x{result.xor_key:02X}")
                details.append("")
                details.append("Hex Dump with Context:")
                details.append(result.format_preview(width=16))
                
                # Add decoded text if applicable
                if result.encoding and result.encoding != "raw":
                    try:
                        text = result.get_match_text(result.encoding)
                        if text and not text.startswith("<binary"):
                            details.append("")
                            details.append(f"Decoded Text ({result.encoding}):")
                            details.append(text)
                    except Exception:
                        pass
                
                detail_text.insert("1.0", "\n".join(details))
                
            except Exception as e:
                detail_text.delete("1.0", tk.END)
                detail_text.insert("1.0", f"Error displaying result: {e}")
        
        def export_results(format_type='csv'):
            """Export results to file."""
            if not current_results:
                messagebox.showinfo("Export", "No results to export")
                return
            
            from tkinter import filedialog
            if format_type == 'csv':
                filename = filedialog.asksaveasfilename(
                    defaultextension=".csv",
                    filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
                )
            else:
                filename = filedialog.asksaveasfilename(
                    defaultextension=".json",
                    filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
                )
            
            if not filename:
                return
            
            try:
                if format_type == 'csv':
                    import csv
                    with open(filename, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow(['File', 'Entry', 'Offset', 'Match (Hex)', 'Match (Text)'])
                        for result in current_results:
                            writer.writerow([
                                str(result.file_path),
                                result.entry_index,
                                f"0x{result.absolute_offset:08X}",
                                result.match_bytes.hex(),
                                result.get_match_text(encoding_var.get())
                            ])
                else:
                    import json
                    data = [{
                        'file': str(r.file_path),
                        'entry': r.entry_index,
                        'offset': f"0x{r.absolute_offset:08X}",
                        'match_hex': r.match_bytes.hex(),
                        'match_text': r.get_match_text(encoding_var.get())
                    } for r in current_results]
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump({'results': data, 'total': len(data)}, f, indent=2)
                
                messagebox.showinfo("Export", f"Exported {len(current_results)} results to {filename}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Export failed:\n{str(e)}")
        
        results_tree.bind("<<TreeviewSelect>>", on_result_select)
 
        # Bind Enter key to search
        query_entry.bind("<Return>", lambda e: perform_search())
 
    def load_pkf_and_count(self) -> None:
        """Load one or more PKF files and display the count of records (entries) from how many files."""
        initial_dir = str(self._pkf_last_dir)
        file_paths = filedialog.askopenfilenames(
            title="Select PKF file(s) to count records",
            initialdir=initial_dir,
            filetypes=(("PKF archives", "*.pkf"), ("All files", "*.*")),
        )
        if not file_paths:
            return
 
        # Show progress dialog
        progress = tk.Toplevel(self.root)
        progress.title("Loading PKF files...")
        progress.geometry("350x100")
        progress.transient(self.root)
        progress.resizable(False)
        ttk.Label(progress, text="Processing PKF files...").pack(pady=10)
        progressbar = ttk.Progressbar(progress, mode='determinate', maximum=len(file_paths))
        progressbar.pack(pady=10, padx=20, fill=tk.X)
        progress_label = ttk.Label(progress, text="Starting...")
        progress_label.pack(pady=5)
 
        total_records = 0
        loaded_files = 0
        errors = []
 
        def worker():
            nonlocal total_records, loaded_files, errors
            for i, file_path in enumerate(file_paths):
                chosen_path = Path(file_path)
                progress_label.config(text=f"Loading {chosen_path.name}...")
                progressbar.config(value=i)
                self.root.update_idletasks()
                try:
                    data = chosen_path.read_bytes()
                    pkf_file = PKFFile.from_bytes(chosen_path.name, data)
                    total_records += len(pkf_file)
                    loaded_files += 1
                    self._pkf_last_dir = chosen_path.parent
                except Exception as exc:
                    errors.append(f"{chosen_path.name}: {exc}")
            progressbar.config(value=len(file_paths))
            progress_label.config(text="Complete")
            self.root.after(0, finalize)
 
        def finalize():
            progress.destroy()
            if loaded_files == 0:
                messagebox.showerror("PKF Loader", "Failed to load any PKF files:\n" + "\n".join(errors))
                self.status_var.set("Error loading PKF files")
                return
 
            message = f"Loaded {loaded_files} PKF file(s)\n\nTotal records (entries): {total_records}"
            if errors:
                message += f"\n\nErrors ({len(errors)}):\n" + "\n".join(errors)
 
            messagebox.showinfo("PKF Record Count", message)
            self.status_var.set(f"PKF loaded: {loaded_files} file(s) ({total_records} total records)")
 
        threading.Thread(target=worker, daemon=True).start()
 
    def load_database(self):
        """Load the database file asynchronously to avoid blocking the UI."""
        # Update status immediately and create a progress dialog on main thread
        self.status_var.set("Loading database...")
        self.root.update_idletasks()
 
        if not Path(self.file_path).exists():
            messagebox.showerror("Error", f"File not found: {self.file_path}")
            self.status_var.set("File not found")
            return
 
        progress = tk.Toplevel(self.root)
        progress.title("Loading Database...")
        progress.geometry("300x100")
        progress.transient(self.root)
        progress_label = ttk.Label(progress, text="Starting database import...")
        progress_label.pack(pady=10)
        progressbar = ttk.Progressbar(progress, mode='determinate', maximum=3)  # Players, Coaches, Teams
        progressbar.pack(pady=10, padx=20, fill=tk.X)
 
        def worker():
            try:
                # Load players
                self.root.after(0, lambda: progress_label.config(text="Loading players from JUG98030.FDI..."))
                self.root.after(0, lambda: progressbar.config(value=0))
                self.file_data = Path(self.file_path).read_bytes()
                fdi = FDIFile(self.file_path)
                fdi.load()
                valid_players, uncertain_players = gather_player_records(self.file_path)
                records = [(entry.offset, entry.record) for entry in valid_players]
                uncertain_count = len(uncertain_players)
 
                # Load coaches
                self.root.after(0, lambda: progress_label.config(text="Loading coaches from ENT98030.FDI..."))
                self.root.after(0, lambda: progressbar.config(value=1))
                parsed_coaches = load_coaches(self.coach_file_path)
 
                # Load teams
                self.root.after(0, lambda: progress_label.config(text="Loading teams from EQ98030.FDI..."))
                self.root.after(0, lambda: progressbar.config(value=2))
                parsed_teams = load_teams(self.team_file_path)
 
                # Schedule UI update on main thread
                self.root.after(
                    0,
                    lambda: self._on_db_loaded_full(
                        progress,
                        progressbar,
                        fdi,
                        records,
                        uncertain_count,
                        parsed_coaches,
                        parsed_teams,
                    ),
                )
            except Exception as e:
                self.root.after(0, lambda: self._on_db_load_failed(progress, progressbar, e))
 
        threading.Thread(target=worker, daemon=True).start()
 
    def _on_db_loaded_full(self, progress, progressbar, fdi, records, uncertain_count, coaches, teams):
        """Callback run on the UI thread when full database load completes successfully."""
        try:
            progressbar.config(value=3)
            progress.destroy()
        except Exception:
            pass
 
        self.fdi_file = fdi
        self.all_records = records
        self.filtered_records = self.all_records.copy()
        self.player_uncertain_count = int(uncertain_count or 0)
        self.populate_tree()
 
        # Set coaches
        self.coach_records = coaches
        self.coaches_loaded = True
        self.filtered_coach_records = self.coach_records.copy()
        self.populate_coach_tree()
 
        # Set teams
        self.team_records = teams
        self.teams_loaded = True
        self.filtered_team_records = self.team_records.copy()
        # Build team lookup
        try:
            self.build_team_lookup()
            self.populate_tree()  # Refresh players to show team names
        except Exception:
            self.team_lookup = {}
        self.populate_team_tree()
 
        total_players = len(self.all_records)
        total_coaches = len(self.coach_records)
        total_teams = len(self.team_records)
 
        uncertainty_suffix = (
            f"\n{self.player_uncertain_count} uncertain player rows hidden from the editor list"
            if self.player_uncertain_count
            else ""
        )
        self.status_var.set(
            f"✓ Loaded database: {total_players} parser-backed players, {total_coaches} coaches, {total_teams} teams"
        )
        messagebox.showinfo(
            "Success",
            f"Loaded database:\n{total_players} parser-backed players\n{total_coaches} coaches\n{total_teams} teams"
            + uncertainty_suffix,
        )
 
    def _on_db_load_failed(self, progress, progressbar, error):
        """Callback run on the UI thread when background load fails."""
        try:
            progressbar.stop()
            progress.destroy()
        except Exception:
            pass
 
        messagebox.showerror("Error", f"Failed to load database:\n{error}")
        self.status_var.set("Error loading database")
    
    def populate_tree(self):
        """Populate the player tree"""
        self.tree.delete(*self.tree.get_children())
        
        for offset, record in self.filtered_records:
            display = getattr(record, 'name', None)
            if not display:
                given = getattr(record, 'given_name', '') or ''
                surname = getattr(record, 'surname', '') or ''
                display = f"{given} {surname}".strip()
 
            # Show team ID and resolved team name when available
            try:
                tid = getattr(record, 'team_id', None)
            except Exception:
                tid = None
            team_name = None
            if tid is not None and hasattr(self, 'team_lookup'):
                team_name = self.team_lookup.get(int(tid))
            if team_name:
                team_display = f"{tid} - {team_name}"
            else:
                team_display = f"{tid}" if tid is not None else ""
 
            self.tree.insert('', tk.END, values=(
                display,
                team_display,
                record.squad_number,
                record.get_position_name()
            ), tags=(str(offset),))
        
        count_text = f"Players: {len(self.filtered_records)} / {len(self.all_records)}"
        if getattr(self, "player_uncertain_count", 0):
            count_text += f" ({self.player_uncertain_count} uncertain hidden)"
        self.count_label.config(text=count_text)
    
    def on_select(self, event):
        """Handle player selection"""
        selection = self.tree.selection()
        if not selection:
            return

        # Get record from tag
        item = self.tree.item(selection[0])
        try:
            offset = int(item['tags'][0])
        except Exception:
            return

        # Find the record
        for o, r in self.all_records:
            if o == offset:
                self.current_record = (o, r)
                self.display_record(r)
                break

    def _player_matches_query(self, record, query: str) -> bool:
        """Match player search against player names and resolved team aliases."""
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return True
        lower_query = normalized_query.lower()

        candidate_names = [
            str(getattr(record, "name", "") or ""),
            str(getattr(record, "given_name", "") or ""),
            str(getattr(record, "surname", "") or ""),
            f"{getattr(record, 'given_name', '') or ''} {getattr(record, 'surname', '') or ''}".strip(),
        ]
        for candidate in candidate_names:
            if candidate and lower_query in candidate.lower():
                return True

        try:
            team_id = getattr(record, "team_id", None)
        except Exception:
            team_id = None
        if team_id is not None:
            team_id_text = str(team_id)
            if lower_query in team_id_text.lower():
                return True
            team_name, full_club_name = (getattr(self, "team_alias_lookup", {}) or {}).get(
                int(team_id),
                ("", ""),
            )
            if team_query_matches(
                normalized_query,
                team_name=str(team_name or ""),
                full_club_name=str(full_club_name or ""),
            ):
                return True
        return False

    def inspect_selected_player_metadata(self):
        """Render selected-player metadata into the analysis workspace without prompts."""
        current = getattr(self, "current_record", None)
        if not (isinstance(current, tuple) and len(current) >= 2):
            messagebox.showinfo("Inspect Selected Player", "Select a player first.")
            return

        offset, record = current
        target_name = str(
            getattr(record, "name", None)
            or f"{getattr(record, 'given_name', '') or ''} {getattr(record, 'surname', '') or ''}".strip()
        ).strip()
        if not target_name:
            messagebox.showinfo("Inspect Selected Player", "The selected player does not have a usable name.")
            return

        try:
            self.status_var.set("Inspecting selected player...")
            self.root.update_idletasks()
            result = inspect_player_metadata_records(
                file_path=str(getattr(self, "file_path", None) or "DBDAT/JUG98030.FDI"),
                target_name=target_name,
                target_offset=int(offset) if isinstance(offset, int) else None,
            )
            self.status_var.set(
                f"✓ Selected player inspection complete ({getattr(result, 'matched_count', 0)} matched)"
            )
            PM99DatabaseEditor._show_player_metadata_inspect_dialog_view(self, result=result)
        except Exception as exc:
            self.status_var.set("Selected player inspection failed")
            messagebox.showerror("Inspect Selected Player", f"Inspection failed:\n{exc}")

    def display_record(self, record: PlayerRecord):
        """Display record in editor"""
        # Populate name fields
        given = getattr(record, 'given_name', '') or ''
        surname = getattr(record, 'surname', '') or ''
        self.given_name_var.set(given)
        self.surname_var.set(surname)

        self.team_id_var.set(getattr(record, 'team_id', 0) or 0)
        self.squad_var.set(getattr(record, 'squad_number', 0) or 0)
        try:
            self.position_var.set(record.get_position_name())
        except Exception:
            self.position_var.set('')

        # Metadata fields (nationality, DOB, height)
        self.nationality_var.set(getattr(record, 'nationality_id', getattr(record, 'nationality', 0)) or 0)

        if getattr(record, 'dob', None):
            day, month, year = record.dob
            self.dob_day_var.set(day)
            self.dob_month_var.set(month)
            self.dob_year_var.set(year)
        else:
            # sensible defaults
            self.dob_day_var.set(1)
            self.dob_month_var.set(1)
            self.dob_year_var.set(1970)

        self.height_var.set(getattr(record, 'height', 175) or 175)

        weight_value = getattr(record, 'weight', None)
        self.weight_var.set("" if weight_value is None else str(weight_value))
        indexed_weight_editable = False
        legacy_weight_editable = False
        try:
            raw_data = getattr(record, 'raw_data', None) or b''
            indexed_name = (getattr(record, 'name', '') or f"{getattr(record, 'given_name', '')} {getattr(record, 'surname', '')}".strip()).strip()
            try:
                stored_name = PlayerRecord._extract_name(raw_data)
            except Exception:
                stored_name = indexed_name
            indexed_weight_editable = (
                PlayerRecord._find_indexed_suffix_anchor(raw_data, stored_name) is not None
                or (
                    stored_name != indexed_name
                    and PlayerRecord._find_indexed_suffix_anchor(raw_data, indexed_name) is not None
                )
            )
            if not indexed_weight_editable:
                legacy_weight_editable = PlayerRecord._find_legacy_weight_offset(raw_data) is not None
        except Exception:
            indexed_weight_editable = False
            legacy_weight_editable = False

        weight_state = 'disabled'
        weight_hint = "(unavailable for this record)"
        if indexed_weight_editable:
            weight_hint = "(indexed JUG only)"
            if not SAVE_NAME_ONLY:
                weight_state = 'normal'
            else:
                weight_hint = "(read-only in safe mode)"
        elif legacy_weight_editable:
            weight_hint = "(legacy marker slot)"
            if not SAVE_NAME_ONLY:
                weight_state = 'normal'
            else:
                weight_hint = "(read-only in safe mode)"
        try:
            self.weight_spinbox.configure(state=weight_state)
        except Exception:
            try:
                self.weight_spinbox.config(state=weight_state)
            except Exception:
                pass
        try:
            self.weight_hint_var.set(weight_hint)
        except Exception:
            pass

        # Clear and rebuild attributes
        for widget in self.attr_container.winfo_children():
            widget.destroy()
 
        self.attr_vars = []
 
        attrs = getattr(record, 'attributes', [])
        if not isinstance(attrs, (list, tuple)):
            attrs = list(attrs) if attrs else []
        for i, attr_val in enumerate(attrs):
            frame = ttk.Frame(self.attr_container)
            frame.pack(fill=tk.X, pady=2)
 
            label_text = self.attr_labels[i] if i < len(self.attr_labels) else f"Attribute {i}"
            ttk.Label(frame, text=label_text, width=18).pack(side=tk.LEFT, padx=5)
 
            var = tk.IntVar(value=attr_val)
            self.attr_vars.append(var)
 
            # Create spinbox and scale but disable them in safe-name-only mode
            slot_editable = i in getattr(self, 'attr_editable_indices', set(PlayerRecord.editable_attribute_indices()))
            spin_state = 'normal' if (slot_editable and not SAVE_NAME_ONLY) else 'disabled'
            spin = ttk.Spinbox(frame, from_=0, to=100, textvariable=var, width=8, state=spin_state)
            spin.pack(side=tk.LEFT, padx=5)
 
            scale = ttk.Scale(frame, from_=0, to=100, variable=var, orient=tk.HORIZONTAL, length=200)
            scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            if SAVE_NAME_ONLY or not slot_editable:
                try:
                    scale.state(['disabled'])
                except Exception:
                    try:
                        scale.configure(state='disabled')
                    except Exception:
                        pass
 
            val_label = ttk.Label(frame, text=str(attr_val), width=4, font=('TkDefaultFont', 9, 'bold'))
            val_label.pack(side=tk.RIGHT, padx=5)
 
            def make_updater(lbl, v):
                return lambda *args: lbl.config(text=str(v.get()))
            var.trace('w', make_updater(val_label, var))

        # Best-effort refresh of the verified dd6361 visible-skill panel for the selected player.
        try:
            self.refresh_visible_skill_panel(show_dialog_errors=False)
        except Exception:
            self._set_visible_skill_panel_unavailable("refresh error")

    def apply_changes(self):
        """Apply changes to current record"""
        if not self.current_record:
            return
 
        offset, record = self.current_record
 
        try:
            changes = []
 
            # Player name (given name and surname)
            new_given = self.given_name_var.get().strip()
            new_surname = self.surname_var.get().strip()
            old_given = getattr(record, 'given_name', '') or ''
            old_surname = getattr(record, 'surname', '') or ''
 
            if new_given != old_given:
                try:
                    record.set_given_name(new_given)
                    changes.append(f"Given Name: {old_given} → {new_given}")
                except Exception as e:
                    messagebox.showerror("Invalid Name", f"Given name error: {e}")
                    return
 
            if new_surname != old_surname:
                try:
                    record.set_surname(new_surname)
                    changes.append(f"Surname: {old_surname} → {new_surname}")
                except Exception as e:
                    messagebox.showerror("Invalid Name", f"Surname error: {e}")
                    return
 
            # If running in safe name-only mode, do not apply any other edits.
            if SAVE_NAME_ONLY:
                # Detect any attempted non-name edits so we can inform the user they are ignored.
                non_name_changes = []
                try:
                    new_team_id = int(self.team_id_var.get() or 0)
                except Exception:
                    new_team_id = 0
                if new_team_id != getattr(record, 'team_id', 0):
                    non_name_changes.append("Team ID")
 
                try:
                    new_squad = int(self.squad_var.get() or 0)
                except Exception:
                    new_squad = 0
                if new_squad != getattr(record, 'squad_number', 0):
                    non_name_changes.append("Squad #")
 
                pos_name = self.position_var.get()
                pos_map = {"Goalkeeper": 0, "Defender": 1, "Midfielder": 2, "Forward": 3}
                new_pos = pos_map.get(pos_name, 0)
                if new_pos != getattr(record, 'position', 0):
                    non_name_changes.append("Position")
 
                try:
                    new_nat = int(self.nationality_var.get() or 0)
                except Exception:
                    new_nat = 0
                if new_nat != getattr(record, 'nationality_id', 0):
                    non_name_changes.append("Nationality")
 
                try:
                    new_day = int(self.dob_day_var.get() or 1)
                    new_month = int(self.dob_month_var.get() or 1)
                    new_year = int(self.dob_year_var.get() or 1970)
                except Exception:
                    new_day, new_month, new_year = 1, 1, 1970
                old_dob = getattr(record, 'dob', None)
                if old_dob is None or (new_day, new_month, new_year) != old_dob:
                    non_name_changes.append("DOB")
 
                try:
                    new_height = int(self.height_var.get() or 175)
                except Exception:
                    new_height = 175
                if new_height != getattr(record, 'height', None):
                    non_name_changes.append("Height")

                weight_text = str(self.weight_var.get() or "").strip()
                if weight_text:
                    try:
                        new_weight = int(weight_text)
                    except Exception:
                        new_weight = getattr(record, 'weight', None)
                    old_weight = getattr(record, 'weight', None)
                    if old_weight is None or new_weight != old_weight:
                        non_name_changes.append("Weight")
 
                # Attributes
                for i, var in enumerate(self.attr_vars):
                    if i not in getattr(self, 'attr_editable_indices', set(PlayerRecord.editable_attribute_indices())):
                        continue
                    try:
                        new_val = int(var.get())
                    except Exception:
                        continue
                    if i < len(getattr(record, 'attributes', [])) and new_val != record.attributes[i]:
                        non_name_changes.append(f"Attribute {i}")
                        break
 
                if non_name_changes:
                    messagebox.showwarning(
                        "Safe Mode: Non-name edits ignored",
                        "This editor is running in SAFE MODE (name-only saves). The following changes will be ignored:\n\n"
                        + ", ".join(non_name_changes)
                    )
 
                if changes:
                    # Only name modifications staged
                    self.modified_records[offset] = record
                    change_text = '\n'.join(changes[:10])
                    if len(changes) > 10:
                        change_text += f"\n... and {len(changes)-10} more changes"
 
                    self.status_var.set(f"✓ {len(changes)} name change(s) applied to {getattr(record, 'name', '')}")
                    messagebox.showinfo(
                        "Success",
                        f"Name changes applied to {getattr(record, 'name', '')}:\n\n{change_text}\n\nSave database to persist changes (Ctrl+S)"
                    )
                else:
                    messagebox.showinfo("Info", "No name changes to apply")
                return
 
            # Legacy (full) behaviour when safe-mode is not enabled: apply all edits
            # Team ID
            try:
                new_team_id = int(self.team_id_var.get() or 0)
            except Exception:
                new_team_id = 0
            if new_team_id != getattr(record, 'team_id', 0):
                try:
                    record.set_team_id(new_team_id)
                    changes.append(f"Team ID: {getattr(record, 'team_id', '')} → {new_team_id}")
                except Exception:
                    pass
 
            # Squad number
            try:
                new_squad = int(self.squad_var.get() or 0)
            except Exception:
                new_squad = 0
            if new_squad != getattr(record, 'squad_number', 0):
                try:
                    record.set_squad_number(new_squad)
                    changes.append(f"Squad #: {getattr(record, 'squad_number', '')} → {new_squad}")
                except Exception:
                    pass
 
            # Position
            pos_name = self.position_var.get()
            pos_map = {"Goalkeeper": 0, "Defender": 1, "Midfielder": 2, "Forward": 3}
            new_pos = pos_map.get(pos_name, 0)
            if new_pos != getattr(record, 'position', 0):
                try:
                    old_pos_name = record.get_position_name()
                except Exception:
                    old_pos_name = ''
                try:
                    record.set_position(new_pos)
                    changes.append(f"Position: {old_pos_name} → {pos_name}")
                except Exception:
                    pass
 
            # Metadata: Nationality, DOB, Height
            try:
                new_nat = int(self.nationality_var.get() or 0)
            except Exception:
                new_nat = 0
            old_nat = getattr(record, 'nationality_id', getattr(record, 'nationality', None))
            old_nat_display = old_nat if old_nat is not None else 'None'
            if new_nat != (old_nat if old_nat is not None else 0):
                try:
                    record.set_nationality(new_nat)
                    changes.append(f"Nationality ID: {old_nat_display} → {new_nat}")
                except Exception:
                    pass
 
            # DOB
            try:
                new_day = int(self.dob_day_var.get() or 1)
                new_month = int(self.dob_month_var.get() or 1)
                new_year = int(self.dob_year_var.get() or 1970)
            except Exception:
                new_day, new_month, new_year = 1, 1, 1970
            old_dob = getattr(record, 'dob', None)
            if old_dob is None or (new_day, new_month, new_year) != old_dob:
                try:
                    record.set_dob(new_day, new_month, new_year)
                    old_dob_display = f"{old_dob[0]}/{old_dob[1]}/{old_dob[2]}" if old_dob else "None"
                    changes.append(f"DOB: {old_dob_display} → {new_day}/{new_month}/{new_year}")
                except Exception:
                    pass
 
            # Height
            try:
                new_height = int(self.height_var.get() or 175)
            except Exception:
                new_height = 175
            old_height = getattr(record, 'height', None)
            if old_height is None or new_height != old_height:
                try:
                    record.set_height(new_height)
                    old_height_display = old_height if old_height is not None else 'None'
                    changes.append(f"Height: {old_height_display} → {new_height} cm")
                except Exception:
                    pass

            # Weight (persisted only when the selected record exposes a parser-backed slot; blank means leave unchanged)
            weight_text = str(self.weight_var.get() or "").strip()
            if weight_text:
                try:
                    new_weight = int(weight_text)
                except Exception as e:
                    messagebox.showerror("Invalid Weight", f"Weight error: {e}")
                    return
                old_weight = getattr(record, 'weight', None)
                if old_weight is None or new_weight != old_weight:
                    try:
                        record.set_weight(new_weight)
                        old_weight_display = old_weight if old_weight is not None else 'None'
                        changes.append(f"Weight: {old_weight_display} → {new_weight} kg")
                    except Exception as e:
                        messagebox.showerror("Invalid Weight", f"Weight error: {e}")
                        return
 
            # Attributes
            for i, var in enumerate(self.attr_vars):
                if i not in getattr(self, 'attr_editable_indices', set(PlayerRecord.editable_attribute_indices())):
                    continue
                try:
                    new_val = int(var.get())
                except Exception:
                    continue
                if i < len(getattr(record, 'attributes', [])) and new_val != record.attributes[i]:
                    old_val = record.attributes[i]
                    try:
                        record.set_attribute(i, new_val)
                        changes.append(f"{self.attr_labels[i]}: {old_val} → {new_val}")
                    except Exception:
                        pass
 
            if changes:
                self.modified_records[offset] = record
                change_text = '\n'.join(changes[:10])
                if len(changes) > 10:
                    change_text += f"\n... and {len(changes)-10} more changes"
 
                self.status_var.set(f"✓ {len(changes)} change(s) applied to {getattr(record, 'name', '')}")
                messagebox.showinfo("Success", f"Changes applied to {getattr(record, 'name', '')}:\n\n{change_text}\n\nSave database to persist changes (Ctrl+S)")
            else:
                messagebox.showinfo("Info", "No changes to apply")
 
        except Exception as e:
            messagebox.showerror("Error", f"Failed to apply changes:\n{str(e)}")

    def reset_current(self):
        """Reset current player to original values"""
        if self.current_record:
            self.display_record(self.current_record[1])
            self.status_var.set("Reset to original values")

    def filter_records(self, *args):
        """Filter players by search"""
        search = self.search_var.get().strip()
        if search:
            self.filtered_records = [
                (offset, record)
                for offset, record in self.all_records
                if self._player_matches_query(record, search)
            ]
        else:
            self.filtered_records = self.all_records.copy()
        self.populate_tree()
 
    def on_tab_changed(self, event):
        """Handle notebook tab changes (lazy-load coaches/teams)"""
        try:
            tab_id = event.widget.select()
            tab_text = event.widget.tab(tab_id, 'text')
        except Exception:
            return

        if tab_text == "Coaches":
            if not getattr(self, 'coaches_loaded', False):
                self.load_coaches()
            self._hide_team_overlay()
            # Show coach overlay when switching to Coaches tab
            # (will be populated when a coach is selected)
            # For now just clear the overlay
            self._clear_coach_overlay()
        elif tab_text == "Teams":
            self._show_team_overlay()
            self._hide_coach_overlay()
        elif tab_text == "⚽ Leagues":
            self._hide_team_overlay()
            self._hide_coach_overlay()
            # Populate leagues if teams are loaded
            if getattr(self, 'teams_loaded', False):
                self.populate_league_tree()
        else:
            # Players tab or other tab
            self._hide_team_overlay()
            self._hide_coach_overlay()
    def save_database(self):
        """Save modified database (players, coaches, teams)."""
        n_players = len(getattr(self, 'modified_records', {}))
        n_coaches = len(getattr(self, 'modified_coach_records', {}))
        n_teams = len(getattr(self, 'modified_team_records', {}))
        n_visible_skill_patches = len(getattr(self, 'staged_visible_skill_patches', {}) or {})

        if n_players == 0 and n_coaches == 0 and n_teams == 0 and n_visible_skill_patches == 0:
            messagebox.showinfo("Info", "No changes to save")
            return

        parts = []
        if n_players:
            parts.append(f"{n_players} player(s) → {self.file_path}")
        if n_visible_skill_patches:
            parts.append(f"{n_visible_skill_patches} dd6361 visible-skill patch(es) → {self.file_path}")
        if n_coaches:
            parts.append(f"{n_coaches} coach(es) → {self.coach_file_path}")
        if n_teams:
            parts.append(f"{n_teams} team(s) → {self.team_file_path}")

        result = messagebox.askyesno(
            "Confirm Save",
            "Save the following changes?\n\n" + "\n".join(parts) + "\n\nA backup will be created for each file."
        )
        if not result:
            return

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backups = []

            # Players
            if n_players or n_visible_skill_patches:
                player_backup = Path(self.file_path + f'.backup_{timestamp}')
                if self.file_data is not None:
                    player_backup.write_bytes(self.file_data)
                else:
                    player_backup.write_bytes(Path(self.file_path).read_bytes())
                backups.append(str(player_backup))

            if n_players:
                # Use FDIFile save which honors SAVE_NAME_ONLY conservative behaviour
                fdi = FDIFile(self.file_path)
                fdi.file_data = self.file_data
                # copy modified records into the FDIFile instance
                fdi.modified_records = {o: r for o, r in self.modified_records.items()}
                fdi.save()
                # Refresh in-memory file data and clear staged modifications
                self.file_data = Path(self.file_path).read_bytes()
                self.modified_records.clear()

            if n_visible_skill_patches:
                patch_results = self._apply_staged_visible_skill_patches(create_backups=False)
                # If save is called before any player data was loaded, ensure memory cache refresh.
                if patch_results and self.file_data is None:
                    try:
                        self.file_data = Path(self.file_path).read_bytes()
                    except Exception:
                        pass

            # Coaches
            if n_coaches:
                modified_list = [(o, r) for o, r in self.modified_coach_records.items()]
                coach_backup = write_coach_staged_records(self.coach_file_path, modified_list)
                self.modified_coach_records.clear()
                if coach_backup:
                    backups.append(str(coach_backup))

            # Teams
            if n_teams:
                modified_list = [(o, r) for o, r in self.modified_team_records.items()]
                # Team loader offsets point inside decoded section records; use the
                # team-aware writer so we patch and rewrite the enclosing FDI entries.
                team_backup = write_team_staged_records(self.team_file_path, modified_list)
                self.modified_team_records.clear()
                if team_backup:
                    backups.append(str(team_backup))
            validation_result = None
            validation_error = None
            try:
                validation_result = validate_database_files(
                    player_file=self.file_path if (n_players or n_visible_skill_patches) else None,
                    team_file=self.team_file_path if n_teams else None,
                    coach_file=self.coach_file_path if n_coaches else None,
                )
            except Exception as exc:
                validation_error = str(exc)

            summary_lines = ["Database saved!", "Backups:"] + backups
            if validation_result is not None and getattr(validation_result, "files", None):
                summary_lines.extend(["", "Validation:"])
                for item in list(getattr(validation_result, "files", []) or []):
                    status = "OK" if getattr(item, "success", False) else "FAIL"
                    summary_lines.append(
                        f"- {getattr(item, 'category', 'unknown')}: {status} "
                        f"(valid={int(getattr(item, 'valid_count', 0) or 0)}, "
                        f"uncertain={int(getattr(item, 'uncertain_count', 0) or 0)})"
                    )
                    detail = str(getattr(item, "detail", "") or "").strip()
                    if detail:
                        summary_lines.append(f"  {detail}")

            if validation_error:
                self.status_var.set("⚠ Database saved, but validation could not complete")
                summary_lines.extend(["", "Validation error:", validation_error])
                messagebox.showwarning("Saved with Validation Warning", "\n".join(summary_lines))
                return

            if validation_result is not None and not getattr(validation_result, "all_valid", False):
                self.status_var.set("⚠ Database saved, but reopen validation reported issues")
                messagebox.showwarning("Saved with Validation Warning", "\n".join(summary_lines))
                return

            self.status_var.set("✓ Database saved and revalidated")
            messagebox.showinfo("Success", "\n".join(summary_lines))

        except Exception as e:
            messagebox.showerror("Error", f"Failed to save:\n{str(e)}")
    def open_file(self):
        """Open different database file"""
        filename = filedialog.askopenfilename(
            filetypes=[("FDI files", "*.FDI"), ("All files", "*.*")],
            initialdir="DBDAT"
        )
        if filename:
            self.file_path = filename
            # Clear tracked modifications for the previous file
            try:
                self.modified_records.clear()
            except Exception:
                self.modified_records = {}
            try:
                self.staged_visible_skill_patches.clear()
            except Exception:
                self.staged_visible_skill_patches = {}
            # Reload database for the newly chosen file
            self.load_database()

try:
    from .gui_refresh import PM99DatabaseEditor as RefreshedPM99DatabaseEditor
except Exception:
    from app.gui_refresh import PM99DatabaseEditor as RefreshedPM99DatabaseEditor

PM99DatabaseEditor = RefreshedPM99DatabaseEditor

def main():
    root = tk.Tk()
    
    style = ttk.Style()
    try:
        style.theme_use('clam')
    except:
        pass
    
    style.configure('Accent.TButton', font=('TkDefaultFont', 10, 'bold'))
    
    app = PM99DatabaseEditor(root)
    root.mainloop()
 
if __name__ == "__main__":
    main()
