#!/usr/bin/env python3
"""
Find the exact Beckham player record structure
"""

import struct
from pathlib import Path

def xor_decode(data: bytes, key: int = 0x61) -> bytes:
    return bytes(b ^ key for b in data)

file_path = 'DBDAT/JUG98030.FDI'
file_data = Path(file_path).read_bytes()

# Check offset 360700 where we know BECKHAM exists
offset = 360700

print(f"Analyzing offset {offset} where BECKHAM was found...")
print("=" * 80)

# Read section
try:
    length = struct.unpack_from("<H", file_data, offset)[0]
    print(f"Section length: {length}")
    
    encoded = file_data[offset+2 : offset+2+length]
    decoded = xor_decode(encoded, 0x61)
    
    # Find BECKHAM in decoded
    text = decoded.decode('latin-1', errors='ignore')
    beckham_idx = text.upper().find('BECKHAM')
    
    if beckham_idx >= 0:
        print(f"\nFound BECKHAM at position {beckham_idx} in decoded section")
        
        # Show context
        context_start = max(0, beckham_idx - 50)
        context_end = min(len(text), beckham_idx + 100)
        context = text[context_start:context_end]
        print(f"Context: {repr(context)}")
        
        # Try to find the record separator
        separator = bytes([0xdd, 0x63, 0x60])
        if separator in decoded:
            print(f"\nFound separator in section")
            parts = decoded.split(separator)
            print(f"Split into {len(parts)} parts")
            
            # Find which part has BECKHAM
            for i, part in enumerate(parts):
                if b'BECKHAM' in part.upper():
                    print(f"\nPart {i} contains BECKHAM:")
                    print(f"  Length: {len(part)}")
                    print(f"  First 100 bytes: {repr(part[:100].decode('latin-1', errors='ignore'))}")
                    
                    if 50 <= len(part) <= 200:
                        print(f"  ✓ This is a clean record size!")
                        # Parse it
                        team_id = struct.unpack_from("<H", part, 0)[0]
                        squad = part[2]
                        print(f"  Team ID: {team_id}, Squad: {squad}")
                        print(f"  Name region (5-50): {repr(part[5:50].decode('latin-1', errors='ignore'))}")
        else:
            print("\nNo separator found in this section")
            
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()