"""Debug script to see if BARTRAM and JONES are parsed but lost."""

from pathlib import Path
import struct
from app.xor import xor_decode
from app.models import PlayerRecord

file_path = Path('DBDAT/JUG98030.FDI')
file_data = file_path.read_bytes()
separator = bytes([0xdd, 0x63, 0x60])

# Specific offsets from debug output where BARTRAM and JONES appear
bartram_offset = 0x9f910  # length 13568
jones_offset = 0xb3f1e    # length 16655

print("Checking BARTRAM section at", hex(bartram_offset))
print("="*80)

length = struct.unpack_from("<H", file_data, bartram_offset)[0]
print(f"Length: {length}")

encoded = file_data[bartram_offset + 2 : bartram_offset + 2 + length]
decoded = xor_decode(encoded, 0x61)

print(f"Has separator: {separator in decoded}")
print(f"Number of parts when split: {len(decoded.split(separator))}")

parts = decoded.split(separator)
bartram_found = False
for i, part in enumerate(parts):
    if 50 <= len(part) <= 200:
        try:
            rec = PlayerRecord.from_bytes(part, bartram_offset)
            if rec.name and 'BARTRAM' in rec.name.upper():
                print(f"\n✓ Found BARTRAM in part {i}:")
                print(f"  Name: {rec.name}")
                print(f"  Part length: {len(part)}")
                print(f"  Team ID: {getattr(rec, 'team_id', 'N/A')}")
                bartram_found = True
        except Exception as e:
            if 'BARTRAM' in part.decode('latin-1', errors='ignore').upper():
                print(f"\n✗ BARTRAM in part {i} but parse failed: {e}")
                print(f"  Part length: {len(part)}")

if not bartram_found:
    print("\n✗ BARTRAM not found in any parsed parts!")
    # Check raw text
    text = decoded.decode('latin-1', errors='ignore')
    if 'BARTRAM' in text.upper():
        print(f"  But 'BARTRAM' IS in the decoded text")
        idx = text.upper().find('BARTRAM')
        print(f"  Found at position {idx}: ...{text[max(0,idx-20):idx+30]}...")

print("\n" + "="*80)
print("Checking JONES section at", hex(jones_offset))
print("="*80)

length = struct.unpack_from("<H", file_data, jones_offset)[0]
print(f"Length: {length}")

encoded = file_data[jones_offset + 2 : jones_offset + 2 + length]
decoded = xor_decode(encoded, 0x61)

print(f"Has separator: {separator in decoded}")
print(f"Number of parts when split: {len(decoded.split(separator))}")

parts = decoded.split(separator)
jones_found = False
for i, part in enumerate(parts):
    if 50 <= len(part) <= 200:
        try:
            rec = PlayerRecord.from_bytes(part, jones_offset)
            if rec.name and 'JONES' in rec.name.upper() and 'LEE' in rec.name.upper():
                print(f"\n✓ Found Lee JONES in part {i}:")
                print(f"  Name: {rec.name}")
                print(f"  Part length: {len(part)}")
                print(f"  Team ID: {getattr(rec, 'team_id', 'N/A')}")
                jones_found = True
        except Exception as e:
            if 'LEE' in part.decode('latin-1', errors='ignore').upper() and 'JONES' in part.decode('latin-1', errors='ignore').upper():
                print(f"\n✗ Lee JONES in part {i} but parse failed: {e}")
                print(f"  Part length: {len(part)}")

if not jones_found:
    print("\n✗ Lee JONES not found in any parsed parts!")
    text = decoded.decode('latin-1', errors='ignore')
    if 'JONES' in text.upper() and 'LEE' in text.upper():
        print(f"  But 'LEE JONES' IS in the decoded text")
        idx = text.upper().find('LEE')
        print(f"  Found at position {idx}: ...{text[max(0,idx-20):idx+50]}...")
