#!/usr/bin/env python3
"""
Test if the last bytes of clean player records are double-XOR encoded.
The hypothesis: attributes are XOR'd twice, or use a different encoding.
"""

def xor_decode(data, key=0x61):
    return bytes(b ^ key for b in data)

def test_hierro_attributes():
    """
    HIERRO last 12 bytes: 2b 31 35 6b 61 35 5f 58 31 29 44 61
    Decimal: 43 49 53 107 97 53 95 88 49 41 68 97
    
    These are clearly not 0-100 attributes. Let's try different decodings.
    """
    
    last_12_raw = bytes([0x2b, 0x31, 0x35, 0x6b, 0x61, 0x35, 0x5f, 0x58, 0x31, 0x29, 0x44, 0x61])
    
    print("HIERRO Last 12 bytes analysis:")
    print("="*80)
    print(f"Raw (hex):     {' '.join(f'{b:02x}' for b in last_12_raw)}")
    print(f"Raw (decimal): {' '.join(f'{b:3d}' for b in last_12_raw)}")
    
    # Try XOR with 0x61 again (double XOR)
    double_xor = xor_decode(last_12_raw, 0x61)
    print(f"\nDouble XOR 0x61: {' '.join(f'{b:3d}' for b in double_xor)}")
    if all(0 <= b <= 100 for b in double_xor):
        print("  ✓ All in 0-100 range!")
    
    # Try XOR with other keys
    for key in [0x60, 0x62, 0x00, 0xff]:
        result = xor_decode(last_12_raw, key)
        if all(0 <= b <= 100 for b in result):
            print(f"XOR 0x{key:02x}: {' '.join(f'{b:3d}' for b in result)} ✓")
    
    # Try subtracting offset
    for offset in [30, 40, 50, 60, 70]:
        result = bytes(max(0, b - offset) for b in last_12_raw)
        if all(0 <= b <= 100 for b in result):
            print(f"Minus {offset}: {' '.join(f'{b:3d}' for b in result)} ✓")
    
    # Try treating 0x61 ('a') as 0
    # This is common: 0x61='a'=0, 0x62='b'=1, etc.
    char_offset = bytes(b - 0x61 if b >= 0x61 else b for b in last_12_raw)
    print(f"\nTreating 'a'(0x61) as 0: {' '.join(f'{b:3d}' for b in char_offset)}")
    
    # Check if it's ASCII encoding offset
    # 'a' = 0, 'b' = 1, 'c' = 2, etc.
    if all(b >= ord('a') or b < ord('a') for b in last_12_raw):
        ascii_decode = bytes(b - ord('a') if b >= ord('a') else b for b in last_12_raw)
        print(f"ASCII 'a'=0 decode: {' '.join(f'{b:3d}' for b in ascii_decode)}")

def analyze_all_clean_records():
    """Check if the pattern holds for other clean records."""
    
    def xor_decode_file(data):
        return bytes(b ^ 0x61 for b in data)
    
    filepath = 'DBDAT/JUG98030.FDI'
    with open(filepath, 'rb') as f:
        encoded_data = f.read()
    
    decoded_data = xor_decode_file(encoded_data)
    separator = bytes([0xdd, 0x63, 0x60])
    parts = decoded_data.split(separator)
    
    print("\n\n" + "="*80)
    print("Analyzing last 12 bytes of all clean records:")
    print("="*80)
    
    successful_decodes = []
    
    for i, record in enumerate(parts[:100]):  # Check first 100
        if 50 < len(record) < 200:  # Clean records
            last_12 = record[-12:]
            
            # Try different decodings
            methods = {
                'raw': last_12,
                'double_xor': xor_decode(last_12, 0x61),
                'minus_a': bytes(b - 0x61 if b >= 0x61 else b for b in last_12),
            }
            
            for method_name, result in methods.items():
                if all(0 <= b <= 100 for b in result):
                    successful_decodes.append({
                        'record_num': i,
                        'method': method_name,
                        'values': result
                    })
    
    print(f"\nFound {len(successful_decodes)} records with valid attribute ranges:")
    for dec in successful_decodes[:10]:
        print(f"  Record #{dec['record_num']}, method={dec['method']:12s}: {' '.join(f'{b:2d}' for b in dec['values'])}")

if __name__ == '__main__':
    test_hierro_attributes()
    analyze_all_clean_records()