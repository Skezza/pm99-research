"""
Try XOR-decoding the index table
"""
import struct
from pathlib import Path

data = Path('DBDAT/JUG98030.FDI').read_bytes()

# Try decoding the table at 0x400
encoded = data[0x400:0x600]
decoded = bytes(b ^ 0x61 for b in encoded)

print("=== XOR-Decoded Index Table ===\n")
print(f"First 64 bytes (hex): {decoded[:64].hex()}\n")
print(f"As ASCII: {''.join(chr(b) if 32<=b<127 else '.' for b in decoded[:64])}\n")

print("Trying to read as offset table:")
for i in range(15):
    pos = i * 8
    if pos + 8 > len(decoded):
        break
    
    offset = struct.unpack_from("<I", decoded, pos)[0]
    meta1 = struct.unpack_from("<H", decoded, pos+4)[0]
    meta2 = struct.unpack_from("<H", decoded, pos+6)[0]
    
    print(f"Entry {i:3d}: offset=0x{offset:08x} ({offset:8d}), m1={meta1:5d}, m2={meta2:5d}", end="")
    
    # Check validity
    if offset < len(data) and offset > 0:
        try:
            rec_len = struct.unpack_from("<H", data, offset)[0]
            if rec_len < 10000:
                print(f" → rec_len={rec_len}")
            else:
                print(f" → BAD")
        except:
            print(" → ERR")
    else:
        print(" → INVALID")