"""
Phase 2: Position Field Discovery
==================================

Strategy:
1. Find known players by name (goalkeepers vs defenders vs midfielders vs forwards)
2. Extract bytes 6-15 from each player record
3. Compare patterns between different positions
4. Identify which byte(s) consistently differ by position

Expected: Position field is likely 1 byte in 0-10 range (GK=0?, DEF, MID, FWD)
"""

import struct
from pathlib import Path
from collections import defaultdict, Counter

def decode_xor61_section(data: bytes, offset: int) -> bytes:
    """Decode XOR-0x61 section"""
    length = struct.unpack_from("<H", data, offset)[0]
    encoded = data[offset + 2 : offset + 2 + length]
    return bytes(b ^ 0x61 for b in encoded)

# Known player positions from Premier Manager 99
# Format: (player_name_fragment, expected_position)
KNOWN_GOALKEEPERS = [
    "Schmeichel", "Seaman", "Barthez", "Kahn", "Buffon", 
    "Casillas", "Van der Sar", "Lehmann"
]

KNOWN_DEFENDERS = [
    "Maldini", "Nesta", "Cannavaro", "Desailly", "Ferdinand",
    "Campbell", "Stam", "Puyol", "Thuram"
]

KNOWN_MIDFIELDERS = [
    "Zidane", "Figo", "Beckham", "Giggs", "Scholes",
    "Pirlo", "Seedorf", "Nedved", "Vieira"
]

KNOWN_FORWARDS = [
    "Ronaldo", "Raul", "Henry", "Shearer", "Batistuta",
    "Vieri", "Inzaghi", "Shevchenko", "Owen"
]

# Load player file
data = Path('DBDAT/JUG98030.FDI').read_bytes()

print("="*80)
print("POSITION FIELD DISCOVERY")
print("="*80)

# Find the main player section
section_offset = 0x378383
decoded = decode_xor61_section(data, section_offset)

# Find all player records
separator = bytes([0xdd, 0x63, 0x60])
player_records = []

pos = 0
while pos < len(decoded):
    pos = decoded.find(separator, pos)
    if pos == -1:
        break
    
    # Extract record
    next_pos = decoded.find(separator, pos + 3)
    if next_pos == -1:
        next_pos = min(pos + 100, len(decoded))
    
    record = decoded[pos:next_pos]
    
    # Extract player name
    name_start = None
    for i in range(8, min(60, len(record))):
        if 65 <= record[i] <= 90:  # Capital letter
            name_start = i
            break
    
    if name_start:
        name_end = name_start
        while name_end < len(record) and (
            (65 <= record[name_end] <= 90) or 
            (97 <= record[name_end] <= 122) or 
            record[name_end] == 32 or
            record[name_end] > 127
        ):
            name_end += 1
        
        name = record[name_start:name_end].decode('latin1', errors='replace').strip()
        
        player_records.append({
            'name': name,
            'record': record,
            'offset': pos
        })
    
    pos += 3

print(f"Found {len(player_records)} player records with names\n")

# Search for known players
def find_players_by_keywords(keywords, player_records):
    """Find players matching any of the keywords"""
    matches = []
    for player in player_records:
        name_upper = player['name'].upper()
        for keyword in keywords:
            if keyword.upper() in name_upper:
                matches.append(player)
                break
    return matches

goalkeepers = find_players_by_keywords(KNOWN_GOALKEEPERS, player_records)
defenders = find_players_by_keywords(KNOWN_DEFENDERS, player_records)
midfielders = find_players_by_keywords(KNOWN_MIDFIELDERS, player_records)
forwards = find_players_by_keywords(KNOWN_FORWARDS, player_records)

print(f"Known Players Found:")
print(f"  Goalkeepers:  {len(goalkeepers)}")
print(f"  Defenders:    {len(defenders)}")
print(f"  Midfielders:  {len(midfielders)}")
print(f"  Forwards:     {len(forwards)}")

# Analyze metadata bytes (6-15) for each position group
def analyze_position_bytes(players, position_name):
    """Analyze bytes 6-15 for a group of players"""
    print(f"\n{'='*80}")
    print(f"{position_name.upper()} - Metadata Analysis (bytes 6-15)")
    print(f"{'='*80}")
    
    byte_values = defaultdict(list)
    
    for player in players:
        record = player['record']
        print(f"\n{player['name'][:40]:<40s}")
        
        if len(record) >= 16:
            metadata = record[6:16]
            print(f"  Bytes 6-15: {metadata.hex()}")
            print(f"  Decimal:    {list(metadata)}")
            
            # Collect values per byte position
            for i, byte_val in enumerate(metadata):
                byte_values[i+6].append(byte_val)
    
    # Statistical summary
    if byte_values:
        print(f"\n{'-'*80}")
        print(f"Statistical Summary for {position_name}:")
        print(f"{'-'*80}")
        print(f"Byte Pos | Values | Most Common | Range")
        print(f"---------+--------+-------------+-------")
        
        for pos in sorted(byte_values.keys()):
            vals = byte_values[pos]
            unique = len(set(vals))
            from collections import Counter
            most_common = Counter(vals).most_common(1)[0] if vals else (0, 0)
            value_range = (min(vals), max(vals)) if vals else (0, 0)
            
            print(f"   +{pos:2d}   | {unique:6d} | {most_common[0]:3d} ({most_common[1]}x) | {value_range[0]:3d}-{value_range[1]:3d}")
    
    return byte_values

# Analyze each position group
gk_bytes = analyze_position_bytes(goalkeepers[:10], "Goalkeepers") if goalkeepers else {}
def_bytes = analyze_position_bytes(defenders[:10], "Defenders") if defenders else {}
mid_bytes = analyze_position_bytes(midfielders[:10], "Midfielders") if midfielders else {}
fwd_bytes = analyze_position_bytes(forwards[:10], "Forwards") if forwards else {}

# Cross-position comparison
print(f"\n{'='*80}")
print(f"CROSS-POSITION COMPARISON")
print(f"{'='*80}")

if all([gk_bytes, def_bytes, mid_bytes, fwd_bytes]):
    print(f"\nLooking for bytes that differ between positions...")
    print(f"\nByte | GK Mode | DEF Mode | MID Mode | FWD Mode | Candidate?")
    print(f"-----+---------+----------+----------+----------+-----------")
    
    from collections import Counter
    
    for pos in range(6, 16):
        if pos in gk_bytes and pos in def_bytes and pos in mid_bytes and pos in fwd_bytes:
            gk_mode = Counter(gk_bytes[pos]).most_common(1)[0][0] if gk_bytes[pos] else 0
            def_mode = Counter(def_bytes[pos]).most_common(1)[0][0] if def_bytes[pos] else 0
            mid_mode = Counter(mid_bytes[pos]).most_common(1)[0][0] if mid_bytes[pos] else 0
            fwd_mode = Counter(fwd_bytes[pos]).most_common(1)[0][0] if fwd_bytes[pos] else 0
            
            # Check if values differ and are in reasonable range (0-20)
            all_modes = [gk_mode, def_mode, mid_mode, fwd_mode]
            is_candidate = (
                len(set(all_modes)) > 1 and  # Values differ
                all(0 <= m <= 20 for m in all_modes)  # Reasonable range
            )
            
            marker = "⭐ CANDIDATE!" if is_candidate else ""
            
            print(f" +{pos:2d} |   {gk_mode:3d}   |   {def_mode:3d}    |   {mid_mode:3d}    |   {fwd_mode:3d}   | {marker}")

# Alternative: Look for any byte in 0-10 range
print(f"\n{'='*80}")
print(f"ALTERNATIVE: Bytes in 0-10 range across all records")
print(f"{'='*80}")

byte_distributions = defaultdict(Counter)
for player in player_records[:200]:  # Sample 200 players
    record = player['record']
    if len(record) >= 16:
        for i in range(6, 16):
            if 0 <= record[i] <= 10:
                byte_distributions[i][record[i]] += 1

if byte_distributions:
    print(f"\nBytes with values in 0-10 range:")
    for pos in sorted(byte_distributions.keys()):
        dist = byte_distributions[pos]
        total = sum(dist.values())
        print(f"\n  Byte +{pos}: {total} occurrences")
        for val, count in sorted(dist.items()):
            percentage = (count / total) * 100
            print(f"    Value {val}: {count:3d} times ({percentage:5.1f}%)")

print(f"\n{'='*80}")
print(f"CONCLUSION")
print(f"{'='*80}")
print(f"""
Based on the analysis:

1. Look for bytes where:
   - Goalkeepers have one consistent value
   - Defenders have a different value
   - Midfielders have a different value  
   - Forwards have a different value
   - All values are in 0-10 range

2. The position field is likely:
   - A single byte
   - Located in bytes 6-15 region
   - Values: GK=0 or 1?, DEF=2-4?, MID=5-7?, FWD=8-10?

3. If no clear pattern, the position might be:
   - Encoded differently (multiple bits/nibbles)
   - In a different location
   - Or we need more known player samples

Next step: Use the candidate byte(s) identified above to validate
by checking more players and their known positions.
""")