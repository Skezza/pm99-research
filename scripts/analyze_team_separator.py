"""
CRITICAL DISCOVERY: Teams also use separator pattern!
Re-analyze with separator pattern approach
"""
import struct
from pathlib import Path
import re

# Load and decode team file section 2
data = Path('DBDAT/EQ98030.FDI').read_bytes()
section_offset = 0x2f04
length_prefix = struct.unpack_from("<H", data, section_offset)[0]
encoded = data[section_offset + 2 : section_offset + 2 + length_prefix]
decoded = bytes(b ^ 0x61 for b in encoded)

print("="*80)
print("TEAM SEPARATOR PATTERN ANALYSIS")
print("="*80)

# Search for separator pattern
# In players (before XOR): dd 63 60
# After XOR with 0x61: bc 02 01
# But we're looking at ALREADY decoded data, so pattern should be: dd 63 60

separator = bytes([0xdd, 0x63, 0x60])
alt_separator = bytes([0x61, 0xdd, 0x63])  # Seen in Real Madrid hex dump

print(f"\nSearching for separator pattern 0xdd 0x63 0x60...")
positions_1 = []
pos = 0
while pos < len(decoded):
    pos = decoded.find(separator, pos)
    if pos == -1:
        break
    positions_1.append(pos)
    pos += 3

print(f"Found {len(positions_1)} occurrences of dd 63 60")

print(f"\nSearching for alt separator pattern 0x61 0xdd 0x63...")
positions_2 = []
pos = 0
while pos < len(decoded):
    pos = decoded.find(alt_separator, pos)
    if pos == -1:
        break
    positions_2.append(pos)
    pos += 3

print(f"Found {len(positions_2)} occurrences of 61 dd 63")

if positions_2:
    print(f"\n✓ Using alt separator 0x61 0xdd 0x63")
    print(f"First 20 positions: {positions_2[:20]}")
    separators = positions_2
    sep_pattern = alt_separator
else:
    print(f"\n✓ Using standard separator 0xdd 0x63 0x60")
    print(f"First 20 positions: {positions_1[:20]}")
    separators = positions_1
    sep_pattern = separator

# Analyze spacing
if len(separators) > 1:
    print(f"\nSeparator spacing analysis:")
    spacings = [separators[i+1] - separators[i] for i in range(min(20, len(separators)-1))]
    print(f"First 20 spacings: {spacings}")
    
    from collections import Counter
    spacing_counts = Counter(spacings)
    print(f"\nMost common spacings:")
    for spacing, count in spacing_counts.most_common(10):
        print(f"  {spacing:4d} bytes: {count:3d} times")

# Extract teams using separator pattern
print("\n" + "="*80)
print(f"EXTRACTING TEAMS USING SEPARATOR PATTERN")
print("="*80)

print(f"\nFound {len(separators)} team records")
print(f"\nFirst 20 teams:\n")

for i in range(min(20, len(separators))):
    sep_pos = separators[i]
    next_sep = separators[i+1] if i+1 < len(separators) else len(decoded)
    record_size = next_sep - sep_pos
    
    # Extract record
    record = decoded[sep_pos:sep_pos + min(78, record_size)]
    
    print(f"Team {i+1:3d} @ offset {sep_pos:6d} ({record_size} bytes):")
    
    # Show hex dump of first 48 bytes
    chunk = record[:48]
    hex_part = ' '.join(f'{b:02x}' for b in chunk)
    asc_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
    print(f"  {hex_part}")
    print(f"  {asc_part}")
    
    # Look for team name (text after separator)
    text_start = 3  # After separator
    match = re.search(rb'[\x20-\x7e]{4,50}', record[text_start:])
    if match:
        text = match.group().decode('latin1', errors='replace')
        # Clean up - team name often has prefix like "ca`qa"
        # Remove non-alpha prefix
        for j, c in enumerate(text):
            if c.isalpha():
                text = text[j:]
                break
        print(f"  >>> Team name: '{text}'")
    
    # Try to find team ID
    for pos in [0, 1, 2]:
        if pos + 2 <= len(record):
            val = struct.unpack_from("<H", record, pos)[0]
            if 3000 < val < 4000:
                print(f"  >>> Potential team ID @ +{pos}: {val} (0x{val:04x})")
    
    print()

# Look for the "HPXXYA%" signature
print("\n" + "="*80)
print("SIGNATURE PATTERN ANALYSIS")
print("="*80)

signature = b"HPXXYA%"
sig_positions = []
pos = 0
while pos < len(decoded):
    pos = decoded.find(signature, pos)
    if pos == -1:
        break
    sig_positions.append(pos)
    pos += 1

print(f"\nFound '{signature.decode()}' signature at {len(sig_positions)} locations")
if sig_positions:
    print(f"First 20 positions: {sig_positions[:20]}")
    
    # Check if signature appears near separators
    print(f"\nChecking relationship to separators:")
    for i in range(min(10, len(separators))):
        sep_pos = separators[i]
        # Find nearest signature
        nearest_sig = min(sig_positions, key=lambda x: abs(x - sep_pos))
        distance = nearest_sig - sep_pos
        print(f"  Separator {i+1} @ {sep_pos:6d}, nearest signature @ {nearest_sig:6d} (distance: {distance:+4d})")

print("\n" + "="*80)
print("SUMMARY")
print("="*80)
print(f"""
Separator pattern found: {len(separators)} times
This matches player file structure!

Team records use SAME structure as player records:
- Separator pattern: {sep_pattern.hex()}
- Variable-length records
- Team names embedded in records

Next steps:
1. Parse all team records using separator pattern
2. Extract team names and IDs
3. Build team-to-player mapping
""")