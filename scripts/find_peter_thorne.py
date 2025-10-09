#!/usr/bin/env python3
"""
Find and analyze the correct Peter THORNE record
"""

from pm99_database_editor import find_player_records, xor_decode
from pathlib import Path
import struct
import re

def main():
    file_path = 'DBDAT/JUG98030.FDI'
    if not Path(file_path).exists():
        print(f"File not found: {file_path}")
        return
    
    file_data = Path(file_path).read_bytes()
    records = find_player_records(file_data)
    
    # Find all THORNE records
    thorne_records = [(o, r) for o, r in records if 'THORNE' in r.name.upper()]
    
    print(f"Found {len(thorne_records)} THORNE records")
    
    # Look for Peter THORNE specifically
    peter_thorne = None
    for offset, record in thorne_records:
        if 'PETER' in record.name.upper():
            peter_thorne = (offset, record)
            break
    
    if not peter_thorne:
        # Fallback: look for Forward position or longer name
        for offset, record in thorne_records:
            if len(record.name) > 10 or record.position == 3:  # Forward
                peter_thorne = (offset, record)
                print(f"Using fallback record: {record.name}")
                break
    
    if not peter_thorne:
        print("❌ Could not identify Peter THORNE record")
        # Show all THORNE records
        for i, (offset, record) in enumerate(thorne_records):
            print(f"{i+1}. {record.name} (Pos: {record.get_position_name()}, Len: {len(record.raw_data)})")
        return
    
    offset, thorne = peter_thorne
    print(f"\n🎯 Selected Peter THORNE Record:")
    print(f"Name: {thorne.name}")
    print(f"Team ID: {thorne.team_id}")
    print(f"Squad #: {thorne.squad_number}")
    print(f"Position: {thorne.position} ({thorne.get_position_name()})")
    print(f"Record length: {len(thorne.raw_data)} bytes")
    print(f"Offset: 0x{offset:08x}")
    
    # THORNE's known stats
    thorne_stats = {
        'age': 25,
        'height_feet': 6,
        'height_inches': 0,
        'weight_stone': 11,
        'weight_pounds': 4,
        'rating': 70,
        'nationality': 'England',
        'position': 3,  # Forward
        'attributes': [66, 63, 74, 64, 73, 84, 28, 69, 65, 73, 69, 80],  # SPEED to SHOOTING
        'attr_names': ['SPEED', 'STAMINA', 'AGGRESSION', 'QUALITY', 'FITNESS', 'MORAL',
                       'HANDLING', 'PASSING', 'DRIBBLING', 'HEADING', 'TACKLING', 'SHOOTING']
    }
    
    print(f"\n📊 Known Stats (Position should be Forward=3):")
    print(f"Age: {thorne_stats['age']}")
    print(f"Height: {thorne_stats['height_feet']}'{thorne_stats['height_inches']}\"")
    print(f"Weight: {thorne_stats['weight_stone']}st {thorne_stats['weight_pounds']}lb")
    print(f"Rating: {thorne_stats['rating']}")
    print(f"Expected Position: {thorne_stats['position']} (Forward)")
    
    print(f"\nAttributes (in game order):")
    for name, val in zip(thorne_stats['attr_names'], thorne_stats['attributes']):
        print(f"  {name}: {val}")
    
    # Detailed byte analysis
    print(f"\n🔍 Detailed Byte Analysis (bytes 0-100)")
    print("Byte | Hex | Dec | XOR | ASCII | Match Notes")
    print("-" * 70)
    
    attr_set = set(thorne_stats['attributes'])
    age_set = {thorne_stats['age']}
    rating_set = {thorne_stats['rating']}
    
    for i in range(min(100, len(thorne.raw_data))):
        b = thorne.raw_data[i]
        xor_val = b ^ 0x61
        ascii_char = chr(b) if 32 <= b <= 126 else '·'
        
        notes = ""
        if i == 0 or i == 1:
            notes = "TEAM ID"
        elif i == 2:
            notes = "SQUAD #"
        elif 5 <= i < 40:
            notes = "NAME"
        elif i == 42:
            notes = f"POSITION ({xor_val})"
        elif 50 <= i < 62:
            notes = f"ATTR? ({xor_val})"
        
        # Check for matches
        if b in attr_set:
            notes += f" ATTR({b})"
        if xor_val in attr_set:
            notes += f" ATTR({xor_val})"
        if b == thorne_stats['age']:
            notes += " AGE!"
        if xor_val == thorne_stats['age']:
            notes += " AGE!"
        if b == thorne_stats['rating']:
            notes += " RATING!"
        if xor_val == thorne_stats['rating']:
            notes += " RATING!"
        if xor_val == 3:  # Expected position
            notes += " POS!"
        
        print(f"{i:4d} | 0x{b:02x} | {b:3d} | {xor_val:3d} | {ascii_char} | {notes}")
    
    # Specific searches
    print(f"\n🎯 Specific Value Search:")
    
    # Position 3 (Forward)
    print(f"\nPosition = 3 (Forward):")
    pos_positions = []
    for i, b in enumerate(thorne.raw_data):
        if (b ^ 0x61) == 3:
            pos_positions.append(i)
    print(f"  Found at: {pos_positions}")
    
    # Age 25
    print(f"\nAge = 25:")
    age_positions = []
    for i, b in enumerate(thorne.raw_data):
        if b == 25:
            age_positions.append((i, 'raw'))
        if (b ^ 0x61) == 25:
            age_positions.append((i, 'xor'))
    print(f"  Found at: {age_positions}")
    
    # Rating 70
    print(f"\nRating = 70:")
    rating_positions = []
    for i, b in enumerate(thorne.raw_data):
        if b == 70:
            rating_positions.append((i, 'raw'))
        if (b ^ 0x61) == 70:
            rating_positions.append((i, 'xor'))
    print(f"  Found at: {rating_positions}")
    
    # Attribute correlation
    print(f"\n📈 Attribute Correlation:")
    if len(thorne.attributes) >= 12:
        print(f"Extracted attributes: {thorne.attributes}")
        matches = []
        for i, attr_val in enumerate(thorne.attributes):
            if attr_val in thorne_stats['attributes']:
                attr_name = thorne_stats['attr_names'][thorne_stats['attributes'].index(attr_val)]
                matches.append(f"{attr_name} at position {i}")
        print(f"  Matches: {matches}")
    else:
        print(f"  Only {len(thorne.attributes)} attributes extracted")
    
    # Height/Weight
    print(f"\n📏 Height/Weight Analysis:")
    height_cm = 183  # 6'0"
    weight_kg = 70   # 11st 4lb
    
    # Look for 6,0 or 183
    print(f"Height patterns:")
    for i in range(len(thorne.raw_data) - 1):
        pair = (thorne.raw_data[i], thorne.raw_data[i+1])
        xor_pair = (thorne.raw_data[i] ^ 0x61, thorne.raw_data[i+1] ^ 0x61)
        if pair == (6, 0) or xor_pair == (6, 0):
            print(f"  Bytes {i}-{i+1}: {pair} {'(XOR)' if xor_pair == (6, 0) else '(raw)'}")
        if thorne.raw_data[i] == height_cm or (thorne.raw_data[i] ^ 0x61) == height_cm:
            print(f"  Byte {i}: 183cm {'(XOR)' if (thorne.raw_data[i] ^ 0x61) == height_cm else '(raw)'}")
    
    # Weight 11,4 or 70
    print(f"\nWeight patterns:")
    for i in range(len(thorne.raw_data) - 1):
        pair = (thorne.raw_data[i], thorne.raw_data[i+1])
        xor_pair = (thorne.raw_data[i] ^ 0x61, thorne.raw_data[i+1] ^ 0x61)
        if pair == (11, 4) or xor_pair == (11, 4):
            print(f"  Bytes {i}-{i+1}: {pair} {'(XOR)' if xor_pair == (11, 4) else '(raw)'}")
        if thorne.raw_data[i] == weight_kg or (thorne.raw_data[i] ^ 0x61) == weight_kg:
            print(f"  Byte {i}: 70kg {'(XOR)' if (thorne.raw_data[i] ^ 0x61) == weight_kg else '(raw)'}")
    
    # Nationality - England
    print(f"\n🏴󠁧󠁢󠁥󠁮󠁧󠁿 Nationality Search (England):")
    england_code_candidates = [1, 2, 3, 25, 30, 44]  # Common country codes
    for candidate in england_code_candidates:
        positions = []
        for i, b in enumerate(thorne.raw_data):
            if b == candidate:
                positions.append((i, 'raw'))
            if (b ^ 0x61) == candidate:
                positions.append((i, 'xor'))
        if positions:
            print(f"  England code {candidate}: {positions[:3]}")
    
    print(f"\n💡 Key Findings:")
    if pos_positions:
        print(f"  - Position 3 (Forward) found at byte(s): {pos_positions}")
    if age_positions:
        print(f"  - Age 25 likely at byte {age_positions[0][0]} ({age_positions[0][1]}-encoded)")
    if rating_positions:
        print(f"  - Rating 70 at byte {rating_positions[0][0]} ({rating_positions[0][1]}-encoded)")
    
    print(f"\n🔍 Recommendations:")
    print(f"1. Byte 42 position is {thorne.position} but should be 3 - check if biography records use different offset")
    print(f"2. Run the same analysis on HIERRO to find consistent patterns")
    print(f"3. Age at byte 67 XOR suggests metadata block 43-49 contains age")
    print(f"4. Rating at byte 163 suggests additional data beyond standard 62 bytes")

if __name__ == '__main__':
    main()