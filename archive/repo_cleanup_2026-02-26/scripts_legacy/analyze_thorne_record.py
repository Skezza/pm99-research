#!/usr/bin/env python3
"""
Analyze Peter THORNE's record and correlate with known stats
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
    
    # Find THORNE
    thorne_records = [r for _, r in records if 'THORNE' in r.name.upper()]
    
    if not thorne_records:
        print("❌ Peter THORNE not found!")
        return
    
    print(f"Found {len(thorne_records)} THORNE records")
    
    # Take the first (most likely clean record)
    thorne = thorne_records[0]
    print(f"\n📋 Peter THORNE Record Analysis")
    print(f"Name: {thorne.name}")
    print(f"Team ID: {thorne.team_id}")
    print(f"Squad #: {thorne.squad_number}")
    print(f"Position: {thorne.position} ({thorne.get_position_name()})")
    print(f"Record length: {len(thorne.raw_data)} bytes")
    
    # THORNE's known stats
    thorne_stats = {
        'age': 25,
        'height_feet': 6,
        'height_inches': 0,
        'weight_stone': 11,
        'weight_pounds': 4,
        'rating': 70,
        'nationality': 'England',  # Need code
        'position': 3,  # Forward
        'attributes': {
            'SPEED': 66, 'STAMINA': 63, 'AGGRESSION': 74, 'QUALITY': 64,
            'FITNESS': 73, 'MORAL': 84, 'HANDLING': 28, 'PASSING': 69,
            'DRIBBLING': 65, 'HEADING': 73, 'TACKLING': 69, 'SHOOTING': 80
        }
    }
    
    print(f"\n📊 Known Stats:")
    print(f"Age: {thorne_stats['age']}")
    print(f"Height: {thorne_stats['height_feet']}'{thorne_stats['height_inches']}\"")
    print(f"Weight: {thorne_stats['weight_stone']}st {thorne_stats['weight_pounds']}lb")
    print(f"Rating: {thorne_stats['rating']}")
    print(f"Position: {thorne_stats['position']} (Forward)")
    print("\nAttributes:")
    for attr, val in thorne_stats['attributes'].items():
        print(f"  {attr}: {val}")
    
    # Analyze raw bytes
    print(f"\n🔍 Raw Record Analysis (first 100 bytes)")
    print("Byte | Hex | Dec | XOR(0x61) | ASCII | Notes")
    print("-" * 60)
    
    for i in range(min(100, len(thorne.raw_data))):
        b = thorne.raw_data[i]
        xor_val = b ^ 0x61
        ascii_char = chr(b) if 32 <= b <= 126 else '·'
        
        notes = ""
        if i == 0:
            notes = f"Team ID low ({b})"
        elif i == 1:
            notes = f"Team ID high ({b})"
        elif i == 2:
            notes = f"Squad # ({b})"
        elif 5 <= i < 40:
            notes = "Name region"
        elif i == 42:
            notes = f"Position ({xor_val})"
        elif 50 <= i < 62:
            notes = f"Attr candidate ({xor_val})"
        
        # Highlight matches
        if b in thorne_stats['attributes'].values() or xor_val in thorne_stats['attributes'].values():
            notes += " ← MATCH!"
        
        if b == thorne_stats['age'] or xor_val == thorne_stats['age']:
            notes += " ← AGE!"
        if b == thorne_stats['rating'] or xor_val == thorne_stats['rating']:
            notes += " ← RATING!"
        
        print(f"{i:4d} | 0x{b:02x} | {b:3d} | {xor_val:3d} | {ascii_char} | {notes}")
    
    # Search for specific values
    print(f"\n🎯 Searching for Known Values:")
    
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
    
    # Attributes search
    print(f"\nAttributes Search:")
    attr_values = list(thorne_stats['attributes'].values())
    print(f"Looking for: {attr_values}")
    
    attr_matches = {}
    for attr_name, attr_val in thorne_stats['attributes'].items():
        positions = []
        for i, b in enumerate(thorne.raw_data):
            if b == attr_val:
                positions.append((i, 'raw'))
            if (b ^ 0x61) == attr_val:
                positions.append((i, 'xor'))
        if positions:
            attr_matches[attr_name] = positions
            print(f"  {attr_name} ({attr_val}): {positions[:5]}")  # First 5 positions
    
    # Look for patterns in attributes
    print(f"\n📈 Attribute Pattern Analysis:")
    if len(thorne.attributes) >= 12:
        print(f"Extracted attributes (double-XOR): {thorne.attributes}")
        print(f"Match count: {sum(1 for v in thorne.attributes if v in attr_values)} / 12")
        
        # Try to match order
        for perm in [[attr_values[i] for i in range(12)],  # Direct order
                     attr_values[::-1],  # Reverse
                     [attr_values[i] for i in [0,2,4,6,8,10,1,3,5,7,9,11]]]:  # Odd/even split
            matches = sum(1 for a, b in zip(thorne.attributes, perm) if a == b)
            if matches >= 6:
                print(f"  Possible match ({matches}/12): {perm}")
                break
    else:
        print("  Not enough attributes extracted")
    
    # Height/Weight search
    print(f"\n📏 Physical Stats Search:")
    height_cm = 183  # 6'0" ≈ 183cm
    weight_kg = 70   # 11st 4lb ≈ 70kg
    
    print(f"Height (6'0\" or 183cm):")
    for i in range(len(thorne.raw_data) - 1):
        if thorne.raw_data[i] == 6 and thorne.raw_data[i+1] == 0:
            print(f"  Bytes {i}-{i+1}: (6, 0) raw")
        if (thorne.raw_data[i] ^ 0x61) == 6 and (thorne.raw_data[i+1] ^ 0x61) == 0:
            print(f"  Bytes {i}-{i+1}: (6, 0) XOR")
        if thorne.raw_data[i] == height_cm or (thorne.raw_data[i] ^ 0x61) == height_cm:
            print(f"  Byte {i}: {height_cm}cm {'(XOR)' if (thorne.raw_data[i] ^ 0x61) == height_cm else '(raw)'}")
    
    print(f"\nWeight (11st 4lb or 70kg):")
    for i in range(len(thorne.raw_data) - 1):
        if thorne.raw_data[i] == 11 and thorne.raw_data[i+1] == 4:
            print(f"  Bytes {i}-{i+1}: (11, 4) raw")
        if (thorne.raw_data[i] ^ 0x61) == 11 and (thorne.raw_data[i+1] ^ 0x61) == 4:
            print(f"  Bytes {i}-{i+1}: (11, 4) XOR")
        if thorne.raw_data[i] == weight_kg or (thorne.raw_data[i] ^ 0x61) == weight_kg:
            print(f"  Byte {i}: {weight_kg}kg {'(XOR)' if (thorne.raw_data[i] ^ 0x61) == weight_kg else '(raw)'}")
    
    # Summary of findings
    print(f"\n📋 ANALYSIS SUMMARY:")
    print(f"- Age 25 found at: {len([p for p in age_positions])} positions")
    print(f"- Rating 70 found at: {len(rating_positions)} positions")
    print(f"- Attribute matches: {len(attr_matches)} / 12 attributes located")
    print(f"- Height/Weight patterns: Check output above")
    
    if attr_matches:
        print(f"\n🔍 Possible Attribute Mapping:")
        for attr, positions in attr_matches.items():
            xor_positions = [p for p in positions if p[1] == 'xor']
            if xor_positions:
                print(f"  {attr} may be at byte {xor_positions[0][0]} (XOR encoded)")
    
    print(f"\n💡 Next Steps:")
    print(f"1. Compare with HIERRO's record to find consistent patterns")
    print(f"2. Look for age=25 in metadata bytes 43-49")
    print(f"3. Check if rating is calculated or stored directly")
    print(f"4. Physical stats may use different encoding (stone/pounds vs kg)")

if __name__ == '__main__':
    main()