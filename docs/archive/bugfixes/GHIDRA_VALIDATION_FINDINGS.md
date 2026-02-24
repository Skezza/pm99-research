# Ghidra Validation Findings for Player Name Renaming

## Function Analysis: FUN_004afd80 (Player Record Parser)

### Decompiled Code Analysis

The game's player record parser (`FUN_004afd80`) confirms our understanding of the binary format:

#### 1. **Team ID Reading** (Lines 19-22)
```c
uVar10 = *(ushort *)*param_4;
*param_4 = (int)((ushort *)*param_4 + 1);
*param_1 = (uint)uVar10;
*(short *)(param_1 + 1) = (short)*param_1;
```
✅ **CONFIRMED:** Team ID is a 16-bit unsigned integer (uint16) at bytes 0-1 (little-endian)

#### 2. **Squad Number Reading** (Lines 23-25)
```c
uVar1 = *(undefined1 *)*param_4;
*param_4 = (int)((undefined1 *)*param_4 + 1);
*(undefined1 *)(param_1 + 0x45) = uVar1;
```
✅ **CONFIRMED:** Squad number is a single byte (byte 2 in file)

#### 3. **Name Parsing** (Lines 26-30)
```c
uVar6 = FUN_00677e30(uVar6);
local_4 = local_4 + uVar6;
if (0xd < uVar6) {
    FUN_004c29b0(param_1[2],0xc);
}
```
✅ **CONFIRMED:** Variable-length name parsing using `FUN_00677e30`
- Returns length in `uVar6`
- If length > 13 (0xd), calls truncation function with max 12 chars (0xc)

---

## Function Analysis: FUN_00677e30 (String Decoder)

### CRITICAL DISCOVERY: Length-Prefixed String Decoding

```c
int __thiscall FUN_00677e30(int *param_1, uint *param_2)
{
  ushort uVar1;
  uint uVar2;
  uint uVar3;
  uint *puVar4;
  
  // Read uint16 length prefix
  uVar1 = *(ushort *)*param_1;
  puVar4 = (uint *)((ushort *)*param_1 + 1);
  *param_1 = (int)((uint)uVar1 + (int)puVar4);
  
  // Process in 4-byte chunks with 0x61616161 XOR
  for (uVar3 = (uint)(uVar1 >> 2); uVar3 != 0; uVar3 = uVar3 - 1) {
    uVar2 = *puVar4;
    puVar4 = puVar4 + 1;
    *param_2 = uVar2 ^ 0x61616161;
    param_2 = param_2 + 1;
  }
  
  // Handle remaining 2 bytes if any
  if ((uVar1 & 2) != 0) {
    uVar3 = *puVar4;
    puVar4 = (uint *)((int)puVar4 + 2);
    *(ushort *)param_2 = (ushort)uVar3 ^ 0x6161;
    param_2 = (uint *)((int)param_2 + 2);
  }
  
  // Handle remaining 1 byte if any
  if ((uVar1 & 1) != 0) {
    *(byte *)param_2 = (byte)*puVar4 ^ 0x61;
    param_2 = (uint *)((int)param_2 + 1);
  }
  
  // Null terminator
  *(undefined1 *)param_2 = 0;
  return uVar1 + 1;  // Return length + 1 (includes 2-byte prefix)
}
```

### ✅ VALIDATED: String Encoding Format

**Structure:**
```
[uint16 length] [XOR-encoded data...]
```

**Encoding:**
1. Read 2-byte little-endian length (N)
2. XOR next N bytes with 0x61 (in chunks: 4-byte, 2-byte, 1-byte)
3. Add null terminator (0x00) after decoded data
4. Total bytes consumed: 2 + N

**This matches our `xor.py` implementation perfectly!** ✅

---

## Player Record Structure - VALIDATED

Based on both functions, here's the confirmed structure:

```
Offset  Size  Field               Encoding
------  ----  -----               --------
0       2     Team ID             uint16 LE
2       1     Squad Number        byte
3       2     [Length Prefix]     uint16 LE (for given name)
5       N     Given Name          XOR 0x61, variable length
5+N     2     [Length Prefix]     uint16 LE (for surname)  
7+N     M     Surname             XOR 0x61, variable length
...     ...   [MORE DATA]         Sequential reading continues
```

### ⚠️ CRITICAL FINDING: Sequential Reading, NOT Marker-Based

The game does **NOT** use a name-end marker (0x61x4) for offset calculations!

Instead:
1. Reads given name (length-prefixed)
2. Reads surname (length-prefixed)  
3. **Continues reading sequentially** for metadata

**This means:**
- Our assumption about `name_end + 7` for position is **WRONG**
- Game reads fields in **sequential order**, not using fixed offsets
- The 0x61x4 pattern we see is likely **padding or a separator**, not a marker

---

## Sequential Field Reading Order

After team ID (2 bytes) and squad (1 byte), the game reads:

1. **Given Name** (length-prefixed string via FUN_00677e30)
2. **Surname** (length-prefixed string via FUN_00677e30)
3. **6-byte initials/codes** (with transformation: subtract 1, 0→'b')
4. **Single byte** (unknown purpose)
5. **Nationality** (1 byte)
6. **Birth Day** (1 byte)
7. **Birth Month** (1 byte)
8. **Birth Year** (2 bytes, uint16)
9. **Height** (1 byte with validation >= 150)
10. **Weight** (1 byte with validation >= 20)
11. **[Contract/Additional Data]** (conditional blocks)
12. **10 Attributes** (individual bytes)

**ALL SEQUENTIAL - no marker-based offset calculations**

---

## Impact on Name Renaming Implementation

### ❌ WRONG APPROACH (Our Current Code):
```python
# Finding marker and using offsets
name_end = find_marker(0x61, 0x61, 0x61, 0x61)
position_offset = name_end + 7
nationality_offset = name_end + 8
```

### ✅ CORRECT APPROACH (Game's Method):
```python
# Sequential parsing and rebuilding
1. Parse entire record sequentially
2. Extract all fields in order
3. When changing name:
   a. Encode new given name (length-prefix + XOR)
   b. Encode new surname (length-prefix + XOR)
   c. Rebuild entire record with ALL fields in correct order
   d. Write back to file
```

---

## Required Code Changes

### 1. Fix `PlayerRecord.from_bytes()` 
Must parse **sequentially**, not using marker offsets:

```python
@classmethod
def from_bytes(cls, data: bytes, offset: int) -> 'PlayerRecord':
    pos = 0
    
    # Team ID (bytes 0-1)
    team_id = struct.unpack_from("<H", data, pos)[0]
    pos += 2
    
    # Squad number (byte 2)
    squad_num = data[pos]
    pos += 1
    
    # Given name (length-prefixed, XOR'd)
    given_len = struct.unpack_from("<H", data, pos)[0]
    pos += 2
    given_name = cls._decode_xor_string(data[pos:pos+given_len])
    pos += given_len
    
    # Surname (length-prefixed, XOR'd)
    surname_len = struct.unpack_from("<H", data, pos)[0]
    pos += 2
    surname = cls._decode_xor_string(data[pos:pos+surname_len])
    pos += surname_len
    
    # 6-byte initials/codes
    initials = bytearray(6)
    for i in range(6):
        b = data[pos]
        pos += 1
        if b == 0:
            initials[i] = ord('b')
        else:
            initials[i] = b - 1
    
    # Continue sequentially for all other fields...
    # Position, nationality, DOB, height, weight, attributes
```

### 2. Fix `PlayerRecord.to_bytes()`
Must rebuild **entire record sequentially**:

```python
def to_bytes(self) -> bytes:
    result = bytearray()
    
    # Team ID (2 bytes)
    result.extend(struct.pack("<H", self.team_id))
    
    # Squad number (1 byte)
    result.append(self.squad_number)
    
    # Given name (length-prefixed + XOR'd)
    given_encoded = self._encode_xor_string(self.given_name)
    result.extend(struct.pack("<H", len(given_encoded)))
    result.extend(given_encoded)
    
    # Surname (length-prefixed + XOR'd)
    surname_encoded = self._encode_xor_string(self.surname)
    result.extend(struct.pack("<H", len(surname_encoded)))
    result.extend(surname_encoded)
    
    # 6-byte initials/codes (with transformation)
    for b in self.initials:
        if b == ord('b'):
            result.append(0)
        else:
            result.append((b + 1) & 0xFF)
    
    # Continue with all other fields in sequential order...
    # Position, nationality, DOB, height, weight, attributes
    
    return bytes(result)
```

### 3. Implement `set_name()` 
Simply update fields and call `to_bytes()`:

```python
def set_given_name(self, new_name: str):
    if not new_name or len(new_name) > 12:
        raise ValueError("Given name must be 1-12 characters")
    new_name.encode('latin-1')  # Validate encoding
    self.given_name = new_name
    self.name = f"{self.given_name} {self.surname}".strip()
    self.modified = True

def set_surname(self, new_name: str):
    if not new_name or len(new_name) > 12:
        raise ValueError("Surname must be 1-12 characters")
    new_name.encode('latin-1')  # Validate encoding
    self.surname = new_name
    self.name = f"{self.given_name} {self.surname}".strip()
    self.modified = True

def set_name(self, full_name: str):
    parts = full_name.strip().split(maxsplit=1)
    if len(parts) < 2:
        raise ValueError("Name must include both given name and surname")
    self.set_given_name(parts[0])
    self.set_surname(parts[1])
```

**No complex offset calculations needed!** Just rebuild the record.

---

## Risk Assessment - UPDATED

### ✅ REDUCED RISK: Name Renaming is SIMPLER Than Expected

**Previous assumption:** Complex marker-based offset calculations  
**Reality:** Simple sequential parsing and rebuilding

**Benefits:**
1. **No offset math** - just sequential field order
2. **Variable-length names** supported naturally via length prefixes
3. **No collision risk** - record size adapts automatically
4. **Existing file_writer.py** already handles variable-length records

### Remaining Risks:

1. **Parsing accuracy** - Must parse ALL fields correctly in sequence
   - **Mitigation:** Validate against known-good records
   
2. **Field order errors** - Missing or reordered fields breaks everything
   - **Mitigation:** Comprehensive unit tests with roundtrip validation
   
3. **Encoding bugs** - XOR or length-prefix errors
   - **Mitigation:** Our xor.py already matches game's implementation

---

## Validation Checklist

Before implementing name renaming:

- [x] Validate Team ID parsing (uint16)
- [x] Validate Squad number parsing (byte)
- [x] Validate string decoding (length-prefix + XOR)
- [ ] Map ALL sequential fields in player record
- [ ] Test parsing roundtrip (read → parse → rebuild → compare)
- [ ] Verify current `PlayerRecord.from_bytes()` accuracy
- [ ] Fix any discrepancies in field order
- [ ] Test with multiple known player records

---

## Recommendation - UPDATED

### ✅ PROCEED WITH IMPLEMENTATION

The validation shows name renaming is **SIMPLER** than initially thought:

**Implementation Plan:**

1. **Fix PlayerRecord parsing** to be purely sequential (1-2 days)
2. **Add name setters** (simple field updates) (1 hour)
3. **Fix to_bytes()** to rebuild sequentially (1-2 days)
4. **Test roundtrip accuracy** with known records (1 day)
5. **Add GUI controls** for name editing (1 day)
6. **Test in PM99 game** (1 day)

**Total: 5-7 days** (less risky than original estimate)

The key insight: **We don't need complex offset calculations. Just parse sequentially and rebuild.**
