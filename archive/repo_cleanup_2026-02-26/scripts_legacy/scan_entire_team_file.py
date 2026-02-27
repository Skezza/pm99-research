"""
Scan ENTIRE team file for ALL XOR sections and team data
"""
import struct
from pathlib import Path

data = Path('DBDAT/EQ98030.FDI').read_bytes()

print("="*80)
print("COMPLETE FILE SCAN - EQ98030.FDI")
print("="*80)
print(f"File size: {len(data):,} bytes ({len(data)/1024:.1f} KB)\n")

# Read FDI directory
signature = data[0:10].decode('ascii', errors='replace')
version = struct.unpack_from("<H", data, 0x10)[0]
num_entries = struct.unpack_from("<I", data, 0x14)[0]

print(f"FDI Header:")
print(f"  Signature: {signature}")
print(f"  Version: {version}")
print(f"  Directory entries: {num_entries}\n")

print(f"Directory entries:")
print("-"*80)
for i in range(num_entries):
    offset = 0x20 + (i * 8)
    entry_offset, tag, index = struct.unpack_from("<IHH", data, offset)
    print(f"  Entry {i:2d}: offset=0x{entry_offset:08x} ({entry_offset:8d}), tag=0x{tag:04x}, index={index:4d}")

# Scan for ALL XOR-encoded sections
print("\n" + "="*80)
print("SCANNING FOR ALL XOR-ENCODED SECTIONS")
print("="*80)

xor_sections = []
pos = 0x100  # Start after header
scan_limit = len(data)

print(f"\nScanning from 0x{pos:08x} to 0x{scan_limit:08x}...")

while pos < scan_limit - 1000:
    try:
        # Try reading length prefix
        length = struct.unpack_from("<H", data, pos)[0]
        
        # Length should be reasonable
        if 100 < length < 100000 and pos + 2 + length <= len(data):
            # Try XOR decoding first 100 bytes
            encoded = data[pos + 2 : pos + 2 + min(100, length)]
            decoded_sample = bytes(b ^ 0x61 for b in encoded)
            
            # Check if it looks like text (printable ASCII)
            printable_count = sum(1 for b in decoded_sample if 32 <= b < 127 or b in [9, 10, 13])
            
            if printable_count > 40:  # >40% printable
                xor_sections.append((pos, length))
                print(f"  XOR section @ 0x{pos:08x}, length={length:6d} bytes")
                print(f"    Preview: {decoded_sample[:60]}")
                pos += length + 2
                continue
        
        pos += 1
    except:
        pos += 1

print(f"\nFound {len(xor_sections)} XOR-encoded sections")

# Decode each section and search for separator pattern
print("\n" + "="*80)
print("SEARCHING FOR TEAM RECORDS IN ALL SECTIONS")
print("="*80)

separator = bytes([0x61, 0xdd, 0x63])
all_teams_found = 0

for section_num, (sec_offset, sec_length) in enumerate(xor_sections):
    # Decode section
    encoded = data[sec_offset + 2 : sec_offset + 2 + sec_length]
    decoded = bytes(b ^ 0x61 for b in encoded)
    
    # Search for separator
    positions = []
    pos = 0
    while pos < len(decoded):
        pos = decoded.find(separator, pos)
        if pos == -1:
            break
        positions.append(pos)
        pos += 3
    
    if positions:
        print(f"\nSection {section_num+1} @ 0x{sec_offset:08x} ({sec_length:,} bytes):")
        print(f"  Found {len(positions)} team records")
        all_teams_found += len(positions)
        
        # Show first 5 team names
        import re
        for i in range(min(5, len(positions))):
            sep_pos = positions[i]
            next_sep = positions[i+1] if i+1 < len(positions) else min(sep_pos + 200, len(decoded))
            record = decoded[sep_pos:next_sep]
            
            # Extract team name
            match = re.search(rb'[\x20-\x7e]{5,100}', record[3:])
            if match:
                text = match.group().decode('latin1', errors='replace')
                # Find first capital letter
                for j, c in enumerate(text):
                    if c.isupper():
                        text = text[j:min(j+40, len(text))]
                        break
                print(f"    {i+1}. {text}")

print(f"\n" + "="*80)
print(f"TOTAL TEAMS FOUND: {all_teams_found}")
print("="*80)

# Also search for raw separator pattern in non-XOR data
print(f"\nSearching for separator in non-XOR-encoded data...")
raw_separator = bytes([0xdd, 0x63, 0x60])  # Before XOR
raw_positions = []
pos = 0
while pos < len(data):
    pos = data.find(raw_separator, pos)
    if pos == -1:
        break
    raw_positions.append(pos)
    pos += 3

print(f"Found {len(raw_positions)} raw separator patterns")
if raw_positions:
    print(f"First 10 positions: {raw_positions[:10]}")

print(f"\n" + "="*80)
print("ANALYSIS SUMMARY")
print("="*80)
print(f"""
XOR sections found: {len(xor_sections)}
Teams with separator pattern: {all_teams_found}
Raw separators (non-XOR): {len(raw_positions)}

The discrepancy with 544 teams suggests:
1. Teams might be stored across MULTIPLE files
2. OR teams are in a different format without separator
3. OR the 544 reference includes all divisions/leagues across files

Player team_ids (3712-3807) = ~96 unique teams
This suggests the main team file has ~96-100 teams, not 544.

Recommendation: Check other database files for more teams
""")