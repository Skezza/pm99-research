"""
Parse the INNER structure of the decoded player blob
"""
import struct
from pathlib import Path

def decode_xor61(data: bytes, offset: int) -> tuple[bytes, int]:
    """Decode XOR-0x61 encoded field at offset."""
    length = struct.unpack_from("<H", data, offset)[0]
    encoded = data[offset+2 : offset+2+length]
    decoded = bytes(b ^ 0x61 for b in encoded)
    return decoded, 2 + length

data = Path('DBDAT/JUG98030.FDI').read_bytes()

# Get the player record blob at 0x410
player_blob, _ = decode_xor61(data, 0x410)

print(f"=== Decoded Player Blob ===")
print(f"Total length: {len(player_blob)} bytes")
print()

# Now parse INSIDE the blob
print(f"=== Parsing Fields Inside Blob ===")
pos = 0

# The blob itself might start with metadata
print("First 128 bytes (hex):")
for i in range(0, min(128, len(player_blob)), 16):
    chunk = player_blob[i:i+16]
    hex_part = ' '.join(f'{b:02x}' for b in chunk)
    asc_part = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in chunk)
    print(f"  {i:04x}: {hex_part:<48} {asc_part}")
print()

# Try to parse as sequential fields
def read_inner_string(blob: bytes, offset: int) -> tuple[str, int]:
    """Read a string with uint16 length prefix from inside the blob."""
    if offset + 2 > len(blob):
        return "<end>", 0
    length = struct.unpack_from("<H", blob, offset)[0]
    if offset + 2 + length > len(blob):
        return f"<invalid len={length}>", 2
    string_bytes = blob[offset+2 : offset+2+length]
    # Remove null terminator if present
    if b'\x00' in string_bytes:
        string_bytes = string_bytes[:string_bytes.index(b'\x00')]
    try:
        text = string_bytes.decode('cp1252')
    except:
        text = f"<error: {string_bytes[:20].hex()}...>"
    return text, 2 + length

# Field-by-field parsing
print("Attempting sequential field parsing:\n")

# First might be region code (single byte)?
if pos < len(player_blob):
    region = player_blob[pos]
    print(f"Offset 0x{pos:04x}: region_code = 0x{region:02x} ({region})")
    pos += 1

# Try reading strings
for i in range(5):  # Try first 5 fields as strings
    if pos >= len(player_blob):
        break
    text, consumed = read_inner_string(player_blob, pos)
    print(f"Offset 0x{pos:04x}: String field {i} = '{text}' (consumed {consumed} bytes)")
    pos += consumed
    if consumed == 0:
        break

print(f"\nCurrent position: 0x{pos:04x}")

# Show what's left
if pos < len(player_blob):
    remaining = player_blob[pos:pos+64]
    print(f"\nRemaining bytes (next 64):")
    print(f"  Hex: {remaining.hex()}")
    print(f"  Raw: {remaining}")
    
    # Try to interpret as integers
    if len(remaining) >= 4:
        val = struct.unpack_from("<I", remaining, 0)[0]
        print(f"  As uint32: {val}")
    if len(remaining) >= 2:
        val = struct.unpack_from("<H", remaining, 0)[0]
        print(f"  As uint16: {val}")
    if len(remaining) >= 1:
        print(f"  First byte: {remaining[0]}")