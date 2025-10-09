"""
Test hypothesis: strings inside the blob are ALSO XOR-0x61 encoded
"""
import struct
from pathlib import Path

def decode_xor61(data: bytes, offset: int) -> tuple[bytes, int]:
    """Decode XOR-0x61 encoded field at offset."""
    length = struct.unpack_from("<H", data, offset)[0]
    encoded = data[offset+2 : offset+2+length]
    decoded = bytes(b ^ 0x61 for b in encoded)
    return decoded, 2 + length

def read_double_xor_string(blob: bytes, offset: int) -> tuple[str, int]:
    """Read a DOUBLE XOR-encoded string from inside the blob."""
    if offset + 2 > len(blob):
        return "<end>", 0
    
    # Read length prefix
    length = struct.unpack_from("<H", blob, offset)[0]
    if offset + 2 + length > len(blob):
        return f"<invalid len={length}>", 2
    
    # Extract the encoded string bytes
    encoded_string = blob[offset+2 : offset+2+length]
    
    # XOR again with 0x61 to decode
    decoded_string = bytes(b ^ 0x61 for b in encoded_string)
    
    # Remove null terminator if present
    if b'\x00' in decoded_string:
        decoded_string = decoded_string[:decoded_string.index(b'\x00')]
    
    try:
        text = decoded_string.decode('cp1252')
    except:
        text = f"<error: {decoded_string[:20].hex()}...>"
    
    return text, 2 + length

data = Path('DBDAT/JUG98030.FDI').read_bytes()

# Get the player record blob at 0x410
player_blob, _ = decode_xor61(data, 0x410)

print(f"=== Player Record (Double XOR Decoding) ===")
print(f"Blob length: {len(player_blob)} bytes\n")

pos = 0

# First byte might be region code
region = player_blob[pos]
print(f"Offset 0x{pos:04x}: region_code = 0x{region:02x} ({region})")
pos += 1

# Now try reading strings with double XOR
field_names = ["given_name", "surname", "common_name", "field_4", "field_5"]

for i, name in enumerate(field_names):
    if pos >= len(player_blob):
        break
    text, consumed = read_double_xor_string(player_blob, pos)
    print(f"Offset 0x{pos:04x}: {name:15s} = '{text}' (consumed {consumed} bytes)")
    pos += consumed
    if consumed == 0:
        break

print(f"\n--- After strings, position: 0x{pos:04x} ---")

# Show remaining data
if pos < len(player_blob):
    remaining = player_blob[pos:pos+128]
    print(f"\nRemaining bytes (next 128):")
    for i in range(0, len(remaining), 16):
        chunk = remaining[i:i+16]
        hex_part = ' '.join(f'{b:02x}' for b in chunk)
        asc_part = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in chunk)
        print(f"  {i:04x}: {hex_part:<48} {asc_part}")
    
    # Try to parse some raw fields
    print(f"\n--- Parsing raw fields ---")
    p = pos
    
    # Try to find birth date (should be 3 bytes: day, month, year)
    if p + 3 <= len(player_blob):
        day = player_blob[p]
        month = player_blob[p+1]
        year = player_blob[p+2]
        print(f"Offset 0x{p:04x}: Potential birth date = {day:02d}/{month:02d}/{year:02d}")
        p += 3
    
    # Try reading some uint16 values
    for i in range(5):
        if p + 2 <= len(player_blob):
            val = struct.unpack_from("<H", player_blob, p)[0]
            print(f"Offset 0x{p:04x}: uint16 = {val}")
            p += 2