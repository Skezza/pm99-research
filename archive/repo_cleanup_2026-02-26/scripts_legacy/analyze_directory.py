"""
Analyze FDI directory structure based on FUN_004b57b0 logic
"""
import struct
from pathlib import Path

data = Path('DBDAT/JUG98030.FDI').read_bytes()

print("=== FDI File Structure Analysis ===\n")

# Header
signature = data[0:10].decode('ascii', errors='replace')
version = struct.unpack_from("<H", data, 0x10)[0]
num_entries = struct.unpack_from("<I", data, 0x14)[0]

print(f"Signature: {signature}")
print(f"Version: {version}")
print(f"Directory entries in header: {num_entries}\n")

# According to FUN_004b57b0:
# iVar5 is the FDI file object
# *(int *)(iVar5 + 0xc) points to the directory
# *(int *)(iVar5 + 0x10) is the record count

# The directory at 0x20 points to the actual data structure
first_entry_offset = struct.unpack_from("<I", data, 0x20)[0]
print(f"First directory entry points to: 0x{first_entry_offset:08x}")

# At that offset, check what structure exists
print(f"\n=== Structure at 0x{first_entry_offset:04x} ===")

# First 2 bytes might be record count or length
val = struct.unpack_from("<H", data, first_entry_offset)[0]
print(f"First uint16: {val} (0x{val:04x})")

if val == 0:
    print("→ This is 0, suggesting it's a count or empty marker")
    print("→ The directory likely starts at offset +2")
    
    # Try reading as a table of player record pointers
    print(f"\n=== Player Record Directory (12-byte entries) ===")
    pos = first_entry_offset + 2
    
    for i in range(min(10, 1218)):  # First 10 of 1218 players
        # Each entry might be: offset (4), length (2), id (2), flags (4)
        # OR: offset (4), id (4), flags (4)
        offset = struct.unpack_from("<I", data, pos)[0]
        field1 = struct.unpack_from("<I", data, pos+4)[0]
        field2 = struct.unpack_from("<I", data, pos+8)[0]
        
        print(f"Entry {i:3d} @ 0x{pos:06x}: offset=0x{offset:08x}, f1={field1:8d}, f2={field2:8d}")
        
        # Check if offset is valid
        if offset < len(data):
            # Try to see if it's a player record by checking for length prefix
            try:
                rec_len = struct.unpack_from("<H", data, offset)[0]
                print(f"            → Points to record with length={rec_len} (0x{rec_len:04x})")
            except:
                pass
        
        pos += 12
        
        # Stop if we hit clearly invalid data
        if offset == 0 or offset > len(data):
            print(f"            → Invalid offset, stopping")
            break
else:
    print(f"→ Non-zero value, might be length of directory")
    print(f"→ Or could be first field of first record")