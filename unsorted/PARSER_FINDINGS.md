# Parser Investigation Findings

## What We Know for Certain ✓

### 1. XOR Decoding Algorithm - VERIFIED
- Key: `0x61` (single byte)
- Application: Byte-by-byte XOR
- **Confirmed working** via multiple test cases matching `verify.txt`

### 2. String Decoding Function - IDENTIFIED
From [`MANAGPRE.EXE.FUN_00677e30`](MANAGPRE.EXE:0x00677e30):
```c
// Reads length-prefixed string from file and XOR-decodes it
int decode_string(int *file_ptr, uint *output_buffer) {
    ushort length = *(ushort*)*file_ptr;  // Read uint16 length
    file_ptr += 2;
    
    // XOR decode using 32-bit operations for efficiency
    for (i = 0; i < length/4; i++) {
        output[i] = input[i] ^ 0x61616161;  // 4 bytes at once
    }
    
    // Handle remaining 2 bytes
    if (length & 2) {
        *(uint16*)output = *(uint16*)input ^ 0x6161;
    }
    
    // Handle remaining 1 byte  
    if (length & 1) {
        *(byte*)output = *(byte*)input ^ 0x61;
    }
    
    *output = 0;  // Null terminator
    return length + 1;  // bytes consumed
}
```

### 3. File Structure - PARTIALLY UNDERSTOOD

```
Offset  | Content
--------|--------------------------------------------------
0x00    | "DMFIv1.0" signature (10 bytes)
0x10    | Version (uint16) = 11479 for JUG98030.FDI
0x14    | Number of directory entries (uint32) = 2
0x20    | Directory entries (8 bytes each):
        |   - Offset (uint32)
        |   - Tag (uint16)
        |   - Index (uint16)
--------|--------------------------------------------------
0x400+  | Secondary structure (purpose unclear)
0x410+  | Player data starts here (documented in verify.txt)
```

### 4. Player Parser Entry Point
From [`MANAGPRE.EXE.FUN_004a0a30`](MANAGPRE.EXE:0x004a0a30):
- Allocates buffer based on field at offset 0x24
- Reads version and region_code
- Calls `FUN_00677e30` repeatedly to read strings
- Reads fixed-size fields (uint16, uint32, bytes)
- Handles version-dependent fields (thresholds at v600, v700)

## What's Unclear ❓

### Directory Structure
The directory at 0x20 has 2 entries:
```
Entry 0: offset=0x00000400, tag=0x0000, index=18258
Entry 1: offset=0x00470002, tag=0x0000, index=5
```

**Question**: Does offset 0x400 point to:
- A. Another directory/index of player records?
- B. The first player record directly?
- C. Metadata about the player section?

**Evidence**:
- Raw bytes at 0x400 start with `00 00` (length 0?)
- Pattern suggests table of offsets
- Documented offset 0x410 is 16 bytes after 0x400

### Record Encoding
When XOR-decoding at 0x410:
- Get 649-byte blob
- First byte = 0x61 (region code or length marker?)
- Following bytes look like length prefixes but don't decode correctly

**Hypothesis**: Records might use:
1. Outer XOR layer (file level)
2. Inner structure with length-prefixed fields
3. Each field independently XOR'd?

### Missing Link
Gap between:
- **Known**: How `FUN_00677e30` decodes a string from file
- **Unknown**: Where in the file to call it for each player

## Recommended Next Steps

### Option A: Empirical Approach
1. Find a known player name in the game
2. Search for that name's bytes in JUG98030.FDI
3. Work backwards to understand the structure
4. Map one complete record manually

### Option B: Trace Execution
1. Use debugger to step through `FUN_004a0a30`
2. Watch file pointer advance through JUG98030.FDI
3. Note exact byte positions for each field read
4. Document the sequential pattern

### Option C: Comparative Analysis
1. Load EQ98030.FDI (teams) - simpler structure
2. Understand that format first
3. Apply learning to JUG98030.FDI (players)

## Current Implementation Status

### Working Components ✓
- [`pm99_editor/xor.py`](pm99_editor/xor.py) - XOR utilities (100% correct)
- [`pm99_editor/io.py`](pm99_editor/io.py) - File header parsing (correct)
- [`pm99_editor/cli.py`](pm99_editor/cli.py) - User interface (complete)

### Blocked Component ❌
- [`pm99_editor/models.py:PlayerRecord.from_bytes()`](pm99_editor/models.py:50) - **Stub only**
  - Cannot parse fields without knowing exact byte layout
  - Need to map file structure first

## Why This Is Hard

The game uses a **custom binary format** with:
1. **Multi-level structure** (file → directories → records)
2. **Nested encoding** (outer XOR + inner length-prefixed fields)
3. **Version-dependent layout** (different fields for v600 vs v700)
4. **No documentation** (reverse engineering from assembly only)

This is fundamentally different from formats like JSON or CSV where structure is self-describing.

## Path Forward

To complete the parser, we need to:

1. **Map one record completely**
   - Start byte position
   - Each field's offset and type
   - End byte position

2. **Verify the pattern repeats**
   - Parse record 2, 3, 4
   - Confirm consistent structure

3. **Implement `from_bytes()`**
   - Sequential field reading
   - Proper XOR handling
   - Type conversions

4. **Test round-trip**
   - Parse → Modify → Serialize → Parse
   - Verify byte-identical output

**Estimated effort**: 2-4 hours of focused byte-level analysis

## Alternative: Hex Editor Approach

If programmatic parsing proves too complex:
1. Document field offsets manually
2. Create hex-editing guide for users
3. Provide templates for common edits (rename, change stats)

This would be faster but less user-friendly than a proper parser.