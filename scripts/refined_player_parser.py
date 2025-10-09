"""
Refined player record parser based on analysis findings.
The key insight: plaintext names appear in records, but there's structure before them.
"""
import struct
from pathlib import Path
from typing import Tuple, Dict, Any, List

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

def find_player_records_by_separator(decoded_data: bytes) -> List[int]:
    """
    Find potential record starts by looking for separator pattern.
    From analysis, we see 'dd 63 60' pattern before names.
    """
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

def parse_player_at_offset(decoded_data: bytes, offset: int) -> Dict[str, Any]:
    """
    Parse a single player record starting at offset.
    Based on the pattern we found: separator (dd 63 60) marks record boundaries.
    """
    player = {}
    pos = offset
    
    try:
        # Skip separator if present
        if decoded_data[pos:pos+3] == bytes([0xdd, 0x63, 0x60]):
            pos += 3
        
        # Next bytes seem to be metadata before name
        # From analysis: we see patterns like d5 0e 62 67 61 before "Kimoni"
        # or d7 0e 6c 6d 61 before "Vangronsveld"
        
        # Try to find the plaintext name (capital letter start)
        # Scan forward up to 20 bytes for a name pattern
        name_start = None
        for i in range(pos, min(pos + 20, len(decoded_data) - 10)):
            # Look for pattern: lowercase letters followed by capital letter
            if (decoded_data[i:i+2].isalpha() and 
                i + 3 < len(decoded_data) and
                decoded_data[i+2] >= 0x41 and decoded_data[i+2] <= 0x5A):  # Capital letter
                name_start = i + 2  # Start of Given name
                break
        
        if name_start:
            # Extract the full name (until we hit non-name characters)
            name_end = name_start
            while name_end < len(decoded_data):
                c = decoded_data[name_end]
                # Name characters: A-Z, a-z, space, accented chars
                if (65 <= c <= 90 or 97 <= c <= 122 or c == 32 or c > 127):
                    name_end += 1
                else:
                    break
            
            player['name'] = decoded_data[name_start:name_end].decode('latin1', errors='replace').strip()
            player['name_offset'] = name_start
            
            # Data after name might be attributes
            data_after = decoded_data[name_end:name_end+50]
            player['data_after_name'] = data_after[:30].hex()
            
            # Look for reasonable attribute values (0-100 range typically)
            potential_attrs = []
            for i in range(name_end, min(name_end + 30, len(decoded_data))):
                val = decoded_data[i]
                if 0 <= val <= 100:
                    potential_attrs.append((i - name_start, val))
            
            player['potential_attributes'] = potential_attrs[:15]
            
    except Exception as e:
        player['error'] = str(e)
    
    return player

# Load and decode the player section
data = Path('DBDAT/JUG98030.FDI').read_bytes()
section_offset = 0x378383
decoded, _ = decode_xor61(data, section_offset)

print("="*80)
print("REFINED PLAYER RECORD ANALYSIS")
print("="*80)

# Find separator patterns
separators = find_player_records_by_separator(decoded)
print(f"\nFound {len(separators)} separator patterns (dd 63 60)")
print(f"First 20 positions: {separators[:20]}")

# Calculate spacing between separators
if len(separators) > 10:
    spacings = [separators[i+1] - separators[i] for i in range(min(20, len(separators)-1))]
    print(f"\nSpacing between separators:")
    print(f"  Min: {min(spacings)} bytes")
    print(f"  Max: {max(spacings)} bytes")
    print(f"  Average: {sum(spacings)/len(spacings):.1f} bytes")
    print(f"  First 10: {spacings[:10]}")

# Parse players starting from each separator
print(f"\n{'='*80}")
print("PARSING PLAYERS FROM SEPARATORS")
print(f"{'='*80}")

players = []
for i, sep_pos in enumerate(separators[:10]):  # First 10 for analysis
    player = parse_player_at_offset(decoded, sep_pos)
    if 'name' in player and len(player['name']) > 3:
        players.append(player)
        print(f"\nPlayer {i+1} @ separator {sep_pos}:")
        print(f"  Name: {player['name']}")
        print(f"  Name offset: +{player['name_offset']}")
        print(f"  Data after: {player['data_after_name']}")
        if 'potential_attributes' in player:
            print(f"  Potential attributes (offset from name, value):")
            for offset, val in player['potential_attributes']:
                print(f"    +{offset:3d}: {val:3d} (0x{val:02x})")

# Now let's do detailed analysis of one known good player
print(f"\n{'='*80}")
print("DETAILED ANALYSIS: Daniel KIMONI")
print(f"{'='*80}")

# We know Daniel KIMONI is at offset +35
kimoni_offset = 35
# Find the separator before it
sep_before = None
for sep in separators:
    if sep < kimoni_offset:
        sep_before = sep
    else:
        break

if sep_before is not None:
    print(f"\nSeparator before KIMONI: @ {sep_before} (name at {kimoni_offset})")
    print(f"Distance: {kimoni_offset - sep_before} bytes")
    
    # Show the bytes between separator and name
    chunk = decoded[sep_before:kimoni_offset+30]
    print(f"\nBytes from separator to name+30:")
    for i in range(0, len(chunk), 16):
        line = chunk[i:i+16]
        hex_part = ' '.join(f'{b:02x}' for b in line)
        asc_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in line)
        rel_offset = sep_before + i - kimoni_offset
        marker = " <-- NAME" if sep_before + i <= kimoni_offset < sep_before + i + 16 else ""
        print(f"  {rel_offset:+5d}: {hex_part:<48} {asc_part}{marker}")

print(f"\n{'='*80}")
print("SUMMARY")
print(f"{'='*80}")
print(f"Separators found: {len(separators)}")
print(f"Average record size: ~{sum(spacings)/len(spacings):.0f} bytes" if separators else "N/A")
print(f"\nNext step: Use separator positions to delineate individual records")
print(f"Then parse each record's fields systematically")