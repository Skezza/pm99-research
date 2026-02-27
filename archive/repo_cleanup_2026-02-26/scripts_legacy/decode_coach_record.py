"""
Decode the actual coach record at 0x026cf6
"""
import struct
from pathlib import Path

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

# The 260-byte record at 0x026cf6
pos = 0x026cf6

# Decode the outer XOR layer
length = struct.unpack_from("<H", data, pos)[0]
print(f"Record at 0x{pos:06x}:")
print(f"  Length field: {length} bytes\n")

encoded = data[pos+2 : pos+2+length]
decoded = bytes(b ^ 0x61 for b in encoded)

print(f"Decoded blob ({len(decoded)} bytes):")
print(f"  First 128 bytes (hex): {decoded[:128].hex()}")
print(f"  As ASCII: {''.join(chr(b) if 32<=b<127 else '.' for b in decoded[:128])}")
print()

# Try parsing as structured data with inner strings
print("Trying to parse coach names:")
inner_pos = 0

# Skip possible header byte
if inner_pos < len(decoded):
    header_byte = decoded[inner_pos]
    print(f"  Byte 0: 0x{header_byte:02x} ({header_byte})")
    inner_pos += 1

# Try reading name strings
for i in range(5):
    if inner_pos >= len(decoded):
        break
    
    text, consumed = decode_string_32bit(decoded, inner_pos)
    if consumed > 0:
        print(f"  String {i} at offset {inner_pos}: '{text}' (consumed {consumed})")
        inner_pos += consumed
    else:
        print(f"  String {i}: FAILED at offset {inner_pos}")
        break

print(f"\nAfter strings, position: {inner_pos}/{len(decoded)}")

# Show remaining bytes
if inner_pos < len(decoded):
    remaining = decoded[inner_pos:inner_pos+32]
    print(f"Remaining bytes (hex): {remaining.hex()}")
    print(f"As bytes: {list(remaining)}")