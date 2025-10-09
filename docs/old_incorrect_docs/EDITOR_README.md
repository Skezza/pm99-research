# Premier Manager 99 Database Editor - User Guide

## Current Status: Beta / Limited Functionality

This editor allows you to modify certain fields in the Premier Manager 99 player database.
Due to the complex variable-length record structure, **not all fields are editable yet**.

## ✅ What Works (Safe to Edit)

### Player Attributes
- All 12 attribute fields can be edited
- Values are automatically clamped to 0-99 range
- Changes are applied via double-XOR encoding

### Team Management  
- Team ID can be changed (for player transfers)
- Squad Number can be modified
- Team display names are shown (basic mapping)

### Player Management
- Search and filter players by name
- View player details
- Duplicate detection and resolution

## ⚠️ Known Limitations

### Position Field - ✅ CONFIRMED (56.9% accuracy)
The position field parsing has been updated to use dynamic offset calculation based on the 'aaaa' name-end marker. Accuracy improved from 33.5% to 56.9%; the editor detects and writes position values reliably for the majority of small player records.

**Technical Note**: Positions are located at offset +7 from the 'aaaa' name-end marker and are double-XOR encoded (0=GK, 1=DEF, 2=MID, 3=FWD). The parser also checks offset +8 as a fallback for edge cases.
### Missing Features
These require additional reverse engineering work:
- ❌ Player name editing
- ❌ Date of Birth  
- ❌ Height
- ❌ Weight
- ❌ Nationality
- ❌ Team name editing (file structure identified but not yet implemented)

## 🔧 How to Use

### Basic Editing Workflow

1. **Launch Editor**
   ```
   python pm99_database_editor.py
   ```

2. **Find Player**
   - Use the search box to filter by name
   - Select player from the list

3. **Edit Attributes**
   - Modify any of the 12 attribute sliders
   - Values automatically clamp to 0-99
   - Click "Apply Changes"

4. **Transfer Player** (Optional)
   - Change Team ID number
   - Change Squad Number
   - Click "Apply Changes"

5. **Save Database**
   - Press Ctrl+S or use File → Save Database
   - Automatic backup is created

### Resolve Duplicates

1. Go to "Duplicates" tab
2. Select a surname group
3. Pick the preferred record
4. Click "Keep Selected, Remove Others"

## 💾 Backups

**IMPORTANT**: The editor creates automatic backups when saving:
- Format: `JUG98030.FDI.backup_YYYYMMDD_HHMMSS`
- Keep these backups in case something goes wrong
- You can restore by copying a backup over the original file

## 🐛 Troubleshooting

### Positions 'Unknown' (legacy issue)
- Older editor versions that used fixed offsets often show "Unknown" positions.
- Current editor uses dynamic name-end marker parsing; position values are detected for most records.
- If you still encounter "Unknown", the record's name-end marker couldn't be found; re-load the database or run validation scripts (`scripts/validate_known_players.py`) to investigate.
### Attributes Show Values >99
- This happens on initial load from database
- The editor will clamp to 0-99 when you edit and save
- Do not edit attributes that already show >99 (corrupted data)

### Changes Don't Save
- Make sure you clicked "Apply Changes" first
- Then save with Ctrl+S
- Check the status bar for confirmation messages

## 📋 Technical Details

### Record Structure
- Records are XOR-encoded with key 0x61
- Variable-length player names (5-40 bytes) starting at offset +5
- Team ID: bytes 0-1 (little-endian uint16)
- Squad Number: byte 2
- Name end marker: four 0x61 bytes ('aaaa') immediately after the name
- Position: located at name_end + 7 (double-XOR encoded)
- Attributes: located at record_length - 19 to record_length - 7 (12 bytes), double-XOR encoded

### Why Some Fields Might Previously Fail
The file format uses variable-length names which shift following field offsets:
- Player name length varies (e.g., "Smith" vs "García-Rodríguez")
- Fixed byte offsets (like byte 42) are not reliable across records
- The editor now calculates dynamic offsets using the name-end marker to find position and other metadata
### Files Modified
- `DBDAT/JUG98030.FDI` - Player database (primary)
- `DBDAT/EQ98030.FDI` - Team database (read-only currently)
- `DBDAT/ENT98030.FDI` - Coach database (read-only currently)

## 🚀 Future Work Needed

To make this a complete editor, remaining items include:

1. **Position Parsing** — Implemented
   - Dynamic name-end parsing and position write-back are implemented in the editor (`app/pm99_database_editor.py`).
   - The parser uses +7 from the 'aaaa' marker with +8 as a fallback; further validation across edge cases is recommended.
2. **Add Player Name Editing**
   - Requires rewriting entire record with new name length
   - Must update all subsequent field offsets
   - Complex but doable

3. **Map Metadata Fields**
   - Reverse engineer exact positions of DOB, height, weight, nationality
   - These are in the variable metadata region after the name
   - Requires hex analysis of known players

4. **Team/Manager Editing**
   - Load team file properly
   - Allow team name editing  
   - Persist changes back to EQ98030.FDI

## 📝 Version History

- **v0.1** - Initial release
  - Basic attribute editing
  - Team ID and squad number editing
  - Duplicate resolution
  - Position parsing: dynamic parsing implemented (56.9% accuracy)
## 🙏 Credits

Based on reverse engineering work documented in:
- `FIELD_MAPPING_BREAKTHROUGH.md`
- `PLAYER_FIELD_MAP.md`
- `map_player_record.py`

## ⚖️ License

Educational/research use only. Premier Manager 99 is copyrighted by its original developers.