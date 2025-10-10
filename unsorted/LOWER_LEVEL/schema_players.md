# Player Record Schema (PM99 FDI Format)

Derived from [`MANAGPRE.EXE.FUN_004afd80()`](MANAGPRE.EXE:0x004afd80) decompilation.

## Record Structure

All records start with a uint16 length field (little-endian), followed by XOR-encrypted data (key=0x61).

### Core Fields (after XOR decode)

| Offset | Type | Field Name | Description | Notes |
|--------|------|------------|-------------|-------|
| 0x00 | uint16 | record_length | Total decoded length | Stored in `param_1[0]` and `param_1[1]` |
| 0x02 | XOR-string | given_name | First name | Decoded via `FUN_00677e30()`, truncated to ≤13 chars |
| +var | XOR-string | surname | Last name | Follows given_name |
| +0 | byte | initial_char | Single character | Stored at `param_1[9]` and offset 0x26 |
| +1 | skip | - | Reserved byte | |
| +2 | byte[6] | initials | Six character codes | Loop-decoded with wrap logic, offsets 0x1d-0x22 |
| +8 | byte | nationality | Nation code | Offset 0x25 |
| +9 | byte | position_primary | Main position | Offset 0x1a |
| +10 | byte | position_secondary | Alt position | Offset 0x1b |
| +11 | byte | unknown_1c | Unknown | `param_1[7]` = offset 0x1c |

### Birth Data

| Offset | Type | Field Name | Default Logic |
|--------|------|------------|---------------|
| 0x48 (72) | byte | birth_day | `DAT_00759794 >> 0x10` if zero |
| 0x121 (289) | byte | birth_month | `DAT_00759794 >> 0x18` if zero |
| 0x11e (286) | uint16 | birth_year | `FUN_004c2830(5)` generates 1990-1999 if out of range |

### Physical Attributes

| Offset | Type | Field Name | Default Logic |
|--------|------|------------|---------------|
| 0x115 (277) | byte | height | If < 150: `FUN_004c2830(10) - 86` |
| 0x116 (278) | byte | weight | If < 20: `FUN_004c2830(10) + 75` |

### Skill Attributes (duplicated offsets)

These bytes are written to two locations each (likely for caching/display):

| Offset Pair | Field Name | Notes |
|-------------|------------|-------|
| 0xdd (221), 0xcf (207) | skill_1 | |
| 0xde (222), 0x34 (52 = param_1[0x34]) | skill_2 | |
| 0xdf (223), 0xd1 (209) | skill_3 | |
| 0x38 (56 = param_1[0x38]), 0xd2 (210) | skill_4 | |
| 0xe5 (229), 0xd7 (215) | skill_5 | |
| 0x39 (57 = param_1[0x39]), 0xd6 (214) | skill_6 | |
| 0xe3 (227), 0xd5 (213) | skill_7 | |
| 0xe6 (230), 0x36 (54 = param_1[0x36]) | skill_8 | |
| 0xe2 (226), 0x35 (53 = param_1[0x35]) | skill_9 | |
| 0xe1 (225), 0xd3 (211) | skill_10 | |

### Extended Fields (version >= 700 only)

| Offset | Type | Field Name |
|--------|------|------------|
| 0x117 (279) | byte | extended_1 |
| 0x118 (280) = param_1[0x46] | byte | extended_2 |
| 0x119 (281) | byte | extended_3 |
| 0x11a (282) | byte | extended_4 |
| 0x11b (283) | byte | extended_5 |
| 0x11c (284) = param_1[0x47] | byte | extended_6 |

### Optional Blocks (conditional)

**Contract Block** (if club_id == 0x26ac):
- `param_1[4]` = pointer to XOR-decoded contract data
- Otherwise: multiple length-prefixed segments skipped via `*ptr = *(ushort *)*ptr + 2 + *ptr` pattern

**Legacy Segments** (if param_6 != 0 or version < 600):
- Series of 7 skip blocks using the same length-prefix pattern
- Each: read uint16 length, skip (length + 2) bytes

### Region Code

| Offset | Type | Field Name | Notes |
|--------|------|------------|-------|
| 0x114 (276) = param_1[0x45] | byte | region_code | 0x1e = 30 (English build) |

## Parsing Algorithm

1. Read uint16 length
2. XOR-decode names (two sequential calls to `FUN_00677e30`)
3. Read single char + skip byte
4. Decode 6 initial bytes with wrap logic
5. Read nationality, positions, birth data
6. Read height/weight with validation
7. Read 10 skill attributes (each written to two offsets)
8. If version >= 700: read 6 extended bytes
9. If param_6 == 0: skip optional blocks conditionally

## Special Values

- `0x26de`, `0x2260`, `0x2261` - Reserved club codes (trigger different parsing paths)
- Character 'c' at offset 0x26 combined with version < 600 triggers early return
- Height < 150 or weight < 20 triggers random generation

## Minimum Record Size

- Estimated ~300 bytes minimum (names + metadata + skills)
- Maximum observed: 649 bytes (from verification tests)