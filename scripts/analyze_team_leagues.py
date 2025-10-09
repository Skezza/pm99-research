"""
Analyze team records to find league information
"""
import struct
from pathlib import Path

data = Path('../DBDAT/EQ98030.FDI').read_bytes()

# Decode Section 2 (main team data)
section_offset = 0x2f04
section_length = 42496

# Read the length prefix and decode
length_prefix = struct.unpack_from("<H", data, section_offset)[0]
print(f"Section 2 @ 0x{section_offset:08x}")
print(f"Length prefix: {length_prefix} bytes")

# XOR decode the section
encoded = data[section_offset + 2 : section_offset + 2 + length_prefix]
decoded = bytes(b ^ 0x61 for b in encoded)

print(f"Decoded: {len(decoded)} bytes")

# Find team records
separator = bytes([0x61, 0xdd, 0x63])
positions = []
pos = 0
while pos < len(decoded):
    pos = decoded.find(separator, pos)
    if pos == -1:
        break
    positions.append(pos)
    pos += 3

print(f"Found {len(positions)} team records")

# Analyze first few teams
for i in range(min(10, len(positions))):
    sep_pos = positions[i]
    next_sep = positions[i+1] if i+1 < len(positions) else min(sep_pos + 2000, len(decoded))
    record = decoded[sep_pos:next_sep]

    print(f"\nTeam {i+1} @ +{sep_pos}:")
    print(f"  Record length: {len(record)} bytes")

    # Extract team name
    import re
    match = re.search(rb'[\x20-\x7e]{5,50}', record[3:])
    if match:
        team_name = match.group().decode('latin1', errors='replace').strip()
        print(f"  Team name: '{team_name}'")
        name_end = match.end() + 3

        # Look for stadium after team name
        stadium_match = re.search(rb'[\x20-\x7e]{5,80}', record[name_end:])
        if stadium_match:
            stadium = stadium_match.group().decode('latin1', errors='replace').strip()
            print(f"  Stadium: '{stadium}'")
            stadium_end = name_end + stadium_match.end()

            # Look at bytes after stadium for league info
            remaining = record[stadium_end:]
            print(f"  After stadium ({len(remaining)} bytes):")
            # Show hex dump of next 100 bytes
            for j in range(0, min(100, len(remaining)), 16):
                chunk = remaining[j:j+16]
                hex_part = ' '.join(f'{b:02x}' for b in chunk)
                asc_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
                print(f"    +{stadium_end+j:04x}: {hex_part:<48} {asc_part}")

            # Look for text strings after stadium
            text_matches = list(re.finditer(rb'[\x20-\x7e]{3,}', remaining))
            if text_matches:
                print("  Text after stadium:")
                for tm in text_matches[:5]:  # First 5 matches
                    text = tm.group().decode('latin1', errors='replace').strip()
                    if len(text) >= 3:
                        print(f"    +{stadium_end + tm.start()}: '{text}'")
        else:
            print("  No stadium found")
    else:
        print("  No team name found")

    if i >= 9:  # Limit to first 10
        break