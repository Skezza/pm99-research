#!/usr/bin/env python3
"""
Debug Beckham and partial name issues
"""

import struct
from pathlib import Path
import sys
sys.path.insert(0, '.')

from pm99_database_editor import find_player_records, xor_decode

file_path = 'DBDAT/JUG98030.FDI'
file_data = Path(file_path).read_bytes()

print("Searching for all BECKHAM entries before deduplication...")
print("=" * 80)

separator = bytes([0xdd, 0x63, 0x60])
pos = 0x400
beckham_records = []

while pos < len(file_data) - 1000:
    try:
        length = struct.unpack_from("<H", file_data, pos)[0]
        
        if 1000 < length < 100000:
            encoded = file_data[pos+2 : pos+2+length]
            decoded = xor_decode(encoded, 0x61)
            
            if separator in decoded:
                parts = decoded.split(separator)
                
                for part in parts:
                    if 50 <= len(part) <= 200:
                        # Check if contains "Beckham" or "BECKHAM"
                        text = part[5:45].decode('latin-1', errors='ignore').upper()
                        if 'BECKHAM' in text:
                            team_id = struct.unpack_from("<H", part, 0)[0]
                            squad = part[2]
                            beckham_records.append({
                                'offset': pos,
                                'team_id': team_id,
                                'squad': squad,
                                'text': part[5:45].decode('latin-1', errors='ignore'),
                                'hex': part[5:45].hex()
                            })
            
            pos += length + 2
        else:
            pos += 1
    except:
        pos += 1

print(f"Found {len(beckham_records)} raw BECKHAM records:\n")

for i, rec in enumerate(beckham_records, 1):
    print(f"{i}. Team: {rec['team_id']:5}, Squad: {rec['squad']:3}")
    print(f"   Text: {repr(rec['text'][:60])}")
    print(f"   Hex:  {rec['hex'][:40]}...")
    print()

# Now check what the deduplication does
print("\n" + "=" * 80)
print("After deduplication:")
print("=" * 80)

records = find_player_records(file_data)
beckham_final = [(o, r) for o, r in records if 'beckham' in r.name.lower()]

print(f"\nFound {len(beckham_final)} BECKHAM after deduplication:\n")
for offset, record in beckham_final:
    print(f"- {record.name} (Team: {record.team_id}, Squad: {record.squad_number})")

# Also check partial names issue
print("\n" + "=" * 80)
print("Checking partial name examples:")
print("=" * 80)

partial_examples = [
    (o, r) for o, r in records 
    if len(r.name.split()) == 2 and len(r.name.split()[1]) == 1
][:10]

for offset, record in partial_examples:
    print(f"\n{record.name}")
    print(f"  Raw text: {repr(record.raw_data[5:45].decode('latin-1', errors='ignore')[:50])}")