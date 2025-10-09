"""
Correct parser based on FUN_00677e30 analysis
Strings inside the blob are XOR'd with 0x61 using 32-bit operations
"""
import struct
from pathlib import Path

def decode_xor61(data: bytes, offset: int) -> tuple[bytes, int]:
    """Decode XOR-0x61 encoded field at offset."""
    length = struct.unpack_from("<H", data, offset)[0]
    encoded = data[offset+2 : offset+2+length]
    decoded = bytes(b ^ 0x61 for b in encoded)
    return decoded, 2 + length

def read_inner_string(blob: bytes, offset: int) -> tuple[str, int]:
    """
    Read string from inside the decoded blob, matching FUN_00677e30 behavior.
    The string has a uint16 length prefix and is XOR-encoded with 0x61.
    """
    if offset + 2 > len(blob):
        return "<end>", 0
    
    # Read string length (in bytes, not including length prefix)
    str_len = struct.unpack_from("<H", blob, offset)[0]
    if offset + 2 + str_len > len(blob):
        return f"<invalid len={str_len}>", 2
    
    # Extract encoded string data
    encoded = blob[offset+2 : offset+2+str_len]
    
    # Decode using 32-bit XOR for efficiency (matching the original code)
    decoded = bytearray()
    
    # Process 4 bytes at a time
    pos = 0
    while pos + 4 <= len(encoded):
        dword = struct.unpack_from("<I", encoded, pos)[0]
        decoded_dword = dword ^ 0x61616161
        decoded.extend(struct.pack("<I", decoded_dword))
        pos += 4
    
    # Handle remaining 0-3 bytes
    if pos + 2 <= len(encoded):
        word = struct.unpack_from("<H", encoded, pos)[0]
        decoded_word = word ^ 0x6161
        decoded.extend(struct.pack("<H", decoded_word))
        pos += 2
    
    if pos < len(encoded):
        byte_val = encoded[pos] ^ 0x61
        decoded.append(byte_val)
    
    # Remove null terminator if present
    if b'\x00' in decoded:
        decoded = decoded[:decoded.index(b'\x00')]
    
    try:
        text = bytes(decoded).decode('cp1252')
    except:
        text = f"<error: {bytes(decoded[:20]).hex()}...>"
    
    # Return consumed bytes: length prefix (2) + string length
    return text, 2 + str_len

data = Path('DBDAT/JUG98030.FDI').read_bytes()

# Get the player record blob at 0x410
player_blob, _ = decode_xor61(data, 0x410)

print(f"=== Player Record at 0x410 (Correct Parsing) ===")
print(f"Blob length: {len(player_blob)} bytes\n")

pos = 0

# First byte is region code
region = player_blob[pos]
print(f"Offset 0x{pos:04x}: region_code = 0x{region:02x} ({region})")
pos += 1

# Read strings
field_names = ["given_name", "surname", "common_name"]

for name in field_names:
    if pos >= len(player_blob):
        break
    text, consumed = read_inner_string(player_blob, pos)
    print(f"Offset 0x{pos:04x}: {name:15s} = '{text}' (consumed {consumed} bytes)")
    pos += consumed

print(f"\nAfter name strings, position: 0x{pos:04x}")

# Show remaining data
if pos < len(player_blob):
    remaining = player_blob[pos:pos+64]
    print(f"\nRemaining bytes (next 64):")
    for i in range(0, len(remaining), 16):
        chunk = remaining[i:i+16]
        hex_part = ' '.join(f'{b:02x}' for b in chunk)
        asc_part = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in chunk)
        print(f"  {i:04x}: {hex_part:<48} {asc_part}")
    
    # Try reading more fields
    print(f"\n--- Parsing Additional Fields ---")
    p = pos
    
    # Try reading uint32
    if p + 4 <= len(player_blob):
        val = struct.unpack_from("<I", player_blob, p)[0]
        print(f"Offset 0x{p:04x}: uint32 = {val} (0x{val:08x})")
        p += 4
    
    # More uint32
    if p + 4 <= len(player_blob):
        val = struct.unpack_from("<I", player_blob, p)[0]
        print(f"Offset 0x{p:04x}: uint32 = {val} (0x{val:08x})")
        p += 4
    
    # Try some uint16 values
    for i in range(3):
        if p + 2 <= len(player_blob):
            val = struct.unpack_from("<H", player_blob, p)[0]
            print(f"Offset 0x{p:04x}: uint16 = {val}")
            p += 2
    
    # Try reading bytes
    for i in range(5):
        if p < len(player_blob):
            val = player_blob[p]
            print(f"Offset 0x{p:04x}: byte = {val}")
            p += 1