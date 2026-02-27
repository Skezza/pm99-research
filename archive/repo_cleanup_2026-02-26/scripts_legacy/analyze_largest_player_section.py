"""
Deep analysis of the largest player name section.
Focus on structure to enable parsing.
"""
import struct
import re
from pathlib import Path
from typing import List, Tuple

def decode_xor61(data: bytes, offset: int) -> Tuple[bytes, int]:
    """Decode XOR-0x61 field"""
    if offset + 2 > len(data):
        return b"", 0
    length = struct.unpack_from("<H", data, offset)[0]
    if offset + 2 + length > len(data):
        return b"", 0
    encoded = data[offset+2 : offset+2+length]
    decoded = bytes(b ^ 0x61 for b in encoded)
    return decoded, 2 + length

def find_name_patterns(data: bytes) -> List[Tuple[int, str, str]]:
    """Find player names and return (offset, given_name, surname)"""
    matches = []
    
    # Pattern: Given SURNAME or Given Surname
    pattern = rb'([A-Z][a-z]{2,15})\s+([A-Z][A-Z]{2,20}|[A-Z][a-z]{2,20})'
    
    for match in re.finditer(pattern, data):
        try:
            given = match.group(1).decode('latin1')
            surname = match.group(2).decode('latin1')
            skip_words = ['THE', 'AND', 'FOR', 'WITH', 'FROM', 'ABOUT', 'WHEN', 'WHERE']
            if surname.upper() in skip_words or len(given) < 3 or len(surname) < 3:
                continue
            matches.append((match.start(), given, surname))
        except:
            continue
    
    return matches

data = Path('DBDAT/JUG98030.FDI').read_bytes()

# Analyze the section with most names
target_offset = 0x00378383
print(f"{'='*80}")
print(f"ANALYZING LARGEST PLAYER SECTION @ 0x{target_offset:08x}")
print(f"{'='*80}\n")

decoded, consumed = decode_xor61(data, target_offset)
print(f"Section size: {consumed-2:,} bytes (decoded)")
print(f"Total consumed: {consumed:,} bytes\n")

# Find all names
names = find_name_patterns(decoded)
print(f"Found {len(names)} player names\n")

# Show first 50 names with their positions
print("First 50 player names and positions:")
print("-" * 80)
for i, (offset, given, surname) in enumerate(names[:50]):
    full_name = f"{given} {surname}"
    print(f"{i+1:3d}. @ +{offset:6d} (0x{offset:05x}): {full_name}")

# Analyze spacing between names
print(f"\n{'='*80}")
print("SPACING ANALYSIS")
print(f"{'='*80}\n")

if len(names) >= 10:
    spacings = [names[i+1][0] - names[i][0] for i in range(min(20, len(names)-1))]
    print(f"Spacing between first 20 names (bytes):")
    for i, spacing in enumerate(spacings):
        print(f"  Name {i} -> {i+1}: {spacing:4d} bytes")
    
    print(f"\nStatistics:")
    print(f"  Min spacing: {min(spacings)}")
    print(f"  Max spacing: {max(spacings)}")
    print(f"  Average: {sum(spacings)/len(spacings):.1f}")

# Look for record boundaries (similar to coaches)
print(f"\n{'='*80}")
print("LOOKING FOR RECORD STRUCTURE")
print(f"{'='*80}\n")

# Check for separator pattern (like coaches used 0x61 0xdd 0x63 0x61)
sep_pattern = b'\x61\xdd\x63\x61'
sep_positions = []
for i in range(len(decoded) - 3):
    if decoded[i:i+4] == sep_pattern:
        sep_positions.append(i)

if sep_positions:
    print(f"Found {len(sep_positions)} separator patterns (0x61 0xdd 0x63 0x61)")
    print(f"First 10 positions: {sep_positions[:10]}")
else:
    print("No standard separator pattern found")

# Try to find pattern: name appears after specific bytes
print(f"\nAnalyzing bytes BEFORE each name:")
for i, (name_offset, given, surname) in enumerate(names[:20]):
    # Look at 16 bytes before the name
    start = max(0, name_offset - 16)
    before = decoded[start:name_offset]
    print(f"{i+1:2d}. {given} {surname}")
    print(f"    Before: {before.hex()}")
    # Also show printable chars
    printable = ''.join(chr(b) if 32 <= b < 127 else '.' for b in before)
    print(f"    Chars:  {printable}")

# Check if names are part of larger records
print(f"\n{'='*80}")
print("CHECKING FOR PLAYER RECORD STRUCTURE")
print(f"{'='*80}\n")

# A player record might be: [metadata] [given_name] [surname] [stats...]
# Let's examine the first few complete sections around names
for i in range(min(5, len(names))):
    name_offset, given, surname = names[i]
    
    print(f"\n--- Player {i+1}: {given} {surname} ---")
    print(f"Name starts at offset +{name_offset} (0x{name_offset:05x})")
    
    # Look for record start (might be before the name)
    # Check 200 bytes before to 100 bytes after
    start = max(0, name_offset - 200)
    end = min(len(decoded), name_offset + len(given) + len(surname) + 100)
    chunk = decoded[start:end]
    
    # Show hex dump
    print(f"Context (from -{name_offset-start} to +{end-name_offset}):")
    for offset in range(0, min(len(chunk), 300), 16):
        line = chunk[offset:offset+16]
        hex_part = ' '.join(f'{b:02x}' for b in line)
        asc_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in line)
        actual_offset = start + offset
        marker = " <-- NAME" if actual_offset <= name_offset < actual_offset + 16 else ""
        print(f"  +{actual_offset:5d}: {hex_part:<48} {asc_part}{marker}")

print(f"\n{'='*80}")
print(f"SUMMARY")
print(f"{'='*80}")
print(f"This section contains {len(names)} player names")
print(f"Names are embedded in a {consumed-2:,} byte structure")
print(f"Next step: Identify the record boundaries and field structure")