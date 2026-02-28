"""
Re-analyze FDI structure - the directory might be multi-level
"""
import struct
from pathlib import Path

def decode_xor61(data: bytes, offset: int) -> tuple[bytes, int]:
    """Decode XOR-0x61 encoded field at offset."""
    length = struct.unpack_from("<H", data, offset)[0]
    encoded = data[offset+2 : offset+2+length]
    decoded = bytes(b ^ 0x61 for b in encoded)
    return decoded, 2 + length

def read_string_xor(data: bytes, offset: int) -> tuple[str, int]:
    """Read XOR-encoded string."""
    decoded, consumed = decode_xor61(data, offset)
    if b'\x00' in decoded:
        decoded = decoded[:decoded.index(b'\x00')]
    try:
        text = decoded.decode('cp1252')
    except:
        text = f"<error>"
    return text, consumed

data = Path('DBDAT/JUG98030.FDI').read_bytes()

# Read header
signature = data[0:10].decode('ascii', errors='replace')
version = struct.unpack_from("<H", data, 0x10)[0]
num_entries = struct.unpack_from("<I", data, 0x14)[0]

print(f"=== FDI Header ===")
print(f"Signature: {signature}")
print(f"Version: {version}")  
print(f"Directory entries: {num_entries}")
print()

# Read directory entries
print(f"=== Directory Entries at 0x20 ===")
for i in range(num_entries):
    pos = 0x20 + (i * 8)
    offset, tag, index = struct.unpack_from("<IHH", data, pos)
    tag_chr = chr(tag) if 32 <= tag < 127 else '?'
    print(f"Entry {i}: offset=0x{offset:08x}, tag=0x{tag:04x} ('{tag_chr}'), index={index}")
print()

# Check what's at the documented offset 0x410 from verify.txt
print(f"=== Player Record at Documented Offset 0x410 ===")
pos = 0x410

# Show raw bytes
print("Raw bytes (first 128):")
raw = data[pos:pos+128]
for i in range(0, len(raw), 16):
    chunk = raw[i:i+16]
    hex_part = ' '.join(f'{b:02x}' for b in chunk)
    asc_part = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in chunk)
    print(f"  {i:04x}: {hex_part:<48} {asc_part}")
print()

# Parse at 0x410
print("=== Parsing at 0x410 ===")
field1_decoded, field1_consumed = decode_xor61(data, pos)
print(f"Field 1 (metadata):")
print(f"  Length: {field1_consumed - 2} bytes")
print(f"  Decoded (first 64 hex): {field1_decoded[:64].hex()}")
pos += field1_consumed

given_name, consumed = read_string_xor(data, pos)
print(f"\nField 2 (given name): '{given_name}'")
print(f"  Consumed: {consumed} bytes")
pos += consumed

surname, consumed = read_string_xor(data, pos)
print(f"\nField 3 (surname): '{surname}'")
print(f"  Consumed: {consumed} bytes")
pos += consumed

common_name, consumed = read_string_xor(data, pos)
print(f"\nField 4 (common name): '{common_name}'")
print(f"  Consumed: {consumed} bytes")
pos += consumed

print(f"\nTotal consumed: {pos - 0x410} bytes")
print(f"Next position: 0x{pos:08x}")

# Check if there's raw data after the strings
print(f"\n=== Raw Data After Strings ===")
remaining = data[pos:pos+32]
print(f"Next 32 bytes (hex): {remaining.hex()}")
# Try to interpret as various data types
if len(remaining) >= 4:
    print(f"As uint32: {struct.unpack_from('<I', remaining, 0)[0]}")
if len(remaining) >= 2:
    print(f"As uint16: {struct.unpack_from('<H', remaining, 0)[0]}")
if len(remaining) >= 1:
    print(f"First byte: 0x{remaining[0]:02x} = {remaining[0]}")

# Now let's examine the structure at 0x400 more carefully
print(f"\n=== Structure at 0x400 (First Directory Entry) ===")
pos = 0x400
# The first uint16 is 0, suggesting this might be a count or empty marker
count_or_length = struct.unpack_from("<H", data, pos)[0]
print(f"First uint16: {count_or_length}")
pos += 2

# The rest looks like a table of offsets
print("\nInterpreting as offset table (12-byte entries):")
for i in range(10):  # Show first 10
    if pos + 12 > len(data):
        break
    offset = struct.unpack_from("<I", data, pos)[0]
    val1 = struct.unpack_from("<I", data, pos+4)[0]
    val2 = struct.unpack_from("<I", data, pos+8)[0]
    print(f"  Entry {i}: offset=0x{offset:08x}, val1={val1}, val2={val2}")
    pos += 12