#!/usr/bin/env python3
"""
Find Andy Cole's EXACT record by searching for the name pattern.
The file has massive concatenated records, so we need to find Cole specifically.
"""

def xor_decode(data):
    return bytes(b ^ 0x61 for b in data)

def main():
    filepath = 'DBDAT/JUG98030.FDI'
    
    with open(filepath, 'rb') as f:
        encoded_data = f.read()
    
    decoded_data = xor_decode(encoded_data)
    
    # Search for "COLE" in the decoded data
    search_text = b'COLE'
    
    print(f"Searching for '{search_text.decode()}' in decoded file...")
    print("="*100)
    
    pos = 0
    found_count = 0
    
    while True:
        pos = decoded_data.find(search_text, pos)
        if pos == -1:
            break
        
        # Check if this is Andrew COLE (look for "Andrew" or "Andy" nearby)
        context_start = max(0, pos - 50)
        context_end = min(len(decoded_data), pos + 200)
        context = decoded_data[context_start:context_end]
        
        try:
            context_text = context.decode('latin-1', errors='ignore').upper()
            
            if 'ANDREW' in context_text or 'ANDY' in context_text:
                found_count += 1
                print(f"\n{'='*100}")
                print(f"FOUND #{found_count}: Andy Cole at file position {pos}")
                print(f"{'='*100}")
                
                # Look backwards for the separator (0xdd 0x63 0x60)
                separator = bytes([0xdd, 0x63, 0x60])
                record_start = decoded_data.rfind(separator, max(0, pos-500), pos)
                
                if record_start == -1:
                    print("Could not find record start (separator)")
                    record_start = max(0, pos - 100)
                else:
                    record_start += 3  # Skip the separator itself
                    print(f"Record starts at position {record_start} (after separator)")
                
                # Find the next separator (end of this record)
                record_end = decoded_data.find(separator, pos + 10)
                if record_end == -1:
                    record_end = min(len(decoded_data), pos + 500)
                    print(f"Record ends at ~{record_end} (no next separator found, truncating)")
                else:
                    print(f"Record ends at position {record_end} (next separator)")
                
                # Extract the record
                record = decoded_data[record_start:record_end]
                record_len = len(record)
                
                print(f"Record length: {record_len} bytes")
                
                # Show the record
                print(f"\nFull record hex dump:")
                for j in range(0, min(150, record_len), 16):
                    hex_part = ' '.join(f'{b:02x}' for b in record[j:j+16])
                    ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in record[j:j+16])
                    print(f"{j:04x}: {hex_part:<48} | {ascii_part}")
                
                if record_len > 150:
                    print(f"... ({record_len - 150} more bytes) ...")
                
                # Show last 30 bytes
                if record_len >= 30:
                    print(f"\nLast 30 bytes (likely contains 12 attributes):")
                    last_30 = record[-30:]
                    print(' '.join(f'{b:02x}' for b in last_30))
                    print(' '.join(f'{b:3d}' for b in last_30))
                    
                    # Try last 12 as attributes
                    print(f"\nLast 12 bytes as attributes:")
                    attrs = record[-12:]
                    attr_names = ['SPEED', 'STAM', 'AGGR', 'QUAL', 'FIT', 'MORL', 'HAND', 'PASS', 'DRIB', 'HEAD', 'TACK', 'SHOT']
                    print("Expected (Cole): 87, 86, 84, 75, 70, 99, 13, 70, 73, 86, 65, 88")
                    print(f"Found:           {', '.join(str(b) for b in attrs)}")
                    
                    match_count = 0
                    for i, (name, expected, found) in enumerate(zip(attr_names, [87,86,84,75,70,99,13,70,73,86,65,88], attrs)):
                        match = "✓" if expected == found else f"✗ (expected {expected})"
                        print(f"  {name:5s}: {found:3d} {match}")
                        if expected == found:
                            match_count += 1
                    
                    if match_count >= 8:
                        print(f"\n✓✓✓ ATTRIBUTES MATCH! ({match_count}/12 correct)")
                    elif match_count >= 4:
                        print(f"\n⚠️ Partial match ({match_count}/12 correct)")
                
        except:
            pass
        
        pos += 1
    
    if found_count == 0:
        print("\n✗ Andy Cole NOT FOUND")
    else:
        print(f"\n\nTotal occurrences of Cole found: {found_count}")

if __name__ == '__main__':
    main()