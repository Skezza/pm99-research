#!/usr/bin/env python3
"""
Focused analysis using CLEAN player records (short ones without biographies).
Manual extraction of metadata region for comparison.
"""

def xor_decode(data):
    return bytes(b ^ 0x61 for b in data)

def analyze_hierro():
    """Hierro has a clean 69-byte record."""
    record_hex = bytes.fromhex(
        "6b 61 65 67 61 48 69 65 72 72 6f 75 61 46 65 72 "
        "6e 61 6e 64 6f 20 52 75 69 7a 20 48 49 45 52 52 "
        "4f 65 61 67 64 65 6e 61 61 77 60 62 60 76 62 d1 "
        "66 da 35 34 3a 38 36 2e 27 2b 31 35 6b 61 35 5f "
        "58 31 29 44 61"
    )
    
    return {
        'name': 'HIERRO',
        'pos': 'Defender',
        'pos_code': 1,
        'age': 30,
        'nat': 'Spain',
        'team_id': int.from_bytes(record_hex[0:2], 'little'),
        'squad': record_hex[2],
        'full_record': record_hex,
        # Name appears to be bytes 3-38, metadata 39-56, attributes 57-66
        'name_region': record_hex[3:39],
        'metadata': record_hex[39:59],  # 20 bytes before attributes
        'attributes': record_hex[59:69]  # Last 10 bytes
    }

def analyze_zidane():
    """Zidane has a clean 70-byte record."""
    record_hex = bytes.fromhex(
        "01 6e 74 67 61 5a 69 64 61 6e 65 74 61 59 61 7a "
        "69 64 20 5a 69 6e 65 64 69 6e 65 20 5a 49 44 41 "
        "4e 45 6a 61 6c 70 71 6b 73 69 79 60 62 63 76 67 "
        "d5 66 d8 31 38 39 35 3c 2f 35 38 34 53 66 61 37 "
        "2f 2a 32 2c 74 61"
    )
    
    return {
        'name': 'ZIDANE',
        'pos': 'Midfielder',
        'pos_code': 2,
        'age': 26,
        'nat': 'France',
        'team_id': int.from_bytes(record_hex[0:2], 'little'),
        'squad': record_hex[2],
        'full_record': record_hex,
        'name_region': record_hex[3:40],
        'metadata': record_hex[40:60],  # 20 bytes before attributes
        'attributes': record_hex[60:70]  # Last 10 bytes
    }

def main():
    players = [analyze_hierro(), analyze_zidane()]
    
    print("="*100)
    print("FOCUSED METADATA ANALYSIS - CLEAN RECORDS ONLY")
    print("="*100)
    
    for p in players:
        print(f"\n{p['name']} - {p['pos']} (pos_code={p['pos_code']}) - Age {p['age']} - {p['nat']}")
        print(f"  Team ID: 0x{p['team_id']:04x} | Squad: {p['squad']}")
        print(f"  Record size: {len(p['full_record'])} bytes")
        print(f"  Name region: {len(p['name_region'])} bytes")
        print(f"  Metadata: {len(p['metadata'])} bytes")
        print(f"  Attributes: {len(p['attributes'])} bytes")
        
        print(f"\n  Name bytes:     {' '.join(f'{b:02x}' for b in p['name_region'])}")
        print(f"  Name text:      {p['name_region'].decode('latin-1', errors='ignore')}")
        
        print(f"\n  Metadata bytes: {' '.join(f'{b:02x}' for b in p['metadata'])}")
        print(f"  Metadata dec:   {' '.join(f'{b:3d}' for b in p['metadata'])}")
        
        print(f"\n  Attributes:     {' '.join(f'{b:02x}' for b in p['attributes'])}")
        print(f"  Attr decimal:   {' '.join(f'{b:3d}' for b in p['attributes'])}")
    
    # Compare metadata byte by byte
    print("\n\n" + "="*100)
    print("METADATA BYTE-BY-BYTE COMPARISON")
    print("="*100)
    print(f"\n{'Byte':<6} {'HIERRO(DEF,30,ESP)':<25} {'ZIDANE(MID,26,FRA)':<25} {'Difference'}")
    print("-"*100)
    
    meta_len = min(len(players[0]['metadata']), len(players[1]['metadata']))
    
    for i in range(meta_len):
        h_val = players[0]['metadata'][i]
        z_val = players[1]['metadata'][i]
        
        h_str = f"{h_val:02x}({h_val:3d})"
        z_str = f"{z_val:02x}({z_val:3d})"
        
        diff = ""
        if h_val == z_val:
            diff = "SAME"
        elif abs(h_val - z_val) == 1:
            diff = "±1"
        elif h_val == players[0]['pos_code'] or z_val == players[1]['pos_code']:
            diff = "⚠️ POSITION?"
        elif h_val == players[0]['age'] or z_val == players[1]['age']:
            diff = "⚠️ AGE?"
        
        print(f"{i:<6} {h_str:<25} {z_str:<25} {diff}")
    
    # Specific field searches
    print("\n\n" + "="*100)
    print("FIELD IDENTIFICATION")
    print("="*100)
    
    print("\n📍 POSITION FIELD CANDIDATES (looking for 1 vs 2):")
    print("-"*50)
    for i in range(meta_len):
        h_val = players[0]['metadata'][i]
        z_val = players[1]['metadata'][i]
        
        if h_val == 1 and z_val == 2:
            print(f"  Byte {i:2d}: HIERRO=1 (Defender), ZIDANE=2 (Midfielder) ✓✓✓ EXACT MATCH!")
        elif h_val == 1 or z_val == 2:
            print(f"  Byte {i:2d}: HIERRO={h_val}, ZIDANE={z_val} (partial match)")
    
    print("\n📅 AGE FIELD CANDIDATES (looking for 30 vs 26):")
    print("-"*50)
    for i in range(meta_len):
        h_val = players[0]['metadata'][i]
        z_val = players[1]['metadata'][i]
        
        if h_val == 30 and z_val == 26:
            print(f"  Byte {i:2d}: HIERRO=30, ZIDANE=26 ✓✓✓ EXACT MATCH!")
        elif h_val == 30 or z_val == 26:
            print(f"  Byte {i:2d}: HIERRO={h_val}, ZIDANE={z_val} (partial match)")
        elif 20 <= h_val <= 40 and 20 <= z_val <= 40:
            print(f"  Byte {i:2d}: HIERRO={h_val}, ZIDANE={z_val} (both in age range)")
    
    print("\n🌍 NATIONALITY FIELD CANDIDATES (Spain vs France):")
    print("-"*50)
    print("  Looking for bytes that differ significantly (different country codes)...")
    for i in range(meta_len):
        h_val = players[0]['metadata'][i]
        z_val = players[1]['metadata'][i]
        
        if h_val != z_val and 0 <= h_val <= 50 and 0 <= z_val <= 50:
            print(f"  Byte {i:2d}: HIERRO={h_val:3d}, ZIDANE={z_val:3d} (diff={abs(h_val-z_val):2d})")

if __name__ == '__main__':
    main()