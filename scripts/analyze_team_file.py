"""
Team File (EQ98030.FDI) Analysis
Reverse engineer team structure to validate player.team_id hypothesis
"""
import struct
from pathlib import Path
from typing import Tuple, List
import re

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

# Load team file
data = Path('DBDAT/EQ98030.FDI').read_bytes()

print("="*80)
print("TEAM FILE (EQ98030.FDI) ANALYSIS")
print("="*80)

# Read FDI header
signature = data[0:10].decode('ascii', errors='replace')
version = struct.unpack_from("<H", data, 0x10)[0]
num_entries = struct.unpack_from("<I", data, 0x14)[0]

print(f"\nFile size: {len(data):,} bytes ({len(data)/1024:.1f} KB)")
print(f"\nHeader:")
print(f"  Signature: {signature}")
print(f"  Version: {version}")
print(f"  Directory entries: {num_entries}")

# Read directory entries
print(f"\nDirectory entries:")
for i in range(min(num_entries, 10)):
    offset = 0x20 + (i * 8)
    entry_offset, tag, index = struct.unpack_from("<IHH", data, offset)
    print(f"  Entry {i}: offset=0x{entry_offset:08x}, tag=0x{tag:04x}, index={index}")

print("\n" + "="*80)
print("SCANNING FOR XOR-ENCODED SECTIONS")
print("="*80)

# Scan for sections with separator patterns (same as player file)
sections_with_seps = []
pos = 0x400
sections_scanned = 0

while pos < len(data) - 1000 and sections_scanned < 100:
    try:
        length = struct.unpack_from("<H", data, pos)[0]
        if 100 < length < 100000:
            encoded = data[pos+2 : pos+2+length]
            decoded = bytes(b ^ 0x61 for b in encoded)
            
            # Check for separator pattern
            if bytes([0xdd, 0x63, 0x60]) in decoded:
                separators = find_records_by_separator(decoded)
                sections_with_seps.append((pos, length, len(separators)))
                sections_scanned += 1
            
            pos += length + 2
        else:
            pos += 1
    except:
        pos += 1

print(f"\nFound {len(sections_with_seps)} sections with separator patterns")
print(f"\nTop 10 sections by record count:")
sections_with_seps.sort(key=lambda x: x[2], reverse=True)
for i, (offset, size, sep_count) in enumerate(sections_with_seps[:10]):
    print(f"  {i+1}. Offset 0x{offset:08x}: {size:6d} bytes, {sep_count:4d} records")

print("\n" + "="*80)
print("ANALYZING LARGEST SECTION FOR TEAM NAMES")
print("="*80)

if sections_with_seps:
    # Analyze the largest section
    target_offset, target_size, sep_count = sections_with_seps[0]
    decoded, _ = decode_xor61(data, target_offset)
    
    print(f"\nSection @ 0x{target_offset:08x}")
    print(f"Size: {target_size} bytes")
    print(f"Records: {sep_count}")
    
    # Search for team names (capital letters followed by text)
    print(f"\nSearching for potential team names...")
    
    # Pattern for team names (similar to player names but teams might be different)
    team_name_pattern = rb'([A-Z][A-Za-z\s]{3,30})'
    
    matches = list(re.finditer(team_name_pattern, decoded))
    print(f"Found {len(matches)} potential name strings\n")
    
    # Show first 30 potential team names
    seen = set()
    print("First 30 unique potential team names:")
    print("-"*80)
    
    count = 0
    for match in matches:
        try:
            name = match.group().decode('latin1', errors='replace').strip()
            if name not in seen and len(name) > 3:
                seen.add(name)
                print(f"  {count+1:3d}. @ +{match.start():6d}: {name}")
                count += 1
                if count >= 30:
                    break
        except:
            pass
    
    # Analyze record structure
    print("\n" + "="*80)
    print("TEAM RECORD STRUCTURE ANALYSIS")
    print("="*80)
    
    separators = find_records_by_separator(decoded)
    print(f"\nFound {len(separators)} team records")
    
    # Analyze first 5 team records
    print("\nFirst 5 team records:")
    print("-"*80)
    
    for i in range(min(5, len(separators))):
        sep_pos = separators[i]
        next_sep = separators[i+1] if i+1 < len(separators) else len(decoded)
        record_size = next_sep - sep_pos
        
        print(f"\nTeam {i+1} @ offset {sep_pos} ({record_size} bytes):")
        
        # Show first 64 bytes
        chunk = decoded[sep_pos:sep_pos+64]
        for j in range(0, len(chunk), 16):
            line = chunk[j:j+16]
            hex_part = ' '.join(f'{b:02x}' for b in line)
            asc_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in line)
            print(f"  +{j:3d}: {hex_part:<48} {asc_part}")
        
        # Try to extract team name
        for match in re.finditer(team_name_pattern, chunk):
            try:
                name = match.group().decode('latin1', errors='replace').strip()
                if len(name) > 3:
                    print(f"  >>> Potential team name: '{name}'")
            except:
                pass

print("\n" + "="*80)
print("TEAM ID ANALYSIS")
print("="*80)

# Look for potential team IDs (comparing with player team_id range: 3712-3807)
print("""
From player analysis, we found team IDs in range 3712-3807 (0x0e80 to 0x0edf).

Looking for these values in team records...
""")

# Check if team records have ID fields
if sections_with_seps:
    target_offset, _, _ = sections_with_seps[0]
    decoded, _ = decode_xor61(data, target_offset)
    separators = find_records_by_separator(decoded)
    
    print("Checking first bytes of each team record for ID patterns:")
    print("-"*80)
    
    for i in range(min(10, len(separators))):
        sep_pos = separators[i]
        if sep_pos + 10 < len(decoded):
            # Try reading as 16-bit value at various positions
            record_start = decoded[sep_pos:sep_pos+10]
            hex_str = ' '.join(f'{b:02x}' for b in record_start)
            
            # Try positions 3-4 (same as players)
            if sep_pos + 5 < len(decoded):
                potential_id = struct.unpack_from("<H", decoded, sep_pos + 3)[0]
                print(f"  Team {i:2d}: {hex_str}  -> ID @ +3: {potential_id:4d} (0x{potential_id:04x})")

print("\n" + "="*80)
print("SUMMARY & RECOMMENDATIONS")
print("="*80)

print(f"""
Team File Analysis Results:
- File size: {len(data)/1024:.1f} KB
- Found {len(sections_with_seps)} sections with separator patterns
- Largest section has {sections_with_seps[0][2] if sections_with_seps else 0} records

Next Steps:
1. Identify which section contains the main team data
2. Map team record structure (similar to players)
3. Extract team IDs and names
4. Validate against player.team_id values (3712-3807)
5. Build team-player relationship map

The structure appears similar to player file - same XOR encoding,
same separator pattern (dd 63 60). Need to:
- Find the exact team ID field position
- Extract team names cleanly
- Map division/league information
""")