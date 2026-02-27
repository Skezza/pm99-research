"""
Debug script to analyze the first player record structure.
Maps raw bytes to fields based on sequential parsing.
"""
import struct
from pathlib import Path

def decode_xor61(data: bytes, offset: int) -> tuple[bytes, int]:
    """Decode XOR-0x61 encoded field at offset. Returns (decoded_bytes, consumed_length)."""
    length = struct.unpack_from("<H", data, offset)[0]
    encoded = data[offset+2 : offset+2+length]
    decoded = bytes(b ^ 0x61 for b in encoded)
    return decoded, 2 + length  # length prefix + data

def read_string_xor(data: bytes, offset: int) -> tuple[str, int]:
    """Read XOR-encoded string. Returns (string, consumed_length)."""
    decoded, consumed = decode_xor61(data, offset)
    # String might be null-terminated
    if b'\x00' in decoded:
        decoded = decoded[:decoded.index(b'\x00')]
    try:
        text = decoded.decode('cp1252')
    except:
        text = f"<decode_error: {decoded.hex()}>"
    return text, consumed

# Load the FDI file
data = Path('DBDAT/JUG98030.FDI').read_bytes()

# Read FDI header
signature = data[0:10].decode('ascii', errors='replace')
version = struct.unpack_from("<H", data, 0x10)[0]
num_entries = struct.unpack_from("<I", data, 0x14)[0]

print(f"=== FDI File Header ===")
print(f"Signature: {signature}")
print(f"Version: {version}")
print(f"Entries: {num_entries}")
print()

# Read first directory entry
dir_offset = 0x20  # Directory starts at 0x20
entry_offset, tag, index = struct.unpack_from("<IHH", data, dir_offset)

print(f"=== First Directory Entry ===")
print(f"Offset: 0x{entry_offset:08x}")
print(f"Tag: 0x{tag:04x} ('{chr(tag) if 32 <= tag < 127 else '?'}')")
print(f"Index: {index}")
print()

# Now parse the player record at that offset
print(f"=== Player Record at 0x{entry_offset:08x} ===")
pos = entry_offset

# Show first 128 bytes of raw data
print("Raw bytes (first 128):")
raw_chunk = data[pos:pos+128]
for i in range(0, len(raw_chunk), 16):
    chunk = raw_chunk[i:i+16]
    hex_part = ' '.join(f'{b:02x}' for b in chunk)
    asc_part = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in chunk)
    print(f"  {i:04x}: {hex_part:<48} {asc_part}")
print()

# Try to parse sequentially
print("=== Sequential Parsing ===")

# Field 1: Should be some metadata blob
print(f"Field 1 at 0x{pos:08x}:")
field1_decoded, field1_consumed = decode_xor61(data, pos)
print(f"  Length: {field1_consumed - 2} bytes")
print(f"  Consumed: {field1_consumed} bytes total")
print(f"  Decoded (hex): {field1_decoded[:64].hex()}")
print(f"  Decoded (first 64 chars): {field1_decoded[:64]}")
pos += field1_consumed

# Field 2: Should be given name
print(f"\nField 2 at 0x{pos:08x}:")
given_name, field2_consumed = read_string_xor(data, pos)
print(f"  Given name: '{given_name}'")
print(f"  Consumed: {field2_consumed} bytes")
pos += field2_consumed

# Field 3: Should be surname
print(f"\nField 3 at 0x{pos:08x}:")
surname, field3_consumed = read_string_xor(data, pos)
print(f"  Surname: '{surname}'")
print(f"  Consumed: {field3_consumed} bytes")
pos += field3_consumed

# Field 4: Common name (might be empty)
print(f"\nField 4 at 0x{pos:08x}:")
common_name, field4_consumed = read_string_xor(data, pos)
print(f"  Common name: '{common_name}'")
print(f"  Consumed: {field4_consumed} bytes")
pos += field4_consumed

# After the strings, we should have raw bytes for other fields
print(f"\nRemaining data at 0x{pos:08x}:")
remaining = data[pos:pos+64]
print(f"  Next 64 bytes (hex): {remaining.hex()}")
print(f"  As bytes: {remaining}")

# Try to parse birth date (should be at specific offset in the decoded blob or raw bytes)
# According to schema, birth_day/month/year are stored somewhere
print(f"\n=== Trying to Find Birth Date ===")
# The Ghidra code writes to param_1[0x24], [0x25], [0x26] for day, month, year
# But we need to figure out where in the FILE these come from

# Let's check the first field's decoded data more carefully
print(f"Field 1 decoded data analysis:")
print(f"  Length: {len(field1_decoded)} bytes")
if len(field1_decoded) >= 10:
    # Try to interpret various positions
    for offset in range(0, min(20, len(field1_decoded))):
        byte_val = field1_decoded[offset]
        print(f"  Offset {offset:02x}: 0x{byte_val:02x} = {byte_val:3d}")

print(f"\n=== Summary ===")
print(f"Total bytes consumed so far: {pos - entry_offset}")
print(f"Starting offset: 0x{entry_offset:08x}")
print(f"Current position: 0x{pos:08x}")