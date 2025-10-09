# Leagues Tab Implementation - Final Plan

## Key Findings

### Data File Analysis
1. **EQ98030.FDI** contains team data in 2 XOR-encoded sections:
   - Section 1 @ 0x201: ~11KB (3 teams)
   - Section 2 @ 0x2f04: ~42KB (21 teams)
   - Only ~24 teams extracted (far fewer than expected)

2. **League names NOT found in data files**:
   - TEXTOS.PKF: No league keywords
   - ENT98030.FDI: No league keywords
   - PKF files: No league structure
   
3. **League structure likely hardcoded** in game executable or derived from:
   - Team ID ranges
   - Team metadata fields
   - Implicit ordering in file

### Current Issues
1. Team name extraction is poor (getting garbage like "Caaa", "BaaanEaaa")
2. Only 24 teams loading (expected hundreds)
3. Team ID extraction unreliable
4. No explicit league field in team records

## Pragmatic Implementation Approach

### Phase 1: Fix Team Loading (PRIORITY)
Before implementing Leagues tab, must fix fundamental team loading issues.

**Issue**: [`TeamRecord._extract_name()`](pm99_editor/models.py:77-141) is not compatible with team file structure

**Solution**: Analyze actual team record structure and rewrite name extraction
```python
def _extract_name(self):
    """Extract team name from record data."""
    # Team records appear to have text after separator + prefix
    # Pattern: 61 dd 63 [prefix bytes] [TEAM NAME]
    
    # Skip separator (3 bytes)
    start = 3
    
    # Skip any prefix bytes (usually a`qa or similar)
    # Look for first uppercase letter
    for i in range(start, min(100, len(self.raw_data))):
        if self.raw_data[i] >= ord('A') and self.raw_data[i] <= ord('Z'):
            start = i
            break
    
    # Extract until 'a' character or stadium text
    # Team names typically end before stadium name starts
    end = start
    for i in range(start, min(start + 50, len(self.raw_data))):
        c = self.raw_data[i]
        # Stop at lowercase 'a' that seems to be a separator
        if c == ord('a') and i > start + 5:
            # Check if followed by more text (stadium)
            if i + 1 < len(self.raw_data) and self.raw_data[i+1] >= ord('A'):
                end = i
                break
        # Stop at non-printable
        if c < 32 or c > 126:
            end = i
            break
    
    if end > start:
        name_bytes = self.raw_data[start:end]
        return name_bytes.decode('latin1', errors='replace').strip(), start, end
    
    return "Unknown Team", 0, 0
```

### Phase 2: Define League Structure
Since league names aren't in data files, **hardcode known league structure**:

```python
# Hardcoded league definitions
LEAGUES = {
    "England": [
        {"name": "Premier League", "id_range": (3712, 3731)},
        {"name": "First Division", "id_range": (3732, 3751)},
        {"name": "Second Division", "id_range": (3752, 3771)},
        {"name": "Third Division", "id_range": (3772, 3791)},
    ],
    "Spain": [
        {"name": "La Liga", "id_range": (3792, 3811)},
    ],
    "Italy": [
        {"name": "Serie A", "id_range": (3812, 3831)},
    ],
    # ... more countries
}

def get_team_league(team_id: int) -> Tuple[str, str]:
    """Return (country, league_name) for a team ID."""
    for country, leagues in LEAGUES.items():
        for league in leagues:
            if league["id_range"][0] <= team_id <= league["id_range"][1]:
                return country, league["name"]
    return "Unknown", "Unknown League"
```

### Phase 3: Implement Leagues Tab UI
Once teams load correctly, add UI in [`pm99_editor/gui.py`](pm99_editor/gui.py):

```python
def create_leagues_tab(self):
    """Create the Leagues tab with hierarchical team view."""
    self.leagues_tab = ttk.Frame(self.notebook)
    self.notebook.add(self.leagues_tab, text="Leagues")
    
    # Country filter
    filter_frame = ttk.Frame(self.leagues_tab)
    filter_frame.pack(fill="x", padx=5, pady=5)
    
    ttk.Label(filter_frame, text="Country:").pack(side="left")
    self.country_filter = ttk.Combobox(filter_frame, 
                                       values=["All", "England", "Spain", "Italy", "Germany", "France"])
    self.country_filter.set("England")
    self.country_filter.pack(side="left", padx=5)
    self.country_filter.bind("<<ComboboxSelected>>", lambda e: self.populate_leagues_tab())
    
    # TreeView
    tree_frame = ttk.Frame(self.leagues_tab)
    tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
    
    columns = ("team_id", "stadium", "capacity")
    self.leagues_tree = ttk.Treeview(tree_frame, columns=columns, show="tree headings")
    
    self.leagues_tree.heading("#0", text="League / Team")
    self.leagues_tree.heading("team_id", text="Team ID")
    self.leagues_tree.heading("stadium", text="Stadium")
    self.leagues_tree.heading("capacity", text="Capacity")
    
    self.leagues_tree.column("#0", width=300)
    self.leagues_tree.column("team_id", width=80)
    self.leagues_tree.column("stadium", width=200)
    self.leagues_tree.column("capacity", width=100)
    
    # Scrollbars
    vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.leagues_tree.yview)
    hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.leagues_tree.xview)
    self.leagues_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    
    self.leagues_tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    
    tree_frame.rowconfigure(0, weight=1)
    tree_frame.columnconfigure(0, weight=1)
    
    # Double-click to edit
    self.leagues_tree.bind("<Double-1>", self.on_league_team_doubleclick)

def populate_leagues_tab(self):
    """Populate leagues tree with teams grouped by league."""
    # Clear existing
    for item in self.leagues_tree.get_children():
        self.leagues_tree.delete(item)
    
    # Get selected country filter
    country_filter = self.country_filter.get()
    
    # Group teams by (country, league)
    leagues_dict = {}
    for offset, team in self.teams:
        country, league_name = get_team_league(team.team_id)
        
        # Apply country filter
        if country_filter != "All" and country != country_filter:
            continue
        
        key = (country, league_name)
        if key not in leagues_dict:
            leagues_dict[key] = []
        leagues_dict[key].append((offset, team))
    
    # Add to tree
    for (country, league_name), teams in sorted(leagues_dict.items()):
        # Add league node
        league_id = self.leagues_tree.insert(
            "", "end",
            text=f"{country} - {league_name}",
            values=("", "", f"{len(teams)} teams")
        )
        
        # Add team children
        for offset, team in sorted(teams, key=lambda x: x[1].name):
            self.leagues_tree.insert(
                league_id, "end",
                text=team.name,
                values=(team.team_id, team.stadium or "", team.stadium_capacity or ""),
                tags=("team",)
            )
```

## Alternative Approach: League Detection

If team_id ranges are unreliable, **detect leagues from team names**:

```python
def detect_league_from_name(team_name: str) -> Tuple[str, str]:
    """Detect country and league from team name patterns."""
    
    # English teams
    english_indicators = ["United", "City", "Town", "FC", "Athletic", "Rovers", 
                         "Wanderers", "County", "Forest", "Palace", "Villa"]
    if any(ind in team_name for ind in english_indicators):
        # Further classify into divisions based on known teams
        premier = ["Manchester United", "Arsenal", "Liverpool", "Chelsea"]
        if any(t in team_name for t in premier):
            return "England", "Premier League"
        return "England", "Division Unknown"
    
    # Spanish teams
    if any(ind in team_name for ind in ["Real", "Barcelona", "Valencia", "Athletic Club", "Sevilla"]):
        return "Spain", "La Liga"
    
    # Italian teams
    if any(ind in team_name for ind in ["Milan", "Juventus", "Inter", "Roma", "Lazio", "Napoli"]):
        return "Italy", "Serie A"
    
    return "Unknown", "Unknown"
```

## Immediate Next Steps

1. **Fix team name extraction** - Priority #1
   - Debug actual team record structure
   - Rewrite `_extract_name()` to work with real data
   - Test with known teams (Real Madrid, Milan, etc.)

2. **Validate team loading** - Get all teams loading
   - Confirm why only 24 teams
   - Check if more sections exist
   - Ensure all separators found

3. **Define league structure** - Hardcode if necessary
   - Map known English teams to divisions
   - Map other countries' teams
   - Create lookup tables

4. **Implement UI** - Once data is clean
   - Add Leagues tab
   - Hierarchical view
   - Team editing

## Success Criteria

- ✅ All teams load with correct names
- ✅ Teams organized into logical leagues
- ✅ Leagues tab displays hierarchical view
- ✅ Can edit teams from Leagues tab
- ✅ Changes save correctly

## Files to Modify

1. [`pm99_editor/models.py`](pm99_editor/models.py) - Fix TeamRecord._extract_name()
2. [`pm99_editor/loaders.py`](pm99_editor/loaders.py) - Verify all teams loading
3. [`pm99_editor/gui.py`](pm99_editor/gui.py) - Add Leagues tab UI
4. New file: `pm99_editor/league_definitions.py` - Hardcoded league structure
