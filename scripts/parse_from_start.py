"""
Parse player records starting from actual beginning at 0x402
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

def decode_inner_string(blob: bytes, offset: int) -> tuple[str, int]:
    """Decode string using 32-bit XOR"""
    if offset + 2 > len(blob):
        return "", 0
    
    length = struct.unpack_from("<H", blob, offset)[0]
    if length > 500 or offset + 2 + length > len(blob):
        return "", 0
    
    encoded = blob[offset+2 : offset+2+length]
    decoded_str = bytearray()
    
    p = 0
    while p + 4 <= len(encoded):
        dword = struct.unpack_from("<I", encoded, p)[0]
        decoded_str.extend(struct.pack("<I", dword ^ 0x61616161))
        p += 4
    if p + 2 <= len(encoded):
        word = struct.unpack_from("<H", encoded, p)[0]
        decoded_str.extend(struct.pack("<H", word ^ 0x6161))
        p += 2
    if p < len(encoded):
        decoded_str.append(encoded[p] ^ 0x61)
    
    if b'\x00' in decoded_str:
        decoded_str = decoded_str[:decoded_str.index(b'\x00')]
    
    try:
        text = bytes(decoded_str).decode('cp1252', errors='replace')
        return text, 2 + length
    except:
        return "", 2 + length

data = Path('DBDAT/JUG98030.FDI').read_bytes()

print("=== Parsing from 0x402 (Actual Start) ===\n")

# Check what's at 0x400
header = struct.unpack_from("<H", data, 0x400)[0]
print(f"Header at 0x400: {header} (0x{header:04x})")
print()

pos = 0x402
for i in range(25):
    if pos >= len(data):
        break
    
    start_pos = pos
    decoded, consumed = decode_xor61(data, pos)
    
    if consumed == 0:
        print(f"[{i}] @ 0x{pos:06x}: PARSE FAILED")
        break
    
    print(f"[{i}] @ 0x{pos:06x}: {consumed:5d} bytes", end="")
    
    # Try to extract name
    if len(decoded) > 10:
        inner_pos = 1  # Skip region byte
        given, c1 = decode_inner_string(decoded, inner_pos)
        if c1 > 0:
            inner_pos += c1
            surname, c2 = decode_inner_string(decoded, inner_pos)
            if given or surname:
                name = f"{given} {surname}".strip()
                print(f" → {name}")
            else:
                print(f" → [no name, first bytes: {decoded[:16].hex()}]")
        else:
            print(f" → [parse failed, bytes: {decoded[:16].hex()}]")
    else:
        print(f" → [tiny: {decoded.hex()}]")
    
    pos += consumed
    
    # Highlight the documented offset
    if start_pos <= 0x410 < pos:
        print(f"    ^^^ Contains documented offset 0x410")

print(f"\nFinal position: 0x{pos:06x}")
print(f"Total bytes consumed: {pos - 0x402:,}")