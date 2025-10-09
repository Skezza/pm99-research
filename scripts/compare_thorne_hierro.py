#!/usr/bin/env python3
"""
Compare Peter THORNE and Fernando HIERRO records to find field patterns
"""

from pm99_database_editor import find_player_records, xor_decode
from pathlib import Path
import struct
import re

def find_player_record(file_data: bytes, name_pattern: str, expected_length: int = None):
    """Find specific player record"""
    pos = 0x400
    while pos < len(file_data) - 1000:
        try:
            length = struct.unpack_from("<H", file_data, pos)[0]
            if 1000 < length < 200000:
                encoded = file_data[pos+2 : pos+2+length]
                decoded = xor_decode(encoded, 0x61)
                
                text = decoded.decode('latin-1', errors='ignore')
                if re.search(name_pattern, text, re.IGNORECASE):
                    # Found candidate
                    if expected_length is None or abs(length - expected_length) < 1000:
                        return pos, length, decoded
            pos += length + 2
        except:
            pos += 1
    return None, None, None

def main():
    file_path = 'DBDAT/JUG98030.FDI'
    if not Path(file_path).exists():
        print(f"File not found: {file_path}")
        return
    
    file_data = Path(file_path).read_bytes()
    
    # Find HIERRO (known clean record ~69 bytes)
    hierro_pos, hierro_len, hierro_data = find_player_record(file_data, r'HIERRO.*FERNANDO', 70)
    
    # Find THORNE (biography record ~11KB)
    thorne_pos, thorne_len, thorne_data = find_player_record(file_data, r'Peter.*THORNE', 11500)
    
    if not hierro_data or not thorne_data:
        print("❌ Could not find both records")
        return
    
    print(f"🎯 Found Records:")
    print(f"HIERRO: offset 0x{hierro_pos:08x}, length {hierro_len} bytes")
    print(f"THORNE: offset 0x{thorne_pos:08x}, length {thorne_len} bytes")
    
    # Known stats
    hierro_stats = {
        'age': 30, 'rating': 85, 'position': 1,  # Defender
        'attributes': [85, 91, 89, 87, 76, 82, 10, 74, 70, 84, 94, 80]
    }
    
    thorne_stats = {
        'age': 25, 'rating': 70, 'position': 3,  # Forward
        'attributes': [66, 63, 74, 64, 73, 84, 28, 69, 65, 73, 69, 80]
    }
    
    # Search for common values in both records
    common_values = set(hierro_stats['attributes'] + thorne_stats['attributes'])
    age_values = {hierro_stats['age'], thorne_stats['age']}
    rating_values = {hierro_stats['rating'], thorne_stats['rating']}
    position_values = {hierro_stats['position'], thorne_stats['position']}
    
    print(f"\n🔍 Searching for Known Values:")
    
    def search_values(data, name, values_set, label):
        print(f"\n{name} - {label}:")
        positions = []
        for i, b in enumerate(data):
            if b in values_set:
                positions.append((i, b, 'raw'))
            xor_val = b ^ 0x61
            if xor_val in values_set:
                positions.append((i, xor_val, 'xor'))
        # Sort by position
        positions.sort(key=lambda x: x[0])
        for pos, val, enc in positions[:10]:  # First 10
            print(f"  Byte {pos}: {val} ({enc})")
        return positions
    
    # Search ages
    search_values(hierro_data, "HIERRO", age_values, "Age")
    search_values(thorne_data, "THORNE", age_values, "Age")
    
    # Search ratings
    search_values(hierro_data, "HIERRO", rating_values, "Rating")
    search_values(thorne_data, "THORNE", rating_values, "Rating")
    
    # Search positions
    search_values(hierro_data, "HIERRO", position_values, "Position")
    search_values(thorne_data, "THORNE", position_values, "Position")
    
    # Attribute correlation
    print(f"\n📈 Attribute Correlation Analysis:")
    
    # For clean records like HIERRO, check bytes 50-61
    if len(hierro_data) > 62:
        hierro_attrs = [hierro_data[i] ^ 0x61 for i in range(50, 62)]
        print(f"HIERRO extracted attributes (bytes 50-61 XOR): {hierro_attrs}")
        matches = [val for val in hierro_attrs if val in hierro_stats['attributes']]
        print(f"HIERRO matches: {len(matches)}/12 = {matches}")
    
    # For THORNE biography, look for attribute values in metadata regions
    thorne_attr_positions = {}
    for attr_name, attr_val in zip(['SPEED', 'STAMINA', 'AGGRESSION', 'QUALITY', 'FITNESS', 'MORAL',
                                   'HANDLING', 'PASSING', 'DRIBBLING', 'HEADING', 'TACKLING', 'SHOOTING'],
                                  thorne_stats['attributes']):
        positions = []
        for i, b in enumerate(thorne_data[:200]):  # First 200 bytes
            if b == attr_val:
                positions.append((i, 'raw'))
            if (b ^ 0x61) == attr_val:
                positions.append((i, 'xor'))
        if positions:
            thorne_attr_positions[attr_name] = positions[:3]  # First 3 positions
            print(f"{attr_name} ({attr_val}): {positions[:3]}")
    
    # Look for patterns in positions
    print(f"\n🔍 Pattern Analysis:")
    if thorne_attr_positions:
        # Check if attributes are in consistent relative positions
        xor_positions = [p[0] for attr, poss in thorne_attr_positions.items() for p in poss if p[1] == 'xor']
        if xor_positions:
            print(f"XOR-encoded attribute positions: {sorted(set(xor_positions))}")
    
    # Height/Weight for THORNE
    print(f"\n📏 THORNE Physical Stats:")
    height_ft = 6
    height_in = 0
    weight_st = 11
    weight_lb = 4
    
    # Look for 6,0
    for i in range(len(thorne_data) - 1):
        pair = (thorne_data[i], thorne_data[i+1])
        xor_pair = (thorne_data[i] ^ 0x61, thorne_data[i+1] ^ 0x61)
        if pair == (height_ft, height_in) or xor_pair == (height_ft, height_in):
            print(f"Height 6'0\": bytes {i}-{i+1} {pair} ({'XOR' if xor_pair == (height_ft, height_in) else 'raw'})")
    
    # Weight 11,4
    for i in range(len(thorne_data) - 1):
        pair = (thorne_data[i], thorne_data[i+1])
        xor_pair = (thorne_data[i] ^ 0x61, thorne_data[i+1] ^ 0x61)
        if pair == (weight_st, weight_lb) or xor_pair == (weight_st, weight_lb):
            print(f"Weight 11st 4lb: bytes {i}-{i+1} {pair} ({'XOR' if xor_pair == (weight_st, weight_lb) else 'raw'})")
    
    # Save records for manual inspection
    with open('hierro_record.bin', 'wb') as f:
        f.write(hierro_data)
    with open('thorne_record_full.bin', 'wb') as f:
        f.write(thorne_data)
    
    print(f"\n💾 Records saved:")
    print(f"  hierro_record.bin ({len(hierro_data)} bytes)")
    print(f"  thorne_record_full.bin ({len(thorne_data)} bytes)")
    
    print(f"\n💡 Analysis Summary:")
    print(f"- HIERRO clean record: {len(hierro_data)} bytes, position {hierro_stats['position']}")
    print(f"- THORNE biography record: {len(thorne_data)} bytes, position {thorne_stats['position']}")
    print(f"- Common patterns needed for field mapping")
    print(f"- Next: Manual hex analysis of saved files or provide more player stats")

if __name__ == '__main__':
    main()