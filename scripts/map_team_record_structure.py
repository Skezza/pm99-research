"""
Map Team Record Structure
Analyze records containing known teams to understand field layout
"""
import struct
from pathlib import Path

# Load and decode team file section 2
data = Path('DBDAT/EQ98030.FDI').read_bytes()
section_offset = 0x2f04
length_prefix = struct.unpack_from("<H", data, section_offset)[0]
encoded = data[section_offset + 2 : section_offset + 2 + length_prefix]
decoded = bytes(b ^ 0x61 for b in encoded)

print("="*80)
print("TEAM RECORD STRUCTURE MAPPING")
print("="*80)

# Known team positions
known_teams = [
    (1131, "Real Madrid", 15),
    (5149, "Valencia", 67),
    (35473, "Milan", 455),
    (37500, "Juventus", 481),
    (41538, "Lazio", 533),
]

record_size = 78

for abs_pos, team_name, record_num in known_teams:
    rec_start = (record_num - 1) * record_size
    offset_in_rec = abs_pos - rec_start
    
    print(f"\n{'='*80}")
    print(f"TEAM: {team_name}")
    print(f"Record {record_num} @ +{rec_start}, team name @ offset +{offset_in_rec} in record")
    print(f"{'='*80}")
    
    # Extract full record
    rec_data = decoded[rec_start:rec_start + record_size]
    
    # Show hex dump of entire record
    print("\nFull record hex dump:")
    for i in range(0, len(rec_data), 16):
        chunk = rec_data[i:i+16]
        hex_part = ' '.join(f'{b:02x}' for b in chunk)
        asc_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        print(f"  +{i:2d}: {hex_part:<48} {asc_part}")
    
    # Try to parse potential fields
    print("\nPotential field analysis:")
    
    # Try 16-bit values at various positions
    print("\n16-bit little-endian values:")
    for i in range(0, min(20, len(rec_data)), 2):
        if i + 2 <= len(rec_data):
            val = struct.unpack_from("<H", rec_data, i)[0]
            # Highlight values in interesting ranges
            marker = ""
            if 3000 < val < 4000:
                marker = " <-- Potential team ID (matches player team_id range!)"
            elif val < 256:
                marker = " <-- Small value (index/flag?)"
            print(f"  +{i:2d}: {val:5d} (0x{val:04x}){marker}")
    
    # Search for text strings
    print("\nText strings in record:")
    import re
    for match in re.finditer(rb'[\x20-\x7e]{4,}', rec_data):
        text = match.group().decode('latin1', errors='replace')
        if any(c.isalpha() for c in text):
            print(f"  +{match.start():2d}: '{text}'")

# Analyze the pattern across all records to find team name position
print("\n" + "="*80)
print("FINDING TEAM NAME FIELD POSITION")
print("="*80)

print("\nAnalyzing all 544 records for text string positions...")

# For each record, find the longest text string
name_positions = {}
for i in range(544):
    rec_start = i * record_size
    rec_data = decoded[rec_start:rec_start + record_size]
    
    # Find longest printable string
    import re
    matches = list(re.finditer(rb'[\x20-\x7e]{4,}', rec_data))
    if matches:
        # Get the longest match that looks like a name
        longest = max(matches, key=lambda m: len(m.group()))
        text = longest.group().decode('latin1', errors='replace')
        
        # Filter for actual names (has letters)
        if any(c.isalpha() for c in text) and len(text) >= 4:
            pos = longest.start()
            if pos not in name_positions:
                name_positions[pos] = 0
            name_positions[pos] += 1

print("\nMost common positions for text strings (potential team names):")
for pos, count in sorted(name_positions.items(), key=lambda x: -x[1])[:15]:
    print(f"  Position +{pos:2d}: {count:3d} records")

# Show team names at most common position
most_common_pos = max(name_positions.items(), key=lambda x: x[1])[0]
print(f"\nTeam names at position +{most_common_pos} (first 30):")
print("-"*80)

count = 0
for i in range(544):
    rec_start = i * record_size
    rec_data = decoded[rec_start:rec_start + record_size]
    
    # Extract text at the most common position
    import re
    match = re.search(rb'[\x20-\x7e]{4,}', rec_data[most_common_pos:])
    if match:
        text = match.group().decode('latin1', errors='replace')
        if any(c.isalpha() for c in text) and len(text) >= 4:
            print(f"  {i+1:3d}. '{text}'")
            count += 1
            if count >= 30:
                break

print("\n" + "="*80)
print("TEAM ID FIELD ANALYSIS")
print("="*80)

print("\nSearching for team IDs in range 3712-3807 (player.team_id range)...")
print("Checking first bytes of each record:\n")

team_ids_found = []
for i in range(min(30, 544)):
    rec_start = i * record_size
    rec_data = decoded[rec_start:rec_start + record_size]
    
    # Check positions 0-10 for 16-bit values in the player team_id range
    for pos in range(0, 11, 2):
        if pos + 2 <= len(rec_data):
            val = struct.unpack_from("<H", rec_data, pos)[0]
            if 3700 < val < 3900:
                team_ids_found.append((i+1, pos, val))
                print(f"  Record {i+1:3d}, pos +{pos}: {val} (0x{val:04x})")
                break

if not team_ids_found:
    print("  No team IDs in expected range found in first 30 records")
    print("\n  Trying broader search (any value 3000-4000)...")
    
    for i in range(min(10, 544)):
        rec_start = i * record_size
        rec_data = decoded[rec_start:rec_start + record_size]
        
        print(f"\n  Record {i+1} first 10 16-bit values:")
        for pos in range(0, 20, 2):
            if pos + 2 <= len(rec_data):
                val = struct.unpack_from("<H", rec_data, pos)[0]
                marker = " <--" if 3000 < val < 4000 else ""
                print(f"    +{pos:2d}: {val:5d} (0x{val:04x}){marker}")

print("\n" + "="*80)
print("SUMMARY")
print("="*80)
print(f"""
Record size: {record_size} bytes
Total records: {len(decoded) // record_size}
Known teams found: {len(known_teams)}

Key findings:
- Team names appear at various offsets within records
- Most common text position: +{most_common_pos}
- Team ID field: Still investigating

Next: Validate team ID hypothesis by comparing with player data
""")