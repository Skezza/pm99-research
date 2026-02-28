#!/usr/bin/env python3
"""
Analyze ENT98030.FDI to see if it contains player attributes.
This file might have extended player data separate from names.
"""

def xor_decode(data):
    return bytes(b ^ 0x61 for b in data)

def main():
    filepath = 'DBDAT/ENT98030.FDI'
    
    try:
        with open(filepath, 'rb') as f:
            encoded_data = f.read()
    except FileNotFoundError:
        print(f"File not found: {filepath}")
        return
    
    print(f"File size: {len(encoded_data)} bytes")
    print("="*100)
    
    # Try XOR decoding
    decoded_data = xor_decode(encoded_data)
    
    # Look for Andy Cole's attribute sequence
    cole_attrs = bytes([87, 86, 84, 75, 70, 99, 13, 70, 73, 86, 65, 88])
    
    print("\nSearching for Andy Cole's exact attributes (87, 86, 84, 75, 70, 99, 13, 70, 73, 86, 65, 88)...")
    pos = decoded_data.find(cole_attrs)
    if pos != -1:
        print(f"✓✓✓ FOUND at position {pos}!")
        print(f"Context:")
        ctx_start = max(0, pos - 30)
        ctx_end = min(len(decoded_data), pos + 30)
        for i in range(ctx_start, ctx_end, 16):
            hex_part = ' '.join(f'{b:02x}' for b in decoded_data[i:i+16])
            marker = " <-- ATTRIBUTES" if i <= pos < i + 16 else ""
            print(f"  {i:06x}: {hex_part}{marker}")
    else:
        print("✗ Not found")
    
    # Look for HIERRO (known team ID 0x616b, squad 101)
    # In ENT file, might be indexed differently
    print("\n\nSearching for pattern of team_id + squad (Real Madrid players)...")
    print("Looking for 0x6b 0x61 (team ID little-endian) followed by 101 (0x65)")
    
    # Real Madrid team ID is 0x616b (24939) = little endian 0x6b 0x61
    pattern = bytes([0x6b, 0x61, 101])  # team_id + squad for HIERRO
    
    pos = 0
    found_count = 0
    while found_count < 5:
        pos = decoded_data.find(pattern, pos)
        if pos == -1:
            break
        found_count += 1
        print(f"\nFound pattern at position {pos}:")
        # Show surrounding data
        ctx_start = max(0, pos - 10)
        ctx_end = min(len(decoded_data), pos + 50)
        context = decoded_data[ctx_start:ctx_end]
        
        hex_part = ' '.join(f'{b:02x}' for b in context)
        print(f"  {hex_part}")
        
        # Check if next 12 bytes could be attributes
        if pos + 3 + 12 <= len(decoded_data):
            potential_attrs = decoded_data[pos+3:pos+3+12]
            if all(0 <= b <= 100 for b in potential_attrs):
                print(f"  ✓ Next 12 bytes are in attribute range: {' '.join(str(b) for b in potential_attrs)}")
        
        pos += 1
    
    # Show first 200 bytes of file structure
    print("\n\nFirst 200 bytes of ENT file (decoded):")
    for i in range(0, min(200, len(decoded_data)), 16):
        hex_part = ' '.join(f'{b:02x}' for b in decoded_data[i:i+16])
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in decoded_data[i:i+16])
        print(f"  {i:04x}: {hex_part:<48} | {ascii_part}")
    
    # Check file structure - might be a table/index
    print("\n\nAnalyzing file structure...")
    
    # Look for repeating patterns (fixed-size records)
    print("Checking for fixed-size record patterns...")
    
    # Try common record sizes
    for record_size in [12, 16, 20, 24, 30, 32, 40, 50]:
        if len(decoded_data) % record_size == 0:
            record_count = len(decoded_data) // record_size
            print(f"  Record size {record_size}: {record_count} records (exact fit)")
        elif record_size < len(decoded_data):
            # Check if there's a header + records
            for header_size in [0, 16, 32, 64]:
                remainder = (len(decoded_data) - header_size) % record_size
                if remainder == 0:
                    record_count = (len(decoded_data) - header_size) // record_size
                    print(f"  Header {header_size} + {record_count} records of {record_size} bytes")

if __name__ == '__main__':
    main()