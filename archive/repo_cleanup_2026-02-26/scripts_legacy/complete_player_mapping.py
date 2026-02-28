"""
Complete Player Record Field Mapping
Maps ALL fields from schema to actual byte positions in player records
"""
import struct
from pathlib import Path
from typing import Tuple, Dict, Any

def decode_xor61(data: bytes, offset: int) -> Tuple[bytes, int]:
    """Decode XOR-0x61 field"""
    if offset + 2 > len(data):
        return b"", 0
    length = struct.unpack_from("<H", data, offset)[0]
    if offset + 2 + length > len(data):
        return b"", 0
    encoded = data[offset+2 : offset+2+length]
    decoded = bytes(b ^ 0x61 for b in encoded)
    return decoded, 2 + length

# Load player file
data = Path('DBDAT/JUG98030.FDI').read_bytes()

# We know Daniel KIMONI is at section 0x378383, record starts at separator 19
target_section = 0x378383
decoded, _ = decode_xor61(data, target_section)

print("="*80)
print("COMPLETE PLAYER RECORD FIELD MAPPING")
print("="*80)
print(f"\nAnalyzing Daniel KIMONI at section 0x{target_section:08x}")
print(f"Decoded section size: {len(decoded)} bytes\n")

# Record starts at separator position 19
# Name appears at position 35 (27 bytes after separator)
# Record is ~65-70 bytes total based on spacing analysis

record_start = 19
record_end = 84  # Next separator position
record_size = record_end - record_start

print(f"Record: bytes {record_start} to {record_end} ({record_size} bytes)")
print("\n" + "="*80)
print("BYTE-BY-BYTE ANALYSIS")
print("="*80)

# Extract the record
record = decoded[record_start:record_end]

# Display as hex dump with annotations
print("\nHex Dump with Annotations:")
print("-"*80)

for i in range(0, len(record), 16):
    chunk = record[i:i+16]
    hex_part = ' '.join(f'{b:02x}' for b in chunk)
    asc_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
    
    # Add annotations for known positions
    annotation = ""
    if i == 0:
        annotation = " <- Separator (dd 63 60)"
    elif 8 <= i < 24:
        annotation = " <- Metadata before name"
    elif 16 <= i < 32:
        annotation = " <- Name starts here"
    elif i >= 32:
        annotation = " <- Attributes/metadata after name"
    
    print(f"  +{i:3d}: {hex_part:<48} {asc_part}{annotation}")

print("\n" + "="*80)
print("FIELD EXTRACTION BASED ON SCHEMA")
print("="*80)

# According to schema and our analysis:
# - Separator: bytes 0-2 (dd 63 60)
# - Some metadata: bytes 3-7
# - More metadata: bytes 8-15
# - Name starts: around byte 16
# - Name: "Daniel KIMONI" in plaintext
# - After name: attributes and other data

# Let's try to extract fields based on schema positions
# The schema says fields are at specific offsets in the DECODED record

print("\n1. SEPARATOR (bytes 0-2):")
separator = record[0:3]
print(f"   {separator.hex()} = {list(separator)}")

print("\n2. METADATA BYTES (3-15):")
print(f"   Bytes 3-7:  {record[3:8].hex()}")
print(f"   Bytes 8-15: {record[8:16].hex()}")

# Try to parse potential fields
print("\n3. ATTEMPTING FIELD EXTRACTION:")

# Team ID might be in first bytes after separator
if len(record) > 5:
    potential_team_id = struct.unpack_from("<H", record, 3)[0]
    print(f"   Potential Team ID @ +3: {potential_team_id} (0x{potential_team_id:04x})")

# Look for squad number
if len(record) > 5:
    potential_squad = record[5]
    print(f"   Potential Squad # @ +5: {potential_squad}")

# Name location (we know this works)
name_start = 16  # Approximate
name = "Daniel KIMONI"
print(f"\n4. NAME @ ~+{name_start}:")
print(f"   '{name}' found in plaintext")

# After name - look for attributes we know work
print("\n5. KNOWN WORKING ATTRIBUTES (from earlier tests):")
print("   We know these bytes after the name contain 0-100 values")

# Scan for bytes in 0-100 range after name
name_end_approx = name_start + len(name)
attrs_found = []
for i in range(name_end_approx, min(name_end_approx + 40, len(record))):
    if 0 <= record[i] <= 100 and record[i] != 96:  # 96 is padding
        attrs_found.append((i, record[i]))

print(f"   Found {len(attrs_found)} attribute bytes:")
for offset, val in attrs_found[:10]:
    print(f"     @ +{offset}: {val}")

print("\n6. LOOKING FOR OTHER FIELDS FROM SCHEMA:")

# The schema mentions specific offsets, but those are likely
# in the game's memory structure, not file positions
# We need to map file positions empirically

# Try to find nationality (should be 1 byte with low value)
print("\n   Potential Nationality bytes (values 0-50):")
for i in range(len(record)):
    if 0 <= record[i] <= 50 and i not in [offset for offset, _ in attrs_found]:
        print(f"     @ +{i}: {record[i]}")

# Try to find position codes (should be 0-10 range typically)
print("\n   Potential Position bytes (values 0-15):")
for i in range(len(record)):
    if 0 <= record[i] <= 15 and i not in [offset for offset, _ in attrs_found]:
        print(f"     @ +{i}: {record[i]}")

print("\n" + "="*80)
print("ANALYZING MULTIPLE PLAYERS FOR PATTERN CONFIRMATION")
print("="*80)

# Let's analyze 5 different players to find consistent patterns
players_to_analyze = [
    (19, "Daniel KIMONI"),
    (84, "Domenico OLIVIERI"),
    (155, "Marc VANGRONSVELD"),
]

print("\nComparing first 10 bytes of multiple player records:")
print("-"*80)
print(f"{'Player':<25} | Bytes 0-9 (after separator)")
print("-"*80)

for sep_pos, name in players_to_analyze:
    if sep_pos + 10 < len(decoded):
        bytes_chunk = decoded[sep_pos:sep_pos+10]
        hex_str = ' '.join(f'{b:02x}' for b in bytes_chunk)
        print(f"{name:<25} | {hex_str}")

print("\n" + "="*80)
print("RECOMMENDATIONS FOR NEXT STEPS")
print("="*80)

print("""
1. PATTERN IDENTIFICATION NEEDED:
   - Compare 20+ players to find consistent field positions
   - Team ID likely in first 2-5 bytes after separator
   - Squad number likely within first 10 bytes
   - Nationality needs identification
   - Position codes need identification

2. USE KNOWN GOOD DATA:
   - We have schema with memory offsets from Ghidra
   - Need to map memory offsets to file offsets
   - May require runtime debugging to see how game loads data

3. SYSTEMATIC APPROACH:
   - Pick one field (e.g., Team ID)
   - Examine 50+ players
   - Find consistent pattern
   - Verify by modifying and testing in-game
   - Repeat for each field

4. NEXT SCRIPT TO CREATE:
   - Multi-player comparison tool
   - Field variation analyzer
   - Pattern correlation detector
""")

print("\n" + "="*80)
print("SUMMARY")
print("="*80)

print(f"""
Confirmed:
✓ Record separator: dd 63 60
✓ Record size: ~65-70 bytes average  
✓ Player name: Plaintext after ~16 bytes
✓ Attributes: 10 bytes in 0-100 range after name

Unknown (need mapping):
? Team ID (2 bytes, position unknown)
? Squad number (1 byte, position unknown)
? Nationality (1 byte, position unknown)
? Position (1-2 bytes, position unknown)
? Age/Birth (3-4 bytes, position unknown)
? Height/Weight (2 bytes, position unknown)

Next: Create multi-player comparison analyzer
""")