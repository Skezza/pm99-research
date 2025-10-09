"""
Team File Deep Analysis
Since teams don't use separator patterns, try different approach
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

# Load team file
data = Path('DBDAT/EQ98030.FDI').read_bytes()

print("="*80)
print("TEAM FILE DEEP ANALYSIS - Different Structure Approach")
print("="*80)

print(f"\nFile size: {len(data):,} bytes")

# The directory says data starts at 0x200
data_start = 0x200
print(f"\nData section starts at: 0x{data_start:08x}")

# Try decoding from data start
print("\nAttempting XOR decode from data start...")
decoded, consumed = decode_xor61(data, data_start)

if decoded:
    print(f"✓ Successfully decoded {consumed} bytes")
    print(f"  Decoded data size: {len(decoded)} bytes")
    
    print("\n" + "="*80)
    print("SEARCHING FOR TEAM NAMES IN DECODED DATA")
    print("="*80)
    
    # Search for known team names (famous football clubs)
    known_teams = [
        "Manchester United", "Arsenal", "Liverpool", "Chelsea",
        "Real Madrid", "Barcelona", "Bayern", "Juventus",
        "Milan", "Inter", "Ajax", "PSG"
    ]
    
    print("\nSearching for known team names...")
    for team in known_teams:
        if team.encode('latin1') in decoded:
            pos = decoded.find(team.encode('latin1'))
            print(f"  ✓ Found '{team}' at offset +{pos}")
    
    # Look for capital letter sequences (team names)
    print("\nSearching for potential team names (capital letter patterns)...")
    
    # Pattern: Words starting with capitals
    pattern = rb'([A-Z][a-z]{2,15}(?:\s+[A-Z][a-z]{2,15})*)'
    matches = list(re.finditer(pattern, decoded))
    
    print(f"Found {len(matches)} potential names")
    print("\nFirst 50 potential team names:")
    print("-"*80)
    
    seen = set()
    count = 0
    for match in matches:
        try:
            name = match.group().decode('latin1', errors='replace').strip()
            if (name not in seen and 
                len(name) > 3 and 
                not name.startswith('The') and
                ' ' in name or len(name) > 6):  # Either multi-word or long single word
                seen.add(name)
                print(f"{count+1:3d}. @ +{match.start():6d}: {name}")
                count += 1
                if count >= 50:
                    break
        except:
            pass
    
    print("\n" + "="*80)
    print("ANALYZING DATA STRUCTURE")
    print("="*80)
    
    # Show hex dump of first 256 bytes
    print("\nFirst 256 bytes of decoded data:")
    print("-"*80)
    for i in range(0, min(256, len(decoded)), 16):
        chunk = decoded[i:i+16]
        hex_part = ' '.join(f'{b:02x}' for b in chunk)
        asc_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        print(f"{i:04x}: {hex_part:<48} {asc_part}")
    
    # Look for repeating patterns that might indicate record boundaries
    print("\n" + "="*80)
    print("LOOKING FOR RECORD PATTERNS")
    print("="*80)
    
    # Try to find repeating byte sequences
    print("\nSearching for potential record separators...")
    
    # Common separator patterns
    potential_seps = [
        bytes([0x00, 0x00]),
        bytes([0xff, 0xff]),
        bytes([0x61, 0x61]),
        bytes([0x00, 0x00, 0x00, 0x00]),
    ]
    
    for sep in potential_seps:
        count = decoded.count(sep)
        if count > 10:
            positions = []
            pos = 0
            for _ in range(min(10, count)):
                pos = decoded.find(sep, pos)
                if pos != -1:
                    positions.append(pos)
                    pos += len(sep)
            print(f"  Pattern {sep.hex()}: found {count} times")
            print(f"    First 10 positions: {positions}")
            if len(positions) > 2:
                spacing = [positions[i+1] - positions[i] for i in range(len(positions)-1)]
                print(f"    Spacing: {spacing}")
    
    # Try to identify fixed-length records
    print("\n" + "="*80)
    print("FIXED-LENGTH RECORD HYPOTHESIS")
    print("="*80)
    
    # If it's 544 teams (reference said so), calculate potential record size
    print("\nReference suggests ~544 teams in database")
    print(f"Decoded data size: {len(decoded)} bytes")
    print(f"Potential record sizes:")
    
    for team_count in [540, 544, 550, 600]:
        record_size = len(decoded) // team_count
        print(f"  {team_count} teams: ~{record_size} bytes per record")

else:
    print("✗ Failed to decode from data start")
    print("\nTrying to find XOR-encoded sections manually...")
    
    # Scan for length-prefixed XOR data
    pos = 0x200
    sections_found = 0
    
    while pos < min(len(data), 0x200 + 50000) and sections_found < 10:
        try:
            length = struct.unpack_from("<H", data, pos)[0]
            if 100 < length < 100000:
                encoded = data[pos+2 : pos+2+length]
                test_decode = bytes(b ^ 0x61 for b in encoded[:100])
                
                # Check if decoded data looks like text
                printable = sum(1 for b in test_decode if 32 <= b < 127 or b in [9, 10, 13])
                if printable > 50:  # More than 50% printable
                    print(f"\nPotential XOR section at 0x{pos:08x}")
                    print(f"  Length: {length} bytes")
                    print(f"  Preview: {test_decode[:50]}")
                    sections_found += 1
                
                pos += length + 2
            else:
                pos += 1
        except:
            pos += 1

print("\n" + "="*80)
print("RECOMMENDATIONS")
print("="*80)

print("""
Team file uses DIFFERENT structure than player file:
- No separator patterns (dd 63 60)
- Likely fixed-length records
- Still XOR-encoded with 0x61

Next steps:
1. Decode entire data section
2. Search for known team names to confirm decoding works
3. Analyze structure around found team names
4. Determine fixed record size (likely ~2000 bytes per team based on file size)
5. Map team record fields systematically

The structure might be:
- Fixed-length records
- Team name at specific offset within each record
- Team ID field to link to players
- Other metadata (division, budget, etc.)
""")