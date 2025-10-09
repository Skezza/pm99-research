# Building a Full Player Editor - Requirements & Roadmap

## Current Status vs Full Editor

### ✅ What We Have Now
**Current Capability**: Name-only editor
- Can find player names in decoded sections
- Can rename players (same-length names)
- Changes persist correctly

**Limitation**: Only edits plaintext names, cannot modify:
- Player abilities/skills (10 attributes)
- Physical characteristics (height, weight)
- Birth date, nationality, position
- Any other player metadata

### 🎯 What's Needed for Full Editor

To edit player **characteristics and abilities**, we need to:

1. **Understand Individual Player Records**
   - Current: We find names in large sections (49KB with 679 names)
   - Needed: Parse each individual player's complete record
   
2. **Map Field Byte Offsets**
   - Current: We know the schema from Ghidra (see [`out/schema_players.md`](out/schema_players.md))
   - Needed: Find where these fields actually are in the file
   
3. **Handle Variable-Length Records**
   - Challenge: Names are variable length, so field offsets shift per player
   - Solution: Parse sequentially through each record

---

## Technical Requirements

### 1. Record Boundary Detection

**Problem**: Large sections contain many players, but we don't know where each player's record starts/ends.

**Current State**:
```
Section @ 0x378383 (49KB):
  Contains 679 player names as plaintext
  But we don't know individual record boundaries
```

**What We Need**:
```
Section @ 0x378383 (49KB):
  Player 1: bytes 0-72    (name + stats)
  Player 2: bytes 73-145  (name + stats)
  Player 3: bytes 146-218 (name + stats)
  ...
```

**Approaches**:

A. **Pattern Analysis** (2-3 hours)
   - Analyze bytes between player names
   - Find consistent separator/header patterns
   - Identify record start markers

B. **Size Estimation** (1-2 hours)
   - Average spacing: 63-144 bytes between names
   - Estimate record size: ~70-80 bytes typical
   - Test with known players

C. **Runtime Debugging** (3-4 hours) - Most Reliable
   - Debug MANAGPRE.EXE while loading players
   - Watch exact byte positions read
   - Map file offsets to memory structure
   - Document precise record format

### 2. Field Parsing Implementation

**Based on Schema** ([`out/schema_players.md`](out/schema_players.md)):

```python
class PlayerRecord:
    # After XOR decode of record:
    
    # Names (variable length, nested XOR)
    given_name: str      # Offset: +0 (length-prefixed XOR string)
    surname: str         # Offset: +var (follows given_name)
    
    # Metadata (fixed positions relative to start)
    nationality: int     # Offset: +8 after surnames
    position_primary: int    # Offset: +9
    position_secondary: int  # Offset: +10
    
    # Birth data (fixed offsets in decoded record)
    birth_day: int       # Offset: 0x48 (72)
    birth_month: int     # Offset: 0x121 (289)
    birth_year: int      # Offset: 0x11e (286)
    
    # Physical attributes
    height: int          # Offset: 0x115 (277)
    weight: int          # Offset: 0x116 (278)
    
    # Skills (10 attributes, each at 2 offsets)
    skill_1: int         # Offsets: 0xdd (221), 0xcf (207)
    skill_2: int         # Offsets: 0xde (222), 0x34 (52)
    skill_3: int         # Offsets: 0xdf (223), 0xd1 (209)
    skill_4: int         # Offsets: 0x38 (56), 0xd2 (210)
    skill_5: int         # Offsets: 0xe5 (229), 0xd7 (215)
    skill_6: int         # Offsets: 0x39 (57), 0xd6 (214)
    skill_7: int         # Offsets: 0xe3 (227), 0xd5 (213)
    skill_8: int         # Offsets: 0xe6 (230), 0x36 (54)
    skill_9: int         # Offsets: 0xe2 (226), 0x35 (53)
    skill_10: int        # Offsets: 0xe1 (225), 0xd3 (211)
```

**Implementation Tasks**:

1. Parse nested XOR strings (names within record)
2. Read byte values at fixed offsets
3. Handle duplicated fields (update both locations)
4. Validate ranges (height 150-200, weight 50-100, etc.)

### 3. Write Operations

**Current**: Only replaces plaintext names in sections

**Needed**: Update byte values at specific offsets
```python
def update_player_stat(record: bytes, offset: int, new_value: int) -> bytes:
    """Update a single byte at offset"""
    modified = bytearray(record)
    modified[offset] = new_value
    return bytes(modified)

def update_player_skill(record: bytes, skill_num: int, new_value: int) -> bytes:
    """Update skill at both duplicate locations"""
    offsets = SKILL_OFFSETS[skill_num]  # e.g., [0xdd, 0xcf] for skill_1
    modified = bytearray(record)
    for offset in offsets:
        modified[offset] = new_value
    return bytes(modified)
```

---

## Implementation Roadmap

### Phase 1: Record Structure Analysis (4-6 hours)

**Goal**: Understand individual player record format

**Steps**:
1. Analyze spacing between names (DONE - we see 63-144 bytes)
2. Find record start/end markers
3. Map one complete player record byte-by-byte
4. Verify with 5-10 different players
5. Document the pattern

**Deliverable**: 
```python
def parse_single_player_record(data: bytes, offset: int) -> PlayerRecord:
    """Parse one complete player record from decoded data"""
    # Implementation here
```

**Estimated Time**: 4-6 hours

### Phase 2: Field Parser Implementation (3-4 hours)

**Goal**: Extract all player attributes

**Steps**:
1. Implement name parsing (handle nested XOR)
2. Read nationality, position, birth data
3. Read height/weight
4. Read all 10 skills from both locations
5. Test with known players
6. Validate data makes sense

**Deliverable**:
```python
class Player:
    name: str
    nationality: str
    position: str
    birth_date: date
    height: int
    weight: int
    skills: dict[str, int]  # 10 skills
```

**Estimated Time**: 3-4 hours

### Phase 3: Editor Implementation (2-3 hours)

**Goal**: Allow editing all fields

**Steps**:
1. Display current player stats
2. Edit interface for each field
3. Validation (ranges, valid values)
4. Update functions for each field type
5. Handle duplicated skill offsets
6. Test modifications persist

**Deliverable**:
```bash
python player_editor.py edit "Mikel LASA"
  
Current Stats:
  Name: Mikel LASA
  Nationality: Spain
  Position: Midfielder
  Height: 178cm, Weight: 75kg
  Skills: [85, 80, 78, ...]

Edit: skill_1 = 90
✓ Updated skill_1 from 85 to 90
```

**Estimated Time**: 2-3 hours

### Phase 4: Testing & Polish (2-3 hours)

**Goal**: Verify everything works in-game

**Steps**:
1. Test name changes persist
2. Test stat changes persist
3. Verify in-game display matches
4. Add batch operations
5. Error handling
6. Documentation

**Estimated Time**: 2-3 hours

---

## Total Time Estimate: 11-16 hours

Breakdown:
- Phase 1 (Record Structure): 4-6 hours
- Phase 2 (Field Parsing): 3-4 hours
- Phase 3 (Editor UI): 2-3 hours
- Phase 4 (Testing): 2-3 hours

---

## Recommended Approach

### Option A: Pattern Analysis (Moderate Difficulty)

**Pros**: 
- Can be done with static analysis
- No need for debugger
- Builds on current knowledge

**Cons**:
- May not find all edge cases
- Trial and error required
- Could miss important fields

**Time**: 11-14 hours

### Option B: Runtime Debugging (Higher Accuracy)

**Pros**:
- See exact byte positions game uses
- Guaranteed accurate mapping
- Understand conditional logic

**Cons**:
- Requires debugger setup (x32dbg, OllyDbg, etc.)
- Learning curve if unfamiliar
- Reverse engineering skills needed

**Time**: 8-12 hours (faster if debugger experience)

### Option C: Hybrid Approach (Recommended)

**Strategy**:
1. Start with pattern analysis (what we can see)
2. Test with a few players
3. Use debugger only for unclear fields
4. Verify in-game

**Time**: 10-13 hours

---

## What We Already Have

### ✅ Working Infrastructure
- XOR encode/decode (100% verified)
- File I/O with backups
- Section finding and parsing
- Name extraction working

### ✅ Known Information
- Field schema from Ghidra ([`out/schema_players.md`](out/schema_players.md))
- File format understood
- 10 skill attributes mapped (with offsets)
- Physical attributes mapped (height, weight, birth)

### ⚠️ What's Missing
- Individual record boundaries
- Variable-length handling after names
- Exact offset calculation per player
- Validation ranges for each field

---

## Quick Start Path

If you want to start **right now**, here's the fastest approach:

### 1. Analyze One Player Record (2 hours)

Find "Daniel KIMONI" in the decoded data and examine the 200 bytes around it:
```python
# We know he's at section 0x378383, offset +35
# Examine bytes from -20 to +180
# Map each byte to possible field
# Look for patterns that match schema
```

### 2. Test Field Changes (1 hour)

Try changing suspected skill bytes:
```python
# If skill_1 is at offset +207 from record start
# Change byte value from 85 to 90
# Reload in game, see if it changed
# Iterate until confirmed
```

### 3. Build Parser (2 hours)

Once one player is mapped:
```python
def parse_player_record(data, offset):
    # Use confirmed pattern
    # Parse all fields
    # Return structured data
```

### 4. Extend Editor (1 hour)

Add to existing player_editor.py:
```python
def edit_stats(player_name):
    # Load player
    # Display current stats
    # Allow editing
    # Save changes
```

**Total Quick Start**: 6 hours for basic working editor

---

## Next Steps - Choose Your Path

### Path 1: Continue with Current Name-Only Editor
- ✅ Already working
- ✅ Ready for in-game testing
- ⏭️ Extend later when needed

### Path 2: Build Full Editor Now
- Choose approach (A, B, or C)
- Follow roadmap phases
- 11-16 hours to completion
- Full featured result

### Path 3: Hybrid - Add Stats Incrementally
- Keep name editor working
- Add one field at a time
- Test each addition in-game
- Build up gradually

---

## Conclusion

**Current State**: Name editor is 100% functional

**For Full Editor**: Need to map individual player records and implement field parsing

**Fastest Path**: 6-8 hours for basic stat editing
**Complete Path**: 11-16 hours for full-featured editor

**Recommended**: 
1. Test current name editor in-game first (5 min)
2. Then decide if stats are needed
3. If yes, use Quick Start approach (6 hours)

All infrastructure is in place. The remaining work is mapping the record structure and implementing field access.