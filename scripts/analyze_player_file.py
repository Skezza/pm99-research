"""
Comprehensive analysis of JUG98030.FDI to locate player names.
Based on successful coach file analysis approach.
"""
import struct
import re
from pathlib import Path
from typing import List, Tuple

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

def find_name_patterns(data: bytes) -> List[Tuple[int, str]]:
    """Find potential player names (Given SURNAME or Given Surname patterns)"""
    matches = []
    
    # Pattern 1: Given SURNAME (all caps surname)
    pattern1 = rb'([A-Z][a-z]{2,15})\s+([A-Z]{3,20})'
    # Pattern 2: Given Surname (mixed case)
    pattern2 = rb'([A-Z][a-z]{2,15})\s+([A-Z][a-z]{2,20})'
    
    for pattern in [pattern1, pattern2]:
        for match in re.finditer(pattern, data):
            try:
                given = match.group(1).decode('latin1')
                surname = match.group(2).decode('latin1')
                # Skip common non-names
                skip_words = ['THE', 'AND', 'FOR', 'WITH', 'FROM', 'ABOUT', 'WHEN', 'WHERE']
                if surname.upper() in skip_words or len(given) < 3 or len(surname) < 3:
                    continue
                full_name = f"{given} {surname}"
                matches.append((match.start(), full_name))
            except:
                continue
    
    return matches

def analyze_directory(data: bytes) -> List[Tuple[int, int, int]]:
    """Parse FDI directory entries"""
    version = struct.unpack_from("<H", data, 0x10)[0]
    num_entries = struct.unpack_from("<I", data, 0x14)[0]
    
    print(f"=== FDI Header ===")
    print(f"Version: {version}")
    print(f"Directory entries: {num_entries}")
    print()
    
    entries = []
    for i in range(num_entries):
        offset = 0x20 + (i * 8)
        if offset + 8 > len(data):
            break
        entry_offset, tag, index = struct.unpack_from("<IHH", data, offset)
        entries.append((entry_offset, tag, index))
        print(f"Entry {i}: offset=0x{entry_offset:08x}, tag=0x{tag:04x}, index={index}")
    
    return entries

print("=" * 80)
print("COMPREHENSIVE PLAYER FILE ANALYSIS")
print("=" * 80)

data = Path('DBDAT/JUG98030.FDI').read_bytes()
print(f"\nFile size: {len(data):,} bytes ({len(data)/1024:.1f} KB)\n")

# Parse directory
entries = analyze_directory(data)

print("\n" + "=" * 80)
print("ANALYZING EACH DIRECTORY ENTRY")
print("=" * 80)

# Analyze each directory entry
for i, (entry_offset, tag, index) in enumerate(entries):
    print(f"\n{'='*60}")
    print(f"ENTRY {i}: Offset 0x{entry_offset:08x}")
    print(f"{'='*60}")
    
    if entry_offset >= len(data):
        print(f"❌ Offset beyond file size!")
        continue
    
    # Check what's at this offset
    marker = struct.unpack_from("<H", data, entry_offset)[0]
    print(f"Marker at offset: 0x{marker:04x}")
    
    if marker == 0:
        print("✓ Zero marker - data section starts here")
        pos = entry_offset + 2  # Skip the marker
    else:
        pos = entry_offset
    
    # Try to decode records from this position
    print(f"\nTrying to decode records starting at 0x{pos:08x}:")
    
    record_count = 0
    max_records = 10  # Sample first 10 records
    
    while record_count < max_records and pos < len(data):
        decoded, consumed = decode_xor61(data, pos)
        
        if consumed == 0 or consumed > 100000:  # Sanity check
            print(f"  Record {record_count}: Invalid (consumed={consumed})")
            break
        
        # Search for names in decoded data
        names = find_name_patterns(decoded)
        
        if names:
            print(f"  Record {record_count} @ 0x{pos:08x} ({consumed-2} bytes):")
            print(f"    ✓ Found {len(names)} name(s):")
            for offset, name in names[:5]:  # Show first 5 names
                print(f"      - {name}")
        else:
            # Show first few bytes if no names found
            preview = decoded[:64].hex()[:80]
            print(f"  Record {record_count} @ 0x{pos:08x} ({consumed-2} bytes): {preview}...")
        
        pos += consumed
        record_count += 1
    
    print(f"\nProcessed {record_count} records from this entry")
    
    # If we found names, this might be the player section
    if record_count > 0:
        # Do a deeper scan of the first record
        first_decoded, _ = decode_xor61(data, entry_offset + 2 if marker == 0 else entry_offset)
        all_names = find_name_patterns(first_decoded)
        if all_names:
            print(f"\n🎯 POTENTIAL PLAYER SECTION FOUND!")
            print(f"   Total names in first record: {len(all_names)}")
            print(f"   Sample names:")
            for offset, name in all_names[:20]:
                print(f"     @ +{offset:5d}: {name}")

print("\n" + "=" * 80)
print("DEEP SCAN: Looking for names in ALL decoded sections")
print("=" * 80)

# Scan entire file for XOR-encoded sections that might contain names
scan_start = 0x400  # Start after header
pos = scan_start
total_names_found = 0
sections_with_names = []

while pos < len(data) - 100:  # Leave room for length field
    decoded, consumed = decode_xor61(data, pos)
    
    if consumed > 0 and consumed < 100000:  # Valid-looking record
        names = find_name_patterns(decoded)
        if names:
            total_names_found += len(names)
            sections_with_names.append((pos, len(names), consumed))
            
            if len(sections_with_names) <= 5:  # Show first 5 sections with names
                print(f"\n📍 Section @ 0x{pos:08x} ({consumed-2} bytes): {len(names)} names")
                for offset, name in names[:10]:
                    print(f"   {name}")
        
        pos += consumed
    else:
        pos += 1  # Move forward byte by byte if no valid record

print(f"\n{'='*80}")
print(f"SUMMARY")
print(f"{'='*80}")
print(f"Total sections with names: {len(sections_with_names)}")
print(f"Total names found: {total_names_found}")

if sections_with_names:
    print(f"\nSections with most names:")
    sections_with_names.sort(key=lambda x: x[1], reverse=True)
    for offset, count, size in sections_with_names[:10]:
        print(f"  0x{offset:08x}: {count:4d} names ({size:6d} bytes)")