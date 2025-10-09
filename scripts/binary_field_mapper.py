"""
Binary Field Mapping - Systematic Reverse Engineering
Compare multiple player records to find exact field positions
"""
import struct
from pathlib import Path
from collections import defaultdict

def decode_xor61_section(data: bytes, offset: int) -> bytes:
    """Decode XOR-0x61 section"""
    length = struct.unpack_from("<H", data, offset)[0]
    encoded = data[offset + 2 : offset + 2 + length]
    return bytes(b ^ 0x61 for b in encoded)

# Load player file
data = Path('DBDAT/JUG98030.FDI').read_bytes()

print("="*80)
print("BINARY FIELD MAPPING - PLAYER RECORDS")
print("="*80)

# Find first large section with players
section_offset = 0x378383  # Known section with players
decoded = decode_xor61_section(data, section_offset)

# Find separator positions
separator = bytes([0xdd, 0x63, 0x60])
separators = []
pos = 0
while pos < len(decoded):
    pos = decoded.find(separator, pos)
    if pos == -1:
        break
    separators.append(pos)
    pos += 3

print(f"\nFound {len(separators)} player records in section @ 0x{section_offset:08x}")

# Analyze first 20 player records in detail
print("\n" + "="*80)
print("DETAILED HEX DUMP ANALYSIS - First 20 Players")
print("="*80)

for i in range(min(20, len(separators))):
    sep_pos = separators[i]
    next_sep = separators[i+1] if i+1 < len(separators) else min(sep_pos + 100, len(decoded))
    record = decoded[sep_pos:next_sep]
    
    print(f"\n{'='*80}")
    print(f"Player {i+1} @ offset {sep_pos} ({len(record)} bytes)")
    print(f"{'='*80}")
    
    # Hex dump with byte positions
    for line_offset in range(0, min(80, len(record)), 16):
        chunk = record[line_offset:line_offset+16]
        hex_bytes = ' '.join(f'{b:02x}' for b in chunk)
        ascii_repr = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        print(f"  +{line_offset:3d}: {hex_bytes:<48} | {ascii_repr}")
    
    # Parse specific fields
    print(f"\n  Field Analysis:")
    print(f"  ---------------")
    
    # Bytes 0-2: Separator
    print(f"  +0-2   Separator: {record[0:3].hex()} = {list(record[0:3])}")
    
    # Bytes 3-4: Potential team_id (16-bit LE)
    if len(record) > 4:
        val = struct.unpack_from("<H", record, 3)[0]
        print(f"  +3-4   16-bit LE: {val:5d} (0x{val:04x})  {'<-- Team ID?' if 3000 < val < 5000 else ''}")
    
    # Byte 5: Potential squad number
    if len(record) > 5:
        print(f"  +5     Byte:      {record[5]:3d} (0x{record[5]:02x})  <-- Squad #?")
    
    # Bytes 6-15: Unknown metadata
    if len(record) > 15:
        print(f"  +6-15  Metadata:  {record[6:16].hex()}")
    
    # Find name (capital letter start)
    name_start = None
    for j in range(len(record)):
        if 65 <= record[j] <= 90 and j+1 < len(record) and 97 <= record[j+1] <= 122:
            name_start = j
            break
    
    if name_start:
        # Extract name
        name_end = name_start
        while name_end < len(record) and (
            (65 <= record[name_end] <= 90) or 
            (97 <= record[name_end] <= 122) or 
            record[name_end] == 32 or 
            record[name_end] > 127
        ):
            name_end += 1
        
        name = record[name_start:name_end].decode('latin1', errors='replace').strip()
        print(f"  +{name_start:3d}   NAME: '{name}'")
        
        # After name - look for attributes (0-100 range)
        attrs = []
        for k in range(name_end, min(name_end + 40, len(record))):
            if 0 <= record[k] <= 100 and record[k] != 96:
                attrs.append((k, record[k]))
        
        if attrs:
            print(f"  +{attrs[0][0]:3d}+  ATTRIBUTES: {[v for _, v in attrs[:10]]}")
    
    # Summary of this record
    print(f"\n  Record Structure Hypothesis:")
    print(f"  - Separator at +0-2")
    print(f"  - Unknown fields +3-{name_start-1 if name_start else '?'}")
    if name_start:
        print(f"  - Name at +{name_start}")
        if attrs:
            print(f"  - Attributes start at +{attrs[0][0]}")

# Statistical analysis across all records
print("\n" + "="*80)
print("STATISTICAL FIELD ANALYSIS - All Records")
print("="*80)

# Collect statistics on byte positions
byte_stats = defaultdict(lambda: defaultdict(int))
for i in range(min(50, len(separators))):
    sep_pos = separators[i]
    next_sep = separators[i+1] if i+1 < len(separators) else min(sep_pos + 100, len(decoded))
    record = decoded[sep_pos:next_sep]
    
    # For each byte position, count value occurrences
    for pos in range(min(60, len(record))):
        byte_stats[pos][record[pos]] += 1

# Analyze which positions have consistent patterns
print("\nByte Position Analysis (first 30 bytes):")
print("Position | Unique Vals | Most Common | Range     | Interpretation")
print("---------+-------------+-------------+-----------+------------------")

for pos in range(30):
    if pos not in byte_stats:
        continue
    
    values = byte_stats[pos]
    unique_count = len(values)
    most_common = max(values.items(), key=lambda x: x[1])
    value_range = (min(values.keys()), max(values.keys()))
    
    interpretation = ""
    if pos < 3:
        interpretation = "Separator"
    elif unique_count == 1:
        interpretation = "Constant"
    elif unique_count < 5 and value_range[1] < 20:
        interpretation = "Enum/Flag?"
    elif value_range[0] >= 0 and value_range[1] <= 100 and unique_count > 10:
        interpretation = "Attribute?"
    elif value_range[0] > 1000:
        interpretation = "ID/Offset?"
    
    print(f"  +{pos:2d}    | {unique_count:11d} | {most_common[0]:3d} ({most_common[1]:2d}x) | {value_range[0]:3d}-{value_range[1]:5d} | {interpretation}")

print("\n" + "="*80)
print("RECOMMENDATIONS")
print("="*80)
print("""
Next steps for precise field mapping:

1. TEAM_ID Field (bytes 3-4):
   - Appears to be 16-bit little-endian
   - Extract from 100+ players and compare with team records
   - Validate by finding matching team names

2. SQUAD NUMBER (byte 5):
   - Single byte, likely 0-99 range
   - Verify by checking if values make sense (jersey numbers)

3. NAME Position:
   - Variable position (appears after metadata)
   - First capital letter followed by lowercase
   - Length varies

4. ATTRIBUTES:
   - Start after name
   - 10 consecutive bytes in 0-100 range
   - Skip 96 (0x60) as padding

5. UNKNOWN Fields (bytes 6-15):
   - Need to identify: nationality, position, age, height, weight
   - Compare known players to find patterns

Recommendation: Extract hex dumps for 5-10 KNOWN players (where we know
their team, position, nationality from the game) and compare byte-by-byte
to deduce field meanings.
""")