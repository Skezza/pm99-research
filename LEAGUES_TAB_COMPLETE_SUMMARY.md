# Leagues Tab Implementation - Complete Summary

## Confirmed League Structure (from game screenshots)

### England (4 Divisions)
Based on the provided game screenshots showing the England league selection screen:

1. **Premier League** (highlighted in yellow/gold)
   - Team IDs: 3712-3731
   - 20 teams per division
   
2. **First Division** (highlighted in orange/red)
   - Team IDs: 3732-3751
   - 20 teams per division
   
3. **Second Division**
   - Team IDs: 3752-3771
   - 20 teams per division
   
4. **Third Division**
   - Team IDs: 3772-3791
   - 20 teams per division

**Total: 80 English teams**

### UI Layout (from screenshots)
- Main area: Team kits displayed in grid
- Right side: League selection buttons (vertically stacked)
- Bottom: Search and Cancel buttons
- Team kits shown as colored shirts

## Completed Implementation ✅

### 1. League Definitions Module
**File**: [`pm99_editor/league_definitions.py`](pm99_editor/league_definitions.py)

Provides:
```python
# Get team's league
country, league = get_team_league(team_id)

# Get all countries
countries = get_all_countries()  # ['England', 'France', 'Germany', ...]

# Get leagues for a country
leagues = get_country_leagues("England")  
# Returns: [Premier League, First Division, Second Division, Third Division]

# Check if English team
is_english = is_english_team(team_id)

# Get division number (England only)
division = get_english_division(team_id)  # Returns 1-4
```

### 2. Team Loader
**File**: [`pm99_editor/loaders.py`](pm99_editor/loaders.py:234-296)

Correctly loads teams from:
- Section 1 @ 0x201 (~11KB)
- Section 2 @ 0x2f04 (~42KB)

Uses:
- XOR 0x61 decoding
- Separator pattern: `0x61 0xdd 0x63`

### 3. TeamRecord Model Updates
**File**: [`pm99_editor/models.py`](pm99_editor/models.py:226-243)

Added methods:
```python
team.league         # Returns "Premier League", etc.
team.get_country()  # Returns "England", "Spain", etc.
```

### 4. Documentation
- [`LEAGUES_TAB_IMPLEMENTATION_PLAN.md`](LEAGUES_TAB_IMPLEMENTATION_PLAN.md) - Initial plan
- [`LEAGUES_TAB_FINAL_PLAN.md`](LEAGUES_TAB_FINAL_PLAN.md) - Updated plan with findings

## Remaining Work 🔧

### Critical Blocker: Fix Team Name Extraction
**File**: [`pm99_editor/models.py`](pm99_editor/models.py:77-141)
**Method**: `TeamRecord._extract_name()`

**Current Issues**:
- Extracting garbage: "Caaa", "BaaanEaaa", "GomesNGvaC.F. Estrela da Amadora"
- Only 8-24 teams loading instead of ~200+
- Validation filters too strict for team data structure

**Proposed Fix**:
```python
def _extract_name(self):
    """Extract team name from decoded team record."""
    try:
        # Team record structure after separator:
        # [0x61 0xdd 0x63] [prefix: 0x61 0x60 XX 0x61] [TEAM NAME] ...
        
        # Skip separator (first 3 bytes)
        start = 3
        
        # Skip prefix bytes until first uppercase letter
        while start < len(self.raw_data) and start < 20:
            if ord('A') <= self.raw_data[start] <= ord('Z'):
                break
            start += 1
        
        if start >= len(self.raw_data):
            return "Unknown Team", 0, 0
        
        # Extract until:
        # 1. Lowercase 'a' separator before stadium text
        # 2. Non-printable character
        # 3. Maximum 60 characters
        end = start
        for i in range(start, min(start + 60, len(self.raw_data))):
            c = self.raw_data[i]
            
            # Stop at lowercase 'a' that looks like separator
            if c == ord('a') and i > start + 5:
                # Check if followed by uppercase (stadium name)
                if i + 1 < len(self.raw_data):
                    next_c = self.raw_data[i + 1]
                    if ord('A') <= next_c <= ord('Z'):
                        end = i
                        break
            
            # Stop at non-printable
            if c < 32 or c > 126:
                end = i
                break
            
            end = i + 1
        
        if end > start:
            name_bytes = self.raw_data[start:end]
            name = name_bytes.decode('latin1', errors='replace').strip()
            
            # Clean up common artifacts
            # Remove trailing 'a' characters if they look like separators
            while name and name[-1] == 'a' and len(name) > 5:
                name = name[:-1]
            
            return name, start, end
        
        return "Unknown Team", 0, 0
        
    except Exception as e:
        logger.debug("Team name extraction failed: %s", e)
        return "Parse Error", 0, 0
```

### Implement Leagues Tab UI
**File**: [`pm99_editor/gui.py`](pm99_editor/gui.py)

**Add after Teams tab**:
```python
def create_leagues_tab(self):
    """Create Leagues tab with hierarchical team view."""
    self.leagues_tab = ttk.Frame(self.notebook)
    self.notebook.add(self.leagues_tab, text="⚽ Leagues")
    
    # Top: Country filter
    filter_frame = ttk.Frame(self.leagues_tab)
    filter_frame.pack(fill="x", padx=5, pady=5)
    
    ttk.Label(filter_frame, text="Country:").pack(side="left", padx=5)
    
    from pm99_editor.league_definitions import get_all_countries
    countries = ["All"] + get_all_countries()
    
    self.country_var = tk.StringVar(value="England")
    self.country_combo = ttk.Combobox(
        filter_frame, 
        textvariable=self.country_var,
        values=countries,
        state="readonly",
        width=15
    )
    self.country_combo.pack(side="left", padx=5)
    self.country_combo.bind("<<ComboboxSelected>>", 
                           lambda e: self.populate_leagues_tab())
    
    # Search box
    ttk.Label(filter_frame, text="Search:").pack(side="left", padx=(20,5))
    self.league_search_var = tk.StringVar()
    self.league_search_entry = ttk.Entry(
        filter_frame,
        textvariable=self.league_search_var,
        width=20
    )
    self.league_search_entry.pack(side="left", padx=5)
    self.league_search_var.trace("w", lambda *args: self.populate_leagues_tab())
    
    # TreeView with hierarchical display
    tree_frame = ttk.Frame(self.leagues_tab)
    tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
    
    # Columns: Team ID, Stadium, Capacity
    columns = ("team_id", "stadium", "capacity")
    self.leagues_tree = ttk.Treeview(
        tree_frame,
        columns=columns,
        show="tree headings"
    )
    
    # Configure columns
    self.leagues_tree.heading("#0", text="League / Team Name")
    self.leagues_tree.heading("team_id", text="Team ID")
    self.leagues_tree.heading("stadium", text="Stadium")
    self.leagues_tree.heading("capacity", text="Capacity")
    
    self.leagues_tree.column("#0", width=300, minwidth=200)
    self.leagues_tree.column("team_id", width=80, minwidth=60)
    self.leagues_tree.column("stadium", width=250, minwidth=150)
    self.leagues_tree.column("capacity", width=100, minwidth=80)
    
    # Scrollbars
    vsb = ttk.Scrollbar(tree_frame, orient="vertical", 
                       command=self.leagues_tree.yview)
    hsb = ttk.Scrollbar(tree_frame, orient="horizontal",
                       command=self.leagues_tree.xview)
    self.leagues_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    
    # Grid layout
    self.leagues_tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    
    tree_frame.rowconfigure(0, weight=1)
    tree_frame.columnconfigure(0, weight=1)
    
    # Double-click to edit team
    self.leagues_tree.bind("<Double-1>", self.on_league_team_doubleclick)
    
    # Context menu
    self.leagues_tree.bind("<Button-3>", self.show_league_context_menu)

def populate_leagues_tab(self):
    """Populate leagues tree with teams grouped by league."""
    if not hasattr(self, 'leagues_tree'):
        return
    
    # Clear existing
    for item in self.leagues_tree.get_children():
        self.leagues_tree.delete(item)
    
    # Get filter values
    country_filter = self.country_var.get()
    search_text = self.league_search_var.get().lower()
    
    # Import league utilities
    from pm99_editor.league_definitions import get_team_league, get_all_countries
    
    # Group teams by (country, league)
    leagues_dict = {}
    for offset, team in self.teams:
        # Apply search filter
        if search_text and search_text not in team.name.lower():
            continue
        
        country, league_name = get_team_league(team.team_id)
        
        # Apply country filter
        if country_filter != "All" and country != country_filter:
            continue
        
        # Skip unknown leagues
        if not country or not league_name:
            continue
        
        key = (country, league_name)
        if key not in leagues_dict:
            leagues_dict[key] = []
        leagues_dict[key].append((offset, team))
    
    # Sort and add to tree
    for (country, league_name), teams in sorted(leagues_dict.items()):
        # Create league parent node
        league_text = f"{country} - {league_name}"
        team_count = len(teams)
        
        league_id = self.leagues_tree.insert(
            "", "end",
            text=league_text,
            values=("", "", f"({team_count} teams)"),
            tags=("league",)
        )
        
        # Configure league node styling
        self.leagues_tree.tag_configure("league", font=("TkDefaultFont", 10, "bold"))
        
        # Add teams as children (sorted alphabetically)
        for offset, team in sorted(teams, key=lambda x: x[1].name):
            self.leagues_tree.insert(
                league_id, "end",
                text=team.name,
                values=(
                    team.team_id,
                    team.stadium or "",
                    f"{team.stadium_capacity:,}" if team.stadium_capacity else ""
                ),
                tags=("team",)
            )

def on_league_team_doubleclick(self, event):
    """Handle double-click on team in leagues tree."""
    selection = self.leagues_tree.selection()
    if not selection:
        return
    
    item = selection[0]
    
    # Check if it's a team (not a league parent)
    if "team" not in self.leagues_tree.item(item, "tags"):
        # It's a league - expand/collapse it
        self.leagues_tree.item(item, open=not self.leagues_tree.item(item, "open"))
        return
    
    # Get team ID and find the team
    team_id = self.leagues_tree.item(item, "values")[0]
    if not team_id:
        return
    
    team_id = int(team_id)
    
    # Find team record
    for offset, team in self.teams:
        if team.team_id == team_id:
            self.edit_team(team)
            break
```

## Implementation Checklist

- [x] Create league_definitions.py with confirmed structure
- [x] Update TeamRecord model with league methods
- [x] Fix team loader to use correct file sections
- [ ] **Fix TeamRecord._extract_name() - CRITICAL BLOCKER**
- [ ] Add Leagues tab UI to gui.py
- [ ] Implement populate_leagues_tab()
- [ ] Add team editing from Leagues tab
- [ ] Test with real data (verify all 80 English teams)
- [ ] Add context menu (right-click options)
- [ ] Add statistics panel (optional)

## Testing Plan

1. **Load Test**: Confirm all teams load with correct names
2. **League Assignment**: Verify teams in correct leagues
3. **UI Test**: Check hierarchical display works
4. **Filter Test**: Test country and search filters
5. **Edit Test**: Ensure team editing works from Leagues tab
6. **Save Test**: Verify changes persist correctly

## Notes

- League names are hardcoded (not in data files)
- Team assignment based on team_id ranges
- England is the only country with 4 divisions
- Other countries have single top-flight leagues
- UI should match game's visual style (see screenshots)
