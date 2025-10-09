#!/usr/bin/env python3
"""
Analyze the METADATA region between player name and attributes.
The record structure is: [team_id][squad][NAME...][METADATA][10 attributes]
"""

PLAYERS = [
    {"name": "HIERRO", "pos": "Defender", "pos_code": 1, "nat": "Spain", "age": 30},
    {"name": "ZIDANE", "pos": "Midfielder", "pos_code": 2, "nat": "France", "age": 26},
    {"name": "KAHN", "pos": "Goalkeeper", "pos_code": 0, "nat": "Germany", "age": 29},
    {"name": "RONALDO", "pos": "Forward", "pos_code": 3, "nat": "Brazil", "age": 22},
]

def xor_decode(data):
    return bytes(b ^ 0x61 for b in data)

def find_player_metadata(filepath, player_info):
    """Extract the metadata region for a player (between name and attributes)."""
    with open(filepath, 'rb') as f:
        encoded_data = f.read()
    
    decoded_data = xor_decode(encoded_data)
    separator = bytes([0xdd, 0x63, 0x60])
    parts = decoded_data.split(separator)
    
    for record in parts:
        if len(record) < 20:
            continue
        
        try:
            text = record.decode('latin-1', errors='ignore').upper()
            if player_info['name'] in text:
                # Find where the surname appears (it's near the start)
                name_pos = text.find(player_info['name'])
                
                # The full name extends beyond just the surname
                # Look for where alpha characters end
                name_end = name_pos
                while name_end < len(text) and (text[name_end].isalpha() or text[name_end] in ' '):
                    name_end += 1
                
                # Metadata is from name_end to record_end - 10 (10 bytes = attributes)
                metadata_start = name_end
                metadata_end = len(record) - 10
                
                if metadata_end > metadata_start:
                    metadata = record[metadata_start:metadata_end]
                    attributes = record[-10:]
                    
                    return {
                        'player': player_info,
                        'team_id': int.from_bytes(record[0:2], 'little') if len(record) >= 2 else 0,
                        'squad': record[2] if len(record) >= 3 else 0,
                        'name_region': record[3:name_end],
                        'metadata': metadata,
                        'attributes': attributes,
                        'text': text
                    }
        except:
            continue
    
    return None

def main():
    filepath = 'DBDAT/JUG98030.FDI'
    
    print("Extracting metadata regions for known players...")
    print("="*100)
    
    player_data = []
    for p in PLAYERS:
        data = find_player_metadata(filepath, p)
        if data:
            player_data.append(data)
            print(f"\n✓ {p['name']} ({p['pos']}, Age {p['age']}, {p['nat']})")
            print(f"  Team ID: 0x{data['team_id']:04x} | Squad: {data['squad']}")
            print(f"  Name region: {len(data['name_region'])} bytes")
            print(f"  Metadata region: {len(data['metadata'])} bytes")
            print(f"  Attributes: {' '.join(f'{b:02x}' for b in data['attributes'])}")
            print(f"  Metadata hex: {' '.join(f'{b:02x}' for b in data['metadata'][:30])}...")
    
    if len(player_data) < 2:
        print("\nInsufficient data!")
        return
    
    # Compare metadata regions
    print("\n\n" + "="*100)
    print("METADATA COMPARISON (first 20 bytes of metadata region)")
    print("="*100)
    
    # Find shortest metadata length
    min_meta_len = min(len(pd['metadata']) for pd in player_data)
    compare_len = min(20, min_meta_len)
    
    print(f"\nComparing {compare_len} bytes:\n")
    print(f"{'Byte':4s} | {'KAHN(GK,29,GER)':20s} | {'HIERRO(DEF,30,ESP)':20s} | {'ZIDANE(MID,26,FRA)':20s} | {'RONALDO(FWD,22,BRA)':20s}")
    print("-" * 100)
    
    for byte_pos in range(compare_len):
        values = []
        for pd in player_data:
            if byte_pos < len(pd['metadata']):
                val = pd['metadata'][byte_pos]
                values.append(f"{val:02x}({val:3d})")
            else:
                values.append("--")
        
        print(f"{byte_pos:4d} | {values[2]:20s} | {values[0]:20s} | {values[1]:20s} | {values[3]:20s}")
    
    # Look for position field (0-3)
    print("\n\nSEARCHING FOR POSITION FIELD (values 0-3):")
    print("-" * 100)
    
    for byte_pos in range(compare_len):
        matches = []
        for pd in player_data:
            if byte_pos < len(pd['metadata']):
                val = pd['metadata'][byte_pos]
                p = pd['player']
                if val == p['pos_code']:
                    matches.append(f"{p['name']}:pos={val}")
                elif 0 <= val <= 3:
                    matches.append(f"{p['name']}:val={val}(pos={p['pos_code']})")
        
        if matches:
            print(f"Byte {byte_pos:2d}: {', '.join(matches)}")
    
    # Look for age field
    print("\n\nSEARCHING FOR AGE FIELD:")
    print("-" * 100)
    
    for byte_pos in range(compare_len):
        matches = []
        for pd in player_data:
            if byte_pos < len(pd['metadata']):
                val = pd['metadata'][byte_pos]
                p = pd['player']
                if val == p['age']:
                    matches.append(f"{p['name']}:age={val}")
                elif 20 <= val <= 40:  # Reasonable age range
                    matches.append(f"{p['name']}:val={val}(age={p['age']})")
        
        if len(matches) >= 2:
            print(f"Byte {byte_pos:2d}: {', '.join(matches)}")

if __name__ == '__main__':
    main()