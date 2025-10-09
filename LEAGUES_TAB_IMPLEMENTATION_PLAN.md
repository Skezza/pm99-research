# Leagues Tab Implementation Plan

## Overview
Add a Leagues tab to the PM99 Editor GUI that displays teams organized by their leagues. For England (the main focus of this English game), there are 4 leagues (divisions). For other nations, there's typically one national league per country.

## Current State Analysis

### Team Loading (FIXED)
The team loader now correctly:
1. Reads teams from known XOR-encoded sections at offsets:
   - `0x201`: Section 1 (~11KB)
   - `0x2f04`: Section 2 (~42KB, main team data)
2. Decodes each section using XOR 0x61
3. Finds team records using separator pattern `0x61 0xdd 0x63`
4. Parses TeamRecord objects from the data between separators

### Team Structure
From [`TeamRecord`](pm99_editor/models.py:16-404):
- `team_id`: Integer ID extracted from record (3000-5000 range)
- `name`: Team name extracted via heuristics
- `stadium`: Stadium name (extracted)
- `stadium_capacity`, `car_park`, `pitch`: Stadium details
- `league`: Computed from team_id ranges

### League Determination
Currently implemented in [`TeamRecord._extract_league()`](pm99_editor/models.py:226-252):
```python
def _extract_league(self):
    """Extract league based on team_id ranges."""
    tid = self.team_id
    if 3712 <= tid <= 3731:
        return "Premier League"
    elif 3732 <= tid <= 3751:
        return "First Division"
    elif 3752 <= tid <= 3771:
        return "Second Division"
    elif 3772 <= tid <= 3791:
        return "Third Division"
    else:
        return "National League"
```

## Implementation Steps

### Step 1: Validate Team ID Ranges
**Goal**: Use Ghidra MCP to verify that team IDs actually follow the assumed ranges

**Actions**:
1. List team names from Ghidra's analyzed binary
2. Search for known English teams (e.g., "Manchester United", "Arsenal")
3. Examine the team ID field in team records
4. Validate that Premier League teams = 3712-3731, etc.

**Expected Outcome**: Confirm or adjust team_id ranges for each league

### Step 2: Update GUI with Leagues Tab
**File**: [`pm99_editor/gui.py`](pm99_editor/gui.py)

**Changes**:
1. Add new notebook tab after Teams tab:
```python
self.leagues_tab = ttk.Frame(self.notebook)
self.notebook.add(self.leagues_tab, text="Leagues")
```

2. Create TreeView with two-level hierarchy:
   - Level 1: League names (Premier League, First Division, etc.)
   - Level 2: Teams within each league

3. TreeView columns:
   - Team Name
   - Team ID
   - Stadium
   - Capacity

4. Add filtering controls:
   - Dropdown to select nation (England, Spain, Italy, etc.)
   - For England: Show all 4 divisions
   - For others: Show single national league

### Step 3: Populate Leagues TreeView
**Implementation**:
```python
def populate_leagues_tab(self):
    """Populate the leagues tab with teams organized by league."""
    # Clear existing
    for item in self.leagues_tree.get_children():
        self.leagues_tree.delete(item)
    
    # Group teams by league
    leagues = {}
    for offset, team in self.teams:
        league = team.league
        if league not in leagues:
            leagues[league] = []
        leagues[league].append((offset, team))
    
    # Add to tree (sorted by league name)
    for league_name in sorted(leagues.keys()):
        # Add league as parent node
        league_id = self.leagues_tree.insert(
            "", "end", 
            text=league_name,
            values=(f"{len(leagues[league_name])} teams", "", "", "")
        )
        
        # Add teams as children (sorted by name)
        teams = sorted(leagues[league_name], key=lambda x: x[1].name)
        for offset, team in teams:
            self.leagues_tree.insert(
                league_id, "end",
                text=team.name,
                values=(team.team_id, team.stadium, team.stadium_capacity or "")
            )
```

### Step 4: Add Team Editing from Leagues Tab
**Features**:
1. Double-click on team in Leagues tab opens team editor
2. Team editor allows:
   - Edit team name
   - Edit stadium name
   - Edit stadium capacity, car park spaces, pitch quality
   - Move team to different league (change team_id)

**Implementation**:
```python
def on_league_team_double_click(self, event):
    """Handle double-click on team in leagues tab."""
    selection = self.leagues_tree.selection()
    if not selection:
        return
    
    item = selection[0]
    # Check if it's a team (not a league parent)
    parent = self.leagues_tree.parent(item)
    if not parent:
        return  # Clicked on league, not team
    
    # Get team details
    team_name = self.leagues_tree.item(item)["text"]
    team_id = self.leagues_tree.item(item)["values"][0]
    
    # Find team in self.teams
    team_record = None
    for offset, team in self.teams:
        if team.team_id == team_id:
            team_record = team
            break
    
    if team_record:
        self.edit_team(team_record)
```

### Step 5: Add League Statistics Panel
**Optional Enhancement**:
Display league-wide statistics:
- Total teams in league
- Average stadium capacity
- Total capacity across all stadiums
- Teams with/without car parks

### Step 6: Testing Plan
1. **Load Test**: Verify all teams load correctly
2. **League Assignment**: Check each team is in correct league
3. **Hierarchy Test**: Verify TreeView displays leagues -> teams correctly
4. **Edit Test**: Ensure team editing works from Leagues tab
5. **Data Integrity**: Verify edited teams save correctly

## File Changes Required

### 1. [`pm99_editor/loaders.py`](pm99_editor/loaders.py) ✅ COMPLETE
- Fixed team loading to use proper section parsing
- Teams now load from XOR-decoded sections with separator pattern

### 2. [`pm99_editor/models.py`](pm99_editor/models.py) 
**Potential Updates**:
- Verify/adjust league ranges after Ghidra validation
- Add method to change team's league (updates team_id to new range)
```python
def set_league(self, new_league: str):
    """Move team to different league by updating team_id."""
    league_ranges = {
        "Premier League": (3712, 3731),
        "First Division": (3732, 3751),
        "Second Division": (3752, 3771),
        "Third Division": (3772, 3791)
    }
    # Find next available ID in new league range
    # Update self.team_id
```

### 3. [`pm99_editor/gui.py`](pm99_editor/gui.py)
**Major Changes**:
- Add Leagues tab widget creation
- Add leagues TreeView setup
- Add populate_leagues_tab() method
- Add league team editor integration
- Add league filtering controls

### 4. New file: `pm99_editor/league_editor.py` (Optional)
**Purpose**: Separate league-specific UI logic
- League statistics calculation
- League filtering
- Inter-league team transfers

## Technical Considerations

### Team ID Management
- Team IDs must stay within valid ranges
- Moving team between leagues requires ID reassignment
- Must check for ID conflicts

### Data Validation
- Ensure team_id ranges are correct via Ghidra
- Validate that all English teams fall within 3712-3791
- Handle edge cases (free agents, reserve teams)

### Performance
- Leagues tab should load instantly (data already in memory)
- Filtering by nation should be fast (<100ms)

### UI/UX
- Expandable league nodes in TreeView
- Visual indication of current league selection
- Context menu for team operations (edit, move league, etc.)

## Next Steps
1. ✅ Fix team loader (DONE)
2. Use Ghidra MCP to validate team ID ranges
3. Implement Leagues tab UI in gui.py
4. Add team editing integration
5. Test with real data
6. Document usage in user guide

## Validation Strategy Using Ghidra MCP

### 1. Search for Known Teams
```python
# Use ghidra.list_strings to find team names
# Filter for known Premier League teams:
# - Manchester United
# - Arsenal
# - Liverpool
# - Chelsea
```

### 2. Examine Team Records
```python
# Use ghidra.get_xrefs_to to find where team names are referenced
# Look at the data structures containing team names
# Identify team_id field positions
```

### 3. Verify ID Ranges
```python
# Check if team IDs follow expected pattern:
# - First 20 teams (3712-3731): Premier League?
# - Next 20 teams (3732-3751): First Division?
# - etc.
```

## Success Criteria
- ✅ Teams load correctly from file
- ✅ Teams organized into correct leagues
- ✅ Leagues tab displays hierarchical view
- ✅ Teams can be edited from Leagues tab
- ✅ Changes persist when saved
- ✅ League assignments validated via Ghidra
