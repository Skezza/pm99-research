#!/usr/bin/env python3
"""
Analyze the structure of clean player records to identify field positions.
Focus on records we know details for (HIERRO, ZIDANE, etc.)
"""

# Known player details for validation
KNOWN_PLAYERS = {
    "HIERRO": {"pos": 1, "age": 30, "nat": "Spain", "nat_code": 25},  # Defender
    "ZIDANE": {"pos": 2, "age": 26, "nat": "France", "nat_code": 9},  # Midfielder
    "RAÚL": {"pos": 3, "age": 21, "nat": "Spain", "nat_code": 25},    # Forward
    "CAÑIZARES": {"pos": 0, "age": 29, "nat": "Spain", "nat_code": 25},  # Goalkeeper
}

def xor_decode(data):
    return bytes(b ^ 0x61 for b in data)

def analyze_record_structure(record, player_name):
    """Analyze a single player record byte by byte."""
    print(f"\n{'='*100}")
    print(f"Analyzing: {player_name}")
    print(f"{'='*100}")
    print(f"Record length: {len(record)} bytes\n")
    
    # Show full hex dump
    for i in range(0, len(record), 16):
        hex_part = ' '.join(f'{b:02x}' for b in record[i:i+16])
        dec_part = ' '.join(f'{b:3d}' for b in record[i:i+16])
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in record[i:i+16])
        print(f"{i:04x}: {hex_part:<48} | {ascii_part}")
    
    # Extract known fields
    team_id = int.from_bytes(record[0:2], 'little')
    squad_num = record[2]
    
    print(f"\nIdentified fields:")
    print(f"  Bytes 0-1: Team ID = 0x{team_id:04x} ({team_id})")
    print(f"  Byte 2: Squad number = {squad_num}")
    
    # Find where the name text starts (skip initial encoded bytes)
    # Pattern seems to be: team_id, squad, then some prefix bytes, then name
    name_start = None
    for i in range(3, min(10, len(record))):
        if chr(record[i]).isupper() or record[i] > 127:
            name_start = i
            break
    
    if name_start:
        print(f"  Name appears to start around byte {name_start}")
        
        # Try to find where name ends (look for pattern of non-text bytes)
        name_end = name_start
        for i in range(name_start, len(record)):
            # Name ends when we hit multiple non-printable or low values
            if i > name_start + 10:  # At least 10 chars for name
                # Check if next 3 bytes are all < 128 and include lowercase 'a'
                if i + 3 < len(record):
                    if record[i] == ord('a') or record[i] < 32:
                        name_end = i
                        break
        
        name_region = record[name_start:name_end]
        print(f"  Name region: bytes {name_start}-{name_end} ({name_end-name_start} bytes)")
        print(f"    Text: {name_region.decode('latin-1', errors='replace')}")
    
    # The interesting part: what comes after the name?
    if name_end and name_end < len(record) - 12:
        post_name = record[name_end:]
        print(f"\n  Post-name region: {len(post_name)} bytes")
        print(f"    Hex: {' '.join(f'{b:02x}' for b in post_name[:30])}")
        print(f"    Dec: {' '.join(f'{b:3d}' for b in post_name[:30])}")
        
        # Look for 12-attribute pattern (values 0-100)
        print(f"\n  Searching for 12 consecutive bytes in range 0-100:")
        for i in range(len(post_name) - 11):
            sequence = post_name[i:i+12]
            if all(0 <= b <= 100 for b in sequence):
                print(f"    Found at offset {name_end + i}: {' '.join(f'{b:3d}' for b in sequence)}")
        
        # Look for position field (0-3)
        print(f"\n  Bytes with value 0-3 (possible position):")
        for i, b in enumerate(post_name[:30]):
            if 0 <= b <= 3:
                print(f"    Byte {name_end + i}: {b}")
        
        # Look for age field (20-40)
        if player_name in KNOWN_PLAYERS:
            expected_age = KNOWN_PLAYERS[player_name]['age']
            print(f"\n  Bytes with value {expected_age} (expected age):")
            for i, b in enumerate(post_name[:30]):
                if b == expected_age:
                    print(f"    Byte {name_end + i}: {b} ✓")
        
        # Check last 12 bytes specifically
        if len(record) >= 12:
            last_12 = record[-12:]
            print(f"\n  Last 12 bytes:")
            print(f"    Hex: {' '.join(f'{b:02x}' for b in last_12)}")
            print(f"    Dec: {' '.join(f'{b:3d}' for b in last_12)}")
            if all(0 <= b <= 100 for b in last_12):
                print(f"    ✓ All in 0-100 range (possible attributes)")
            else:
                print(f"    ✗ Not all in 0-100 range")

def main():
    filepath = 'DBDAT/JUG98030.FDI'
    
    with open(filepath, 'rb') as f:
        encoded_data = f.read()
    
    decoded_data = xor_decode(encoded_data)
    separator = bytes([0xdd, 0x63, 0x60])
    parts = decoded_data.split(separator)
    
    # Find our known players
    for player_name in KNOWN_PLAYERS.keys():
        found = False
        for record in parts:
            if len(record) < 50 or len(record) > 200:
                continue
            try:
                text = record.decode('latin-1', errors='ignore').upper()
                if player_name in text:
                    analyze_record_structure(record, player_name)
                    found = True
                    break
            except:
                continue
        
        if not found:
            print(f"\n{player_name} not found in clean records")

if __name__ == '__main__':
    main()