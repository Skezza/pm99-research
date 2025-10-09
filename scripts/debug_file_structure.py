"""
Re-analyze: FUN_00677e30 reads FROM file and writes TO buffer
So at 0x410, we have a length prefix followed by encoded data for field 1
"""
import struct
from pathlib import Path

def decode_string_from_file(data: bytes, offset: int) -> tuple[str, int]:
    """
    Mimic FUN_00677e30: read length-prefixed XOR-encoded string from file.
    Returns (decoded_string, bytes_consumed_from_file)
    """
    # Read uint16 length
    length = struct.unpack_from("<H", data, offset)[0]
    
    # Extract encoded bytes
    encoded = data[offset+2 : offset+2+length]
    
    # Decode using 32-bit XOR (matching FUN_00677e30)
    decoded = bytearray()
    pos = 0
    
    # Process 4 bytes at a time
    while pos + 4 <= len(encoded):
        dword = struct.unpack_from("<I", encoded, pos)[0]
        decoded_dword = dword ^ 0x61616161
        decoded.extend(struct.pack("<I", decoded_dword))
        pos += 4
    
    # Handle remaining 2 bytes
    if pos + 2 <= len(encoded):
        word = struct.unpack_from("<H", encoded, pos)[0]
        decoded_word = word ^ 0x6161
        decoded.extend(struct.pack("<H", decoded_word))
        pos += 2
    
    # Handle remaining 1 byte
    if pos < len(encoded):
        byte_val = encoded[pos] ^ 0x61
        decoded.append(byte_val)
    
    # Add null terminator (FUN_00677e30 does this)
    decoded.append(0)
    
    # Remove null terminator for display
    if b'\x00' in decoded:
        decoded = decoded[:decoded.index(b'\x00')]
    
    try:
        text = bytes(decoded).decode('cp1252')
    except:
        text = f"<error: {bytes(decoded[:20]).hex()}>"
    
    # Return bytes consumed from file: 2 (length) + length
    return text, 2 + length

data = Path('DBDAT/JUG98030.FDI').read_bytes()

print(f"=== Player Record Parsing (Direct from File at 0x410) ===\n")

# According to FUN_004a0a30, after allocating the blob based on length at offset 0x24:
# It reads version (uint16) and region_code (byte) 
# Then calls FUN_00677e30 for strings

# Let's check if there's metadata before 0x410
print("Checking structure before 0x410:")
# Look backwards from 0x410
for test_offset in [0x3f0, 0x400, 0x408]:
    val = struct.unpack_from("<H", data, test_offset)[0]
    print(f"  uint16 at 0x{test_offset:04x} = {val} (0x{val:04x})")

print()

# Now parse at 0x410 directly
print("Parsing strings starting at 0x410:")
pos = 0x410

# Try parsing 3 strings
for i, name in enumerate(["Field 1", "Field 2", "Field 3"]):
    if pos < len(data):
        text, consumed = decode_string_from_file(data, pos)
        print(f"Offset 0x{pos:04x}: {name:10s} = '{text[:80]}{'...' if len(text) > 80 else ''}' (consumed {consumed} bytes)")
        pos += consumed

print(f"\nAfter 3 fields, position: 0x{pos:04x}")

# Show what's next
if pos < len(data):
    remaining = data[pos:pos+32]
    print(f"\nNext 32 bytes:")
    hex_part = ' '.join(f'{b:02x}' for b in remaining)
    print(f"  {hex_part}")