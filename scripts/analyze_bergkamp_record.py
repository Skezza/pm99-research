#!/usr/bin/env python3
"""
Analyze Dennis BERGKAMP's record and correlate with known stats
"""

from pm99_database_editor import find_player_records
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
    
    # Find BERGKAMP
    bergkamp_records = [r for _, r in records if 'BERGAMP' in r.name.upper()]
    
    if not bergkamp_records:
        print("❌ Dennis BERGKAMP not found!")
        return
    
    print(f"Found {len(bergkamp_records)} BERGKAMP records")
    
    # Take the first (most likely clean record)
    bergkamp = bergkamp_records[0]
    print(f"\n📋 Dennis BERGKAMP Record Analysis")
    print(f"Name: {bergkamp.name}")
    print(f"Team ID: {bergkamp.team_id}")
    print(f"Squad #: {bergkamp.squad_number}")
    print(f"Position: {bergkamp.position} ({bergkamp.get_position_name()})")
    print(f"Record length: {len(bergkamp.raw_data)} bytes")
    
    # BERGKAMP's known stats
    bergkamp_stats = {
        'age': 29,
        'weight_stone': 12,
        'weight_pounds': 8,
        'height_feet': 6,
        'height_inches': 0,
        'rating': 84,
        'nationality': 'Holland',  # Need code
        'position': 3,  # Forward
        'attributes': {
            'SPEED': 89, 'STAMINA': 79, 'AGGRESSION': 59, 'QUALITY': 96,
            'FITNESS': 73, 'MORAL': 99, 'HANDLING': 4, 'PASSING': 90,
            'DRIBBLING': 91, 'HEADING': 62, 'TACKLING': 58, 'SHOOTING': 87
        }
    }
    
    print(f"\n📊 Known Stats:")
    print(f"Age: {bergkamp_stats['age']}")
    print(f"Height: {bergkamp_stats['height_feet']}'{bergkamp_stats['height_inches']}\"")
    print(f"Weight: {bergkamp_stats['weight_stone']}st {bergkamp_stats['weight_pounds']}lb")
    print(f"Rating: {bergkamp_stats['rating']}")
    print(f"Position: {bergkamp_stats['position']} (Forward)")
    print("\nAttributes:")
    for attr, val in bergkamp_stats['attributes'].items():
        print(f"  {attr}: {val}")
    
    # Analyze raw bytes
    print(f"\n🔍 Raw Record Analysis (first 100 bytes)")
    print("Byte | Hex | Dec | XOR(0x61) | ASCII | Notes")
    print("-" * 60)
    
    for i in range(min(100, len(bergkamp.raw_data))):
        b = bergkamp.raw_data[i]
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
        if b in bergkamp_stats['attributes'].values() or xor_val in bergkamp_stats['attributes'].values():
            notes += " ← MATCH!"
        
        if b == bergkamp_stats['age'] or xor_val == bergkamp_stats['age']:
            notes += " ← AGE!"
        if b == bergkamp_stats['rating'] or xor_val == bergkamp_stats['rating']:
            notes += " ← RATING!"
        
        print(f"{i:4d} | 0x{b:02x} | {b:3d} | {xor_val:3d} | {ascii_char} | {notes}")
    
    # Search for specific values
    print(f"\n🎯 Searching for Known Values:")
    
    # Age 29
    print(f"\nAge = 29:")
    age_positions = []
    for i, b in enumerate(bergkamp.raw_data):
        if b == 29:
            age_positions.append((i, 'raw'))
        if (b ^ 0x61) == 29:
            age_positions.append((i, 'xor'))
    print(f"  Found at: {age_positions}")
    
    # Rating 84
    print(f"\nRating = 84:")
    rating_positions = []
    for i, b in enumerate(bergkamp.raw_data):
        if b == 84:
            rating_positions.append((i, 'raw'))
        if (b ^ 0x61) == 84:
            rating_positions.append((i, 'xor'))
    print(f"  Found at: {rating_positions}")
    
    # Attributes search
    print(f"\nAttributes Search:")
    attr_values = list(bergkamp_stats['attributes'].values())
    print(f"Looking for: {attr_values}")
    
    attr_matches = {}
    for attr_name, attr_val in bergkamp_stats['attributes'].items():
        positions = []
        for i, b in enumerate(bergkamp.raw_data):
            if b == attr_val:
                positions.append((i, 'raw'))
            if (b ^ 0x61) == attr_val:
                positions.append((i, 'xor'))
        if positions:
            attr_matches[attr_name] = positions
            print(f"  {attr_name} ({attr_val}): {positions[:5]}")  # First 5 positions
    
    # Look for patterns in attributes
    print(f"\n📈 Attribute Pattern Analysis:")
    if len(bergkamp.attributes) >= 12:
        print(f"Extracted attributes (double-XOR): {bergkamp.attributes}")
        print(f"Match count: {sum(1 for v in bergkamp.attributes if v in attr_values)} / 12")
        
        # Try to match order
        for perm in [[attr_values[i] for i in range(12)],  # Direct order
                     attr_values[::-1],  # Reverse
                     [attr_values[i] for i in [0,2,4,6,8,10,1,3,5,7,9,11]]]:  # Odd/even split
            matches = sum(1 for a, b in zip(bergkamp.attributes, perm) if a == b)
            if matches >= 6:
                print(f"  Possible match ({matches}/12): {perm}")
                break
    else:
        print("  Not enough attributes extracted")
    
    # Height/Weight search
    print(f"\n📏 Physical Stats Search:")
    height_cm = 183  # 6'0" ≈ 183cm
    weight_kg = 79   # 12st 8lb ≈ 79kg
    
    print(f"Height (6'0\" or 183cm):")
    for i in range(len(bergkamp.raw_data) - 1):
        if bergkamp.raw_data[i] == 6 and bergkamp.raw_data[i+1] == 0:
            print(f"  Bytes {i}-{i+1}: (6, 0) raw")
        if (bergkamp.raw_data[i] ^ 0x61) == 6 and (bergkamp.raw_data[i+1] ^ 0x61) == 0:
            print(f"  Bytes {i}-{i+1}: (6, 0) XOR")
        if bergkamp.raw_data[i] == height_cm:
            print(f"  Byte {i}: {height_cm}cm raw")
        if (bergkamp.raw_data[i] ^ 0x61) == height_cm:
            print(f"  Byte {i}: {height_cm}cm XOR")
    
    print(f"\nWeight (12st 8lb or 79kg):")
    for i in range(len(bergkamp.raw_data) - 1):
        if bergkamp.raw_data[i] == 12 and bergkamp.raw_data[i+1] == 8:
            print(f"  Bytes {i}-{i+1}: (12, 8) raw")
        if (bergkamp.raw_data[i] ^ 0x61) == 12 and (bergkamp.raw_data[i+1] ^ 0x61) == 8:
            print(f"  Bytes {i}-{i+1}: (12, 8) XOR")
        if bergkamp.raw_data[i] == weight_kg:
            print(f"  Byte {i}: {weight_kg}kg raw")
        if (bergkamp.raw_data[i] ^ 0x61) == weight_kg:
            print(f"  Byte {i}: {weight_kg}kg XOR")
    
    # Summary of findings
    print(f"\n📋 ANALYSIS SUMMARY:")
    print(f"- Age 29 found at: {len([p for p in age_positions])} positions")
    print(f"- Rating 84 found at: {len(rating_positions)} positions")
    print(f"- Attribute matches: {len(attr_matches)} / 12 attributes located")
    print(f"- Height/Weight patterns: Check output above")
    
    if attr_matches:
        print(f"\n🔍 Possible Attribute Mapping:")
        for attr, positions in attr_matches.items():
            xor_positions = [p for p in positions if p[1] == 'xor']
            if xor_positions:
                print(f"  {attr} may be at byte {xor_positions[0][0]} (XOR encoded)")
    
    print(f"\n💡 Next Steps:")
    print(f"1. Compare with THORNE's record to find consistent patterns")
    print(f"2. Look for age=29 in metadata bytes 43-49")
    print(f"3. Check if rating is calculated or stored directly")
    print(f"4. Physical stats may use different encoding (stone/pounds vs kg)")

if __name__ == '__main__':
    main()