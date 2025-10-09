#!/usr/bin/env python3
"""
Find Andy Cole's record and analyze its structure.
Known data: Age 27, Forward, England, Man Utd, Rating 83
"""

def xor_decode(data):
    return bytes(b ^ 0x61 for b in data)

def main():
    filepath = 'DBDAT/JUG98030.FDI'
    
    with open(filepath, 'rb') as f:
        encoded_data = f.read()
    
    decoded_data = xor_decode(encoded_data)
    separator = bytes([0xdd, 0x63, 0x60])
    parts = decoded_data.split(separator)
    
    print("Searching for Andy Cole (COLE)...")
    print("="*100)
    
    found_count = 0
    for i, record in enumerate(parts):
        if len(record) < 20:
            continue
        
        try:
            text = record.decode('latin-1', errors='ignore').upper()
            
            # Search for COLE and check if it's Andrew
            if 'COLE' in text and 'ANDREW' in text:
                found_count += 1
                print(f"\n✓ FOUND Andy Cole in record #{i}")
                
                # Extract basic info
                team_id = int.from_bytes(record[0:2], 'little') if len(record) >= 2 else 0
                squad_num = record[2] if len(record) >= 3 else 0
                
                print(f"Team ID: 0x{team_id:04x} ({team_id})")
                print(f"Squad #: {squad_num}")
                print(f"Record size: {len(record)} bytes")
                
                # Show first 100 bytes
                print(f"\nFirst 100 bytes (hex):")
                for j in range(0, min(100, len(record)), 16):
                    hex_part = ' '.join(f'{b:02x}' for b in record[j:j+16])
                    ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in record[j:j+16])
                    print(f"{j:04x}: {hex_part:<48} | {ascii_part}")
                
                # Show last 20 bytes (likely attributes)
                print(f"\nLast 20 bytes (hex):")
                last_20 = record[-20:]
                print(' '.join(f'{b:02x}' for b in last_20))
                print(' '.join(f'{b:3d}' for b in last_20))
                
                # Check if last 12 bytes match Cole's attributes
                print(f"\nChecking if last 12 bytes match Cole's attributes:")
                print("Expected: SPEED=87, STAMINA=86, AGGR=84, QUAL=75, FIT=70, MORAL=99")
                print("          HANDL=13, PASS=70, DRIB=73, HEAD=86, TACK=65, SHOOT=88")
                
                if len(record) >= 12:
                    attrs = record[-12:]
                    print(f"Last 12:  {' '.join(f'{b:3d}' for b in attrs)}")
                    
                    if attrs[0] == 87 and attrs[1] == 86 and attrs[2] == 84:
                        print("  ✓✓✓ ATTRIBUTES MATCH! Last 12 bytes are player attributes!")
                
                # Look for age (27)
                print(f"\nSearching for age value (27) in first 100 bytes:")
                for pos in range(min(100, len(record))):
                    if record[pos] == 27:
                        print(f"  Byte {pos:3d}: value = 27 ← Possible age field")
                
                # Full hex dump
                print(f"\n--- COMPLETE RECORD HEX DUMP ({len(record)} bytes) ---")
                for j in range(0, len(record), 16):
                    hex_part = ' '.join(f'{b:02x}' for b in record[j:j+16])
                    ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in record[j:j+16])
                    print(f"{j:04x}: {hex_part:<48} | {ascii_part}")
        except:
            continue
    
    if found_count == 0:
        print("\n✗ Andy Cole NOT FOUND")

if __name__ == '__main__':
    main()