# Player Name Renaming - Technical Analysis

## Current State

### Why You Can't Rename Players

**GUI Issue:**
- In [`gui.py:360-363`](gui.py:360-363), the player name is displayed using a read-only `ttk.Label` widget
- Comment explicitly states: "Name (read-only for now)"
- Teams and Coaches CAN be renamed because they use `ttk.Entry` widgets in their editors

**Model Issue:**
- [`PlayerRecord`](models.py:560) lacks name mutation methods
- [`TeamRecord.set_name()`](models.py:282-319) ✓ Exists
- [`CoachRecord.set_name()`](models.py:531-554) ✓ Exists  
- `PlayerRecord.set_name()` ✗ **Missing**

---

## Why Player Renaming is Complex

### 1. Variable-Length Name Storage

Players use a complex binary structure:
```
Bytes 0-1:   Team ID (uint16, little-endian)
Byte 2:      Squad number
Bytes 3-4:   Padding
Bytes 5-45:  Name region (variable length, Latin-1)
             Format: [abbreviated]<separator>[Given Name SURNAME]
After name:  0x61 0x61 0x61 0x61 (name-end marker)
```

**Problem:** Names are variable length but occupy a fixed 40-byte region

### 2. Dependent Offsets

All metadata fields are positioned RELATIVE to the name-end marker:
- `name_end + 7`: Position (XOR encoded)
- `name_end + 8`: Nationality (XOR encoded)
- `name_end + 9`: Birth day (XOR encoded)
- `name_end + 10`: Birth month (XOR encoded)
- `name_end + 11-12`: Birth year (uint16, XOR encoded)
- `name_end + 13`: Height (XOR encoded)

**Problem:** Changing name length shifts ALL these offsets

### 3. Attributes at Fixed End Offset

Attributes are stored at a FIXED position from the record END:
- Attributes occupy bytes `[len-19, len-7]` (12 bytes, XOR encoded)

**Problem:** Two-way constraint - name can't grow too much or it collides with attributes

### 4. Record Size Constraints

From [`file_writer.py`](file_writer.py:103-178):
- Each record has a 2-byte length prefix
- Changing record size requires:
  - Rebuilding the entire record
  - Updating the length prefix
  - Adjusting ALL directory entry offsets after this record
  - Updating the file header's `max_offset`

---

## Required Changes

### Phase 1: Model Layer (SAFE)

**File:** [`pm99_editor/models.py`](models.py)

Add to `PlayerRecord` class:

```python
def set_given_name(self, new_given_name: str):
    """Set player's given name (first name)."""
    if not new_given_name or len(new_given_name) > 15:
        raise ValueError("Given name must be 1-15 characters")
    
    # Validate characters (Latin-1 safe)
    try:
        new_given_name.encode('latin-1')
    except:
        raise ValueError("Given name contains invalid characters")
    
    self.given_name = new_given_name
    self.name = f"{self.given_name} {self.surname}".strip()
    self._rebuild_name_region()
    self.modified = True

def set_surname(self, new_surname: str):
    """Set player's surname (last name)."""
    if not new_surname or len(new_surname) > 20:
        raise ValueError("Surname must be 1-20 characters")
    
    try:
        new_surname.encode('latin-1')
    except:
        raise ValueError("Surname contains invalid characters")
    
    self.surname = new_surname
    self.name = f"{self.given_name} {self.surname}".strip()
    self._rebuild_name_region()
    self.modified = True

def set_name(self, full_name: str):
    """Set player's full name (splits into given name + surname)."""
    if not full_name or len(full_name) > 35:
        raise ValueError("Full name must be 1-35 characters")
    
    parts = full_name.strip().split(maxsplit=1)
    if len(parts) < 2:
        raise ValueError("Name must include both given name and surname")
    
    self.set_given_name(parts[0])
    self.set_surname(parts[1])

def _rebuild_name_region(self):
    """Rebuild the name region in raw_data after name change.
    
    This is the CRITICAL method that handles:
    1. Building new name bytes
    2. Checking if it fits in available space
    3. Repositioning the name-end marker
    4. Adjusting all dependent metadata offsets
    5. Ensuring attributes remain at fixed end offset
    """
    if self.raw_data is None:
        # No raw_data yet - will be constructed in to_bytes()
        return
    
    # Build new name format: "GivenName SURNAME" (mixed case)
    new_name = f"{self.given_name.title()} {self.surname.upper()}"
    new_name_bytes = new_name.encode('latin-1', errors='replace')
    
    # Find current name region
    name_start = 5
    old_name_end = self._find_name_end_in_data(self.raw_data)
    if old_name_end is None:
        old_name_end = 45  # Default fallback
    
    # Calculate space available (must not collide with attributes)
    attr_start = len(self.raw_data) - 19
    max_name_bytes = attr_start - name_start - 10  # Reserve 10 bytes for marker + metadata
    
    if len(new_name_bytes) > max_name_bytes:
        raise ValueError(f"Name too long (max {max_name_bytes} bytes, got {len(new_name_bytes)})")
    
    # Build new name region
    data = bytearray(self.raw_data)
    
    # Clear old name region
    for i in range(name_start, min(45, len(data))):
        data[i] = 0x20  # Space character
    
    # Write new name
    data[name_start:name_start + len(new_name_bytes)] = new_name_bytes
    
    # Write name-end marker
    new_name_end = name_start + len(new_name_bytes)
    if new_name_end + 4 <= attr_start:
        data[new_name_end:new_name_end + 4] = bytes([0x61, 0x61, 0x61, 0x61])
    
    # Rewrite metadata at new offsets (relative to new name_end)
    # Position at new_name_end + 7
    if new_name_end + 7 < attr_start:
        data[new_name_end + 7] = self.position_primary ^ 0x61
    
    # Nationality at new_name_end + 8
    if new_name_end + 8 < attr_start:
        data[new_name_end + 8] = self.nationality ^ 0x61
    
    # DOB at new_name_end + 9, 10, 11-12
    if new_name_end + 12 < attr_start:
        data[new_name_end + 9] = self.birth_day ^ 0x61
        data[new_name_end + 10] = self.birth_month ^ 0x61
        year_bytes = struct.pack("<H", self.birth_year)
        data[new_name_end + 11] = year_bytes[0] ^ 0x61
        data[new_name_end + 12] = year_bytes[1] ^ 0x61
    
    # Height at new_name_end + 13
    if new_name_end + 13 < attr_start:
        data[new_name_end + 13] = self.height ^ 0x61
    
    # Attributes remain at fixed end offset - no changes needed
    # (They're already at len-19 to len-7)
    
    self.raw_data = bytes(data)
```

**Complexity:** High - requires deep understanding of binary format

**Risk:** Medium - metadata could be corrupted if offsets are wrong

---

### Phase 2: GUI Layer (SIMPLE)

**File:** [`pm99_editor/gui.py`](gui.py)

**Changes needed:**

1. **Replace Label with Entry widget** (line 360-363):

```python
# Name (editable)
ttk.Label(info_frame, text="Given Name:", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, pady=5)
self.given_name_var = tk.StringVar()
ttk.Entry(info_frame, textvariable=self.given_name_var, width=20).grid(row=0, column=1, sticky=tk.W, padx=10, pady=5)

ttk.Label(info_frame, text="Surname:", font=('TkDefaultFont', 10, 'bold')).grid(row=1, column=0, sticky=tk.W, pady=5)
self.surname_var = tk.StringVar()
ttk.Entry(info_frame, textvariable=self.surname_var, width=30).grid(row=1, column=1, sticky=tk.W, padx=10, pady=5)
```

2. **Update `display_record()` method** (line 1567-1620):

```python
def display_record(self, record: PlayerRecord):
    """Display record in editor"""
    # Set name fields
    self.given_name_var.set(record.given_name)
    self.surname_var.set(record.surname)
    
    # ... rest of existing code
```

3. **Update `apply_changes()` method** (line 1621-1701):

```python
def apply_changes(self):
    """Apply changes to current record"""
    if not self.current_record:
        return
    
    offset, record = self.current_record
    
    try:
        changes = []
        
        # Given Name
        new_given = self.given_name_var.get().strip()
        if new_given != record.given_name:
            try:
                record.set_given_name(new_given)
                changes.append(f"Given Name: {record.given_name} → {new_given}")
            except ValueError as e:
                messagebox.showerror("Invalid Name", str(e))
                return
        
        # Surname
        new_surname = self.surname_var.get().strip()
        if new_surname != record.surname:
            try:
                record.set_surname(new_surname)
                changes.append(f"Surname: {record.surname} → {new_surname}")
            except ValueError as e:
                messagebox.showerror("Invalid Name", str(e))
                return
        
        # ... rest of existing code (Team ID, Squad, etc.)
```

**Complexity:** Low - standard Tkinter patterns

**Risk:** Low - GUI changes are isolated

---

### Phase 3: Testing Requirements

#### Unit Tests Needed

**File:** `tests/test_player_renaming.py` (NEW)

```python
def test_set_given_name():
    """Test changing player's given name."""
    # Load a real player record
    # Change given name
    # Verify raw_data is updated correctly
    # Verify metadata offsets are preserved
    # Verify attributes are intact

def test_set_surname():
    """Test changing player's surname."""
    # Similar to above

def test_set_full_name():
    """Test changing full name at once."""
    # Should split and update both

def test_name_too_long():
    """Test that overly long names are rejected."""
    # Should raise ValueError

def test_name_with_special_chars():
    """Test names with accents/special characters."""
    # Should handle Latin-1 charset

def test_name_change_roundtrip():
    """Test that renamed player can be saved and reloaded."""
    # Critical - ensures file format integrity
```

#### Integration Tests Needed

```python
def test_rename_and_save():
    """Test full workflow: load -> rename -> save -> reload -> verify."""
    # This is THE critical test
    
def test_multiple_renames():
    """Test renaming multiple players in same session."""
    # Ensures state management works

def test_rename_undo():
    """Test that reset button works after rename."""
    # GUI state consistency
```

#### Manual Testing Checklist

- [ ] Load database with 100+ players
- [ ] Rename 10 different players (various name lengths)
- [ ] Save database
- [ ] Reload in PM99 game - verify names display correctly
- [ ] Check all player stats are intact
- [ ] Verify team assignments unchanged
- [ ] Test edge cases:
  - [ ] Very short names (e.g., "Li Bo")
  - [ ] Very long names (hitting 35 char limit)
  - [ ] Names with accents (José, François, etc.)
  - [ ] Names with spaces (Van der Sar)
  - [ ] Names with punctuation (O'Brien)

---

## Risks and Mitigation

### Risk 1: Data Corruption
**Impact:** HIGH - Could make save file unreadable by game  
**Probability:** MEDIUM - Complex binary manipulation  
**Mitigation:**
- Automatic backup before any save (already implemented)
- Extensive unit tests covering edge cases
- Validation of name length before accepting
- Test with game after each change

### Risk 2: Offset Calculation Errors
**Impact:** HIGH - Could corrupt player stats/metadata  
**Probability:** MEDIUM - Easy to get offsets wrong  
**Mitigation:**
- Helper methods with clear documentation
- Assertion checks in debug mode
- Compare before/after attribute values in tests

### Risk 3: Name Encoding Issues
**Impact:** MEDIUM - Names could display incorrectly  
**Probability:** LOW - Latin-1 is well understood  
**Mitigation:**
- Validate encoding before accepting input
- Test with international character sets
- Document supported character ranges

### Risk 4: File Size Changes
**Impact:** HIGH - Could corrupt directory structure  
**Probability:** LOW - Using existing `file_writer.py` logic  
**Mitigation:**
- Rely on proven `save_modified_records()` function
- This already handles length changes for teams/coaches
- Test with known-good records first

---

## Recommended Implementation Plan

### Stage 1: Proof of Concept (1-2 days)
- [ ] Implement `set_given_name()` / `set_surname()` in models
- [ ] Write unit tests for name changing
- [ ] Test with a single player in isolation
- [ ] Verify `to_bytes()` produces valid output

### Stage 2: GUI Integration (1 day)
- [ ] Add Entry widgets to GUI
- [ ] Wire up `apply_changes()` logic
- [ ] Add validation error messages
- [ ] Test in GUI environment

### Stage 3: Integration Testing (1-2 days)
- [ ] Full roundtrip tests (save/reload)
- [ ] Test with actual PM99 game executable
- [ ] Test edge cases and special characters
- [ ] Performance test with large databases

### Stage 4: Documentation & Release (1 day)
- [ ] Update user documentation
- [ ] Add tooltips/help text in GUI
- [ ] Create backup/restore instructions
- [ ] Release notes with warnings

**Total Estimated Time:** 4-6 days (experienced developer)

---

## Alternative Approaches

### Option A: Name Substitution Table
Instead of modifying binary records, maintain a separate mapping file:
- `player_offset -> display_name`
- GUI shows mapped name
- Game still sees original name

**Pros:** Zero risk of corruption  
**Cons:** Names don't change in game, only in editor

### Option B: Length-Preserving Only
Only allow renames that fit in existing space:
- Calculate current name length
- Only accept new names ≤ current length
- Pad with spaces

**Pros:** Simpler, safer  
**Cons:** Very restrictive, poor UX

### Option C: Hybrid Approach
Implement Option B first (length-preserving), then expand to full variable-length later

**Recommended:** This is actually the safest path forward

---

## Validation Against Game Executable

From [`GHIDRA_VALIDATION_PLAN.md`](GHIDRA_VALIDATION_PLAN.md), you have Ghidra analysis available:

**Critical Validation Steps:**
1. Use Ghidra MCP server to:
   - Verify name parsing logic in game code
   - Confirm name-end marker handling
   - Check metadata offset calculations
   - Validate encoding/decoding routines

2. Compare our implementation against:
   - `FUN_004afd80()` - player record parser
   - `FUN_00416d80()` - name extraction
   - Validate our offset calculations match game's

**MCP Server Tools Available:**
- `decompile_function` - See game's name parsing code
- `list_functions` - Find related name handling
- `get_xrefs_to` - Find all places that access names

---

## Summary

### Can you rename players? 
**Not currently** - functionality is incomplete

### Should you implement it?
**Yes**, but carefully and in stages

### Key Challenges:
1. ✓ Variable-length name storage (solvable)
2. ✓ Dependent metadata offsets (requires careful coding)
3. ✓ Fixed attribute positions (constrains max name length)
4. ✓ File format integrity (use existing save logic)

### Biggest Risk:
Corrupting player data due to incorrect offset calculations

### Best Mitigation:
Comprehensive testing + validation against game code + automatic backups

### Recommended Next Step:
Start with **Stage 1: Proof of Concept** using length-preserving approach