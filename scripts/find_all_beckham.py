#!/usr/bin/env python3
"""
Find ALL Beckham records in the entire file
"""

import struct
from pathlib import Path

def xor_decode(data: bytes, key: int = 0x61) -> bytes:
    return bytes(b ^ key for b in data)

file_path = 'DBDAT/JUG98030.FDI'
file_data = Path(file_path).read_bytes()

separator = bytes([0xdd, 0x63, 0x60])

print("Searching for ALL Beckham records in entire database...")
print("=" * 80)

pos = 0x400
beckham_records = []

while pos < len(file_data) - 1000:
    try:
        length = struct.unpack_from("<H", file_data, pos)[0]
        
        if 50 < length < 200000:
            encoded = file_data[pos+2 : pos+2+length]
            decoded = xor_decode(encoded, 0x61)
            
            if b'BECKHAM' in decoded.upper() or b'Beckham' in decoded:
                # Found a section with Beckham
                print(f"\n{'='*80}")
                print(f"Offset: {pos}, Length: {length}")
                
                # Check if it has separators
                if separator in decoded:
                    print("✓ Has standard separator")
                    parts = decoded.split(separator)
                    print(f"  Split into {len(parts)} parts")
                    
                    for i, part in enumerate(parts):
                        if b'BECKHAM' in part.upper() or b'Beckham' in part:
                            print(f"\n  Part {i}: Length={len(part)}")
                            if 50 <= len(part) <= 200:
                                print(f"    ✓ Clean record size!")
                                team_id = struct.unpack_from("<H", part, 0)[0]
                                squad = part[2]
                                print(f"    Team: {team_id}, Squad: {squad}")
                                print(f"    Name region: {repr(part[5:50].decode('latin-1', errors='ignore'))}")
                            else:
                                print(f"    First 80 chars: {repr(part[:80].decode('latin-1', errors='ignore'))}")
                else:
                    print("✗ No standard separator - may be different format")
                    # Look for the name pattern
                    text = decoded.decode('latin-1', errors='ignore')
                    import re
                    
                    # Look for the pattern we saw: "Beckham<separator>David Robert BECKHAM"
                    beckham_matches = list(re.finditer(r'([A-Za-z]+)[a-z]{1,2}a(David Robert BECKHAM)', text, re.IGNORECASE))
                    if beckham_matches:
                        for match in beckham_matches:
                            print(f"\n  Found pattern: {repr(match.group(0))}")
                            # Get surrounding context
                            start = max(0, match.start() - 100)
                            end = min(len(text), match.end() + 100)
                            context = text[start:end]
                            print(f"  Context: {repr(context[:200])}")
            
            pos += length + 2
        else:
            pos += 1
    except:
        pos += 1

print("\n" + "=" * 80)
print("Search complete")