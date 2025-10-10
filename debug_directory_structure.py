#!/usr/bin/env python3
"""
Debug FDI directory structure
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from app.io import FDIFile
from app.xor import decode_entry
from pathlib import Path

def analyze_fdi_directory(file_path, file_type):
    print(f"\n{'='*60}")
    print(f"Analyzing {file_type}: {file_path}")
    print(f"{'='*60}")
    
    # Load FDI file
    fdi = FDIFile(file_path)
    fdi.load()
    
    print(f"\nHeader Information:")
    print(f"  Signature: {fdi.header.signature}")
    print(f"  Record Count: {fdi.header.record_count}")
    print(f"  Version: {fdi.header.version}")
    print(f"  Max Offset: 0x{fdi.header.max_offset:x}")
    print(f"  Directory Size: {fdi.header.dir_size} bytes ({fdi.header.dir_size // 8} entries)")
    
    print(f"\nDirectory Entries: {len(fdi.directory)}")
    
    # Group by tag
    by_tag = {}
    for entry in fdi.directory:
        tag_char = chr(entry.tag) if 32 <= entry.tag < 127 else f"0x{entry.tag:x}"
        if tag_char not in by_tag:
            by_tag[tag_char] = []
        by_tag[tag_char].append(entry)
    
    print(f"\nEntries by Tag:")
    for tag, entries in sorted(by_tag.items()):
        print(f"  Tag '{tag}': {len(entries)} entries")
        # Show first 3 entries
        for i, entry in enumerate(entries[:3]):
            print(f"    [{i}] offset=0x{entry.offset:x}, index={entry.index}")
    
    # Try decoding a few entries of each type
    print(f"\nSample Decoded Entries:")
    for tag, entries in sorted(by_tag.items()):
        print(f"\n  Tag '{tag}' samples:")
        for i, entry in enumerate(entries[:2]):
            try:
                data = Path(file_path).read_bytes()
                decoded, length = decode_entry(data, entry.offset)
                # Show first 100 chars as hex and ascii
                hex_preview = decoded[:100].hex()
                ascii_preview = ''.join(chr(b) if 32 <= b < 127 else '.' for b in decoded[:100])
                print(f"    [{i}] offset=0x{entry.offset:x}, len={length}")
                print(f"        hex: {hex_preview[:80]}...")
                print(f"        ascii: {ascii_preview[:60]}...")
            except Exception as e:
                print(f"    [{i}] offset=0x{entry.offset:x} - ERROR: {e}")

if __name__ == "__main__":
    analyze_fdi_directory('DBDAT/ENT98030.FDI', 'Coaches')
    analyze_fdi_directory('DBDAT/EQ98030.FDI', 'Teams')
