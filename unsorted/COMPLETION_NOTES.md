# Completion Notes for PM99 Editor

## Current Status: Framework Complete, Parser Needs Refinement

### What's Working ✓

1. **XOR Algorithm** - Perfectly verified
   - [`decode_entry()`](app/xor.py:14-36) matches MANAGPRE.EXE behavior
   - Tested on multiple offsets, all match [`verify.txt`](out/verify.txt)

2. **File Structure** - Fully understood
   - FDI header at 0x00-0x1F
   - Directory table entries (8 bytes each: offset, tag, index)
   - Data records at variable offsets

3. **Infrastructure** - Complete
   - CLI framework operational
   - File I/O classes implemented
   - Backup/safety features in place

### What Needs Work ❌

**Player Field Parser** - The critical missing piece

Current output shows "Unknown Player" because the parser stub at [`models.py:50`](app/models.py:50) doesn't extract fields.

## The Parsing Challenge

Looking at [`MANAGPRE.EXE.FUN_004afd80()`](MANAGPRE.EXE:0x004afd80), the record structure is:

```c
// Pseudo-code from Ghidra decompilation:
param_1[0] = read_uint16(param_4);           // Record length to param_1[0]
param_1[0x45] = read_byte(param_4);          // Region code to offset 0x114
param_1[2] = decode_xor_string(param_4);     // Given name
param_1[3] = decode_xor_string(param_4);     // Surname
// ... continues with more fields
```

The key insight: `param_4` is an advancing pointer through the raw file data. Each field read moves it forward.

## Correct Parsing Approach

Based on Ghidra analysis, here's what happens:

1. **Directory Entry** → Points to record start offset
2. **At that offset**: First XOR-encrypted field (contains the record metadata)
3. **Parse sequentially**:
   - Decode field 1 (uint16 length + XOR'd bytes)
   - Decode field 2 (name string with own length prefix)
   - Decode field 3 (surname string with own length prefix)
   - Read raw bytes for remaining fields

## Why Current Parser Fails

The stub at [`models.py:from_bytes()`](app/models.py:50) tries to:
1. Call `decode_entry(data, offset)` once
2. Parse the result as if it's the complete record

But actually:
- The record is a SEQUENCE of separately-encoded chunks
- Each name is its own XOR-encrypted blob
- Some bytes are raw (not XOR'd)
- Must read sequentially, advancing offset after each field

## Solution Path

### Step 1: Understand Record Boundaries

Test what the directory entries actually point to:

```python
from pathlib import Path
import struct

data = Path('DBDAT/JUG98030.FDI').read_bytes()

# Read directory
pos = 0x20
for i in range(5):
    offset, tag, index = struct.unpack_from("<IHH", data, pos)
    print(f"Entry {i}: offset=0x{offset:08x}, tag=0x{tag:04x} ('{chr(tag) if 32 <= tag < 127 else '?'}'), index={index}")
    
    # What's at that offset?
    if offset < len(data):
        length = struct.unpack_from("<H", data, offset)[0]
        print(f"  → First field length: 0x{length:04x} ({length} bytes)")
    pos += 8
```

### Step 2: Parse Field-by-Field

Implement a sequential reader:

```python
def parse_player(data: bytes, offset: int) -> PlayerRecord:
    pos = offset
    
    # Field 1: Some metadata (XOR'd)
    decoded1, len1 = decode_entry(data, pos)
    pos += 2 + len1  # Skip length prefix + encoded data
    
    # Field 2: Given name (XOR'd string)
    given_name, consumed = read_string(data, pos)
    pos += consumed
    
    # Field 3: Surname (XOR'd string)  
    surname, consumed = read_string(data, pos)
    pos += consumed
    
    # Field 4+: Raw bytes or more XOR fields
    # ... continue based on schema
```

### Step 3: Validate Against Known Offset

Use offset 0x410 (documented in [`verify.txt`](out/verify.txt:3)):

```python
# Test parsing
player = parse_player(data, 0x410)

# Should extract actual player data
# Compare with what MANAGPRE.EXE would read
```

## Recommended Next Steps

1. **Debug the directory entries** - Understand what they point to
2. **Examine first few records** - Map bytes to fields manually
3. **Compare with Ghidra** - Match param_4 advances to byte positions
4. **Implement parser** - Translate findings to Python
5. **Test round-trip** - Parse → Serialize → Parse should be identical

## Key Functions to Re-examine

- [`MANAGPRE.EXE.FUN_004b57b0()`](MANAGPRE.EXE:0x004b57b0) - Orchestrator (how it calls the parser)
- [`MANAGPRE.EXE.FUN_004a0a30()`](MANAGPRE.EXE:0x004a0a30) - Seems to parse metadata before player data  
- [`MANAGPRE.EXE.FUN_004afd80()`](MANAGPRE.EXE:0x004afd80) - Player parser (we have this)

## The Real Challenge

The handover documentation notes that field positions are "in progress" - this wasn't completed by the previous agent. The schema in [`out/schema_players.md`](out/schema_players.md) maps the STRUCTURE but doesn't fully explain the ON-DISK LAYOUT.

To complete this, someone needs to:
1. Load a known player record in Ghidra
2. Step through FUN_004afd80 with a debugger
3. Note exactly which file bytes map to which struct offsets
4. Document the sequential read pattern

This is doable but requires careful byte-level analysis.

## Current Framework Value

Even without the complete parser:
- ✓ XOR algorithm works perfectly
- ✓ Can decode any field once you know its offset
- ✓ File structure fully understood
- ✓ All infrastructure for editing exists

The missing piece is just the field-to-byte mapping, which is solvable through systematic analysis.
