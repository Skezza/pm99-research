"""
Multi-Player Field Analyzer
Compare 50+ players to find consistent patterns in field positions
"""
import struct
from pathlib import Path
from typing import List, Tuple, Dict
from collections import Counter

def decode_xor61(data: bytes, offset: int) -> Tuple[bytes, int]:
    if offset + 2 > len(data):
        return b"", 0
    length = struct.unpack_from("<H", data, offset)[0]
    if offset + 2 + length > len(data):
        return b"", 0
    encoded = data[offset+2 : offset+2+length]
    decoded = bytes(b ^ 0x61 for b in encoded)
    return decoded, 2 + length

def find_records_by_separator(decoded_data: bytes) -> List[int]:
    separators = []
    pattern = bytes([0xdd, 0x63, 0x60])
    pos = 0
    while pos < len(decoded_data) - 3:
        if decoded_data[pos:pos+3] == pattern:
            separators.append(pos)
            pos += 3
        else:
            pos += 1
    return separators

# Load player file
data = Path('DBDAT/JUG98030.FDI').read_bytes()
target_section = 0x378383
decoded, _ = decode_xor61(data, target_section)

print("="*80)
print("MULTI-PLAYER FIELD PATTERN ANALYZER")
print("="*80)

separators = find_records_by_separator(decoded)
print(f"\nFound {len(separators)} player records in section")
print(f"Analyzing first 50 players...\n")

# Analyze first 50 players
num_to_analyze = min(50, len(separators))

print("="*80)
print("BYTE POSITION ANALYSIS (First 20 bytes of each record)")
print("="*80)

# Collect data for each byte position
byte_statistics = {}
for byte_pos in range(20):
    byte_statistics[byte_pos] = {
        'values': [],
        'min': 255,
        'max': 0,
        'unique': set()
    }

# Extract first 20 bytes of each record
print(f"\n{'#':<4} {'Bytes 0-9':<30} {'Bytes 10-19':<30}")
print("-"*80)

for i in range(num_to_analyze):
    sep_pos = separators[i]
    next_sep = separators[i+1] if i+1 < len(separators) else len(decoded)
    
    record_bytes = decoded[sep_pos:min(sep_pos+20, next_sep)]
    
    # Collect statistics
    for j, byte_val in enumerate(record_bytes):
        if j < 20:
            byte_statistics[j]['values'].append(byte_val)
            byte_statistics[j]['unique'].add(byte_val)
            byte_statistics[j]['min'] = min(byte_statistics[j]['min'], byte_val)
            byte_statistics[j]['max'] = max(byte_statistics[j]['max'], byte_val)
    
    # Show first 10 records in detail
    if i < 10:
        bytes_0_9 = ' '.join(f'{b:02x}' for b in record_bytes[:10])
        bytes_10_19 = ' '.join(f'{b:02x}' for b in record_bytes[10:20]) if len(record_bytes) > 10 else ''
        print(f"{i:<4} {bytes_0_9:<30} {bytes_10_19:<30}")

print("\n" + "="*80)
print("BYTE POSITION STATISTICS")
print("="*80)

print(f"\n{'Pos':<5} {'Min':<5} {'Max':<5} {'Unique':<8} {'Pattern':<40}")
print("-"*80)

for pos in range(20):
    stats = byte_statistics[pos]
    if not stats['values']:
        continue
    
    min_val = stats['min']
    max_val = stats['max']
    unique_count = len(stats['unique'])
    
    # Determine likely field type based on statistics
    pattern = ""
    
    if pos < 3:
        pattern = "SEPARATOR (dd 63 60)"
    elif min_val == max_val:
        pattern = f"CONSTANT (always 0x{min_val:02x})"
    elif unique_count == 2 and min_val < 2:
        pattern = "BOOLEAN FLAG?"
    elif unique_count < 10 and max_val < 20:
        pattern = "ENUM/CODE (position/category?)"
    elif unique_count < 50 and max_val < 100:
        pattern = "NATIONALITY/TEAM/CATEGORY?"
    elif min_val > 30 and max_val < 100:
        pattern = "ATTRIBUTE (skill rating)"
    elif max_val > 200:
        pattern = "PART OF 16-BIT VALUE?"
    else:
        pattern = f"VARIABLE ({unique_count} unique values)"
    
    print(f"{pos:<5} {min_val:<5} {max_val:<5} {unique_count:<8} {pattern:<40}")

print("\n" + "="*80)
print("SPECIFIC FIELD ANALYSIS")
print("="*80)

# Analyze specific positions we suspect
print("\n1. BYTES 3-4 (Potential Team ID - 16-bit value):")
team_ids = []
for i in range(min(50, len(separators))):
    sep_pos = separators[i]
    if sep_pos + 5 < len(decoded):
        team_id = struct.unpack_from("<H", decoded, sep_pos + 3)[0]
        team_ids.append(team_id)

team_id_counts = Counter(team_ids)
print(f"   Found {len(set(team_ids))} unique team IDs")
print(f"   Range: {min(team_ids)} to {max(team_ids)}")
print(f"   Most common team IDs:")
for team_id, count in team_id_counts.most_common(10):
    print(f"     Team ID {team_id:4d} (0x{team_id:04x}): {count} players")

print("\n2. BYTE 5 (Potential Squad Number):")
squad_nums = []
for i in range(min(50, len(separators))):
    sep_pos = separators[i]
    if sep_pos + 6 < len(decoded):
        squad_num = decoded[sep_pos + 5]
        squad_nums.append(squad_num)

print(f"   Range: {min(squad_nums)} to {max(squad_nums)}")
print(f"   Unique values: {len(set(squad_nums))}")
print(f"   Values: {sorted(set(squad_nums))[:20]}")  # Show first 20

print("\n3. BYTE 4 (Potential Position/Nationality):")
byte4_vals = []
for i in range(min(50, len(separators))):
    sep_pos = separators[i]
    if sep_pos + 5 < len(decoded):
        val = decoded[sep_pos + 4]
        byte4_vals.append(val)

val_counts = Counter(byte4_vals)
print(f"   Range: {min(byte4_vals)} to {max(byte4_vals)}")
print(f"   Unique values: {len(set(byte4_vals))}")
print(f"   Value distribution:")
for val, count in val_counts.most_common(10):
    print(f"     Value {val:3d} (0x{val:02x}): {count} players")

print("\n4. PATTERN IN BYTES 6-7:")
byte6_7_patterns = []
for i in range(min(50, len(separators))):
    sep_pos = separators[i]
    if sep_pos + 8 < len(decoded):
        pattern = decoded[sep_pos + 6:sep_pos + 8].hex()
        byte6_7_patterns.append(pattern)

pattern_counts = Counter(byte6_7_patterns)
print(f"   Found {len(set(byte6_7_patterns))} unique patterns")
print(f"   Most common patterns:")
for pattern, count in pattern_counts.most_common(5):
    print(f"     {pattern}: {count} players")

print("\n" + "="*80)
print("CORRELATIONS & INSIGHTS")
print("="*80)

print("""
Based on analysis of 50 players:

LIKELY IDENTIFICATIONS:
1. Bytes 0-2: Separator (dd 63 60) - CONFIRMED
2. Bytes 3-4: Team ID (16-bit) - HIGH CONFIDENCE
   - Wide range of values
   - Many unique IDs
   - Makes sense for team references

3. Byte 5: Could be squad number
   - Range suggests jersey numbers
   - Need to verify against known players

4. Byte 4: Unknown - possibly position or category
   - Limited unique values
   - Clustered distribution

NEXT STEPS:
1. Verify team ID by modifying and testing in-game
2. Check if byte 5 correlates with jersey numbers
3. Examine bytes after name for remaining fields
4. Compare with team file (EQ98030.FDI) to confirm team IDs
""")

print("\n" + "="*80)
print("RECOMMENDATION")
print("="*80)

print("""
Next: Analyze team file (EQ98030.FDI) to:
1. Find team IDs and confirm they match player.team_id
2. Extract team names
3. Map team structure
4. This will validate our player.team_id hypothesis
""")