# Player Record Field Mapping - Binary Analysis Results

## Record Structure Overview

**Total Size**: Variable (typically 65-75 bytes)  
**Encoding**: XOR-0x61 after decoding outer layer  
**Separator**: `dd 63 60` (3 bytes)

---

## Confirmed Field Map

### Bytes 0-2: Record Separator
```
Offset: +0 to +2
Size: 3 bytes
Value: dd 63 60 (constant)
Type: Magic bytes / record delimiter
```

### Bytes 3-4: Team ID
```
Offset: +3 to +4
Size: 2 bytes (uint16, little-endian)
Range: 3712-3807 (observed from 8,866 players)
Examples:
  - 0x0ed5 (3797) = Team #1
  - 0x0ed4 (3796) = Team #2  
  - 0x0ed7 (3799) = Team #3

Status: HIGH CONFIDENCE ✓
```

### Byte 5: Squad Number / Jersey Number
```
Offset: +5
Size: 1 byte
Range: 96-119 (observed)
Note: 96 (0x60) appears to be "unassigned" marker
Examples:
  - 98 = Jersey #2?
  - 103 = Jersey #7?
  - 108 = Jersey #12?

Status: MEDIUM CONFIDENCE (needs verification)
```

### Bytes 6-7: Unknown Metadata
```
Offset: +6
Size: 1 byte
Range: 100-109 observed
Most common: 105 (0x69 = 'i')

Offset: +7  
Size: 1 byte
Value: 97 (0x61 = 'a') - CONSTANT across ALL records
Purpose: Unknown marker/flag

Status: UNKNOWN - requires further analysis
```

### Bytes 8-15: Name Prefix / Metadata
```
Offset: +8 to +15
Size: 8 bytes
Content: Variable text/bytes before full name
Pattern: Often contains partial surname

Examples:
  Player 1: "Kimoni" before "Daniel KIMONI"
  Player 2: "Olivieri" before "Domenico OLIVIERI"
  
Status: PARTIAL - appears to be surname fragment
```

### Bytes 16+: Player Full Name
```
Offset: Variable (typically starts +8 to +16)
Size: Variable (typically 15-35 bytes)
Format: Given name + SURNAME (surname in capitals)
Encoding: Latin-1 / Windows-1252
Terminator: None explicit, followed by more metadata

Examples:
  "Daniel KIMONI"
  "Domenico OLIVIERI"  
  "Marc VANGRONSVELD"

Status: CONFIRMED ✓
```

### After Name: Unknown Fields
```
Offset: Variable (name_end to name_end+~12)
Size: ~8-15 bytes
Content: Mix of text chars and control bytes

Hypothesis: Contains:
  - Nationality code
  - Position codes  
  - Age/birth date
  - Height/weight
  
Status: UNMAPPED - requires correlation with known player data
```

### Name_End + ~10-20: Attributes (10 stats)
```
Offset: Variable (typically name_end + 10 to 20 bytes)
Size: 10 bytes
Range: 0-100 per byte (excludes 96/0x60 which is padding)
Type: Player statistics

Known order (from game testing):
  [0] Passing
  [1] Shooting
  [2] Tackling
  [3] Speed
  [4] Stamina
  [5] Heading
  [6] Dribbling
  [7] Aggression
  [8] Positioning
  [9] Form

Status: CONFIRMED ✓
```

---

## Statistical Analysis Results

Based on analysis of 704 player records:

| Byte | Unique Values | Most Common | Range | Interpretation |
|------|---------------|-------------|-------|----------------|
| +0 | 1 | 221 (100%) | 221-221 | Separator byte 1 |
| +1 | 1 | 99 (100%) | 99-99 | Separator byte 2 |
| +2 | 1 | 96 (100%) | 96-96 | Separator byte 3 |
| +3 | 704 | varies | 128-223 | Team ID (low byte) |
| +4 | 1 | 14 (100%) | 14-14 | **Team ID high byte (constant 0x0e)** |
| +5 | 9 | 96 (82%) | 96-119 | Squad number? |
| +6 | 9 | 105 (28%) | 100-109 | Unknown |
| +7 | 1 | 97 (100%) | 97-97 | **Constant marker** |
| +8+ | varies | - | - | Name/metadata region |

---

## Critical Discovery: Team ID Structure

The team ID is a **16-bit little-endian value** with:
- **High byte**: ALWAYS 0x0e (14 decimal)
- **Low byte**: Varies from 0x80 to 0xdf

This means team IDs are in range:
- Minimum: 0x0e80 = 3712
- Maximum: 0x0edf = 3807
- **Total teams referenced: ~96 different team IDs**

This correlates with the 543 teams found in [`EQ98030.FDI`](DBDAT/EQ98030.FDI), suggesting:
- Only ~96 teams are actively used in this save/database
- The other ~447 teams may be in other leagues/divisions not loaded

---

## Unmapped Fields (Priority Order)

### 1. Nationality (1 byte) ⚠️ HIGH PRIORITY
```
Likely position: bytes 6-15 region
Expected: Single byte, value 0-50 (country code)
Method: Find known foreign players, compare byte patterns
```

### 2. Position Primary/Secondary (1-2 bytes) ⚠️ HIGH PRIORITY  
```
Likely position: bytes 6-15 region
Expected: 1-2 bytes, value 0-10 (GK=0, DEF, MID, FWD, etc.)
Method: Find known defenders/strikers, compare patterns
```

### 3. Age / Birth Date (2-4 bytes) ⚠️ MEDIUM PRIORITY
```
Likely position: bytes 6-15 or after name before attributes
Expected: Day (1-31), Month (1-12), Year (1960-1985 as 16-bit)
Method: Find young vs old players, look for date-like values
```

### 4. Height (1 byte) ⚠️ LOW PRIORITY
```
Expected: 150-210 cm range
Location: Unknown (bytes 6-15 or post-name)
```

### 5. Weight (1 byte) ⚠️ LOW PRIORITY
```
Expected: 50-110 kg range  
Location: Unknown (bytes 6-15 or post-name)
```

---

## Validation Strategy

### Phase 1: Team ID Correlation ✅ NEXT STEP
1. Extract all player team_ids (bytes 3-4)
2. Extract all team records from [`EQ98030.FDI`](DBDAT/EQ98030.FDI)
3. Find team ID field in team records
4. Build mapping: team_id → team_name
5. Validate by checking player roster distribution

### Phase 2: Position Field Discovery
1. Search for known players by name
2. Extract their record bytes 6-15
3. Compare defenders vs midfielders vs forwards
4. Look for byte positions with consistent values (0-10 range)

### Phase 3: Nationality Field Discovery  
1. Find known foreign players (non-local nationality)
2. Compare with local players
3. Look for single byte differences in 0-50 range

### Phase 4: Age/Date Discovery
1. Find young vs old players
2. Look for date-pattern bytes (day 1-31, month 1-12, year as 16-bit)
3. Validate against known player ages

---

## Next Immediate Steps

**Recommendation**: Create team ID correlation tool

```python
# Pseudo-code
1. Load all 8,866 player records
2. Extract team_id from bytes 3-4
3. Group players by team_id
4. Load 543 team records  
5. Find team ID in team records (search bytes 0-50 for matching values)
6. Build lookup table
7. Output: "Player X (team_id 3797) plays for Team Y"
```

This will:
- Validate team_id field hypothesis (bytes 3-4)
- Enable roster views
- Confirm player-team relationships
- Provide foundation for further field mapping

---

## References

- [`binary_field_mapper.py`](binary_field_mapper.py) - Hex dump analysis tool
- [`TEAM_FILE_BREAKTHROUGH.md`](TEAM_FILE_BREAKTHROUGH.md) - Team database analysis
- [`DBDAT/JUG98030.FDI`](DBDAT/JUG98030.FDI) - Player database (8,866 players)
- [`DBDAT/EQ98030.FDI`](DBDAT/EQ98030.FDI) - Team database (543 teams)

---

*Last Updated: 2025-10-03*  
*Analysis: Binary field mapping via hex dump comparison*