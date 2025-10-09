#!/usr/bin/env python3
"""
Extract the full Peter THORNE biography section and search for all known stats
"""

from pathlib import Path
import struct

def xor_decode(data: bytes, key: int = 0x61) -> bytes:
    return bytes(b ^ key for b in data)

def main():
    file_path = 'DBDAT/JUG98030.FDI'
    if not Path(file_path).exists():
        print(f"File not found: {file_path}")
        return
    
    file_data = Path(file_path).read_bytes()
    
    # From previous analysis, THORNE section at 0x001c0366, length 11585
    section_offset = 0x1c0366
    section_length = 11585
    
    if section_offset + 2 + section_length > len(file_data):
        print(f"Section offset out of bounds")
        return
    
    # Extract section
    length_prefix = struct.unpack_from("<H", file_data, section_offset)[0]
    encoded = file_data[section_offset+2 : section_offset+2+section_length]
    decoded = xor_decode(encoded, 0x61)
    
    print(f"Extracted full THORNE section:")
    print(f"Offset: 0x{section_offset:08x}")
    print(f"Length: {section_length} bytes")
    print(f"Decoded length: {len(decoded)} bytes")
    
    # Save full decoded section
    with open('thorne_full_decoded.bin', 'wb') as f:
        f.write(decoded)
    print(f"Full decoded section saved to: thorne_full_decoded.bin")
    
    # THORNE's known stats
    thorne_stats = {
        'age': 25,
        'rating': 70,
        'position': 3,  # Forward
        'attributes': [66, 63, 74, 64, 73, 84, 28, 69, 65, 73, 69, 80],
        'attr_names': ['SPEED', 'STAMINA', 'AGGRESSION', 'QUALITY', 'FITNESS', 'MORAL',
                       'HANDLING', 'PASSING', 'DRIBBLING', 'HEADING', 'TACKLING', 'SHOOTING'],
        'height_ft': 6,
        'height_in': 0,
        'weight_st': 11,
        'weight_lb': 4,
        'nationality': 'England'
    }
    
    print(f"\n📊 Searching for Known Values in Full Record:")
    
    # Search for age 25
    print(f"\nAge = 25:")
    age_pos = []
    for i, b in enumerate(decoded):
        if b == 25:
            age_pos.append((i, 'raw'))
        if (b ^ 0x61) == 25:
            age_pos.append((i, 'xor'))
    if age_pos:
        print(f"  Found at: {age_pos[:5]}")  # First 5
    else:
        print("  Not found")
    
    # Rating 70
    print(f"\nRating = 70:")
    rating_pos = []
    for i, b in enumerate(decoded):
        if b == 70:
            rating_pos.append((i, 'raw'))
        if (b ^ 0x61) == 70:
            rating_pos.append((i, 'xor'))
    if rating_pos:
        print(f"  Found at: {rating_pos[:5]}")
    else:
        print("  Not found")
    
    # Position 3
    print(f"\nPosition = 3 (Forward):")
    pos_pos = []
    for i, b in enumerate(decoded):
        if (b ^ 0x61) == 3:
            pos_pos.append(i)
    if pos_pos:
        print(f"  Found at: {pos_pos[:5]}")
    else:
        print("  Not found")
    
    # Attributes
    print(f"\n📈 Attributes Search:")
    attr_values = thorne_stats['attributes']
    attr_found = {}
    for idx, attr_val in enumerate(attr_values):
        attr_name = thorne_stats['attr_names'][idx]
        positions = []
        for i, b in enumerate(decoded):
            if b == attr_val:
                positions.append((i, 'raw'))
            if (b ^ 0x61) == attr_val:
                positions.append((i, 'xor'))
        if positions:
            attr_found[attr_name] = positions[:3]  # First 3
            print(f"  {attr_name} ({attr_val}): {positions[:3]}")
        else:
            print(f"  {attr_name} ({attr_val}): Not found")
    
    # Physical stats
    print(f"\n📏 Physical Stats:")
    # Height 6,0
    height_pos = []
    for i in range(len(decoded) - 1):
        pair_raw = (decoded[i], decoded[i+1])
        pair_xor = (decoded[i] ^ 0x61, decoded[i+1] ^ 0x61)
        if pair_raw == (6, 0) or pair_xor == (6, 0):
            enc = 'XOR' if pair_xor == (6, 0) else 'RAW'
            height_pos.append((i, enc))
    if height_pos:
        print(f"  Height 6'0\": {height_pos[:3]}")
    else:
        print("  Height 6'0\": Not found")
    
    # Weight 11,4
    weight_pos = []
    for i in range(len(decoded) - 1):
        pair_raw = (decoded[i], decoded[i+1])
        pair_xor = (decoded[i] ^ 0x61, decoded[i+1] ^ 0x61)
        if pair_raw == (11, 4) or pair_xor == (11, 4):
            enc = 'XOR' if pair_xor == (11, 4) else 'RAW'
            weight_pos.append((i, enc))
    if weight_pos:
        print(f"  Weight 11st 4lb: {weight_pos[:3]}")
    else:
        print("  Weight 11st 4lb: Not found")
    
    # Nationality - look for "England" text
    print(f"\n🏴󠁧󠁢󠁥󠁮󠁧󠁿 Nationality:")
    england_text = b'ENGLAND'
    eng_pos = decoded.find(england_text)
    if eng_pos != -1:
        print(f"  'ENGLAND' found at byte {eng_pos}")
        # Look around for code
        context = decoded[eng_pos-10:eng_pos+20]
        print(f"  Context: {context}")
    else:
        print("  'ENGLAND' text not found")
    
    # Summary
    print(f"\n📋 SUMMARY:")
    print(f"- Age 25: {'✅' if age_pos else '❌'}")
    print(f"- Rating 70: {'✅' if rating_pos else '❌'}")
    print(f"- Position 3: {'✅' if pos_pos else '❌'}")
    print(f"- Attributes found: {len(attr_found)}/12")
    print(f"- Height 6'0\": {'✅' if height_pos else '❌'}")
    print(f"- Weight 11st 4lb: {'✅' if weight_pos else '❌'}")
    print(f"- England text: {'✅' if eng_pos != -1 else '❌'}")
    
    if attr_found:
        print(f"\n🔍 Possible Attribute Locations (first occurrence):")
        for attr, poss in attr_found.items():
            first_xor = next((p for p in poss if p[1] == 'xor'), None)
            if first_xor:
                print(f"  {attr}: byte {first_xor[0]} (XOR)")
    
    print(f"\n💡 Next Steps:")
    print(f"1. The stats are embedded in the biography text")
    print(f"2. Look for patterns around the found positions")
    print(f"3. Age/rating may be in fixed offsets relative to name")
    print(f"4. Attributes likely in a block after biography text")

if __name__ == '__main__':
    main()