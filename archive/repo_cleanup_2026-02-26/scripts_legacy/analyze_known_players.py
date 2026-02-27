#!/usr/bin/env python3
"""
Comparative analysis of known players to identify position, nationality, and age fields.
Focuses on the first ~100 bytes of structured data, ignoring text descriptions.
"""

# Known player data from game
PLAYERS = [
    {
        "name": "HIERRO",
        "full": "Fernando HIERRO",
        "pos": "Defender",
        "pos_code": 1,  # GK=0, DEF=1, MID=2, FWD=3
        "nat": "Spain",
        "nat_code": 13,  # Estimated Spain code
        "age": 30,
        "team_id": 0x616b,
        "squad": 101
    },
    {
        "name": "ZIDANE",
        "full": "Zinedine ZIDANE",
        "pos": "Midfielder",
        "pos_code": 2,
        "nat": "France",
        "nat_code": 7,  # Estimated France code
        "age": 26,
        "team_id": 0x6e01,
        "squad": 116
    },
    {
        "name": "KAHN",
        "full": "Oliver KAHN",
        "pos": "Goalkeeper",
        "pos_code": 0,
        "nat": "Germany",
        "nat_code": 8,  # Estimated Germany code
        "age": 29,
        "team_id": 0x2c25,
        "squad": 39
    },
    {
        "name": "RONALDO",
        "full": "Ronaldo",
        "pos": "Forward",
        "pos_code": 3,
        "nat": "Brazil",
        "nat_code": 3,  # Estimated Brazil code
        "age": 22,
        "team_id": 0x7daf,
        "squad": 96
    }
]

def xor_decode(data):
    """XOR decode with key 0x61."""
    return bytes(b ^ 0x61 for b in data)

def find_name_end(record, search_name):
    """Find where the player name ends in the record."""
    try:
        text = record.decode('latin-1', errors='ignore').upper()
        name_pos = text.find(search_name)
        if name_pos >= 0:
            # Find end of full name (look for non-alpha characters after name)
            end_pos = name_pos
            while end_pos < len(text) and (text[end_pos].isalpha() or text[end_pos] in ' -'):
                end_pos += 1
            return end_pos
    except:
        pass
    return -1

def extract_player_data(filepath, player_info):
    """Extract structured data for a specific player."""
    with open(filepath, 'rb') as f:
        encoded_data = f.read()
    
    decoded_data = xor_decode(encoded_data)
    separator = bytes([0xdd, 0x63, 0x60])
    parts = decoded_data.split(separator)
    
    for i, record in enumerate(parts):
        if len(record) < 10:
            continue
        
        try:
            record_text = record.decode('latin-1', errors='ignore').upper()
            if player_info['name'] in record_text:
                # Extract first 100 bytes of structured data
                structured_data = record[:min(100, len(record))]
                
                # Find where name ends
                name_end = find_name_end(record, player_info['name'])
                
                return {
                    'player': player_info,
                    'record_index': i,
                    'structured_data': structured_data,
                    'name_end_pos': name_end,
                    'team_id': int.from_bytes(record[0:2], 'little') if len(record) >= 2 else 0,
                    'squad_num': record[2] if len(record) >= 3 else 0,
                }
        except:
            continue
    
    return None

def compare_players(player_data_list):
    """Compare player records to find position, nationality, and age fields."""
    print("\n" + "="*100)
    print("COMPARATIVE ANALYSIS - POSITION, NATIONALITY, AGE FIELD MAPPING")
    print("="*100)
    
    # Group by position
    by_position = {}
    for pd in player_data_list:
        pos = pd['player']['pos_code']
        if pos not in by_position:
            by_position[pos] = []
        by_position[pos].append(pd)
    
    print("\n### RECORDS GROUPED BY POSITION ###\n")
    pos_names = {0: "Goalkeeper", 1: "Defender", 2: "Midfielder", 3: "Forward"}
    
    for pos_code in sorted(by_position.keys()):
        print(f"\n{pos_names[pos_code]} (code={pos_code}):")
        for pd in by_position[pos_code]:
            p = pd['player']
            data = pd['structured_data']
            print(f"  {p['full']:20s} | Age {p['age']} | {p['nat']:10s}")
            print(f"    First 60 bytes: {' '.join(f'{b:02x}' for b in data[:60])}")
            print(f"    Decimal:        {' '.join(f'{b:3d}' for b in data[:60])}")
    
    # Byte-by-byte comparison
    print("\n\n### BYTE-BY-BYTE COMPARISON (Positions 0-50) ###\n")
    print("Looking for bytes that correlate with Position, Nationality, or Age...\n")
    
    max_len = min(50, min(len(pd['structured_data']) for pd in player_data_list))
    
    for byte_pos in range(max_len):
        values = {}
        for pd in player_data_list:
            byte_val = pd['structured_data'][byte_pos]
            p = pd['player']
            key = f"{p['pos']:10s}"
            values[key] = byte_val
        
        # Check if this byte correlates with position
        unique_vals = set(values.values())
        if len(unique_vals) == len(values):  # All different = potential match
            print(f"Byte {byte_pos:2d}: {' '.join(f'{v:02x}({v:3d})' for v in values.values())} <- Positions all unique!")
        elif len(unique_vals) <= 4:  # Some pattern
            print(f"Byte {byte_pos:2d}: {' '.join(f'{v:02x}({v:3d})' for v in values.values())}")
    
    # Age analysis
    print("\n\n### AGE FIELD SEARCH ###")
    print("Looking for bytes matching player ages (30, 26, 29, 22)...\n")
    
    for byte_pos in range(max_len):
        ages_found = []
        for pd in player_data_list:
            byte_val = pd['structured_data'][byte_pos]
            p = pd['player']
            if byte_val == p['age']:
                ages_found.append(p['full'])
        
        if len(ages_found) >= 2:
            print(f"Byte {byte_pos:2d}: Matches age for {len(ages_found)} players: {', '.join(ages_found)}")
    
    # Look for position values (0-3)
    print("\n\n### POSITION FIELD CANDIDATES (values 0-3) ###\n")
    
    for byte_pos in range(max_len):
        values_with_players = []
        for pd in player_data_list:
            byte_val = pd['structured_data'][byte_pos]
            p = pd['player']
            if 0 <= byte_val <= 3:
                values_with_players.append((byte_val, p['pos'], p['full']))
        
        if len(values_with_players) >= 2:
            print(f"Byte {byte_pos:2d}:", end=" ")
            for val, pos, name in values_with_players:
                match = "✓" if val == PLAYERS[0]['pos_code'] and pos == "Goalkeeper" or \
                              val == PLAYERS[1]['pos_code'] and pos == "Defender" or \
                              val == PLAYERS[2]['pos_code'] and pos == "Midfielder" or \
                              val == PLAYERS[3]['pos_code'] and pos == "Forward" else "✗"
                print(f"{name}={val}({pos}) {match}", end=" | ")
            print()

def main():
    filepath = 'DBDAT/JUG98030.FDI'
    
    print("Extracting player data...")
    player_data = []
    for player_info in PLAYERS:
        data = extract_player_data(filepath, player_info)
        if data:
            player_data.append(data)
            print(f"  ✓ {player_info['full']}")
        else:
            print(f"  ✗ {player_info['full']} - NOT FOUND")
    
    if len(player_data) >= 2:
        compare_players(player_data)
    else:
        print("\nInsufficient player data for comparison!")

if __name__ == '__main__':
    main()