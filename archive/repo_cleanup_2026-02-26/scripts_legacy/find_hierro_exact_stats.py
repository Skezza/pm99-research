#!/usr/bin/env python3
"""
Search for HIERRO's exact attribute values from the game.
User provided complete stats - this should definitively locate all fields.
"""

def xor_decode(data, key=0x61):
    return bytes(b ^ key for b in data)

def main():
    # HIERRO's exact stats from game
    hierro_stats = {
        'age': 30,
        'weight_stone': 13,
        'weight_pounds': 3,
        'height_feet': 6,
        'height_inches': 1,
        'rating': 85,
        'attributes': [85, 91, 89, 87, 76, 82, 10, 74, 70, 84, 94, 80]  # All 12 attributes
    }
    
    attr_names = ['SPEED', 'STAMINA', 'AGGRESSION', 'QUALITY', 'FITNESS', 'MORAL',
                  'HANDLING', 'PASSING', 'DRIBBLING', 'HEADING', 'TACKLING', 'SHOOTING']
    
    # HIERRO's complete record (69 bytes)
    hierro_record = bytes([
        0x6b, 0x61, 0x65, 0x67, 0x61, 0x48, 0x69, 0x65, 0x72, 0x72, 0x6f, 0x75, 0x61, 0x46, 0x65, 0x72,
        0x6e, 0x61, 0x6e, 0x64, 0x6f, 0x20, 0x52, 0x75, 0x69, 0x7a, 0x20, 0x48, 0x49, 0x45, 0x52, 0x52,
        0x4f, 0x65, 0x61, 0x67, 0x64, 0x65, 0x6e, 0x61, 0x61, 0x77, 0x60, 0x62, 0x60, 0x76, 0x62, 0xd1,
        0x66, 0xda, 0x35, 0x34, 0x3a, 0x38, 0x36, 0x2e, 0x27, 0x2b, 0x31, 0x35, 0x6b, 0x61, 0x35, 0x5f,
        0x58, 0x31, 0x29, 0x44, 0x61
    ])
    
    print("="*100)
    print("HIERRO EXACT STATS LOCATION FINDER")
    print("="*100)
    print(f"\nSearching for HIERRO's exact values from game:\n")
    
    # Search for exact 12-attribute sequence
    attrs_bytes = bytes(hierro_stats['attributes'])
    print(f"12 Attributes: {' '.join(str(a) for a in hierro_stats['attributes'])}")
    print(f"Expected order: {', '.join(attr_names)}\n")
    
    pos = hierro_record.find(attrs_bytes)
    if pos != -1:
        print(f"✓✓✓ FOUND EXACT SEQUENCE at byte {pos}!")
    else:
        print(f"✗ Exact sequence NOT found as raw bytes")
        print(f"\nSearching with double-XOR encoding...")
        
        # Try double-XOR encoded
        encoded_attrs = bytes(a ^ 0x61 for a in attrs_bytes)
        pos = hierro_record.find(encoded_attrs)
        if pos != -1:
            print(f"✓✓✓ FOUND as DOUBLE-XOR at byte {pos}!")
        else:
            print(f"✗ Not found as double-XOR either")
            
            # Try searching for subsequences
            print(f"\nSearching for partial matches (6+ consecutive attributes)...")
            for start_idx in range(len(attrs_bytes) - 5):
                for length in range(12, 5, -1):
                    if start_idx + length > len(attrs_bytes):
                        continue
                    
                    partial = attrs_bytes[start_idx:start_idx + length]
                    partial_encoded = bytes(a ^ 0x61 for a in partial)
                    
                    pos_raw = hierro_record.find(partial)
                    pos_enc = hierro_record.find(partial_encoded)
                    
                    if pos_raw != -1:
                        attr_list = [attr_names[start_idx + i] for i in range(length)]
                        print(f"  Found {length} attrs (raw) at byte {pos_raw}: {', '.join(attr_list)}")
                        break
                    elif pos_enc != -1:
                        attr_list = [attr_names[start_idx + i] for i in range(length)]
                        print(f"  Found {length} attrs (XOR) at byte {pos_enc}: {', '.join(attr_list)}")
                        break
    
    # Search for individual values
    print(f"\n\nSearching for individual key values:")
    print("="*100)
    
    # Age
    print(f"\nAge = {hierro_stats['age']}:")
    for i, b in enumerate(hierro_record):
        if b == hierro_stats['age']:
            print(f"  Byte {i}: raw value = {b}")
        if (b ^ 0x61) == hierro_stats['age']:
            print(f"  Byte {i}: double-XOR value = {b ^ 0x61} (raw byte = 0x{b:02x})")
    
    # Height
    print(f"\nHeight (6 feet 1 inch = possibly 6, 1 or 185cm):")
    height_cm = 185  # 6'1" in cm
    for i in range(len(hierro_record) - 1):
        if hierro_record[i] == 6 and hierro_record[i+1] == 1:
            print(f"  Bytes {i}-{i+1}: (6, 1) raw")
        if (hierro_record[i] ^ 0x61) == 6 and (hierro_record[i+1] ^ 0x61) == 1:
            print(f"  Bytes {i}-{i+1}: (6, 1) double-XOR")
        if hierro_record[i] == height_cm:
            print(f"  Byte {i}: {height_cm}cm raw")
        if (hierro_record[i] ^ 0x61) == height_cm:
            print(f"  Byte {i}: {height_cm}cm double-XOR")
    
    # Weight  
    print(f"\nWeight (13 stone 3 pounds = possibly 13, 3 or 83kg):")
    weight_kg = 83  # 13st 3lb in kg
    for i in range(len(hierro_record) - 1):
        if hierro_record[i] == 13 and hierro_record[i+1] == 3:
            print(f"  Bytes {i}-{i+1}: (13, 3) raw")
        if (hierro_record[i] ^ 0x61) == 13 and (hierro_record[i+1] ^ 0x61) == 3:
            print(f"  Bytes {i}-{i+1}: (13, 3) double-XOR")
    
    # Show all bytes that match ANY attribute value
    print(f"\n\nBytes matching any attribute value (0-100 range):")
    print("="*100)
    attr_set = set(hierro_stats['attributes'])
    print(f"Attribute values: {sorted(attr_set)}\n")
    
    for i, b in enumerate(hierro_record):
        raw_val = b
        xor_val = b ^ 0x61
        
        if raw_val in attr_set or xor_val in attr_set:
            matches = []
            if raw_val in attr_set:
                matching_attrs = [attr_names[j] for j, a in enumerate(hierro_stats['attributes']) if a == raw_val]
                matches.append(f"raw={raw_val} ({', '.join(matching_attrs)})")
            if xor_val in attr_set:
                matching_attrs = [attr_names[j] for j, a in enumerate(hierro_stats['attributes']) if a == xor_val]
                matches.append(f"XOR={xor_val} ({', '.join(matching_attrs)})")
            
            print(f"  Byte {i:2d} (0x{b:02x}): {' | '.join(matches)}")

if __name__ == '__main__':
    main()