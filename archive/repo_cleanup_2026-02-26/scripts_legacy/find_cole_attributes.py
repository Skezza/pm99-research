#!/usr/bin/env python3
"""
Search for Andy Cole's exact attribute values within his record.
Expected: 87, 86, 84, 75, 70, 99, 13, 70, 73, 86, 65, 88
"""

def xor_decode(data):
    return bytes(b ^ 0x61 for b in data)

def main():
    filepath = 'DBDAT/JUG98030.FDI'
    
    with open(filepath, 'rb') as f:
        encoded_data = f.read()
    
    decoded_data = xor_decode(encoded_data)
    
    # Andy Cole's expected attributes
    cole_attrs = bytes([87, 86, 84, 75, 70, 99, 13, 70, 73, 86, 65, 88])
    
    # Also search for height/weight: 5'10" and 11st 11lb
    # Could be stored as: 5, 10 (feet/inches) and 11, 11 (stone/pounds)
    height_pattern = bytes([5, 10])
    weight_pattern = bytes([11, 11])
    
    # Find Cole's record
    cole_pos = decoded_data.find(b'Andrew Alexander COLE')
    if cole_pos == -1:
        print("Cole not found!")
        return
    
    # Find separator before Cole
    separator = bytes([0xdd, 0x63, 0x60])
    record_start = decoded_data.rfind(separator, max(0, cole_pos-500), cole_pos)
    if record_start == -1:
        record_start = max(0, cole_pos - 100)
    else:
        record_start += 3
    
    # Find next separator
    record_end = decoded_data.find(separator, cole_pos + 10)
    if record_end == -1:
        record_end = min(len(decoded_data), cole_pos + 30300)
    
    record = decoded_data[record_start:record_end]
    
    print(f"Andy Cole record: {len(record)} bytes")
    print(f"Record starts at: {record_start}")
    print("="*100)
    
    # Search for exact 12-byte attribute sequence
    attr_pos = record.find(cole_attrs)
    if attr_pos != -1:
        print(f"\n✓✓✓ FOUND EXACT 12 ATTRIBUTES at offset {attr_pos} from record start!")
        print(f"File position: {record_start + attr_pos}")
        print(f"Context:")
        
        # Show 20 bytes before and after
        ctx_start = max(0, attr_pos - 20)
        ctx_end = min(len(record), attr_pos + 12 + 20)
        
        for i in range(ctx_start, ctx_end, 16):
            hex_part = ' '.join(f'{b:02x}' for b in record[i:i+16])
            dec_part = ' '.join(f'{b:3d}' for b in record[i:i+16])
            marker = ""
            if i <= attr_pos < i + 16:
                marker = " <-- ATTRIBUTES START HERE"
            print(f"{i:04x}: {hex_part:<48} {marker}")
            print(f"      {dec_part}")
    else:
        print("\n✗ Exact 12-byte sequence NOT found as contiguous block")
        print("Searching for partial matches...")
        
        # Try to find subsequences
        for length in [8, 6, 4]:
            for start_idx in range(len(cole_attrs) - length + 1):
                partial = cole_attrs[start_idx:start_idx + length]
                pos = record.find(partial)
                if pos != -1:
                    print(f"\nFound {length} bytes starting at attr[{start_idx}]: offset {pos}")
                    print(f"Pattern: {' '.join(str(b) for b in partial)}")
    
    # Search for height pattern
    print(f"\n\nSearching for HEIGHT (5, 10)...")
    pos = 0
    found_count = 0
    while True:
        pos = record.find(height_pattern, pos)
        if pos == -1:
            break
        found_count += 1
        print(f"  Found at offset {pos}: context = {record[max(0,pos-5):pos+7]}")
        pos += 1
    
    if found_count == 0:
        print("  Not found as contiguous bytes")
    
    # Search for weight pattern  
    print(f"\nSearching for WEIGHT (11, 11)...")
    pos = 0
    found_count = 0
    while True:
        pos = record.find(weight_pattern, pos)
        if pos == -1:
            break
        found_count += 1
        print(f"  Found at offset {pos}: context = {record[max(0,pos-5):pos+7]}")
        pos += 1
    
    if found_count == 0:
        print("  Not found as contiguous bytes")
    
    # Try looking for individual attribute values
    print(f"\n\nSearching for individual attribute values:")
    for i, (val, name) in enumerate(zip(cole_attrs, 
        ['SPEED', 'STAM', 'AGGR', 'QUAL', 'FIT', 'MORL', 'HAND', 'PASS', 'DRIB', 'HEAD', 'TACK', 'SHOT'])):
        count = record.count(bytes([val]))
        if count > 0 and count < 50:
            print(f"  {name}={val}: appears {count} times")

if __name__ == '__main__':
    main()