# Premier Manager 99 - Full Editor Enhancement Plan

## Current State Assessment

### ✅ What We Have
- **Player Attributes**: Can edit 10 stats per player (0-100 range)
- **Player Names**: Can rename (same-length names only)
- **File Format**: Fully understood (XOR-0x61, separator patterns)
- **8,866 Players**: All loaded and accessible
- **GUI**: Working Tkinter interface

### ⚠️ Limitations
- **Name editing**: Same-length only (need variable-length support)
- **No team data**: Can't view/edit teams or rosters
- **No player-team links**: Can't see which team a player belongs to
- **No transfers**: Can't move players between teams
- **Limited attributes**: Only 10 basic stats (need nationality, position, age, etc.)

---

## Football Manager-Style Features Required

### Phase 1: Enhanced Player Editor (2-3 days)

#### 1.1 Variable-Length Name Editing
**Current**: Names must be same length  
**Need**: Allow any length names with automatic padding/restructuring

**Technical Challenges**:
- Record lengths are fixed in current structure
- Need to handle record resizing or padding
- May need to shift following records

**Implementation**:
```python
def modify_player_name_variable(record, new_given, new_surname):
    # If shorter: pad with 0x60 (existing pattern)
    # If longer: Need to expand record (complex)
    # Or: Use abbreviations to fit in same space
```

**Time**: 4-6 hours  
**Priority**: HIGH

#### 1.2 Additional Player Fields
**Need to add**:
- Nationality (1 byte) - Already in schema
- Position (1 byte) - Already in schema  
- Age/Birth date (3-4 bytes) - Already in schema
- Height/Weight (2 bytes) - Already in schema
- Shirt number (1 byte)
- Contract details
- Morale/form indicators

**Technical Challenges**:
- Need to map exact byte positions (we have schema from Ghidra)
- Validate each field's location in real data
- Some fields may be in different record sections

**Implementation**: Use existing schema from [`out/schema_players.md`](out/schema_players.md)

**Time**: 6-8 hours  
**Priority**: HIGH

---

### Phase 2: Team Database Integration (3-4 days)

#### 2.1 Team File Analysis
**File**: `DBDAT/EQ98030.FDI` (1.1MB, teams data)

**Need to discover**:
- Team record structure
- Team name location
- Team metadata (division, stadium, budget, etc.)
- Link between teams and players

**Steps**:
1. Apply same XOR-0x61 decoding
2. Find separator patterns
3. Locate team names
4. Map team record structure
5. Find player roster section

**Time**: 8-12 hours  
**Priority**: CRITICAL

#### 2.2 Player-Team Relationship
**Current knowledge**:
- Players have 2-byte team pointer (offset +0 in record)
- Need to verify this links to team IDs

**Implementation**:
```python
class Player:
    team_id: int  # 2-byte reference
    
class Team:
    team_id: int
    name: str
    players: List[Player]  # Derived from team_id matching
```

**Time**: 4-6 hours  
**Priority**: CRITICAL

#### 2.3 Team Editor UI
**Features needed**:
- List all teams
- View team details (name, division, budget, stadium)
- Edit team attributes
- View team roster (list of players)

**Time**: 6-8 hours  
**Priority**: HIGH

---

### Phase 3: Squad/Roster Management (2-3 days)

#### 3.1 Team Roster View
**UI Features**:
- Show all players in selected team
- Display player names, positions, ratings
- Sort by position, rating, name
- Filter by various criteria

**Implementation**:
```python
def get_team_players(team_id):
    return [p for p in all_players if p.team_id == team_id]
```

**Time**: 4-6 hours  
**Priority**: HIGH

#### 3.2 Player Transfer System
**Features**:
- Move player from one team to another
- Update player's team_id field
- Validate squad size limits
- Handle free agents

**Technical Challenge**:
- Need to update team_id byte in player record
- May need to update team roster in team file
- Ensure referential integrity

**Time**: 6-8 hours  
**Priority**: MEDIUM

#### 3.3 Squad Building Tools
**Advanced features**:
- Drag & drop players between teams
- Position-based filtering
- Rating-based sorting
- Budget constraints (if available)

**Time**: 8-10 hours  
**Priority**: LOW

---

### Phase 4: Advanced Features (3-5 days)

#### 4.1 Search & Filter Enhancements
**Current**: Basic name search  
**Need**:
- Filter by team
- Filter by position
- Filter by nationality
- Filter by rating range
- Multi-criteria filters

**Time**: 4-6 hours  
**Priority**: MEDIUM

#### 4.2 Batch Operations
**Features**:
- Bulk attribute editing (e.g., boost entire team)
- Mass transfers
- Global stat adjustments
- Import/Export rosters

**Time**: 6-8 hours  
**Priority**: MEDIUM

#### 4.3 Data Validation & Integrity
**Features**:
- Validate all edits before save
- Check for duplicate players
- Ensure team rosters are complete
- Validate stat ranges
- Checksum verification (if needed)

**Time**: 4-6 hours  
**Priority**: HIGH

---

## Detailed Implementation Roadmap

### Week 1: Enhanced Player Editor

**Day 1-2: Variable-Length Names**
- [ ] Implement padding system for shorter names
- [ ] Test with various name lengths
- [ ] Add UI for name editing
- [ ] Verify in-game

**Day 3-4: Additional Player Fields**
- [ ] Map nationality byte location
- [ ] Map position byte location  
- [ ] Map age/birth date bytes
- [ ] Map height/weight bytes
- [ ] Add UI controls for all fields
- [ ] Test modifications

**Day 5: Enhanced Player UI**
- [ ] Redesign player details panel
- [ ] Add all new fields to display
- [ ] Improve layout and usability
- [ ] Add field validation

### Week 2: Team Database

**Day 1-3: Team File Reverse Engineering**
- [ ] Analyze EQ98030.FDI structure
- [ ] Decode team records
- [ ] Extract team names
- [ ] Map team attributes
- [ ] Find player roster section
- [ ] Document structure

**Day 4-5: Team Editor Implementation**
- [ ] Create Team data model
- [ ] Build team parser
- [ ] Link teams to players
- [ ] Create team list UI
- [ ] Create team details UI
- [ ] Test team editing

### Week 3: Squad Management

**Day 1-2: Roster Views**
- [ ] Implement team roster display
- [ ] Add position-based grouping
- [ ] Add sorting options
- [ ] Add filtering

**Day 3-4: Transfer System**
- [ ] Implement player transfer logic
- [ ] Update team_id in player records
- [ ] Add drag & drop UI
- [ ] Test transfers
- [ ] Verify in-game

**Day 5: Polish & Testing**
- [ ] Bug fixes
- [ ] UI improvements
- [ ] Performance optimization
- [ ] Documentation

### Week 4: Advanced Features & Polish

**Day 1-2: Search & Filter**
- [ ] Multi-criteria filtering
- [ ] Advanced search options
- [ ] Saved searches

**Day 3: Batch Operations**
- [ ] Bulk editing
- [ ] Import/Export
- [ ] Templates

**Day 4-5: Final Polish**
- [ ] Full testing suite
- [ ] Bug fixes
- [ ] Documentation
- [ ] User guide
- [ ] Video tutorial

---

## Technical Architecture

### Enhanced Data Model

```python
class Player:
    # Identity
    given_name: str
    surname: str
    team_id: int
    
    # Physical
    age: int
    birth_date: tuple  # (day, month, year)
    height: int  # cm
    weight: int  # kg
    nationality: int  # country code
    
    # Position
    position_primary: int
    position_secondary: int
    
    # Attributes (10)
    passing: int
    shooting: int
    tackling: int
    speed: int
    stamina: int
    heading: int
    dribbling: int
    aggression: int
    positioning: int
    form: int
    
    # Contract
    contract_end: int
    wage: int
    value: int
    
    # File location
    section_offset: int
    record_start: int
    record_end: int

class Team:
    team_id: int
    name: str
    short_name: str
    division: int
    budget: int
    stadium: str
    capacity: int
    
    # Roster
    players: List[Player]  # Computed from player.team_id
    
    # File location
    section_offset: int
    record_start: int

class Database:
    players: List[Player]  # 8,866
    teams: List[Team]      # ~544 teams
    coaches: List[Coach]   # 4 coaches
    
    def get_team_roster(self, team_id) -> List[Player]
    def transfer_player(self, player, from_team, to_team)
    def save_all(self)
```

### Enhanced UI Structure

```
PM99 Professional Editor
├── Menu Bar
│   ├── File (Open, Save, Import, Export, Exit)
│   ├── Edit (Undo, Redo, Preferences)
│   ├── View (Players, Teams, Coaches, Tactics)
│   └── Tools (Batch Edit, Validate, Backup)
│
├── Main Window (Tabbed)
│   │
│   ├── [Players Tab]
│   │   ├── Search Panel
│   │   │   ├── Name search
│   │   │   ├── Team filter
│   │   │   ├── Position filter
│   │   │   ├── Nationality filter
│   │   │   └── Rating range
│   │   │
│   │   ├── Player List (sortable table)
│   │   │   └── Columns: Name, Team, Pos, Age, Rating
│   │   │
│   │   └── Player Editor Panel
│   │       ├── Name fields (editable)
│   │       ├── Physical attrs
│   │       ├── Position
│   │       ├── 10 skill sliders
│   │       └── Buttons (Save, Reset, Delete)
│   │
│   ├── [Teams Tab]
│   │   ├── Team List
│   │   │   └── Shows: Name, Division, Budget
│   │   │
│   │   ├── Team Details
│   │   │   ├── Name, Stadium, Division
│   │   │   ├── Budget, Value
│   │   │   └── Edit buttons
│   │   │
│   │   └── Team Roster
│   │       ├── Player list (with positions)
│   │       ├── Formation view (optional)
│   │       └── Add/Remove buttons
│   │
│   ├── [Transfers Tab]
│   │   ├── Available Players (free agents)
│   │   ├── Source Team roster
│   │   ├── Transfer controls
│   │   └── Destination Team roster
│   │
│   └── [Coaches Tab]
│       └── Coach editor (already working)
│
└── Status Bar
    ├── File loaded indicator
    ├── Modified indicator
    └── Player/Team counts
```

---

## Priority Order

### Must Have (Phase 1-2)
1. ✅ Variable-length name editing
2. ✅ Additional player fields (nationality, position, age)
3. ✅ Team file parsing
4. ✅ Team list view
5. ✅ Player-team linking
6. ✅ Basic roster view

### Should Have (Phase 3)
7. Transfer system
8. Enhanced search/filter
9. Team editing
10. Batch operations

### Nice to Have (Phase 4)
11. Formation editor
12. Tactics editor
13. Match data editor
14. Save game editor
15. Statistics viewer

---

## Estimated Time

**Minimum Viable Product**: 2 weeks (Phases 1-2)
- Enhanced player editor with all fields
- Team viewer
- Basic roster management

**Full Featured Editor**: 4 weeks (Phases 1-4)
- Everything above
- Transfer system
- Advanced features
- Full polish

**Football Manager-Level**: 6-8 weeks
- All features
- Tactics editor
- Match engine integration
- Advanced analytics

---

## Immediate Next Steps (This Week)

### Day 1: Variable-Length Names (TODAY)
1. Implement padding system
2. Test with various lengths
3. Update UI for name editing

### Day 2: Additional Player Fields
1. Map nationality, position, age from schema
2. Verify byte locations in real data
3. Add to data model

### Day 3: Enhanced Player UI
1. Add input fields for all new attributes
2. Update display
3. Test modifications

### Day 4-5: Team File Analysis
1. Start analyzing EQ98030.FDI
2. Find team names
3. Map team structure

---

## Technical Challenges & Solutions

### Challenge 1: Variable-Length Names
**Problem**: Records are fixed size, names are variable  
**Solutions**:
- Option A: Pad with 0x60 (simple, works for shorter names)
- Option B: Restructure records (complex, allows any length)
- Option C: Use abbreviations/truncation (practical)

**Recommendation**: Start with Option A (padding), add Option B later if needed

### Challenge 2: Team-Player Linking
**Problem**: Need to verify team_id field location  
**Solution**: 
1. Examine first few bytes of player records
2. Cross-reference with team IDs in team file
3. Validate linking works

### Challenge 3: Performance with Large Datasets
**Problem**: 8,866 players + 544 teams = slow UI  
**Solutions**:
- Lazy loading
- Virtual scrolling
- Caching
- Background threads

---

## Success Criteria

### Phase 1 Complete When:
- [ ] Can edit player names (any length)
- [ ] Can edit nationality, position, age
- [ ] Can edit height, weight
- [ ] All changes persist correctly
- [ ] Changes verified in-game

### Phase 2 Complete When:
- [ ] Can view all teams
- [ ] Can see team rosters
- [ ] Can identify which team each player belongs to
- [ ] Can edit team names/details

### Phase 3 Complete When:
- [ ] Can transfer players between teams
- [ ] Can view complete squad for any team
- [ ] Can filter players by team

### Full Project Complete When:
- [ ] All Football Manager-style features implemented
- [ ] Full documentation provided
- [ ] Tested extensively
- [ ] User guide written
- [ ] No known critical bugs

---

## Risk Assessment

### High Risk
- **Team file structure unknown**: May take longer than estimated
- **Player-team linking complex**: May need multiple iterations
- **Variable-length names**: Could break file structure

### Medium Risk
- **Performance with large datasets**: May need optimization
- **UI complexity**: Could take longer to polish
- **Testing coverage**: Hard to test all edge cases

### Low Risk
- **XOR encoding**: Already mastered
- **Basic CRUD operations**: Already working
- **File backups**: Already implemented

---

## Conclusion

This is a **4-6 week project** for a full Football Manager-style editor.

**Recommendation**: Start with Phases 1-2 (2 weeks) to get:
- Full player editing (all fields)
- Team viewing
- Basic roster management

Then evaluate if Phases 3-4 are needed based on user requirements.

**Ready to proceed?** We can start with Day 1: Variable-Length Names today!