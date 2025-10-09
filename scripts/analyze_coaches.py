"""
Analyze ENT98030.FDI (Coaches) - simpler file to learn the format
"""
import struct
from pathlib import Path

def decode_xor61(data: bytes, offset: int) -> tuple[bytes, int]:
    """Decode XOR-0x61 field"""
    if offset + 2 > len(data):
        return b"", 0
    length = struct.unpack_from("<H", data, offset)[0]
    if offset + 2 + length > len(data):
        return b"", 0
    encoded = data[offset+2 : offset+2+length]
    decoded = bytes(b ^ 0x61 for b in encoded)
    return decoded, 2 + length

def decode_string_32bit(blob: bytes, offset: int) -> tuple[str, int]:
    """Decode string using 32-bit XOR"""
    if offset + 2 > len(blob):
        return "", 0
    
    length = struct.unpack_from("<H", blob, offset)[0]
    if length > 500 or offset + 2 + length > len(blob):
        return "", 0
    
    encoded = blob[offset+2 : offset+2+length]
    decoded = bytearray()
    
    p = 0
    while p + 4 <= len(encoded):
        dword = struct.unpack_from("<I", encoded, p)[0]
        decoded.extend(struct.pack("<I", dword ^ 0x61616161))
        p += 4
    if p + 2 <= len(encoded):
        word = struct.unpack_from("<H", encoded, p)[0]
        decoded.extend(struct.pack("<H", word ^ 0x6161))
        p += 2
    if p < len(encoded):
        decoded.append(encoded[p] ^ 0x61)
    
    if b'\x00' in decoded:
        decoded = decoded[:decoded.index(b'\x00')]
    
    try:
        return bytes(decoded).decode('cp1252', errors='replace'), 2 + length
    except:
        return "", 2 + length

data = Path('DBDAT/ENT98030.FDI').read_bytes()

print("=== ENT98030.FDI (Coaches) Analysis ===\n")
print(f"File size: {len(data):,} bytes\n")

# Read header
signature = data[0:10].decode('ascii', errors='replace')
version = struct.unpack_from("<H", data, 0x10)[0]
num_entries = struct.unpack_from("<I", data, 0x14)[0]

print(f"Header:")
print(f"  Signature: {signature}")
print(f"  Version: {version}")
print(f"  Directory entries: {num_entries}")
print()

# Read directory
print("Directory:")
for i in range(num_entries):
    pos = 0x20 + (i * 8)
    offset, tag, index = struct.unpack_from("<IHH", data, pos)
    print(f"  Entry {i}: offset=0x{offset:08x}, tag=0x{tag:04x}, index={index}")
print()

# Get first directory entry
first_offset = struct.unpack_from("<I", data, 0x20)[0]
print(f"First directory points to: 0x{first_offset:08x}")

# Check structure at that offset
print(f"\n=== Structure at 0x{first_offset:04x} ===")
marker = struct.unpack_from("<H", data, first_offset)[0]
print(f"First uint16: {marker} (0x{marker:04x})")

# Parse sequential records
print(f"\n=== Sequential Records ===")
pos = first_offset + 2  # Skip marker

for i in range(30):  # Try first 30 records
    if pos >= len(data):
        break
    
    start_pos = pos
    decoded, consumed = decode_xor61(data, pos)
    
    if consumed == 0:
        print(f"[{i}] @ 0x{pos:06x}: FAILED")
        break
    
    print(f"[{i}] @ 0x{pos:06x}: {consumed:5d} bytes", end="")
    
    # Try to extract coach name
    if len(decoded) > 10:
        inner_pos = 1  # Skip first byte (region/type)
        given, c1 = decode_string_32bit(decoded, inner_pos)
        if c1 > 0:
            inner_pos += c1
            surname, c2 = decode_string_32bit(decoded, inner_pos)
            if c2 > 0:
                name = f"{given} {surname}".strip()
                if name and len(name) > 1:
                    print(f" → {name}")
                else:
                    print(f" → [no valid name]")
            else:
                print(f" → [surname failed]")
        else:
            print(f" → [parse failed, hex: {decoded[:32].hex()}]")
    else:
        print(f" → [tiny: {decoded.hex()}]")
    
    pos += consumed

print(f"\n=== Summary ===")
print(f"Processed up to: 0x{pos:06x}")
print(f"Bytes consumed: {pos - (first_offset + 2):,}")