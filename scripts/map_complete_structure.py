#!/usr/bin/env python3
"""
Now that we know double-XOR is used, map the complete record structure.
Focus on finding the exact position of all fields including the 12 attributes.
"""

def xor_decode(data, key=0x61):
    return bytes(b ^ key for b in data)

def analyze_hierro_complete():
    """Deep dive into HIERRO's complete record structure."""
    
    # HIERRO's complete record (69 bytes)
    hierro_record = bytes([
        0x6b, 0x61, 0x65, 0x67, 0x61, 0x48, 0x69, 0x65, 0x72, 0x72, 0x6f, 0x75, 0x61, 0x46, 0x65, 0x72,
        0x6e, 0x61, 0x6e, 0x64, 0x6f, 0x20, 0x52, 0x75, 0x69, 0x7a, 0x20, 0x48, 0x49, 0x45, 0x52, 0x52,
        0x4f, 0x65, 0x61, 0x67, 0x64, 0x65, 0x6e, 0x61, 0x61, 0x77, 0x60, 0x62, 0x60, 0x76, 0x62, 0xd1,
        0x66, 0xda, 0x35, 0x34, 0x3a, 0x38, 0x36, 0x2e, 0x27, 0x2b, 0x31, 0x35, 0x6b, 0x61, 0x35, 0x5f,
        0x58, 0x31, 0x29, 0x44, 0x61
    ])
    
    print("HIERRO Complete Structure Analysis")
    print("="*100)
    print(f"Total length: {len(hierro_record)} bytes\n")
    
    # Known facts about HIERRO:
    # Position: Defender (1)
    # Age: 30
    # Nationality: Spain (code might be 25)
    # Team: Real Madrid (0x616b)
    
    # Parse structure
    team_id = int.from_bytes(hierro_record[0:2], 'little')
    squad_num = hierro_record[2]
    
    print(f"Bytes 0-1:  Team ID = 0x{team_id:04x} ({team_id})")
    print(f"Byte 2:     Squad = {squad_num}")
    print(f"Bytes 3-4:  Unknown = 0x{hierro_record[3]:02x} 0x{hierro_record[4]:02x} ({hierro_record[3]}, {hierro_record[4]})")
    
    # Name starts at byte 5
    # "Hierro" starts at byte 5
    # Full name "Fernando Ruiz HIERRO" spans bytes 5-33
    
    print(f"\nBytes 5-33: Name region")
    print(f"  Text: {hierro_record[5:34].decode('latin-1', errors='replace')}")
    
    # After name (byte 34 onwards)
    post_name = hierro_record[34:]
    print(f"\nBytes 34-68: Post-name region ({len(post_name)} bytes)")
    
    # Show this region byte by byte
    print("\nByte-by-byte analysis of post-name region:")
    print("Offset | Raw  | Dec | DoubleXOR | Description")
    print("-------+------+-----+-----------+-------------")
    
    for i, b in enumerate(post_name):
        offset = 34 + i
        double_xor = b ^ 0x61
        char = chr(b) if 32 <= b < 127 else '.'
        print(f"  {offset:2d}   | 0x{b:02x} | {b:3d} |   {double_xor:3d}     | {char}")
    
    # Try to identify fields
    print("\n\nField Identification:")
    print("="*100)
    
    # Check for sequence of 12 bytes in 0-100 range using double XOR
    print("\nSearching for 12 consecutive bytes that decode to 0-100 range:")
    for start in range(len(post_name) - 11):
        sequence = post_name[start:start+12]
        decoded = xor_decode(sequence, 0x61)
        if all(0 <= b <= 100 for b in decoded):
            print(f"  Bytes {34+start}-{34+start+11}: {' '.join(f'{b:3d}' for b in decoded)}")
    
    # Look for position (0-3) and age (30)
    print("\nLooking for position (expected: 1) and age (expected: 30):")
    for i, b in enumerate(post_name[:20]):
        if b == 1:
            print(f"  Byte {34+i}: value=1 (possible position)")
        if b == 30:
            print(f"  Byte {34+i}: value=30 (possible age)")
        # Also check XOR decoded values
        decoded_val = b ^ 0x61
        if decoded_val == 1:
            print(f"  Byte {34+i}: XOR decoded=1 (possible position)")
        if decoded_val == 30:
            print(f"  Byte {34+i}: XOR decoded=30 (possible age)")
    
    # The "ea" pattern at bytes 34-35 might be encoding
    # e=0x65, a=0x61 in the data
    print(f"\nBytes 34-42 might be metadata:")
    metadata = post_name[0:9]
    print(f"  Raw: {' '.join(f'0x{b:02x}' for b in metadata)}")
    print(f"  Dec: {' '.join(f'{b:3d}' for b in metadata)}")
    print(f"  XOR: {' '.join(f'{b^0x61:3d}' for b in metadata)}")
    print(f"  Chr: {' '.join(chr(b) if 32 <= b < 127 else '.' for b in metadata)}")

def compare_known_players():
    """Compare multiple known players to find patterns."""
    
    filepath = 'DBDAT/JUG98030.FDI'
    with open(filepath, 'rb') as f:
        encoded_data = f.read()
    
    decoded_data = xor_decode(encoded_data, 0x61)
    separator = bytes([0xdd, 0x63, 0x60])
    parts = decoded_data.split(separator)
    
    players = {
        "HIERRO": {"pos": 1, "age": 30},
        "ZIDANE": {"pos": 2, "age": 26},
        "RAÚL": {"pos": 3, "age": 21},
        "CAÑIZARES": {"pos": 0, "age": 29},
    }
    
    records_found = {}
    
    for name, info in players.items():
        for record in parts:
            if 50 < len(record) < 200:
                try:
                    text = record.decode('latin-1', errors='ignore').upper()
                    if name in text:
                        records_found[name] = {
                            'record': record,
                            'info': info
                        }
                        break
                except:
                    continue
    
    print("\n\n" + "="*100)
    print("Comparing metadata regions across known players:")
    print("="*100)
    
    # Find where names end and compare post-name regions
    for name, data in records_found.items():
        record = data['record']
        info = data['info']
        
        # Estimate name end (look for 'aa' or similar pattern)
        name_end = None
        for i in range(30, min(50, len(record)-20)):
            if record[i:i+2] == bytes([0x61, 0x61]):  # 'aa'
                name_end = i + 2
                break
        
        if name_end:
            post_name = record[name_end:name_end+20]
            print(f"\n{name} (Pos={info['pos']}, Age={info['age']}):")
            print(f"  Name ends at byte {name_end}")
            print(f"  Next 20 bytes: {' '.join(f'{b:02x}' for b in post_name)}")
            print(f"  Decoded:       {' '.join(f'{b^0x61:3d}' for b in post_name)}")

if __name__ == '__main__':
    analyze_hierro_complete()
    compare_known_players()