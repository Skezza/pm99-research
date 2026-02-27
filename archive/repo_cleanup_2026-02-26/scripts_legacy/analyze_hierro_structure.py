#!/usr/bin/env python3
"""
Detailed byte-by-byte analysis of HIERRO's record to correctly map all fields.
"""

def xor_decode(data, key=0x61):
    return bytes(b ^ key for b in data)

def main():
    # HIERRO's known stats from game
    hierro_stats = {
        'team_id': 24939,  # 0x616b
        'squad': 101,
        'position': 1,  # Defender
        'age': 30,
        'rating': 85,
        'attributes': {
            'SPEED': 85, 'STAMINA': 91, 'AGGRESSION': 89, 'QUALITY': 87,
            'FITNESS': 76, 'MORAL': 82, 'HANDLING': 10, 'PASSING': 74,
            'DRIBBLING': 70, 'HEADING': 84, 'TACKLING': 94, 'SHOOTING': 80
        }
    }
    
    # Load and decode file
    filepath = 'DBDAT/JUG98030.FDI'
    with open(filepath, 'rb') as f:
        encoded_data = f.read()
    
    decoded_data = xor_decode(encoded_data, 0x61)
    separator = bytes([0xdd, 0x63, 0x60])
    parts = decoded_data.split(separator)
    
    # Find HIERRO
    hierro_record = None
    record_index = None
    
    for i, record in enumerate(parts):
        if len(record) < 50 or len(record) > 200:
            continue
        try:
            text = record.decode('latin-1', errors='ignore').upper()
            if 'HIERRO' in text and 'FERNANDO' in text:
                hierro_record = record
                record_index = i
                break
        except:
            continue
    
    if not hierro_record:
        print("ERROR: HIERRO not found!")
        return
    
    print("="*100)
    print(f"HIERRO RECORD STRUCTURE (Record #{record_index}, {len(hierro_record)} bytes)")
    print("="*100)
    
    # Display header info
    team_id_bytes = hierro_record[0:2]
    team_id = int.from_bytes(team_id_bytes, 'little')
    squad = hierro_record[2]
    
    print(f"\nHEADER:")
    print(f"  Bytes 0-1 (Team ID): 0x{team_id_bytes.hex()} = {team_id} (expected: {hierro_stats['team_id']})")
    print(f"  Byte 2 (Squad #):    {squad} (expected: {hierro_stats['squad']})")
    print(f"  Bytes 3-4:           0x{hierro_record[3:5].hex()}")
    
    # Find name boundaries
    name_start = 5
    name_bytes = hierro_record[name_start:]
    
    # Try to find where name actually ends
    try:
        name_text = hierro_record[name_start:45].decode('latin-1').split('\x00')[0]
        print(f"\n  Name (bytes 5-~40): '{name_text}'")
    except:
        print(f"\n  Name: [decode error]")
    
    # Show complete byte-by-byte breakdown
    print(f"\nCOMPLETE BYTE-BY-BYTE ANALYSIS:")
    print(f"{'Byte':>4} | {'Hex':>4} | {'Raw':>4} | {'XOR':>4} | ASCII | Notes")
    print("-" * 80)
    
    # First 50 bytes with interpretation
    for i in range(min(70, len(hierro_record))):
        b = hierro_record[i]
        xor_val = b ^ 0x61
        
        # ASCII representation
        ascii_char = chr(b) if 32 <= b < 127 else '·'
        
        # Notes for specific byte ranges
        notes = ""
        if i == 0:
            notes = "Team ID (low byte)"
        elif i == 1:
            notes = "Team ID (high byte)"
        elif i == 2:
            notes = "Squad Number"
        elif i == 3 or i == 4:
            notes = "Unknown prefix"
        elif 5 <= i < 40:
            notes = "Name region"
        elif i == 42:
            notes = f"POSITION? (XOR={xor_val})"
        elif 50 <= i < 62:
            notes = "Attribute candidate region"
        elif i >= len(hierro_record) - 12:
            notes = f"Last 12 bytes (offset -{len(hierro_record)-i})"
        
        print(f"{i:4d} | 0x{b:02x} | {b:4d} | {xor_val:4d} | {ascii_char:^5s} | {notes}")
    
    # Special analysis sections
    print("\n" + "="*100)
    print("FIELD SEARCH ANALYSIS")
    print("="*100)
    
    # Search for position value (expected: 1 for Defender)
    print(f"\nSearching for POSITION = {hierro_stats['position']} (Defender):")
    for i, b in enumerate(hierro_record):
        if (b ^ 0x61) == hierro_stats['position']:
            print(f"  Byte {i:2d}: raw=0x{b:02x}, double-XOR={b^0x61}")
    
    # Search for age value (expected: 30)
    print(f"\nSearching for AGE = {hierro_stats['age']}:")
    for i, b in enumerate(hierro_record):
        if b == hierro_stats['age']:
            print(f"  Byte {i:2d}: raw value {b}")
        if (b ^ 0x61) == hierro_stats['age']:
            print(f"  Byte {i:2d}: double-XOR value {b^0x61} (raw=0x{b:02x})")
    
    # Search for rating (expected: 85)
    print(f"\nSearching for RATING = {hierro_stats['rating']}:")
    for i, b in enumerate(hierro_record):
        if b == hierro_stats['rating']:
            print(f"  Byte {i:2d}: raw value {b}")
        if (b ^ 0x61) == hierro_stats['rating']:
            print(f"  Byte {i:2d}: double-XOR value {b^0x61} (raw=0x{b:02x})")
    
    # Look for sequences of attributes
    print(f"\nSearching for ATTRIBUTE SEQUENCES:")
    attr_values = list(hierro_stats['attributes'].values())
    print(f"Expected values: {attr_values}")
    
    # Check every possible 12-byte window
    for start_offset in range(len(hierro_record) - 11):
        window = hierro_record[start_offset:start_offset + 12]
        
        # Try raw values
        if any(b in attr_values for b in window):
            match_count = sum(1 for b in window if b in attr_values)
            if match_count >= 6:  # At least half match
                print(f"\n  Bytes {start_offset}-{start_offset+11} (RAW, {match_count}/12 matches):")
                print(f"    {' '.join(f'{b:3d}' for b in window)}")
        
        # Try double-XOR
        xor_window = bytes(b ^ 0x61 for b in window)
        if any(b in attr_values for b in xor_window):
            match_count = sum(1 for b in xor_window if b in attr_values)
            if match_count >= 6:  # At least half match
                print(f"\n  Bytes {start_offset}-{start_offset+11} (DOUBLE-XOR, {match_count}/12 matches):")
                print(f"    {' '.join(f'{b:3d}' for b in xor_window)}")
    
    # Show last 20 bytes in detail
    print(f"\n" + "="*100)
    print(f"LAST 20 BYTES DETAIL:")
    print("="*100)
    last_20 = hierro_record[-20:]
    print(f"Raw (hex):     {' '.join(f'{b:02x}' for b in last_20)}")
    print(f"Raw (decimal): {' '.join(f'{b:3d}' for b in last_20)}")
    print(f"Double-XOR:    {' '.join(f'{b^0x61:3d}' for b in last_20)}")

if __name__ == '__main__':
    main()