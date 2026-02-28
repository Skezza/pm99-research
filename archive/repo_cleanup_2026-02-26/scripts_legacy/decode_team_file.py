"""
Comprehensive Team File Decoder
Decode XOR sections and search for team names and structure
"""
import struct
from pathlib import Path
import re
from typing import List, Tuple

def decode_xor61_section(data: bytes, offset: int, length: int) -> bytes:
    """Decode XOR-0x61 encoded section"""
    encoded = data[offset:offset+length]
    return bytes(b ^ 0x61 for b in encoded)

# Load team file
data = Path('DBDAT/EQ98030.FDI').read_bytes()

print("="*80)
print("TEAM FILE COMPREHENSIVE DECODER")
print("="*80)

# Decode the two found sections
sections = [
    (0x201, 11520, "Section 1"),
    (0x2f04, 42496, "Section 2"),
]

all_decoded = []

for offset, length, name in sections:
    print(f"\n{name} @ 0x{offset:08x} ({length:,} bytes)")
    print("-"*80)
    
    decoded = decode_xor61_section(data, offset, length)
    all_decoded.append((name, offset, decoded))
    
    # Search for known football team names
    known_teams = [
        b"Manchester United", b"Manchester Utd", b"Man United", b"Man Utd",
        b"Arsenal", b"Liverpool", b"Chelsea", b"Everton",
        b"Tottenham", b"Spurs", b"Newcastle", b"Leeds",
        b"Real Madrid", b"Barcelona", b"Bayern", b"Juventus",
        b"Milan", b"Inter", b"Ajax", b"PSG", b"Benfica",
        b"Celtic", b"Rangers", b"Porto", b"Sporting"
    ]
    
    found_teams = []
    for team in known_teams:
        pos = decoded.find(team)
        if pos != -1:
            found_teams.append((team.decode('latin1'), pos))
    
    if found_teams:
        print(f"\n✓ Found {len(found_teams)} known team names:")
        for team, pos in sorted(found_teams, key=lambda x: x[1])[:20]:
            print(f"  @ +{pos:6d}: {team}")
    else:
        print("  ✗ No known teams found")
    
    # Search for any capitalized words (potential team names)
    print(f"\nSearching for potential team names (capitalized patterns)...")
    pattern = rb'[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*'
    matches = list(re.finditer(pattern, decoded))
    
    unique_names = set()
    for match in matches[:100]:
        try:
            name = match.group().decode('latin1', errors='replace')
            if len(name) > 4 and name not in unique_names:
                unique_names.add(name)
        except:
            pass
    
    if unique_names:
        print(f"  Found {len(unique_names)} unique potential names")
        print(f"  First 20:")
        for i, name in enumerate(sorted(unique_names)[:20]):
            print(f"    {i+1:2d}. {name}")

print("\n" + "="*80)
print("ANALYZING SECTION 2 (LARGEST - LIKELY MAIN TEAM DATA)")
print("="*80)

# Section 2 is the largest, most likely contains team records
section_name, section_offset, decoded = all_decoded[1]  # Section 2

print(f"\nSize: {len(decoded):,} bytes")

# Show hex dump of first 512 bytes to understand structure
print("\nHex dump of first 512 bytes:")
print("-"*80)
for i in range(0, min(512, len(decoded)), 16):
    chunk = decoded[i:i+16]
    hex_part = ' '.join(f'{b:02x}' for b in chunk)
    asc_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
    print(f"{i:04x}: {hex_part:<48} {asc_part}")

# Calculate potential fixed record sizes
print("\n" + "="*80)
print("FIXED-LENGTH RECORD ANALYSIS")
print("="*80)

print(f"\nDecoded section size: {len(decoded):,} bytes")
print(f"\nPotential record sizes for different team counts:")

for team_count in [100, 200, 300, 400, 500, 544, 600, 700]:
    record_size = len(decoded) // team_count
    remainder = len(decoded) % team_count
    print(f"  {team_count:3d} teams: {record_size:4d} bytes/record (remainder: {remainder})")

# Try to find repeating patterns
print("\n" + "="*80)
print("SEARCHING FOR RECORD BOUNDARIES")
print("="*80)

# Look for common byte sequences that might mark record starts
print("\nSearching for potential record markers...")

# Try various patterns
patterns = [
    (b'\x00\x00', "null bytes"),
    (b'\xff\xff', "0xff bytes"),
    (b'aa', "0x61^0x61 pattern"),
    (b'\x01\x00', "little-endian 1"),
]

for pattern, description in patterns:
    positions = []
    pos = 0
    while pos < len(decoded) and len(positions) < 20:
        pos = decoded.find(pattern, pos)
        if pos == -1:
            break
        positions.append(pos)
        pos += len(pattern)
    
    if len(positions) > 5:
        spacing = [positions[i+1] - positions[i] for i in range(min(10, len(positions)-1))]
        avg_spacing = sum(spacing) / len(spacing) if spacing else 0
        print(f"  {description:20s}: {len(positions):4d} occurrences, avg spacing: {avg_spacing:.1f}")
        if positions:
            print(f"    First positions: {positions[:10]}")
            if spacing and min(spacing) == max(spacing):
                print(f"    ✓ REGULAR SPACING: {spacing[0]} bytes")

# Try 78-byte fixed records (42496 / 544 ≈ 78)
print("\n" + "="*80)
print("TESTING 78-BYTE FIXED RECORDS (42496 / 544 = 78.1)")
print("="*80)

record_size = 78
num_records = len(decoded) // record_size

print(f"\nAssuming {record_size}-byte records: {num_records} complete records")
print(f"Analyzing first 10 records:\n")

for i in range(min(10, num_records)):
    rec_start = i * record_size
    rec_data = decoded[rec_start:rec_start + record_size]
    
    print(f"Record {i+1} @ offset {rec_start}:")
    
    # Show first 32 bytes
    chunk = rec_data[:32]
    hex_part = ' '.join(f'{b:02x}' for b in chunk)
    print(f"  {hex_part}")
    
    # Try to extract potential team ID (assume 16-bit at various positions)
    for pos in [0, 1, 2, 3, 4]:
        if pos + 2 <= len(rec_data):
            val = struct.unpack_from("<H", rec_data, pos)[0]
            if 3000 < val < 4000:  # Player team IDs were 3712-3807
                print(f"  Potential ID @ +{pos}: {val} (0x{val:04x})")
    
    # Search for text strings in this record
    text_matches = re.finditer(rb'[A-Z][a-z]{3,}', rec_data)
    for match in text_matches:
        try:
            text = match.group().decode('latin1', errors='replace')
            if len(text) > 4:
                print(f"  Text @ +{match.start()}: '{text}'")
        except:
            pass
    
    print()

print("\n" + "="*80)
print("RECOMMENDATIONS")
print("="*80)

print("""
Based on analysis:

1. Section 2 (42,496 bytes) is likely the main team database
2. File size suggests ~78 bytes per record if 544 teams
3. Need to identify:
   - Exact record size (try 78, 80, or other values)
   - Team ID field position (check positions 0-4 for values in 3712-3807 range)
   - Team name field position
   - Other fields (division, budget, etc.)

Next step: Create detailed record parser to map all fields
""")