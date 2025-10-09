# Premier Manager 99 - Field Mapping Session Report
**Date**: 2025-10-03  
**Status**: Partial Progress - 12-Attribute Discovery

## 🎯 Session Objective
Map the position, nationality, and age fields in player records from [`DBDAT/JUG98030.FDI`](DBDAT/JUG98030.FDI).

---

## ✅ Key Discoveries

### 1. **CRITICAL: Game Uses 12 Attributes, Not 10**

From in-game analysis of Andy Cole:
```
Attribute Order (12 total):
1.  SPEED       = 87
2.  STAMINA     = 86
3.  AGGRESSION  = 84
4.  QUALITY     = 75
5.  FITNESS     = 70
6.  MORALE      = 99
7.  HANDLING    = 13
8.  PASSING     = 70
9.  DRIBBLING   = 73
10. HEADING     = 86
11. TACKLING    = 65
12. SHOOTING    = 88
```

**Previous assumption of 10 attributes was incorrect!**

### 2. **Two Record Types Identified**

#### Type A: Clean Records (HIERRO, ZIDANE)
- Size: ~70 bytes
- Structure: `[team_id][squad][name][20-byte metadata][10 unknown bytes]`
- Example (HIERRO): 69 bytes total

```
Bytes 0-1:   Team ID (0x616b = 24939)
Byte 2:      Squad number (101)
Bytes 3-38:  Player name (36 bytes)
Bytes 39-58: Metadata region (20 bytes)
Bytes 59-68: Unknown (10 bytes) - possibly partial attributes?
```

#### Type B: Biography Records (KAHN, RONALDO, COLE)
- Size: 4KB - 150KB
- Contains: Extensive career history, statistics, text descriptions
- Gameplay data is embedded somewhere within
- Much harder to parse

### 3. **Sample Data Extracted**

**Fernando HIERRO** (Defender, Age 30, Spain):
```
Metadata (20 bytes):
61 61 77 60 62 60 76 62 d1 66 da 35 34 3a 38 36 2e 27 2b 31
97 97 119 96 98 96 118 98 209 102 218 53 52 58 56 54 46 39 43 49
```

**Zinedine ZIDANE** (Midfielder, Age 26, France):
```
Metadata (20 bytes):
73 69 79 60 62 63 76 67 d5 66 d8 31 38 39 35 3c 2f 35 38 34
115 105 121 96 98 99 118 103 213 102 216 49 56 57 53 60 47 53 56 52
```

### 4. **Metadata Comparison Results**

Byte-by-byte comparison of HIERRO vs ZIDANE metadata:
- **No clear position field found** (expected 1 vs 2)
- **No clear age field found** (expected 30 vs 26)
- **No obvious nationality pattern** (Spain vs France)

The metadata bytes show some variation but no obvious correlation with known values.

---

## ❌ Problems Encountered

### Problem 1: Attribute Count Mismatch
- Previous documentation assumed 10 attributes
- Game shows 12 attributes
- Clean records only have 10 bytes at the end (not 12)
- **Implication**: The 10 bytes might not all be attributes, or attributes stored differently

### Problem 2: Metadata Encoding Unknown
The 20-byte metadata region doesn't contain obvious:
- Position codes (0-3 or 1-4)
- Age values (22-30 range)
- Simple country codes

Possible explanations:
1. Fields are encoded/obfuscated beyond simple values
2. Fields are bit-packed or use complex encoding
3. Position/age/nationality stored elsewhere in record
4. The metadata region serves a different purpose

### Problem 3: Biography Records
Players with biographies have massive variable-length records making it impossible to identify field positions by offset alone.

---

## 📋 Tools Created

1. [`extract_known_players.py`](extract_known_players.py) - Search and extract player records
2. [`analyze_known_players.py`](analyze_known_players.py) - Comparative byte analysis
3. [`focused_metadata_analysis.py`](focused_metadata_analysis.py) - HIERRO/ZIDANE comparison
4. [`analyze_metadata_region.py`](analyze_metadata_region.py) - Metadata boundary detection
5. [`find_andy_cole.py`](find_andy_cole.py) - Locate Cole's record
6. [`find_cole_precise.py`](find_cole_precise.py) - Precise Cole data extraction

---

## 🔍 Recommended Next Steps

### Immediate Actions (High Priority)

**1. Use Memory Editing to Validate**
- Load a save game in the game
- Use a memory editor (Cheat Engine) to find Andy Cole's data in RAM
- Modify his position/age/nationality values
- Observe which bytes change in memory
- Compare memory layout to disk layout

**2. Find Players Without Biographies**
- Search for simple players (non-stars) with clean records
- Build a dataset of 10-20 clean records
- Compare metadata across different positions/ages/nationalities
- Look for statistical patterns

**3. Examine Height/Weight Fields**
Andy Cole's data shows:
```
WEIGHT: 11 11 (11 stone 11 pounds)
HEIGHT: 5 10  (5 feet 10 inches)
```

These unusual values might be findable in the metadata region!

**4. Test Attribute Theory**
The "10 bytes" at the end of clean records might be:
- Position (1 byte)
- Nationality (1 byte)
- Age or birth date (2-4 bytes)
- Height (2 bytes)
- Weight (2 bytes)
- **NOT attributes**

Attributes might be stored elsewhere or in a different file.

### Analysis Strategies

**Strategy A: Statistical Analysis**
Extract 50+ clean player records and run statistical correlation:
- Find bytes that correlate with known ages
- Find bytes that correlate with known positions
- Use chi-square or correlation analysis

**Strategy B: Bit-field Analysis**
The metadata might use bit-packing:
```
Example: Single byte storing multiple fields
Bits 0-1: Position (0-3)
Bits 2-3: Foot preference (left/right/both)
Bits 4-7: Other flags
```

**Strategy C: Reference File Cross-check**
Check if position/age/nationality stored in a separate file:
- [`DBDAT/ENT98030.FDI`](DBDAT/ENT98030.FDI) (teams/coaches?)
- [`DBDAT/EQ98030.FDI`](DBDAT/EQ98030.FDI) (confirmed teams file)
- Other .FDI files

---

## 💡 Critical Questions to Answer

1. **Where are the 12 attributes stored?**
   - In JUG98030.FDI?
   - In a separate file?
   - Only 10 stored, 2 calculated?

2. **What is the "10-byte" region at the end of clean records?**
   - Not all attributes (only 10 bytes, need 12)
   - Might be metadata instead

3. **How are biography records structured?**
   - Where is gameplay data vs text?
   - Is there a secondary structure?

4. **Are clean vs biography records fundamentally different formats?**
   - Do they use different field layouts?
   - Is biography text an addon to standard structure?

---

## 📊 Current Understanding

### Confirmed Facts ✅
- XOR encryption: `0x61` key
- Separator: `0xdd 0x63 0x60`
- Team ID: 2 bytes (little-endian), range 3712-3807
- Squad number: 1 byte, range 96-119
- Player names: Variable length, surname first
- Game uses 12 attributes (not 10)

### Uncertain 🤔
- Position field location/encoding
- Nationality field location/encoding
- Age field location/encoding
- Attribute storage method
- Purpose of 10-byte end region
- Height/weight storage

### Unknown ❌
- Complete field layout
- Encoding schemes used
- Relationship between clean/biography records
- Secondary data files

---

## 🎯 Success Criteria for Next Session

To consider field mapping complete, we need:

1. ✅ Identify position field (1 byte or bits)
2. ✅ Identify nationality field (1 byte)
3. ✅ Identify age or birth date field (2-4 bytes)
4. ✅ Locate all 12 attributes
5. ✅ Understand height/weight storage
6. ✅ Validate by modifying and testing in-game

---

## 📁 Session Artifacts

- Clean record samples: HIERRO (69 bytes), ZIDANE (70 bytes)
- Biography record samples: KAHN (149KB), RONALDO (4KB), COLE (30KB)
- Comparative analysis: 20-byte metadata region mapped
- Tools: 6 Python analysis scripts created
- Documentation: This report

**Next engineer should start with memory editing validation or clean player dataset expansion.**