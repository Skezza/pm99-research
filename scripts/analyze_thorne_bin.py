#!/usr/bin/env python3
"""
Analyze the saved thorne_record.bin file with known stats
"""

from pathlib import Path
import struct

def xor_decode(data: bytes, key: int = 0x61) -> bytes:
    return bytes(b ^ key for b in data)

def main():
    bin_path = 'thorne_record.bin'
    if not Path(bin_path).exists():
        print(f"File not found: {bin_path}")
        print("Run locate_thorne_exact.py first to generate it")
        return
    
    record_data = Path(bin_path).read_bytes()
    print(f"Loaded {len(record_data)} bytes from {bin_path}")
    
    # THORNE's known stats
    thorne_stats = {
        'age': 25,
        'rating': 70,
        'position': 3,  # Forward
        'attributes': [66, 63, 74, 64, 73, 84, 28, 69, 65, 73, 69, 80],  # SPEED to SHOOTING
        'attr_names': ['SPEED', 'STAMINA', 'AGGRESSION', 'QUALITY', 'FITNESS', 'MORAL',
                       'HANDLING', 'PASSING', 'DRIBBLING', 'HEADING', 'TACKLING', 'SHOOTING']
    }
    
    # Physical
    height_ft = 6
    height_in = 0
    weight_st = 11
    weight_lb = 4
    
    print(f"\n📊 Known Stats:")
    print(f"Age: {thorne_stats['age']}")
    print(f"Rating: {thorne_stats['rating']}")
    print(f"Position: {thorne_stats['position']} (Forward)")
    print(f"Height: {height_ft}'{height_in}\"")
    print(f"Weight: {weight_st}st {weight_lb}lb")
    print("\nAttributes:")
    for name, val in zip(thorne_stats['attr_names'], thorne_stats['attributes']):
        print(f"  {name}: {val}")
    
    # Byte-by-byte analysis
    print(f"\n🔍 Byte Analysis (all {len(record_data)} bytes)")
    print("Byte | Hex | Dec | XOR | ASCII | Match")
    print("-" * 50)
    
    attr_set = set(thorne_stats['attributes'])
    age_set = {thorne_stats['age']}
    rating_set = {thorne_stats['rating']}
    pos_set = {thorne_stats['position']}
    
    for i in range(len(record_data)):
        b = record_data[i]
        xor_val = b ^ 0x61
        ascii_char = chr(b) if 32 <= b <= 126 else '·'
        
        match = ""
        if b in attr_set:
            match = f"ATTR({b})"
        if xor_val in attr_set:
            match = f"ATTR({xor_val})"
        if b == thorne_stats['age']:
            match = "AGE!"
        if xor_val == thorne_stats['age']:
            match = "AGE!"
        if b == thorne_stats['rating']:
            match = "RATING!"
        if xor_val == thorne_stats['rating']:
            match = "RATING!"
        if xor_val == thorne_stats['position']:
            match = "POS!"
        if b == height_ft or b == height_in or b == weight_st or b == weight_lb:
            match = f"PHYS({b})"
        if xor_val == height_ft or xor_val == height_in or xor_val == weight_st or xor_val == weight_lb:
            match = f"PHYS({xor_val})"
        
        print(f"{i:4d} | 0x{b:02x} | {b:3d} | {xor_val:3d} | {ascii_char} | {match}")
    
    # Summary of matches
    print(f"\n📋 Match Summary:")
    attr_matches = 0
    for i, attr_val in enumerate(thorne_stats['attributes']):
        found = False
        for j, b in enumerate(record_data):
            if b == attr_val or (b ^ 0x61) == attr_val:
                found = True
                xor_type = 'XOR' if (b ^ 0x61) == attr_val else 'RAW'
                print(f"  {thorne_stats['attr_names'][i]} ({attr_val}): found at byte {j} ({xor_type})")
                break
        if found:
            attr_matches += 1
    
    print(f"\nAttribute matches found: {attr_matches}/12")
    
    # Age and Rating
    age_found = any(b == thorne_stats['age'] or (b ^ 0x61) == thorne_stats['age'] for b in record_data)
    rating_found = any(b == thorne_stats['rating'] or (b ^ 0x61) == thorne_stats['rating'] for b in record_data)
    pos_found = any((b ^ 0x61) == thorne_stats['position'] for b in record_data)
    
    print(f"Age ({thorne_stats['age']}): {'✅ Found' if age_found else '❌ Not found'}")
    print(f"Rating ({thorne_stats['rating']}): {'✅ Found' if rating_found else '❌ Not found'}")
    print(f"Position ({thorne_stats['position']}): {'✅ Found' if pos_found else '❌ Not found'}")
    
    # Physical
    height_found = any(b == height_ft and record_data[i+1] == height_in for i in range(len(record_data)-1)) or \
                   any((b ^ 0x61) == height_ft and (record_data[i+1] ^ 0x61) == height_in for i in range(len(record_data)-1))
    weight_found = any(b == weight_st and record_data[i+1] == weight_lb for i in range(len(record_data)-1)) or \
                   any((b ^ 0x61) == weight_st and (record_data[i+1] ^ 0x61) == weight_lb for i in range(len(record_data)-1))
    
    print(f"Height (6,0): {'✅ Found' if height_found else '❌ Not found'}")
    print(f"Weight (11,4): {'✅ Found' if weight_found else '❌ Not found'}")
    
    print(f"\n💡 Recommendations for Field Mapping:")
    if age_found:
        for i, b in enumerate(record_data):
            if (b ^ 0x61) == thorne_stats['age']:
                print(f"  - Age likely at byte {i} (XOR encoded)")
    if rating_found:
        for i, b in enumerate(record_data):
            if b == thorne_stats['rating']:
                print(f"  - Rating likely at byte {i} (raw)")
    
    # Look for consistent patterns with HIERRO
    print(f"\n🔍 Pattern Comparison with HIERRO:")
    # Note: Run analyze_hierro_structure.py for HIERRO comparison
    print(f"  - THORNE record length: {len(record_data)} bytes (biography)")
    print(f"  - HIERRO record length: ~69 bytes (clean)")
    print(f"  - Different structures, but metadata fields may align")
    print(f"  - Run 'python analyze_hierro_structure.py' for HIERRO analysis")
    print(f"  - Compare XOR positions for age/rating between records")

if __name__ == '__main__':
    main()