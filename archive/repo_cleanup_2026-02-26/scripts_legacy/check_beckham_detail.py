#!/usr/bin/env python3
"""
Check Beckham's exact name in database
"""

import struct
from pathlib import Path
import sys
sys.path.insert(0, '.')

from pm99_database_editor import find_player_records, xor_decode

file_path = 'DBDAT/JUG98030.FDI'
file_data = Path(file_path).read_bytes()

print("Searching for ALL Beckham entries...")
print("=" * 80)

# Find all records
records = find_player_records(file_data)

# Find all Beckham entries
beckham_records = [(o, r) for o, r in records if 'beckham' in r.name.lower()]

print(f"Found {len(beckham_records)} Beckham record(s):\n")

for offset, record in beckham_records:
    print(f"Name: {record.name}")
    print(f"Team: {record.team_id}, Squad: {record.squad_number}")
    print(f"Position: {record.get_position_name()}")
    print(f"Raw bytes (5-50): {repr(record.raw_data[5:50].decode('latin-1', errors='ignore'))}")
    print()

# Also search raw data for "BECKHAM" to see all occurrences
print("\n" + "=" * 80)
print("Searching raw file for 'BECKHAM' patterns...")
print("=" * 80)

pos = 0
beckham_positions = []

while pos < len(file_data) - 100:
    try:
        length = struct.unpack_from("<H", file_data, pos)[0]
        
        if 50 < length < 100000:
            encoded = file_data[pos+2 : pos+2+length]
            decoded = xor_decode(encoded, 0x61)
            text = decoded.decode('latin-1', errors='ignore').upper()
            
            if 'BECKHAM' in text:
                # Extract context around BECKHAM
                beckham_idx = text.find('BECKHAM')
                context_start = max(0, beckham_idx - 30)
                context_end = min(len(text), beckham_idx + 50)
                context = text[context_start:context_end]
                
                # Try to parse it
                import re
                name_match = re.search(r'([A-Z][A-Z\s]{5,40}BECKHAM[A-Z\s]{0,20})', text[max(0, beckham_idx-30):beckham_idx+30])
                if name_match:
                    print(f"\nAt offset {pos}:")
                    print(f"  Full name candidate: {name_match.group(1).strip()}")
                    print(f"  Context: ...{context}...")
            
            pos += length + 2
        else:
            pos += 1
    except:
        pos += 1