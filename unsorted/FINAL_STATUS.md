
# Premier Manager 99 Reverse Engineering - Final Status Report

## Completed Work

### 1. XOR Decoder Verification ✓

- Confirmed [`MANAGPRE.EXE.FUN_00677e30()`](MANAGPRE.EXE:0x00677e30) implements XOR decode with key `0x61`
- Algorithm: Read uint16 length, XOR each byte, append null terminator
- Verified implementation in [`out/decode_one.py`](out/decode_one.py:23-42) produces identical output
- Tested across multiple offsets (FDI @ 0x410, TEXTOS @ 0x0, various sizes)
- All tests match [`out/verify.txt`](out/verify.txt:1-53) expectations

### 2. FDI Header Structure ✓

- Signature: `DMFIv1.0` at offset 0x00
- Record count: uint32 at 0x10 (11,479 for JUG98030.FDI)
- Version: uint32 at 0x14 (value 2)
- Max offset: uint32 at 0x18
- Directory size: uint32 at 0x1C (0x5300 = 21,248 bytes)
- Documented in [`out/struct_notes.md`](out/struct_notes.md:1-65)

### 3. Player Record Schema Mapping ✓

- Decompiled [`MANAGPRE.EXE.FUN_004afd80()`](MANAGPRE.EXE:0x004afd80) - primary player parser
- Identified fields:
  - Two XOR-encrypted name strings (given name, surname)
  - Birth data (day, month, year with validation)
  - Physical attributes (height, weight)
  - 10 skill attributes (written to duplicate offsets)
  - 6 extended fields (version >= 700)
  - Regional/positional metadata
- Complete schema documented in [`out/schema_players.md`](out/schema_players.md:1-90)

### 4. Python Editor Framework ✓

Created modular Python package [`app/`](app/):

- [`xor.py`](app/xor.py:1-102) - XOR encode/decode utilities
- [`models.py`](app/models.py:1-243
