"""
Map individual player record structure by analyzing known players.
Combines our XOR findings with the reference structure.

Expected structure (after XOR-0x61 decode):
- Team Pointer/ID (2 bytes)
- Squad Number (1 byte)
- Short name (length-prefixed string)
- Long name (length-prefixed string)
- Unknown (2 bytes)
- Attributes block 1 (6 bytes)
- Nationality (1 byte)
- Skin tone (1 byte)
- Hair color (1 byte)
- Position (1 byte)
- Birth date (4 bytes: day, month, year)
- Height (1 byte)
- Weight (1 byte)
- Comment flag (1 byte)
- Attributes block 2 (10 bytes)
"""
import struct
from pathlib import Path
from typing import Tuple, Dict, Any

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

def read_length_prefixed_string(data: bytes, offset: int) -> Tuple[str, int]:
    """Read a length-prefixed string (1 byte length + chars + null terminator)"""
    if offset >= len(data):
        return "", 0
    
    length = data[offset]
    if length == 0 or offset + 1 + length >= len(data):
        return "", 1
    
    # Read the string bytes
    string_bytes = data[offset + 1 : offset + 1 + length]
    
    # Find null terminator
    consumed = 1 + length
    if offset + consumed < len(data) and data[offset + consumed] == 0:
        consumed += 1  # Include null terminator
    
    try:
        text = string_bytes.decode('latin1').rstrip('\x00')
    except:
        text = string_bytes.hex()
    
    return text, consumed

def analyze_player_record(decoded_data: bytes, name_offset: int, player_name: str) -> Dict[str, Any]:
    """
    Analyze the structure of a player record starting from before the name.
    We know the plaintext name location, so work backwards to find record start.
    """
    print(f"\n{'='*80}")
    print(f"Analyzing: {player_name} (name @ +{name_offset})")
    print(f"{'='*80}")
    
    # Search backwards for potential record start (try 50 bytes before name)
    search_start = max(0, name_offset - 100)
    
    # Show hex dump around the name
    print(f"\nHex dump from -{name_offset - search_start} to +100 bytes:")
    context_start = search_start
    context_end = min(len(decoded_data), name_offset + 150)
    
    for i in range(context_start, context_end, 16):
        chunk = decoded_data[i:i+16]
        hex_part = ' '.join(f'{b:02x}' for b in chunk)
        asc_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        
        marker = ""
        if i <= name_offset < i + 16:
            marker = " <-- NAME HERE"
        
        offset_from_name = i - name_offset
        print(f"  {offset_from_name:+5d}: {hex_part:<48} {asc_part}{marker}")
    
    # Try to parse as fixed structure from various starting points
    print(f"\n{'='*60}")
    print("Attempting to parse from different offsets:")
    print(f"{'='*60}")
    
    # Try starting 40, 30, 20, 10 bytes before name
    for try_start in [name_offset - 50, name_offset - 40, name_offset - 30, name_offset - 20]:
        if try_start < 0:
            continue
            
        print(f"\n--- Trying record start @ {try_start-name_offset:+d} from name ---")
        pos = try_start
        
        try:
            # Team pointer (2 bytes)
            if pos + 2 <= len(decoded_data):
                team_id = struct.unpack_from("<H", decoded_data, pos)[0]
                print(f"  +0: Team ID: {team_id} (0x{team_id:04x})")
                pos += 2
            
            # Squad number (1 byte)
            if pos < len(decoded_data):
                squad_num = decoded_data[pos]
                print(f"  +2: Squad number: {squad_num}")
                pos += 1
            
            # Short name (length-prefixed)
            if pos < len(decoded_data):
                short_name, consumed = read_length_prefixed_string(decoded_data, pos)
                print(f"  +3: Short name: '{short_name}' ({consumed} bytes)")
                pos += consumed
            
            # Long name (length-prefixed)
            if pos < len(decoded_data):
                long_name, consumed = read_length_prefixed_string(decoded_data, pos)
                print(f"  +{pos-try_start}: Long name: '{long_name}' ({consumed} bytes)")
                
                # Check if this matches our known player name
                if player_name.lower() in long_name.lower() or long_name.lower() in player_name.lower():
                    print(f"    ✓✓✓ NAME MATCH! This might be the correct offset!")
                
                pos += consumed
            
            # Unknown 2 bytes
            if pos + 2 <= len(decoded_data):
                unknown = struct.unpack_from("<H", decoded_data, pos)[0]
                print(f"  +{pos-try_start}: Unknown: 0x{unknown:04x}")
                pos += 2
            
            # Attributes block 1 (6 bytes)
            if pos + 6 <= len(decoded_data):
                attrs1 = decoded_data[pos:pos+6]
                print(f"  +{pos-try_start}: Attributes 1: {' '.join(f'{b:02x}' for b in attrs1)}")
                print(f"           Decimal: {list(attrs1)}")
                pos += 6
            
            # Nationality
            if pos < len(decoded_data):
                nationality = decoded_data[pos]
                print(f"  +{pos-try_start}: Nationality: {nationality} (0x{nationality:02x})")
                pos += 1
            
            # Skin tone
            if pos < len(decoded_data):
                skin = decoded_data[pos]
                print(f"  +{pos-try_start}: Skin tone: {skin}")
                pos += 1
            
            # Hair color
            if pos < len(decoded_data):
                hair = decoded_data[pos]
                print(f"  +{pos-try_start}: Hair color: {hair}")
                pos += 1
            
            # Position
            if pos < len(decoded_data):
                position = decoded_data[pos]
                print(f"  +{pos-try_start}: Position: {position}")
                pos += 1
            
            # Birth date (4 bytes: day, month, year)
            if pos + 4 <= len(decoded_data):
                day = decoded_data[pos]
                month = decoded_data[pos+1]
                year = struct.unpack_from("<H", decoded_data, pos+2)[0]
                print(f"  +{pos-try_start}: Birth: {day:02d}/{month:02d}/{year}")
                pos += 4
            
            # Height
            if pos < len(decoded_data):
                height = decoded_data[pos]
                print(f"  +{pos-try_start}: Height: {height} cm")
                pos += 1
            
            # Weight
            if pos < len(decoded_data):
                weight = decoded_data[pos]
                print(f"  +{pos-try_start}: Weight: {weight} kg")
                pos += 1
            
            # Comment flag
            if pos < len(decoded_data):
                comment = decoded_data[pos]
                print(f"  +{pos-try_start}: Comment flag: {comment}")
                pos += 1
            
            # Attributes block 2 (10 bytes)
            if pos + 10 <= len(decoded_data):
                attrs2 = decoded_data[pos:pos+10]
                print(f"  +{pos-try_start}: Attributes 2: {' '.join(f'{b:02x}' for b in attrs2)}")
                print(f"           Decimal: {list(attrs2)}")
                pos += 10
            
            total_size = pos - try_start
            print(f"  Total record size: {total_size} bytes")
            
        except Exception as e:
            print(f"  Error parsing: {e}")

# Load the player file
data = Path('DBDAT/JUG98030.FDI').read_bytes()

print("="*80)
print("PLAYER RECORD STRUCTURE ANALYSIS")
print("="*80)

# Analyze the section with most players (0x378383 with Daniel KIMONI at +35)
target_section = 0x378383
decoded, _ = decode_xor61(data, target_section)

print(f"\nSection @ 0x{target_section:08x}")
print(f"Decoded size: {len(decoded)} bytes")

# Known players and their offsets in this section
known_players = [
    (35, "Daniel KIMONI"),
    (102, "Domenico OLIVIERI"),
    (177, "Marc VANGRONSVELD"),
]

for name_offset, player_name in known_players:
    analyze_player_record(decoded, name_offset, player_name)

print(f"\n{'='*80}")
print("ANALYSIS COMPLETE")
print(f"{'='*80}")
print("\nLook for patterns where the long name matches the player name.")
print("That offset is likely the correct record start position.")