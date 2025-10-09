# Handover: GUI Loading Issues Investigation

## Overview
The Premier Manager 99 Database Editor GUI has persistent issues with loading Coaches and Teams tabs. Despite implemented fixes, the tabs are not displaying data correctly. This handover provides context for further investigation.

## Current State

### Implemented Fixes
1. **Coach Name Parsing**: Updated `coach_models.py` to handle accented characters and improved regex patterns
2. **Team Name Extraction**: Enhanced `TeamRecord._extract_name()` with better validation and scoring
3. **Sequential Scanning**: Added fallback sequential scanning for both coaches and teams when directory entries fail
4. **GUI Selection**: Fixed coach selection "sticking" by clearing displays on tab changes

### Test Results
- Sequential scanning finds 4,891 coach entries and 2,391 team entries
- However, the actual GUI tabs still show "Unknown Coach" and "Unknown Team"
- Coach selection appears to work but displays garbled names

## Issues to Investigate

### 1. FDI Directory Structure
**Problem**: The GUI relies on FDI directory entries, but these may be corrupted or incorrectly formatted.

**Investigation Points**:
- Verify FDI header parsing in `io.py`
- Check directory entry offsets in ENT98030.FDI and EQ98030.FDI
- Compare directory entries with actual data locations
- Test if directory scanning works correctly

**Files to Examine**:
- `pm99_editor/io.py` - FDIFile class
- `DBDAT/ENT98030.FDI` - Coach file directory
- `DBDAT/EQ98030.FDI` - Team file directory

### 2. Data Decoding Issues
**Problem**: Coach and team data may require different decoding than implemented.

**Investigation Points**:
- Verify XOR key (currently 0x61) is correct for all data types
- Check if coach data uses 32-bit XOR encoding as suspected
- Test different decoding approaches on sample data
- Compare decoded output with expected plaintext

**Files to Examine**:
- `pm99_editor/xor.py` - Decoding functions
- `pm99_editor/coach_models.py` - Coach parsing logic
- `pm99_editor/models.py` - Team parsing logic

### 3. GUI Loading Logic
**Problem**: The GUI loading functions may not be properly integrating the parsing results.

**Investigation Points**:
- Verify `load_coaches()` and team loading functions complete successfully
- Check if parsed data is properly stored in `self.coach_records` and `self.team_records`
- Test if `populate_coach_tree()` and `populate_team_tree()` receive valid data
- Debug the threading/async loading mechanisms

**Files to Examine**:
- `pm99_editor/gui.py` - Loading and population functions
- Check console output for error messages during loading

### 4. Data Format Understanding
**Problem**: The binary format of coach and team records may not be fully understood.

**Investigation Points**:
- Analyze raw binary structure of coach records
- Compare coach record format with player records
- Verify field offsets and data types
- Test parsing on known coach/team data samples

**Files to Examine**:
- `scripts/analyze_coaches.py` - Existing analysis
- `scripts/analyze_team_file.py` - Team analysis
- Raw binary inspection of FDI files

## Debugging Steps

### Step 1: Verify Directory Loading
```python
from pm99_editor.io import FDIFile
fdi = FDIFile('DBDAT/ENT98030.FDI')
fdi.load()
print(f"Directory entries: {len(fdi.directory)}")
for i, entry in enumerate(fdi.directory[:5]):
    print(f"Entry {i}: offset=0x{entry.offset:x}, tag={entry.tag}")
```

### Step 2: Test Individual Record Decoding
```python
from pm99_editor.xor import decode_entry
data = open('DBDAT/ENT98030.FDI', 'rb').read()
decoded, length = decode_entry(data, 0x402)  # First data offset
print(f"Decoded length: {length}")
print(f"First 100 bytes: {decoded[:100]}")
```

### Step 3: Test Coach Parsing
```python
from pm99_editor.coach_models import parse_coaches_from_record
coaches = parse_coaches_from_record(decoded)
print(f"Found {len(coaches)} coaches")
for c in coaches[:3]:
    print(f"Coach: {c.full_name}")
```

### Step 4: GUI Loading Debug
Add debug prints to `load_coaches()` and `populate_coach_tree()` to trace data flow:
```python
def load_coaches(self):
    # ... existing code ...
    print(f"DEBUG: Found {len(parsed_coaches)} coaches")
    for i, (offset, coach) in enumerate(parsed_coaches[:3]):
        print(f"DEBUG: Coach {i}: {getattr(coach, 'full_name', 'no name')}")

def populate_coach_tree(self):
    print(f"DEBUG: Populating tree with {len(self.coach_records)} coaches")
    # ... existing code ...
```

## Expected Outcomes

1. **Directory Issues**: If directory is corrupted, implement manual offset scanning
2. **Decoding Issues**: If XOR key is wrong, identify correct decoding method
3. **Parsing Issues**: If record structure is wrong, fix field offsets and types
4. **GUI Issues**: If data flows correctly but display fails, fix tree population

## Files Modified Recently
- `pm99_editor/coach_models.py` - Coach parsing improvements
- `pm99_editor/models.py` - Team name extraction improvements
- `pm99_editor/gui.py` - Sequential scanning and selection fixes
- `test_gui_loading.py` - Test script for verification

## Next Steps
1. Run the debugging steps above to isolate the issue
2. Check console output for error messages
3. Verify data flows from parsing to GUI display
4. Implement fixes based on findings

## Contact
If issues persist, check the test script output and compare with GUI behavior.