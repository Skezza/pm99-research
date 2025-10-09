# Make gui.py runnable either as a package (python -m pm99_editor.gui) or directly (python pm99_editor/gui.py)
# This tries relative imports first; if that fails (no package context), it adjusts sys.path
import os, sys
try:
    # When executed as a package: python -m pm99_editor.gui
    from .models import PlayerRecord, TeamRecord, CoachRecord
    from .io import FDIFile
    from .file_writer import save_modified_records
    from .xor import xor_decode
    from .loaders import load_teams, load_coaches
except Exception:
    # When executed directly: python pm99_editor/gui.py
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from pm99_editor.models import PlayerRecord, TeamRecord, CoachRecord
    from pm99_editor.io import FDIFile
    from pm99_editor.file_writer import save_modified_records
    from pm99_editor.xor import xor_decode
    from pm99_editor.loaders import load_teams, load_coaches

# Ensure common helpers are available when run as a script
from pathlib import Path

"""
Modern GUI application for Premier Manager 99 Database Editor
Uses the modular package structure
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pm99_editor.models import PlayerRecord, TeamRecord, CoachRecord
from pm99_editor.io import FDIFile
from pm99_editor.file_writer import save_modified_records
from pm99_editor.xor import xor_decode
from pm99_editor.loaders import load_teams, load_coaches
from datetime import datetime
import re
from collections import defaultdict
import threading

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
        
        self.root.bind('<Control-s>', lambda e: self.save_database())
        
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
        
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.filter_records)
        ttk.Entry(search_frame, textvariable=self.search_var).pack(fill=tk.X)
        
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
            from pm99_editor.league_definitions import get_all_countries
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

        # Start background load of teams (lazy but triggered at UI creation for discoverability)
        def _load_teams_background():
            # Show a transient progress dialog on the main thread
            try:
                progress = tk.Toplevel(self.root)
                progress.title("Loading teams...")
                progress.geometry("300x80")
                progress.transient(self.root)
                ttk.Label(progress, text="Scanning teams file...").pack(pady=10)
                progressbar = ttk.Progressbar(progress, mode='indeterminate')
                progressbar.pack(pady=10)
                progressbar.start()
            except Exception:
                progress = None
                progressbar = None

            def worker():
                # Use shared loader with strict validation
                parsed = load_teams(self.team_file_path)

                def finalize():
                    try:
                        if progressbar:
                            progressbar.stop()
                        if progress:
                            progress.destroy()
                    except Exception:
                        pass
                    self.team_records = parsed
                    self.teams_loaded = True
                    self.filtered_team_records = self.team_records.copy()
                    # Build a lookup from team_id -> team_name for display in Players tab
                    try:
                        self.build_team_lookup()
                    except Exception:
                        self.team_lookup = {}
                    self.populate_team_tree()
                    # Refresh players tree so team names can be shown if mapping was found
                    try:
                        self.populate_tree()
                    except Exception:
                        pass
                    # Refresh leagues if on leagues tab
                    try:
                        current_tab = self.notebook.tab(self.notebook.select(), 'text')
                        if current_tab == "Leagues":
                            self.populate_league_tree()
                    except Exception:
                        pass
                    self.status_var.set(f"✓ Loaded {len(self.team_records)} teams")
                self.root.after(0, finalize)

            threading.Thread(target=worker, daemon=True).start()

        # Trigger background load (non-blocking)
        _load_teams_background()
        
        # Right: Editor
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=2)
        
        # Player info
        info_frame = ttk.LabelFrame(right_frame, text="Player Information", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Name (editable - given name and surname)
        ttk.Label(info_frame, text="Given Name:", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, pady=5)
        self.given_name_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.given_name_var, width=20).grid(row=0, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(info_frame, text="(max 12 chars)", font=('TkDefaultFont', 8)).grid(row=0, column=2, sticky=tk.W)
        
        ttk.Label(info_frame, text="Surname:", font=('TkDefaultFont', 10, 'bold')).grid(row=1, column=0, sticky=tk.W, pady=5)
        self.surname_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.surname_var, width=20).grid(row=1, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(info_frame, text="(max 12 chars)", font=('TkDefaultFont', 8)).grid(row=1, column=2, sticky=tk.W)
        
        # Team ID
        ttk.Label(info_frame, text="Team ID:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.team_id_var = tk.IntVar()
        ttk.Spinbox(info_frame, from_=0, to=65535, textvariable=self.team_id_var, width=10).grid(row=2, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(info_frame, text="(0-65535)", font=('TkDefaultFont', 8)).grid(row=2, column=2, sticky=tk.W)
        
        # Squad Number
        ttk.Label(info_frame, text="Squad #:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.squad_var = tk.IntVar()
        ttk.Spinbox(info_frame, from_=0, to=255, textvariable=self.squad_var, width=10).grid(row=3, column=1, sticky=tk.W, padx=10, pady=5)
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
        ttk.Spinbox(info_frame, from_=0, to=255, textvariable=self.nationality_var, width=8).grid(row=5, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(info_frame, text="(ID, mapping TBD)", font=('TkDefaultFont', 8)).grid(row=5, column=2, sticky=tk.W)
        
        # Date of Birth (day/month/year)
        ttk.Label(info_frame, text="DOB:").grid(row=6, column=0, sticky=tk.W, pady=5)
        self.dob_day_var = tk.IntVar()
        self.dob_month_var = tk.IntVar()
        self.dob_year_var = tk.IntVar()
        dob_frame = ttk.Frame(info_frame)
        dob_frame.grid(row=6, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Spinbox(dob_frame, from_=1, to=31, width=4, textvariable=self.dob_day_var).pack(side=tk.LEFT)
        ttk.Label(dob_frame, text="/").pack(side=tk.LEFT)
        ttk.Spinbox(dob_frame, from_=1, to=12, width=4, textvariable=self.dob_month_var).pack(side=tk.LEFT)
        ttk.Label(dob_frame, text="/").pack(side=tk.LEFT)
        ttk.Spinbox(dob_frame, from_=1900, to=2100, width=6, textvariable=self.dob_year_var).pack(side=tk.LEFT)
        ttk.Label(info_frame, text="(day/month/year)", font=('TkDefaultFont', 8)).grid(row=6, column=2, sticky=tk.W)
        
        # Height
        ttk.Label(info_frame, text="Height (cm):").grid(row=7, column=0, sticky=tk.W, pady=5)
        self.height_var = tk.IntVar()
        ttk.Spinbox(info_frame, from_=50, to=250, textvariable=self.height_var, width=8).grid(row=7, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Label(info_frame, text="cm", font=('TkDefaultFont', 8)).grid(row=7, column=2, sticky=tk.W)
        
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
        
        # Attribute labels (best guess - user can verify)
        self.attr_labels = [
            "Attr 0 (Speed?)", "Attr 1 (Stamina?)", "Attr 2 (Aggression?)",
            "Attr 3 (Quality?)", "Attr 4 (Fitness?)", "Attr 5 (Moral?)",
            "Attr 6 (Handling?)", "Attr 7 (Passing?)", "Attr 8 (Dribbling?)",
            "Attr 9 (Heading?)", "Attr 10 (Tackling?)", "Attr 11 (Shooting?)"
        ]
        
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
        ttk.Spinbox(team_panel, from_=0, to=1000000, textvariable=self.team_panel_capacity_var, width=14).grid(row=3, column=1, sticky=tk.W, padx=10, pady=5)

        ttk.Label(team_panel, text="Car Park:").grid(row=4, column=0, sticky=tk.W, pady=5)
        ttk.Spinbox(team_panel, from_=0, to=200000, textvariable=self.team_panel_car_var, width=14).grid(row=4, column=1, sticky=tk.W, padx=10, pady=5)

        ttk.Label(team_panel, text="Pitch quality:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.team_panel_pitch_combo = ttk.Combobox(team_panel, textvariable=self.team_panel_pitch_var, state='readonly', width=16)
        self.team_panel_pitch_combo['values'] = ['GOOD', 'EXCELLENT', 'AVERAGE', 'POOR', 'UNKNOWN']
        self.team_panel_pitch_combo.grid(row=5, column=1, sticky=tk.W, padx=10, pady=5)

        # Roster toggle + frame (collapsible)
        roster_toggle_frame = ttk.Frame(self.team_overlay)
        roster_toggle_frame.pack(fill=tk.X)
        self.team_panel_roster_visible = False
        self.team_panel_roster_toggle_btn = ttk.Button(roster_toggle_frame, text="Show squad lineup", command=self._toggle_roster)
        self.team_panel_roster_toggle_btn.pack(side=tk.LEFT, padx=5, pady=5)

        self.team_panel_roster_frame = ttk.LabelFrame(self.team_overlay, text="Squad Lineup", padding="5")
        # roster is not packed initially (collapsed)

        # Enhanced roster tree with all attributes (PM99 style)
        roster_cols = ('num', 'name', 'en', 'sp', 'st', 'ag', 'qu', 'fi', 'mo', 'av', 'role', 'pos')
        self.team_roster_tree = ttk.Treeview(self.team_panel_roster_frame, columns=roster_cols, show='headings', selectmode='browse', height=20)
        
        # Configure columns with PM99-style headers
        self.team_roster_tree.heading('num', text='N.')
        self.team_roster_tree.heading('name', text='PLAYER')
        self.team_roster_tree.heading('en', text='EN')  # Energy
        self.team_roster_tree.heading('sp', text='SP')  # Speed
        self.team_roster_tree.heading('st', text='ST')  # Stamina
        self.team_roster_tree.heading('ag', text='AG')  # Agility
        self.team_roster_tree.heading('qu', text='QU')  # Quality
        self.team_roster_tree.heading('fi', text='FI')  # Fitness
        self.team_roster_tree.heading('mo', text='MO')  # Morale
        self.team_roster_tree.heading('av', text='AV')  # Average
        self.team_roster_tree.heading('role', text='ROL.')
        self.team_roster_tree.heading('pos', text='POS')
        
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

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(side=tk.BOTTOM, fill=tk.X)
    
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
        progress.title("Loading...")
        progress.geometry("300x80")
        progress.transient(self.root)
        ttk.Label(progress, text="Importing database...").pack(pady=10)
        progressbar = ttk.Progressbar(progress, mode='indeterminate')
        progressbar.pack(pady=10)
        progressbar.start()

        def worker():
            try:
                # Read and load the file (heavy work) in background thread
                self.file_data = Path(self.file_path).read_bytes()
                fdi = FDIFile(self.file_path)
                fdi.load()
                # Prefer the offset-aware structure when available
                records = getattr(fdi, 'records_with_offsets', [(None, r) for r in getattr(fdi, 'records', [])])
                # Schedule UI update on main thread
                self.root.after(0, lambda: self._on_db_loaded(progress, progressbar, fdi, records))
            except Exception as e:
                self.root.after(0, lambda: self._on_db_load_failed(progress, progressbar, e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_db_loaded(self, progress, progressbar, fdi, records):
        """Callback run on the UI thread when background load completes successfully."""
        try:
            progressbar.stop()
            progress.destroy()
        except Exception:
            pass

        self.fdi_file = fdi
        self.all_records = records
        self.filtered_records = self.all_records.copy()
        self.populate_tree()

        self.status_var.set(f"✓ Loaded {len(self.all_records)} players")
        messagebox.showinfo("Success", f"Loaded {len(self.all_records)} players from database")

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
        
        self.count_label.config(text=f"Players: {len(self.filtered_records)} / {len(self.all_records)}")
    
    # ----------------------------
    # Coaches: lazy loading & UI
    # ----------------------------
    def load_coaches(self):
        """Load coaches from the ENT98030.FDI file asynchronously."""
        if getattr(self, 'coaches_loaded', False):
            return

        self.status_var.set("Loading coaches...")
        self.root.update_idletasks()

        if not Path(self.coach_file_path).exists():
            messagebox.showerror("Error", f"Coaches file not found: {self.coach_file_path}")
            self.status_var.set("Coaches file not found")
            return

        progress = tk.Toplevel(self.root)
        progress.title("Loading coaches...")
        progress.geometry("300x80")
        progress.transient(self.root)
        ttk.Label(progress, text="Scanning coaches file...").pack(pady=10)
        progressbar = ttk.Progressbar(progress, mode='indeterminate')
        progressbar.pack(pady=10)
        progressbar.start()

        def worker():
            # Use shared loader with strict validation
            parsed_coaches = load_coaches(self.coach_file_path)
            self.root.after(0, lambda: self._on_coaches_loaded(progress, progressbar, None, parsed_coaches))

        threading.Thread(target=worker, daemon=True).start()

    def _on_coaches_loaded(self, progress, progressbar, fdi, coaches):
        try:
            progressbar.stop()
            progress.destroy()
        except Exception:
            pass

        self.coach_records = coaches
        self.coaches_loaded = True
        self.filtered_coach_records = self.coach_records.copy()
        self.populate_coach_tree()

        self.status_var.set(f"✓ Loaded {len(self.coach_records)} coaches")

    def _on_coaches_load_failed(self, progress, progressbar, error):
        try:
            progressbar.stop()
            progress.destroy()
        except Exception:
            pass

        messagebox.showerror("Error", f"Failed to load coaches:\n{error}")
        self.status_var.set("Error loading coaches")

    def populate_coach_tree(self):
        """Populate coach tree from loaded coach_records / filtered_coach_records.
        If any entries appear as 'Unknown Coach' or 'Parse Error' we load the
        decoded blobs for diagnostics and print a short hex/ascii preview to stdout.
        """
        if not hasattr(self, 'coach_tree'):
            return
        self.coach_tree.delete(*self.coach_tree.get_children())

        # Quick check whether we need to load decoded blobs for debugging
        need_debug = False
        for _offset, _coach in getattr(self, 'filtered_coach_records', []):
            display_check = getattr(_coach, 'full_name', str(_coach))
            if display_check in ('Unknown Coach', 'Parse Error', ''):
                need_debug = True
                break

        decoded_map = {}
        if need_debug:
            try:
                fdi = FDIFile(self.coach_file_path)
                fdi.load()
                for entry, decoded, length in fdi.iter_decoded_directory_entries():
                    decoded_map[entry.offset] = (decoded, length, entry.tag)
            except Exception as e:
                print(f"[COACH DEBUG] Failed to load {self.coach_file_path} for diagnostics: {e}")

        for offset, coach in getattr(self, 'filtered_coach_records', []):
            display = getattr(coach, 'full_name', str(coach))

            # If parsing returned a placeholder, show a short preview and emit diagnostics
            if display in ('Unknown Coach', 'Parse Error', ''):
                if offset in decoded_map:
                    decoded, length, tag = decoded_map[offset]
                    try:
                        tag_char = chr(tag) if 32 <= tag < 127 else '?'
                    except Exception:
                        tag_char = '?'
                    hex_preview = decoded[:64].hex()
                    ascii_preview = ''.join(chr(b) if 32 <= b < 127 else '.' for b in decoded[:64])
                    print(f"[COACH] offset=0x{offset:x}, tag=0x{tag:x} ('{tag_char}'), decoded_len={length}")
                    print(f"  hex: {hex_preview}")
                    print(f"  ascii: {ascii_preview}")
                    display = f"{display} - preview: {ascii_preview[:40]}"
                else:
                    display = f"{display} - (no decoded data)"

            self.coach_tree.insert('', tk.END, values=(display, f"0x{offset:x}"), tags=(str(offset),))

        self.coach_count_label.config(text=f"Coaches: {len(getattr(self, 'filtered_coach_records', []))} / {len(getattr(self, 'coach_records', []))}")

    def _on_coach_double(self, event):
        """Handle double-click on a coach row to open the editor (when editable)."""
        selection = self.coach_tree.selection()
        if not selection:
            return
        item = self.coach_tree.item(selection[0])
        try:
            offset = int(item['tags'][0])
        except Exception:
            return
        for o, c in self.coach_records:
            if o == offset:
                if not hasattr(c, 'to_bytes') and not hasattr(c, 'set_name'):
                    messagebox.showinfo("Not editable", "This coach entry cannot be edited in the GUI.")
                    return
                self.open_coach_editor(o, c)
                break

    def _on_team_double(self, event):
        """Handle double-click on a team row to open the team editor."""
        selection = self.team_tree.selection()
        if not selection:
            return
        item = self.team_tree.item(selection[0])
        try:
            offset = int(item['tags'][0])
        except Exception:
            return
        for o, t in self.team_records:
            if o == offset:
                self.open_team_editor(o, t)
                break

    def open_coach_editor(self, offset, coach):
        """Open modal dialog to edit coach (given name / surname)."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Edit Coach")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text="Given name:").grid(row=0, column=0, sticky=tk.W, padx=8, pady=6)
        given_var = tk.StringVar(value=getattr(coach, 'given_name', '') or '')
        given_entry = ttk.Entry(dlg, textvariable=given_var, width=30)
        given_entry.grid(row=0, column=1, padx=8, pady=6)

        ttk.Label(dlg, text="Surname:").grid(row=1, column=0, sticky=tk.W, padx=8, pady=6)
        surname_var = tk.StringVar(value=getattr(coach, 'surname', '') or getattr(coach, 'full_name', '').split()[-1] if getattr(coach, 'full_name', '') else '')
        surname_entry = ttk.Entry(dlg, textvariable=surname_var, width=30)
        surname_entry.grid(row=1, column=1, padx=8, pady=6)

        def on_save():
            g = given_var.get().strip()
            s = surname_var.get().strip()
            try:
                # Only structured coach records that provide to_bytes/set_name are editable
                if not hasattr(coach, 'to_bytes') and not hasattr(coach, 'set_name'):
                    messagebox.showinfo("Not editable", "This coach entry cannot be edited in the GUI.")
                    return

                # Prefer structured setter when available
                if hasattr(coach, 'set_name'):
                    coach.set_name(g, s)
                else:
                    # Best-effort: update attributes and rely on to_bytes when present
                    try:
                        coach.given_name = g
                        coach.surname = s
                        coach.full_name = f"{g} {s}".strip()
                    except Exception:
                        pass

                self.modified_coach_records[offset] = coach
                self.populate_coach_tree()
                self.status_var.set(f"✓ Updated coach: {getattr(coach, 'full_name', str(coach))}")
                dlg.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to update coach: {e}")

        btn_frame = ttk.Frame(dlg)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=(8,12))
        ttk.Button(btn_frame, text="Save", command=on_save).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_frame, text="Cancel", command=dlg.destroy).pack(side=tk.LEFT, padx=6)

    def open_team_editor(self, offset, team):
        """Open modal dialog to edit team name, team_id and stadium metadata."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Edit Team")
        dlg.transient(self.root)
        dlg.grab_set()
    
        # Team name
        ttk.Label(dlg, text="Team Name:").grid(row=0, column=0, sticky=tk.W, padx=8, pady=6)
        name_var = tk.StringVar(value=getattr(team, 'name', '') or '')
        ttk.Entry(dlg, textvariable=name_var, width=40).grid(row=0, column=1, padx=8, pady=6, columnspan=2)
    
        # Team ID
        ttk.Label(dlg, text="Team ID (optional):").grid(row=1, column=0, sticky=tk.W, padx=8, pady=6)
        id_var = tk.IntVar(value=getattr(team, 'team_id', 0) or 0)
        ttk.Spinbox(dlg, from_=0, to=65535, textvariable=id_var, width=12).grid(row=1, column=1, sticky=tk.W, padx=8, pady=6)
    
        # Stadium name (single-line; stadium descriptions are typically short)
        ttk.Label(dlg, text="Stadium:").grid(row=2, column=0, sticky=tk.W, padx=8, pady=6)
        stadium_var = tk.StringVar(value=getattr(team, 'stadium', '') or '')
        ttk.Entry(dlg, textvariable=stadium_var, width=60).grid(row=2, column=1, padx=8, pady=6, columnspan=2)
    
        # Capacity
        ttk.Label(dlg, text="Capacity:").grid(row=3, column=0, sticky=tk.W, padx=8, pady=6)
        cap_val = getattr(team, 'stadium_capacity', 0) or 0
        cap_var = tk.IntVar(value=cap_val)
        ttk.Spinbox(dlg, from_=0, to=1000000, textvariable=cap_var, width=14).grid(row=3, column=1, sticky=tk.W, padx=8, pady=6)
        ttk.Label(dlg, text="(seats)").grid(row=3, column=2, sticky=tk.W)
    
        # Car park
        ttk.Label(dlg, text="Car Park (spaces):").grid(row=4, column=0, sticky=tk.W, padx=8, pady=6)
        car_val = getattr(team, 'car_park', 0) or 0
        car_var = tk.IntVar(value=car_val)
        ttk.Spinbox(dlg, from_=0, to=200000, textvariable=car_var, width=14).grid(row=4, column=1, sticky=tk.W, padx=8, pady=6)
    
        # Pitch quality
        ttk.Label(dlg, text="Pitch quality:").grid(row=5, column=0, sticky=tk.W, padx=8, pady=6)
        pitch_var = tk.StringVar(value=(getattr(team, 'pitch', '') or '').upper())
        pitch_combo = ttk.Combobox(dlg, textvariable=pitch_var, state='readonly', width=16)
        pitch_combo['values'] = ['GOOD', 'EXCELLENT', 'AVERAGE', 'POOR', 'UNKNOWN']
        pitch_combo.grid(row=5, column=1, sticky=tk.W, padx=8, pady=6)
    
        def on_save():
            new_name = name_var.get().strip()
            try:
                # Name
                if hasattr(team, 'set_name'):
                    team.set_name(new_name)
                else:
                    team.name = new_name
    
                # Team ID (best-effort)
                try:
                    new_id = int(id_var.get())
                    if new_id:
                        team.team_id = new_id
                except Exception:
                    pass
    
                # Stadium text
                new_stadium = stadium_var.get().strip()
                if new_stadium:
                    if hasattr(team, 'set_stadium_name'):
                        team.set_stadium_name(new_stadium)
                    else:
                        team.stadium = new_stadium
    
                # Capacity (only apply if > 0)
                try:
                    c = int(cap_var.get())
                    if c and hasattr(team, 'set_capacity'):
                        team.set_capacity(c)
                except Exception:
                    pass
    
                # Car park
                try:
                    cp = int(car_var.get())
                    if cp and hasattr(team, 'set_car_park'):
                        team.set_car_park(cp)
                except Exception:
                    pass
    
                # Pitch
                p = (pitch_var.get() or '').strip().upper()
                if p and hasattr(team, 'set_pitch'):
                    team.set_pitch(p)
    
                # Mark modified and refresh UI
                self.modified_team_records[offset] = team
                self.populate_team_tree()
                try:
                    self.build_team_lookup()
                    self.populate_tree()
                except Exception:
                    pass
    
                self.status_var.set(f"✓ Updated team: {getattr(team,'name','')}")
                dlg.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to update team: {e}")
    
        btn_frame = ttk.Frame(dlg)
        btn_frame.grid(row=6, column=0, columnspan=3, pady=(8,12))
        ttk.Button(btn_frame, text="Save", command=on_save).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_frame, text="Cancel", command=dlg.destroy).pack(side=tk.LEFT, padx=6)

    def populate_team_tree(self):
        """Populate team tree from loaded team_records / filtered_team_records.
        When teams show as 'Unknown Team' or 'Parse Error' this will attempt to
        decode the entry and print diagnostics (hex/ascii preview) to stdout.
        """
        if not hasattr(self, 'team_tree'):
            return
        self.team_tree.delete(*self.team_tree.get_children())

        # Determine if we need to load decoded blobs for diagnostics
        need_debug = False
        for _offset, _team in getattr(self, 'filtered_team_records', []):
            display_check = getattr(_team, 'name', None) or "Unknown Team"
            if display_check in ('Unknown Team', 'Parse Error', ''):
                need_debug = True
                break

        decoded_map = {}
        if need_debug:
            try:
                fdi = FDIFile(self.team_file_path)
                fdi.load()
                for entry, decoded, length in fdi.iter_decoded_directory_entries():
                    decoded_map[entry.offset] = (decoded, length, entry.tag)
            except Exception as e:
                print(f"[TEAM DEBUG] Failed to load {self.team_file_path} for diagnostics: {e}")

        for offset, team in getattr(self, 'filtered_team_records', []):
            name = getattr(team, 'name', None) or "Unknown Team"
            # If parsing returned a placeholder, show a short preview and emit diagnostics
            if name in ('Unknown Team', 'Parse Error', ''):
                if offset in decoded_map:
                    decoded, length, tag = decoded_map[offset]
                    try:
                        tag_char = chr(tag) if 32 <= tag < 127 else '?'
                    except Exception:
                        tag_char = '?'
                    hex_preview = decoded[:64].hex()
                    ascii_preview = ''.join(chr(b) if 32 <= b < 127 else '.' for b in decoded[:64])
                    print(f"[TEAM] offset=0x{offset:x}, tag=0x{tag:x} ('{tag_char}'), decoded_len={length}")
                    print(f"  hex: {hex_preview}")
                    print(f"  ascii: {ascii_preview}")
                    name = f"{name} - preview: {ascii_preview[:40]}"
                else:
                    name = f"{name} - (no decoded data)"

            team_id = getattr(team, 'team_id', 0)
            self.team_tree.insert('', tk.END, values=(name, team_id if team_id else '', f"0x{offset:x}"), tags=(str(offset),))

        self.team_count_label.config(text=f"Teams: {len(getattr(self, 'filtered_team_records', []))} / {len(getattr(self, 'team_records', []))}")

    def build_team_lookup(self):
        """Build mapping from team_id to team_name from parsed team_records."""
        self.team_lookup = {}
        for offset, team in getattr(self, 'team_records', []):
            try:
                tid = getattr(team, 'team_id', 0)
                name = getattr(team, 'name', None)
                if tid and name:
                    self.team_lookup[int(tid)] = name
            except Exception:
                continue
        # Fallback: if no mapping discovered, attempt to correlate by scanning team bytes (slow)
        if not self.team_lookup:
            try:
                from pm99_editor.correlate import correlate_teams_players
                mapping, _ = correlate_teams_players(self.file_path, self.team_file_path)
                for k, v in mapping.items():
                    try:
                        self.team_lookup[int(k)] = v
                    except Exception:
                        continue
            except Exception:
                pass

    def filter_teams(self, *args):
        """Filter teams by search box"""
        search = self.team_search_var.get().lower()
        if search:
            self.filtered_team_records = [(o, t) for o, t in self.team_records if search in (getattr(t, 'name','').lower())]
        else:
            self.filtered_team_records = self.team_records.copy()
        self.populate_team_tree()

    def populate_league_tree(self):
        """Populate league tree with hierarchical Country -> League -> Teams structure"""
        if not hasattr(self, 'league_tree'):
            return
        
        # Clear existing items
        for item in self.league_tree.get_children():
            self.league_tree.delete(item)
        
        # Get country filter
        country_filter = self.league_country_var.get() if hasattr(self, 'league_country_var') else "All"
        search_text = self.league_search_var.get().lower() if hasattr(self, 'league_search_var') else ""
        
        try:
            from pm99_editor.league_definitions import get_team_league
        except:
            get_team_league = None
        
        # Group teams by (country, league)
        structure = defaultdict(lambda: defaultdict(list))
        
        for offset, team in getattr(self, 'filtered_team_records', []):
            # Apply search filter
            team_name = getattr(team, 'name', 'Unknown Team')
            if search_text and search_text not in team_name.lower():
                continue
            
            # Get country and league
            if get_team_league:
                country, league_name = get_team_league(team.team_id)
                if not country:
                    country = "Unknown"
                if not league_name:
                    league_name = "Unknown League"
            else:
                country = "Unknown"
                league_name = getattr(team, 'league', 'Unknown League')
            
            # Apply country filter
            if country_filter != "All" and country != country_filter:
                continue
            
            structure[country][league_name].append((offset, team))
        
        # Build tree: Country -> League -> Teams
        total_leagues = 0
        for country in sorted(structure.keys()):
            # Add country node
            country_id = self.league_tree.insert('', tk.END, text=country,
                                                  values=('', '', f"{sum(len(teams) for teams in structure[country].values())} teams"),
                                                  tags=('country',))
            
            # Add league nodes under country
            for league_name in sorted(structure[country].keys()):
                teams = structure[country][league_name]
                total_leagues += 1
                
                # Add league node
                league_id = self.league_tree.insert(country_id, tk.END, text=league_name,
                                                     values=('', '', f"{len(teams)} teams"),
                                                     tags=('league',))
                
                # Add team nodes under league
                for offset, team in sorted(teams, key=lambda x: getattr(x[1], 'name', '')):
                    team_name = getattr(team, 'name', 'Unknown Team')
                    team_id = getattr(team, 'team_id', 0)
                    stadium = getattr(team, 'stadium', '')
                    capacity = getattr(team, 'stadium_capacity', None)
                    capacity_str = f"{capacity:,}" if capacity else ""
                    
                    self.league_tree.insert(league_id, tk.END, text=team_name,
                                           values=(team_id if team_id else '', stadium, capacity_str),
                                           tags=('team', str(offset)))
        
        # Style the tree
        try:
            self.league_tree.tag_configure('country', font=('TkDefaultFont', 10, 'bold'))
            self.league_tree.tag_configure('league', font=('TkDefaultFont', 9, 'bold'))
        except:
            pass
        
        self.league_count_label.config(text=f"Leagues: {total_leagues}")

    def filter_leagues(self, *args):
        """Filter leagues by search box"""
        search = self.league_search_var.get().lower()
        if search:
            # Filter teams first
            filtered_teams = [(o, t) for o, t in self.team_records if search in (getattr(t, 'name','').lower()) or search in (getattr(t, 'league','').lower())]
            self.filtered_team_records = filtered_teams
        else:
            self.filtered_team_records = self.team_records.copy()
        self.populate_league_tree()

    def on_select_league(self, event):
        """Handle selection in the league tree"""
        selection = self.league_tree.selection()
        if not selection:
            return

        item = self.league_tree.item(selection[0])
        tags = item['tags']
        if not tags:
            return

        # Check what was selected
        tag = tags[0]
        if tag == 'country':
            country_name = item['text']
            self.status_var.set(f"Selected country: {country_name}")
        elif tag == 'league':
            league_name = item['text']
            self.status_var.set(f"Selected league: {league_name}")
        elif tag == 'team':
            # Team selected - show in status
            team_name = item['text']
            try:
                offset = int(tags[1]) if len(tags) > 1 else 0
                self.status_var.set(f"Selected team: {team_name} (double-click to edit)")
            except:
                self.status_var.set(f"Selected team: {team_name}")
    
    def on_league_doubleclick(self, event):
        """Handle double-click in league tree - edit team if team is selected"""
        selection = self.league_tree.selection()
        if not selection:
            return
        
        item = self.league_tree.item(selection[0])
        tags = item['tags']
        if not tags:
            return
        
        # Only handle team double-clicks
        if 'team' not in tags:
            # If it's a country or league, expand/collapse it
            current_open = self.league_tree.item(selection[0], 'open')
            self.league_tree.item(selection[0], open=not current_open)
            return
        
        # Find offset from tags
        try:
            offset = int(tags[1]) if len(tags) > 1 else None
            if offset is None:
                return
        except:
            return
        
        # Find and edit the team
        for o, t in self.team_records:
            if o == offset:
                self.open_team_editor(o, t)
                break

    def on_select_team(self, event):
        """Handle team selection in the team tree"""
        selection = self.team_tree.selection()
        if not selection:
            return

        item = self.team_tree.item(selection[0])
        try:
            offset = int(item['tags'][0])
        except Exception:
            return

        for o, t in self.team_records:
            if o == offset:
                try:
                    self._show_team_overlay()
                    self._populate_team_overlay(t)
                    name = getattr(t, 'name', 'Unknown Team')
                    self.status_var.set(f"Selected team: {name}")
                except Exception:
                    pass
                break

    def _toggle_roster(self):
        """Toggle roster panel visibility in the team overlay."""
        try:
            if self.team_panel_roster_visible:
                self.team_panel_roster_frame.pack_forget()
                self.team_panel_roster_visible = False
                self.team_panel_roster_toggle_btn.config(text="Show squad lineup")
            else:
                self.team_panel_roster_frame.pack(fill=tk.BOTH, expand=True, pady=(5,5))
                self.team_panel_roster_visible = True
                self.team_panel_roster_toggle_btn.config(text="Hide squad lineup")
        except Exception:
            pass

    def _populate_roster_tree_with_team(self, team):
        """Populate roster tree for given TeamRecord with PM99-style lineup (Starting XI, Subs, Reserves)."""
        try:
            # Clear existing items
            for it in self.team_roster_tree.get_children():
                self.team_roster_tree.delete(it)
        except Exception:
            pass
        
        try:
            tid = getattr(team, 'team_id', None)
            # Search all_records list for players with matching team_id
            players = []
            for o, r in getattr(self, 'all_records', []):
                try:
                    if getattr(r, 'team_id', None) == tid:
                        players.append((o, r))
                except Exception:
                    continue
            
            # Sort by squad number
            players.sort(key=lambda x: getattr(x[1], 'squad_number', 99))
            
            # Insert section headers and players
            section_tags = {
                'starting': ('STARTING XI', '#e8f4f8', 'bold'),
                'subs': ('SUBSTITUTES', '#fff4e6', 'bold'),
                'reserves': ('RESERVES', '#f0f0f0', 'bold')
            }
            
            for off, rec in players:
                squad_num = getattr(rec, 'squad_number', 0)
                
                # Determine section
                if squad_num >= 1 and squad_num <= 11:
                    section = 'starting'
                elif squad_num >= 12 and squad_num <= 16:
                    section = 'subs'
                elif squad_num >= 17 and squad_num <= 20:
                    section = 'reserves'
                else:
                    continue  # Skip players outside squad range
                
                # Get player name
                display = getattr(rec, 'name', None)
                if not display:
                    given = getattr(rec, 'given_name', '') or ''
                    surname = getattr(rec, 'surname', '') or ''
                    display = f"{given} {surname}".strip()
                
                # Get position
                pos_abbr = self._get_position_abbr(rec.get_position_name() if hasattr(rec, 'get_position_name') else 'Unknown')
                
                # Get role based on position and squad number
                role = self._get_player_role(rec, squad_num)
                
                # Get attributes (12 attributes total)
                attrs = getattr(rec, 'attributes', [50] * 12)
                if len(attrs) < 12:
                    attrs = list(attrs) + [50] * (12 - len(attrs))
                
                # Calculate average (first 10 attributes for average)
                avg = sum(attrs[:10]) // 10 if attrs else 50
                
                # Map attributes to display columns
                # Based on PM99: EN SP ST AG QU FI MO AV
                # attrs[0-11] map to various skills
                en = attrs[0] if len(attrs) > 0 else 50  # Energy/Pace
                sp = attrs[1] if len(attrs) > 1 else 50  # Speed
                st = attrs[2] if len(attrs) > 2 else 50  # Stamina
                ag = attrs[3] if len(attrs) > 3 else 50  # Agility/Aggression
                qu = attrs[4] if len(attrs) > 4 else 50  # Quality
                fi = attrs[5] if len(attrs) > 5 else 50  # Fitness
                mo = attrs[6] if len(attrs) > 6 else 50  # Morale
                
                try:
                    item_id = self.team_roster_tree.insert('', tk.END,
                        values=(squad_num, display, en, sp, st, ag, qu, fi, mo, avg, role, pos_abbr),
                        tags=(section, str(off)))
                    
                    # Apply section-specific styling
                    if section == 'starting':
                        self.team_roster_tree.item(item_id, tags=(section, str(off)))
                    elif section == 'subs':
                        self.team_roster_tree.item(item_id, tags=(section, str(off)))
                    elif section == 'reserves':
                        self.team_roster_tree.item(item_id, tags=(section, str(off)))
                        
                except Exception as e:
                    logger.debug(f"Failed to insert player {display}: {e}")
                    continue
            
            # Configure tag colors for different sections
            try:
                self.team_roster_tree.tag_configure('starting', background='#e8f4f8')
                self.team_roster_tree.tag_configure('subs', background='#fff4e6')
                self.team_roster_tree.tag_configure('reserves', background='#f0f0f0')
            except Exception:
                pass
                
        except Exception as e:
            logger.debug(f"Failed to populate roster: {e}")
            pass
    
    def _get_position_abbr(self, position_name):
        """Get position abbreviation for display."""
        abbr_map = {
            'Goalkeeper': 'GOAL',
            'Defender': 'DEF',
            'Midfielder': 'MID',
            'Forward': 'FOR',
            'Unknown': 'UNK'
        }
        return abbr_map.get(position_name, 'UNK')
    
    def _get_player_role(self, player, squad_num):
        """Determine player role based on position and squad number."""
        pos_name = player.get_position_name() if hasattr(player, 'get_position_name') else 'Unknown'
        
        if squad_num == 1:
            return '🟢'  # Goalkeeper indicator
        elif squad_num >= 2 and squad_num <= 11:
            return '⚪'  # Starting XI indicator
        else:
            return '🔵'  # Sub/Reserve indicator

    def _populate_team_overlay(self, team):
        """Set overlay vars and roster for selected TeamRecord."""
        try:
            if not getattr(self, 'team_overlay_active', False):
                self._show_team_overlay()
            self.team_panel_name_var.set(getattr(team, 'name', '') or '')
            self.team_panel_id_var.set(getattr(team, 'team_id', 0) or 0)
            self.team_panel_stadium_var.set(getattr(team, 'stadium', '') or '')
            self.team_panel_capacity_var.set(getattr(team, 'stadium_capacity', 0) or 0)
            self.team_panel_car_var.set(getattr(team, 'car_park', 0) or 0)
            self.team_panel_pitch_var.set((getattr(team, 'pitch', '') or '').upper() or 'UNKNOWN')
            if self.team_panel_roster_visible:
                self._toggle_roster()
            else:
                self.team_panel_roster_toggle_btn.config(text="Show squad lineup")
            self._populate_roster_tree_with_team(team)
        except Exception:
            pass

    def _clear_team_overlay(self):
        """Reset overlay fields to default/blank state and collapse the roster."""
        try:
            self.team_panel_name_var.set("")
            self.team_panel_id_var.set(0)
            self.team_panel_stadium_var.set("")
            self.team_panel_capacity_var.set(0)
            self.team_panel_car_var.set(0)
            self.team_panel_pitch_var.set("UNKNOWN")
            for item in self.team_roster_tree.get_children():
                self.team_roster_tree.delete(item)
            if self.team_panel_roster_visible:
                self._toggle_roster()
            else:
                self.team_panel_roster_toggle_btn.config(text="Show squad lineup")
        except Exception:
            pass

    def _show_team_overlay(self):
        """Display the team overlay panel, hiding the underlying player editor."""
        try:
            if not getattr(self, 'team_overlay_active', False):
                self._clear_team_overlay()
                self.team_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
                self.team_overlay_active = True
        except Exception:
            pass

    def _hide_team_overlay(self):
        """Hide the team overlay panel and restore the player editor."""
        try:
            if getattr(self, 'team_overlay_active', False):
                self.team_overlay.place_forget()
                self.team_overlay_active = False
                self._clear_team_overlay()
        except Exception:
            pass

    def apply_team_changes(self):
        """Apply edits from the team overlay back to the TeamRecord and mark modified."""
        try:
            selection = self.team_tree.selection()
            if not selection:
                messagebox.showinfo("Info", "No team selected")
                return
            item = self.team_tree.item(selection[0])
            offset = int(item['tags'][0])
            for o, t in self.team_records:
                if o == offset:
                    new_name = self.team_panel_name_var.get().strip()
                    if hasattr(t, 'set_name'):
                        t.set_name(new_name)
                    else:
                        t.name = new_name
                    try:
                        new_id = int(self.team_panel_id_var.get())
                        if new_id:
                            t.team_id = new_id
                    except Exception:
                        pass
                    new_stad = self.team_panel_stadium_var.get().strip()
                    if new_stad:
                        if hasattr(t, 'set_stadium_name'):
                            t.set_stadium_name(new_stad)
                        else:
                            t.stadium = new_stad
                    try:
                        c = int(self.team_panel_capacity_var.get())
                        if c and hasattr(t, 'set_capacity'):
                            t.set_capacity(c)
                    except Exception:
                        pass
                    try:
                        cp = int(self.team_panel_car_var.get())
                        if cp and hasattr(t, 'set_car_park'):
                            t.set_car_park(cp)
                    except Exception:
                        pass
                    p = (self.team_panel_pitch_var.get() or '').strip().upper()
                    if p and hasattr(t, 'set_pitch'):
                        t.set_pitch(p)
                    self.modified_team_records[o] = t
                    self.populate_team_tree()
                    try:
                        self.build_team_lookup()
                        self.populate_tree()
                    except Exception:
                        pass
                    self.status_var.set(f"✓ Updated team: {getattr(t, 'name', '')}")
                    break
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save team changes: {e}")

    def reset_team_editor(self):
        """Reset team overlay fields to current TeamRecord values."""
        try:
            selection = self.team_tree.selection()
            if not selection:
                return
            item = self.team_tree.item(selection[0])
            offset = int(item['tags'][0])
            for o, t in self.team_records:
                if o == offset:
                    self.team_panel_name_var.set(getattr(t, 'name', '') or '')
                    self.team_panel_id_var.set(getattr(t, 'team_id', 0) or 0)
                    self.team_panel_stadium_var.set(getattr(t, 'stadium', '') or '')
                    self.team_panel_capacity_var.set(getattr(t, 'stadium_capacity', 0) or 0)
                    self.team_panel_car_var.set(getattr(t, 'car_park', 0) or 0)
                    self.team_panel_pitch_var.set((getattr(t, 'pitch', '') or '').upper() or 'UNKNOWN')
                    self._populate_roster_tree_with_team(t)
                    break
        except Exception:
            pass

    def filter_coaches(self, *args):
        """Filter coaches by search box"""
        search = self.coach_search_var.get().lower()
        if search:
            self.filtered_coach_records = [(o, c) for o, c in self.coach_records if search in (getattr(c, 'full_name', str(c)).lower())]
        else:
            self.filtered_coach_records = self.coach_records.copy()
        self.populate_coach_tree()

    def on_select_coach(self, event):
        """Handle coach selection in the coach tree"""
        selection = self.coach_tree.selection()
        if not selection:
            return

        item = self.coach_tree.item(selection[0])
        try:
            offset = int(item['tags'][0])
        except Exception:
            self.status_var.set("Error: Invalid coach selection")
            return

        # Find the coach record
        coach_found = False
        for o, c in getattr(self, 'coach_records', []):
            if o == offset:
                display = getattr(c, 'full_name', str(c))
                # Clear name fields and attribute widgets (coaches don't have player attributes)
                self.given_name_var.set("")
                self.surname_var.set("")
                for widget in self.attr_container.winfo_children():
                    widget.destroy()
                self.status_var.set(f"Selected coach: {display}")
                coach_found = True
                break

        if not coach_found:
            self.status_var.set(f"Error: Coach at offset 0x{offset:x} not found")
            self.given_name_var.set("")
            self.surname_var.set("")

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
            # Clear player-specific display when switching to coaches
            self.given_name_var.set("")
            self.surname_var.set("")
            for widget in self.attr_container.winfo_children():
                widget.destroy()
        elif tab_text == "Teams":
            self._show_team_overlay()
            # Clear player-specific display when switching to teams
            self.given_name_var.set("")
            self.surname_var.set("")
            for widget in self.attr_container.winfo_children():
                widget.destroy()
        elif tab_text == "Leagues":
            self._hide_team_overlay()
            # Populate leagues if teams are loaded
            if getattr(self, 'teams_loaded', False):
                self.populate_league_tree()
            # Clear player-specific display when switching to leagues
            self.given_name_var.set("")
            self.surname_var.set("")
            for widget in self.attr_container.winfo_children():
                widget.destroy()
        else:
            self._hide_team_overlay()
    
    def filter_records(self, *args):
        """Filter players by search"""
        search = self.search_var.get().lower()
        if search:
            self.filtered_records = [(o, r) for o, r in self.all_records if search in r.name.lower()]
        else:
            self.filtered_records = self.all_records.copy()
        self.populate_tree()
    
    def on_select(self, event):
        """Handle player selection"""
        selection = self.tree.selection()
        if not selection:
            return
        
        # Get record from tag
        item = self.tree.item(selection[0])
        offset = int(item['tags'][0])
        
        # Find the record
        for o, r in self.all_records:
            if o == offset:
                self.current_record = (o, r)
                self.display_record(r)
                break
    
    def display_record(self, record: PlayerRecord):
        """Display record in editor"""
        # Populate name fields
        given = getattr(record, 'given_name', '') or ''
        surname = getattr(record, 'surname', '') or ''
        self.given_name_var.set(given)
        self.surname_var.set(surname)
        
        self.team_id_var.set(record.team_id)
        self.squad_var.set(record.squad_number)
        self.position_var.set(record.get_position_name())
        
        # Metadata fields (nationality, DOB, height)
        self.nationality_var.set(record.nationality_id if getattr(record, 'nationality_id', None) is not None else 0)
        
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
        
        self.height_var.set(record.height if getattr(record, 'height', None) is not None else 175)
        
        # Clear and rebuild attributes
        for widget in self.attr_container.winfo_children():
            widget.destroy()
        
        self.attr_vars = []
        
        for i, attr_val in enumerate(record.attributes):
            frame = ttk.Frame(self.attr_container)
            frame.pack(fill=tk.X, pady=2)
            
            label_text = self.attr_labels[i] if i < len(self.attr_labels) else f"Attribute {i}"
            ttk.Label(frame, text=label_text, width=18).pack(side=tk.LEFT, padx=5)
            
            var = tk.IntVar(value=attr_val)
            self.attr_vars.append(var)
            
            ttk.Spinbox(frame, from_=0, to=100, textvariable=var, width=8).pack(side=tk.LEFT, padx=5)
            ttk.Scale(frame, from_=0, to=100, variable=var, orient=tk.HORIZONTAL, length=200).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            
            val_label = ttk.Label(frame, text=str(attr_val), width=4, font=('TkDefaultFont', 9, 'bold'))
            val_label.pack(side=tk.RIGHT, padx=5)
            
            def make_updater(lbl, v):
                return lambda *args: lbl.config(text=str(v.get()))
            var.trace('w', make_updater(val_label, var))
    
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
                except ValueError as e:
                    messagebox.showerror("Invalid Name", f"Given name error: {e}")
                    return
            
            if new_surname != old_surname:
                try:
                    record.set_surname(new_surname)
                    changes.append(f"Surname: {old_surname} → {new_surname}")
                except ValueError as e:
                    messagebox.showerror("Invalid Name", f"Surname error: {e}")
                    return
            
            # Team ID
            new_team_id = self.team_id_var.get()
            if new_team_id != record.team_id:
                record.set_team_id(new_team_id)
                changes.append(f"Team ID: {record.team_id} → {new_team_id}")
            
            # Squad number
            new_squad = self.squad_var.get()
            if new_squad != record.squad_number:
                record.set_squad_number(new_squad)
                changes.append(f"Squad #: {record.squad_number} → {new_squad}")
            
            # Position
            pos_name = self.position_var.get()
            pos_map = {"Goalkeeper": 0, "Defender": 1, "Midfielder": 2, "Forward": 3}
            new_pos = pos_map.get(pos_name, 0)
            if new_pos != record.position:
                old_pos_name = record.get_position_name()
                record.set_position(new_pos)
                changes.append(f"Position: {old_pos_name} → {pos_name}")
            
            # Metadata: Nationality, DOB, Height
            # Nationality ID
            new_nat = self.nationality_var.get()
            old_nat = getattr(record, 'nationality_id', None)
            old_nat_display = old_nat if old_nat is not None else 'None'
            old_nat_comp = old_nat if old_nat is not None else 0
            if new_nat != old_nat_comp:
                record.set_nationality(new_nat)
                changes.append(f"Nationality ID: {old_nat_display} → {new_nat}")
            
            # DOB
            new_day = self.dob_day_var.get()
            new_month = self.dob_month_var.get()
            new_year = self.dob_year_var.get()
            old_dob = getattr(record, 'dob', None)
            old_dob_comp = old_dob if old_dob is not None else None
            if old_dob_comp is None or (new_day, new_month, new_year) != old_dob_comp:
                record.set_dob(new_day, new_month, new_year)
                old_dob_display = f"{old_dob[0]}/{old_dob[1]}/{old_dob[2]}" if old_dob else "None"
                changes.append(f"DOB: {old_dob_display} → {new_day}/{new_month}/{new_year}")
            
            # Height
            new_height = self.height_var.get()
            old_height = getattr(record, 'height', None)
            if old_height is None or new_height != old_height:
                record.set_height(new_height)
                old_height_display = old_height if old_height is not None else 'None'
                changes.append(f"Height: {old_height_display} → {new_height} cm")
            
            # Attributes
            for i, var in enumerate(self.attr_vars):
                new_val = var.get()
                if new_val != record.attributes[i]:
                    old_val = record.attributes[i]
                    record.set_attribute(i, new_val)
                    changes.append(f"{self.attr_labels[i]}: {old_val} → {new_val}")
            
            if changes:
                self.modified_records[offset] = record
                change_text = '\n'.join(changes[:10])  # Show first 10 changes
                if len(changes) > 10:
                    change_text += f"\n... and {len(changes)-10} more changes"
                
                self.status_var.set(f"✓ {len(changes)} change(s) applied to {record.name}")
                messagebox.showinfo("Success", f"Changes applied to {record.name}:\n\n{change_text}\n\nSave database to persist changes (Ctrl+S)")
            else:
                messagebox.showinfo("Info", "No changes to apply")
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to apply changes:\n{str(e)}")
    
    def reset_current(self):
        """Reset current player to original values"""
        if self.current_record:
            self.display_record(self.current_record[1])
            self.status_var.set("Reset to original values")
    
    def save_database(self):
        """Save modified database (players, coaches, teams)."""
        n_players = len(getattr(self, 'modified_records', {}))
        n_coaches = len(getattr(self, 'modified_coach_records', {}))
        n_teams = len(getattr(self, 'modified_team_records', {}))

        if n_players == 0 and n_coaches == 0 and n_teams == 0:
            messagebox.showinfo("Info", "No changes to save")
            return

        parts = []
        if n_players:
            parts.append(f"{n_players} player(s) → {self.file_path}")
        if n_coaches:
            parts.append(f"{n_coaches} coach(es) → {self.coach_file_path}")
        if n_teams:
            parts.append(f"{n_teams} team(s) → {self.team_file_path}")

        result = messagebox.askyesno("Confirm Save",
            "Save the following changes?\n\n" + "\n".join(parts) + "\n\nA backup will be created for each file.")
        if not result:
            return

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backups = []

            # Players
            if n_players:
                player_backup = Path(self.file_path + f'.backup_{timestamp}')
                player_backup.write_bytes(self.file_data)
                modified_list = [(o, r) for o, r in self.modified_records.items()]
                new_data = save_modified_records(self.file_path, self.file_data, modified_list)
                Path(self.file_path).write_bytes(new_data)
                self.file_data = new_data
                self.modified_records.clear()
                backups.append(str(player_backup))

            # Coaches
            if n_coaches:
                coach_path = Path(self.coach_file_path)
                coach_data = coach_path.read_bytes()
                coach_backup = coach_path.with_name(coach_path.name + f'.backup_{timestamp}')
                coach_backup.write_bytes(coach_data)
                modified_list = [(o, r) for o, r in self.modified_coach_records.items()]
                new_data = save_modified_records(self.coach_file_path, coach_data, modified_list)
                coach_path.write_bytes(new_data)
                self.modified_coach_records.clear()
                backups.append(str(coach_backup))

            # Teams
            if n_teams:
                team_path = Path(self.team_file_path)
                team_data = team_path.read_bytes()
                team_backup = team_path.with_name(team_path.name + f'.backup_{timestamp}')
                team_backup.write_bytes(team_data)
                modified_list = [(o, r) for o, r in self.modified_team_records.items()]
                new_data = save_modified_records(self.team_file_path, team_data, modified_list)
                team_path.write_bytes(new_data)
                self.modified_team_records.clear()
                backups.append(str(team_backup))

            self.status_var.set(f"✓ Database saved")
            messagebox.showinfo("Success", f"Database saved!\nBackups:\n" + "\n".join(backups))

        except Exception as e:
            messagebox.showerror("Error", f"Failed to save:\n{str(e)}")
    
    def export_coaches(self):
        """Export coach list to clipboard"""
        if not hasattr(self, 'filtered_coach_records'):
            return
        coach_names = []
        for offset, coach in self.filtered_coach_records:
            display = getattr(coach, 'full_name', str(coach))
            coach_names.append(display)
        export_text = '\n'.join(coach_names)
        self.root.clipboard_clear()
        self.root.clipboard_append(export_text)
        messagebox.showinfo("Export Complete", f"Exported {len(coach_names)} coaches to clipboard")

    def export_teams(self):
        """Export team list to clipboard with offset and team_id for debugging"""
        if not hasattr(self, 'filtered_team_records'):
            return
        team_lines = []
        for offset, team in self.filtered_team_records:
            name = getattr(team, 'name', None) or "Unknown Team"
            team_id = getattr(team, 'team_id', 0)
            league = getattr(team, 'league', 'Unknown')
            # Format: offset | team_id | name | league
            team_lines.append(f"0x{offset:08x} | {team_id:5d} | {name:<50s} | {league}")
        
        # Add header
        header = f"{'Offset':<12} | {'ID':<5} | {'Name':<50} | League\n" + "="*100
        export_text = header + '\n' + '\n'.join(team_lines)
        
        self.root.clipboard_clear()
        self.root.clipboard_append(export_text)
        messagebox.showinfo("Export Complete",
                          f"Exported {len(team_lines)} teams to clipboard\n\n" +
                          "Format: Offset | Team ID | Name | League")

    def open_file(self):
        """Open different database file"""
        filename = filedialog.askopenfilename(
            filetypes=[("FDI files", "*.FDI"), ("All files", "*.*")],
            initialdir="DBDAT"
        )
        if filename:
            self.file_path = filename
            self.modified_records.clear()
            self.load_database()

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