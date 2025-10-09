#!/usr/bin/env python3
"""
Comprehensive Position Field Validation
Tests byte 42 hypothesis across all 9,106 clean player records
"""

def xor_byte(b):
    """Apply XOR 0x61 to a single byte"""
    return b ^ 0x61

def double_xor(b):
    """Apply double XOR (file-level + field-level)"""
    return xor_byte(xor_byte(b))

def analyze_position_field():
    """Analyze byte 42 across all clean records"""
    
    # Read the player database
    with open('DBDAT/JUG98030.FDI', 'rb') as f:
        data = f.read()
    
    # XOR decode entire file
    decoded = bytes([xor_byte(b) for b in data])
    
    # Read clean players list
    with open('clean_players.txt', 'r', encoding='latin-1') as f:
        lines = f.readlines()
    
    position_stats = {0: [], 1: [], 2: [], 3: []}
    other_values = {}
    
    print("=" * 80)
    print("POSITION FIELD VALIDATION - Byte 42 Analysis")
    print("=" * 80)
    
    total_analyzed = 0
    
    for line in lines:
        if not line.strip() or line.startswith('---'):
            continue
            
        # Parse the line format: "Offset XXXXX (XXX bytes): NAME"
        if 'Offset' in line and 'bytes):' in line:
            try:
                offset_str = line.split('Offset ')[1].split(' ')[0]
                offset = int(offset_str)
                size_str = line.split('(')[1].split(' bytes')[0]
                size = int(size_str)
                
                # Extract player name
                name_part = line.split('): ')[1].strip()
                
                # Get the record
                record = decoded[offset:offset + size]
                
                if len(record) < 43:
                    continue
                
                # Get byte 42 (0-indexed, so position 42)
                byte_42_raw = record[42]
                
                # Apply double XOR
                byte_42_decoded = double_xor(byte_42_raw)
                
                # Categorize
                if byte_42_decoded in [0, 1, 2, 3]:
                    position_stats[byte_42_decoded].append((name_part, offset, byte_42_raw))
                else:
                    if byte_42_decoded not in other_values:
                        other_values[byte_42_decoded] = []
                    other_values[byte_42_decoded].append((name_part, offset, byte_42_raw))
                
                total_analyzed += 1
                
            except (ValueError, IndexError) as e:
                continue
    
    print(f"\nTotal records analyzed: {total_analyzed}")
    print("\n" + "=" * 80)
    print("POSITION DISTRIBUTION (Double-XOR decoded)")
    print("=" * 80)
    
    position_names = {0: "GK (Goalkeeper)", 1: "D (Defender)", 2: "M (Midfielder)", 3: "F (Forward)"}
    
    for pos in [0, 1, 2, 3]:
        count = len(position_stats[pos])
        percentage = (count / total_analyzed * 100) if total_analyzed > 0 else 0
        print(f"\nPosition {pos} - {position_names[pos]}: {count} players ({percentage:.1f}%)")
        
        # Show first 10 examples
        if count > 0:
            print("  Examples:")
            for name, offset, raw in position_stats[pos][:10]:
                print(f"    {name} (offset {offset}, raw byte: 0x{raw:02x})")
    
    print("\n" + "=" * 80)
    print("OTHER VALUES FOUND")
    print("=" * 80)
    
    if other_values:
        for value in sorted(other_values.keys()):
            count = len(other_values[value])
            print(f"\nValue {value} (0x{value:02x}): {count} occurrences")
            # Show first 5 examples
            for name, offset, raw in other_values[value][:5]:
                print(f"  {name} (offset {offset}, raw byte: 0x{raw:02x})")
    else:
        print("\nNo unexpected values found - ALL records fall into 0-3 range!")
        print("✅ This strongly validates the position field hypothesis!")
    
    # Calculate validation score
    valid_positions = sum(len(position_stats[i]) for i in [0, 1, 2, 3])
    validation_percentage = (valid_positions / total_analyzed * 100) if total_analyzed > 0 else 0
    
    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)
    print(f"Records with valid position (0-3): {valid_positions}/{total_analyzed} ({validation_percentage:.1f}%)")
    
    if validation_percentage > 95:
        print("✅ HYPOTHESIS CONFIRMED: Byte 42 is the position field!")
    elif validation_percentage > 80:
        print("⚠️  HYPOTHESIS LIKELY: Byte 42 is probably the position field")
    else:
        print("❌ HYPOTHESIS QUESTIONABLE: Byte 42 may not be the position field")
    
    # Expected squad distribution (rough estimate)
    print("\n" + "=" * 80)
    print("EXPECTED SQUAD COMPOSITION")
    print("=" * 80)
    print("Typical squad: ~2-3 GK, ~8-10 D, ~8-10 M, ~4-6 F per team")
    print("\nActual distribution:")
    for pos in [0, 1, 2, 3]:
        count = len(position_stats[pos])
        avg_per_team = count / 180  # Assuming ~180 teams
        print(f"  {position_names[pos]}: {avg_per_team:.1f} per team average")

if __name__ == '__main__':
    analyze_position_field()