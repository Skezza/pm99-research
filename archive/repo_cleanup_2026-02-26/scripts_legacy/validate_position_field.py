#!/usr/bin/env python3
"""
Validate the position field discovery (Byte 42, double-XOR encoded).
Test with multiple known players across all 4 positions.
"""

def xor_decode(data, key=0x61):
    return bytes(b ^ key for b in data)

# Known players with positions
KNOWN_PLAYERS = [
    # Goalkeepers (0)
    {"name": "KAHN", "pos": 0, "pos_name": "Goalkeeper"},
    {"name": "CAÑIZARES", "pos": 0, "pos_name": "Goalkeeper"},
    {"name": "SCHMEICHEL", "pos": 0, "pos_name": "Goalkeeper"},
    
    # Defenders (1)
    {"name": "HIERRO", "pos": 1, "pos_name": "Defender"},
    {"name": "MALDINI", "pos": 1, "pos_name": "Defender"},
    {"name": "NESTA", "pos": 1, "pos_name": "Defender"},
    {"name": "DESAILLY", "pos": 1, "pos_name": "Defender"},
    
    # Midfielders (2)
    {"name": "ZIDANE", "pos": 2, "pos_name": "Midfielder"},
    {"name": "FIGO", "pos": 2, "pos_name": "Midfielder"},
    {"name": "BECKHAM", "pos": 2, "pos_name": "Midfielder"},
    
    # Forwards (3)
    {"name": "RONALDO", "pos": 3, "pos_name": "Forward"},
    {"name": "RAÚL", "pos": 3, "pos_name": "Forward"},
    {"name": "BATISTUTA", "pos": 3, "pos_name": "Forward"},
    {"name": "COLE", "pos": 3, "pos_name": "Forward"},
]

def find_position_byte(record):
    """
    Find the position byte in a player record.
    Returns the position value after double-XOR.
    """
    # Try to find where name ends (look for 'aa' pattern)
    name_end = None
    for i in range(30, min(50, len(record)-20)):
        if record[i:i+2] == bytes([0x61, 0x61]):
            name_end = i + 2
            break
    
    if not name_end:
        # Fallback: estimate based on record length
        name_end = 40
    
    # Position field should be at name_end + 8 (byte 42 in HIERRO example)
    # But we need to be flexible for different name lengths
    # The pattern seems to be: after 'aa', skip ~8 bytes
    
    # Try offset +8 from name_end
    if name_end + 8 < len(record):
        pos_byte_offset = name_end + 8
        pos_byte = record[pos_byte_offset]
        pos_value = pos_byte ^ 0x61  # Double XOR
        return pos_value, pos_byte_offset
    
    return None, None

def main():
    filepath = 'DBDAT/JUG98030.FDI'
    
    with open(filepath, 'rb') as f:
        encoded_data = f.read()
    
    decoded_data = xor_decode(encoded_data, 0x61)
    separator = bytes([0xdd, 0x63, 0x60])
    parts = decoded_data.split(separator)
    
    print("Position Field Validation")
    print("="*100)
    print(f"Hypothesis: Position stored at variable offset after name, double-XOR encoded")
    print(f"Expected values: GK=0, DEF=1, MID=2, FWD=3\n")
    
    results = []
    
    for player_info in KNOWN_PLAYERS:
        name = player_info['name']
        expected_pos = player_info['pos']
        pos_name = player_info['pos_name']
        
        # Find player record
        found = False
        for i, record in enumerate(parts):
            if len(record) < 50 or len(record) > 200:
                continue
            
            try:
                text = record.decode('latin-1', errors='ignore').upper()
                if name in text:
                    # Found the player
                    found_pos, offset = find_position_byte(record)
                    
                    if found_pos is not None:
                        match = "✓" if found_pos == expected_pos else "✗"
                        results.append({
                            'name': name,
                            'expected': expected_pos,
                            'found': found_pos,
                            'match': match == "✓",
                            'offset': offset
                        })
                        
                        print(f"{match} {name:15s} | Expected: {expected_pos} ({pos_name:11s}) | Found: {found_pos} | Offset: {offset}")
                    else:
                        print(f"? {name:15s} | Could not locate position byte")
                        results.append({'name': name, 'expected': expected_pos, 'found': None, 'match': False})
                    
                    found = True
                    break
            except:
                continue
        
        if not found:
            print(f"✗ {name:15s} | Not found in database")
            results.append({'name': name, 'expected': expected_pos, 'found': None, 'match': False})
    
    # Summary
    print("\n" + "="*100)
    print("VALIDATION SUMMARY")
    print("="*100)
    
    total = len(results)
    matches = sum(1 for r in results if r['match'])
    not_found = sum(1 for r in results if r['found'] is None)
    
    print(f"Total players tested: {total}")
    print(f"Successful matches: {matches}")
    print(f"Incorrect values: {total - matches - not_found}")
    print(f"Not found in DB: {not_found}")
    
    if matches > 0:
        accuracy = (matches / (total - not_found)) * 100 if (total - not_found) > 0 else 0
        print(f"\nAccuracy: {accuracy:.1f}%")
        
        if accuracy >= 80:
            print("\n✓✓✓ POSITION FIELD CONFIRMED!")
            print("The hypothesis is strongly supported by the data.")
        elif accuracy >= 50:
            print("\n⚠️ PARTIAL CONFIRMATION")
            print("The pattern shows promise but needs refinement.")
        else:
            print("\n✗ HYPOTHESIS REJECTED")
            print("The position field is not at the expected location.")

if __name__ == '__main__':
    main()