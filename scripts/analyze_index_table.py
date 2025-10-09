"""
Analyze the index table at 0x400 to find player record offsets
"""
import struct
from pathlib import Path

data = Path('DBDAT/JUG98030.FDI').read_bytes()

print("=== Index Table Analysis ===\n")

# The structure at 0x400 starts with uint16 = 0
# Then it's likely a packed table of some format

# Try 8-byte entries
print("Trying 8-byte entry format (offset + metadata):")
pos = 0x402  # Skip the initial 0x0000

for i in range(15):
    offset = struct.unpack_from("<I", data, pos)[0]
    meta1 = struct.unpack_from("<H", data, pos+4)[0]
    meta2 = struct.unpack_from("<H", data, pos+6)[0]
    
    print(f"Entry {i:3d} @ 0x{pos:06x}: offset=0x{offset:08x}, m1={meta1:5d}, m2={meta2:5d}", end="")
    
    # Check if offset is valid and try to read record length
    if 0x400 < offset < len(data):
        try:
            rec_len = struct.unpack_from("<H", data, offset)[0]
            if rec_len < 10000:  # Sanity check
                print(f" → rec_len={rec_len}")
            else:
                print(f" → BAD len={rec_len}")
        except:
            print(" → Read error")
    else:
        print(" → Invalid offset")
    
    pos += 8

# Also try 16-byte entries
print("\n\nTrying 16-byte entry format:")
pos = 0x402

for i in range(10):
    offset = struct.unpack_from("<I", data, pos)[0]
    f1 = struct.unpack_from("<I", data, pos+4)[0]
    f2 = struct.unpack_from("<I", data, pos+8)[0]
    f3 = struct.unpack_from("<I", data, pos+12)[0]
    
    print(f"Entry {i:3d}: offset=0x{offset:08x}, f1={f1:8d}, f2={f2:8d}, f3={f3:8d}")
    
    pos += 16