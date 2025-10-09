"""
Extract Team Names from Team File
Properly decode XOR and find all team names with their positions
"""
import struct
from pathlib import Path
import re

# Load team file
data = Path('DBDAT/EQ98030.FDI').read_bytes()

print("="*80)
print("TEAM NAME EXTRACTION - SECTION 2 ANALYSIS")
print("="*80)

# Decode Section 2 (main team data)
section_offset = 0x2f04
section_length = 42496

# Read the length prefix and decode
length_prefix = struct.unpack_from("<H", data, section_offset)[0]
print(f"\nSection 2 @ 0x{section_offset:08x}")
print(f"Length prefix: {length_prefix} bytes")
print(f"Expected length: {section_length} bytes")

# XOR decode the section
encoded = data[section_offset + 2 : section_offset + 2 + length_prefix]
decoded = bytes(b ^ 0x61 for b in encoded)

print(f"Decoded: {len(decoded)} bytes")

# Show properly decoded hex dump
print("\nFirst 256 bytes of DECODED data:")
print("-"*80)
for i in range(0, min(256, len(decoded)), 16):
    chunk = decoded[i:i+16]
    hex_part = ' '.join(f'{b:02x}' for b in chunk)
    asc_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
    print(f"{i:04x}: {hex_part:<48} {asc_part}")

# Search for all text strings (potential team names)
print("\n" + "="*80)
print("SEARCHING FOR TEAM NAMES")
print("="*80)

# Find all sequences of printable ASCII (likely team names)
pattern = rb'[\x20-\x7e]{5,}'  # 5+ printable chars
matches = list(re.finditer(pattern, decoded))

print(f"\nFound {len(matches)} text strings")
print("\nAll text strings (100+ chars shown):")
print("-"*80)

team_names = []
for i, match in enumerate(matches):
    text = match.group().decode('latin1', errors='replace')
    pos = match.start()
    
    # Filter for likely team names (contains letters, reasonable length)
    if any(c.isalpha() for c in text) and 4 <= len(text) <= 50:
        team_names.append((pos, text))
        if i < 100:
            print(f"{i+1:3d}. @ +{pos:6d}: '{text}'")

print(f"\nTotal team name candidates: {len(team_names)}")

# Analyze spacing between team names
if len(team_names) > 10:
    print("\n" + "="*80)
    print("TEAM NAME SPACING ANALYSIS")
    print("="*80)
    
    spacings = []
    for i in range(len(team_names) - 1):
        spacing = team_names[i+1][0] - team_names[i][0]
        spacings.append(spacing)
    
    print(f"\nFirst 20 spacings between consecutive team names:")
    for i, spacing in enumerate(spacings[:20]):
        print(f"  {i+1:2d}. {spacings[i]:4d} bytes  ('{team_names[i][1]}' -> '{team_names[i+1][1]}')")
    
    # Check for regular patterns
    avg_spacing = sum(spacings) / len(spacings)
    print(f"\nAverage spacing: {avg_spacing:.1f} bytes")
    
    # Look for common spacing values
    from collections import Counter
    spacing_counts = Counter(spacings)
    print(f"\nMost common spacings:")
    for spacing, count in spacing_counts.most_common(10):
        print(f"  {spacing:4d} bytes: {count:3d} times")

# Try 78-byte fixed records
print("\n" + "="*80)
print("78-BYTE FIXED RECORD ANALYSIS")
print("="*80)

record_size = 78
num_records = len(decoded) // record_size

print(f"\nAssuming {record_size}-byte records: {num_records} records")
print(f"Analyzing first 20 records for team names:\n")

for i in range(min(20, num_records)):
    rec_start = i * record_size
    rec_data = decoded[rec_start:rec_start + record_size]
    
    # Search for text in this record
    text_pattern = rb'[\x20-\x7e]{4,}'
    matches = list(re.finditer(text_pattern, rec_data))
    
    if matches:
        print(f"Record {i+1:3d} @ +{rec_start:5d}:")
        for match in matches:
            text = match.group().decode('latin1', errors='replace')
            if any(c.isalpha() for c in text) and len(text) >= 4:
                print(f"  +{match.start():2d}: '{text}'")

# Look for known teams more carefully
print("\n" + "="*80)
print("SEARCHING FOR KNOWN FOOTBALL TEAMS")
print("="*80)

known_teams = [
    "Manchester United", "Man United", "Man Utd", "Arsenal", "Liverpool", 
    "Chelsea", "Everton", "Tottenham", "Newcastle", "Leeds", "Aston Villa",
    "Real Madrid", "Barcelona", "Atletico Madrid", "Valencia", "Sevilla",
    "Bayern Munich", "Bayern", "Borussia", "Juventus", "Milan", "Inter",
    "Roma", "Lazio", "PSG", "Marseille", "Lyon", "Ajax", "Benfica",
    "Celtic", "Rangers", "Porto", "Sporting"
]

print("\nSearching decoded data for known teams:")
found_count = 0
for team in known_teams:
    pos = decoded.find(team.encode('latin1'))
    if pos != -1:
        # Find which record this belongs to
        record_num = pos // record_size
        offset_in_record = pos % record_size
        print(f"  ✓ '{team}' @ +{pos} (Record {record_num+1}, offset +{offset_in_record})")
        found_count += 1

print(f"\nFound {found_count} known teams")

print("\n" + "="*80)
print("SUMMARY")
print("="*80)
print(f"""
Decoded section: {len(decoded):,} bytes
Text strings found: {len(team_names)}
Known teams found: {found_count}
Estimated record size: {record_size} bytes
Estimated team count: {num_records}

Next: Map exact record structure and field positions
""")