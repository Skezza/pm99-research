"""
Analyze the 52-byte records - likely the actual player data
"""
import struct
from pathlib import Path

def decode_xor61(data: bytes, offset: int) -> tuple[bytes, int]:
    length = struct.unpack_from("<H", data, offset)[0]
    if offset + 2 + length > len(data):
        return b"", 0
    encoded = data[offset+2 : offset+2+length]
    decoded = bytes(b ^ 0x61 for b in encoded)
    return decoded, 2 + length

data = Path('DBDAT/JUG98030.FDI').read_bytes()

print("=== Analyzing 52-Byte Records ===\n")

# Start at first 52-byte record
pos = 0x017e56

for i in range(5):
    decoded, consumed = decode_xor61(data, pos)
    
    print(f"\nRecord {i} @ 0x{pos:06x}:")
    print(f"  Total: {consumed} bytes ({len(decoded)} decoded)")
    print(f"  Hex: {decoded.hex()}")
    print(f"  ASCII: {''.join(chr(b) if 32<=b<127 else '.' for b in decoded)}")
    
    # Try parsing as structured data
    if len(decoded) >= 8:
        # Try as uint32 values
        print(f"  As uint32s:", end="")
        for j in range(min(4, len(decoded)//4)):
            val = struct.unpack_from("<I", decoded, j*4)[0]
            print(f" {val}", end="")
        print()
        
        # Try as uint16 values
        print(f"  As uint16s:", end="")
        for j in range(min(8, len(decoded)//2)):
            val = struct.unpack_from("<H", decoded, j*2)[0]
            print(f" {val}", end="")
        print()
    
    pos += consumed

print(f"\n\nThese 52-byte records likely contain:")
print("  - Player IDs / Team IDs / Match data")
print("  - NOT full player records with names")
print("\nThe actual player names/data are probably in those first 3 large blocks!")