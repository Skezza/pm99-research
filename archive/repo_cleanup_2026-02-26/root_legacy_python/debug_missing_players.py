"""Debug script to find missing canonical players in specific sections."""

from pathlib import Path
import struct
from app.xor import xor_decode
from app.models import PlayerRecord

# Missing players
missing = ['Vince BARTRAM', 'Dennis BERGKAMP', 'Lee JONES']

file_path = Path('DBDAT/JUG98030.FDI')
file_data = file_path.read_bytes()
separator = bytes([0xdd, 0x63, 0x60])

print("Scanning for missing players...")
print(f"Missing: {missing}\n")

file_len = len(file_data)
pos = 0x400
section_count = 0

while pos < file_len - 1000 and section_count < 1000:
    try:
        length = struct.unpack_from("<H", file_data, pos)[0]
        
        if not (100 < length < 200000) or pos + 2 + length > file_len:
            pos += 1
            continue
        
        encoded = file_data[pos + 2 : pos + 2 + length]
        decoded = xor_decode(encoded, 0x61)
        text = decoded.decode('latin-1', errors='ignore')
        
        # Check if any missing player is in this section
        found_in_section = []
        for player_name in missing:
            if player_name.upper() in text.upper():
                found_in_section.append(player_name)
        
        if found_in_section:
            print(f"\n{'='*80}")
            print(f"Section at offset {hex(pos)}, length {length}")
            print(f"Found players: {found_in_section}")
            print(f"Has separator: {separator in decoded}")
            
            # Determine which branch would process this
            if 1000 < length < 100000 and separator in decoded:
                print("➜ Would be processed by: SEPARATED RECORDS branch")
            elif 5000 < length < 200000:
                print("➜ Would be processed by: EMBEDDED RECORDS branch")
            else:
                print("➜ ⚠️ SKIPPED - Not in any processing range!")
                print(f"   Length {length} doesn't match any condition:")
                print(f"   - Separated: 1000 < {length} < 100000 AND has_separator={separator in decoded}")
                print(f"   - Embedded: 5000 < {length} < 200000")
        
        pos += length + 2
        section_count += 1
    except Exception as e:
        pos += 1

print(f"\n\nScanned {section_count} sections")
