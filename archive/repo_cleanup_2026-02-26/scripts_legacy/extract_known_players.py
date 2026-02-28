#!/usr/bin/env python3
"""
Extract specific known players from JUG98030.FDI for field mapping.
Searches for players by name and outputs their complete hex records.
"""

# Sample players with known attributes:
KNOWN_PLAYERS = [
    {"name": "HIERRO", "full": "Fernando HIERRO", "pos": "Defender", "nat": "Spain", "age": 30, "team": "Real Madrid"},
    {"name": "ZIDANE", "full": "Zinedine ZIDANE", "pos": "Midfielder", "nat": "France", "age": 26, "team": "Juventus"},
    {"name": "KAHN", "full": "Oliver KAHN", "pos": "Goalkeeper", "nat": "Germany", "age": 29, "team": "Bayern Munich"},
    {"name": "RONALDO", "full": "Ronaldo NAZARIO", "pos": "Forward", "nat": "Brazil", "age": 22, "team": "Inter Milan"},
]

def xor_decode(data):
    """XOR decode with key 0x61."""
    return bytes(b ^ 0x61 for b in data)

def find_player_records(filepath, search_names):
    """Find and extract complete player records by searching for names."""
    with open(filepath, 'rb') as f:
        encoded_data = f.read()
    
    decoded_data = xor_decode(encoded_data)
    
    # Player separator: 0xdd 0x63 0x60
    separator = bytes([0xdd, 0x63, 0x60])
    
    # Split into records
    parts = decoded_data.split(separator)
    
    results = []
    
    for search_name in search_names:
        print(f"\n{'='*80}")
        print(f"Searching for: {search_name['full']}")
        print(f"Position: {search_name['pos']} | Nationality: {search_name['nat']} | Age: {search_name['age']}")
        print(f"{'='*80}")
        
        found = False
        for i, record in enumerate(parts):
            if len(record) < 10:
                continue
            
            # Search for surname in the record (case-insensitive)
            try:
                record_text = record.decode('latin-1', errors='ignore').upper()
                if search_name['name'] in record_text:
                    found = True
                    print(f"\n✓ FOUND in record #{i} (offset ~{decoded_data.find(separator + record)})")
                    
                    # Extract team_id (bytes 0-1 of record after separator)
                    team_id = int.from_bytes(record[0:2], 'little') if len(record) >= 2 else 0
                    
                    # Extract squad number (byte 2)
                    squad_num = record[2] if len(record) >= 3 else 0
                    
                    print(f"Team ID: {team_id} (0x{team_id:04x})")
                    print(f"Squad #: {squad_num}")
                    
                    # Show full record text
                    print(f"\nDecoded text: {record_text[:100]}")
                    
                    # Find where the name actually appears in the record
                    name_start = record_text.find(search_name['name'])
                    if name_start >= 0:
                        print(f"Name starts at byte offset: {name_start}")
                        
                        # Calculate post-name region (critical for field mapping)
                        name_end_estimate = name_start + len(search_name['full']) + 5  # rough estimate
                        
                        if name_end_estimate < len(record):
                            post_name_region = record[name_end_estimate:min(name_end_estimate+30, len(record))]
                            print(f"\nPost-name region (~30 bytes after estimated name end):")
                            print(' '.join(f'{b:02x}' for b in post_name_region))
                            print(' '.join(f'{b:3d}' for b in post_name_region))
                    
                    # Show last 10 bytes (should be attributes)
                    if len(record) >= 10:
                        attrs = record[-10:]
                        print(f"\nLast 10 bytes (attributes):")
                        print(' '.join(f'{b:02x}' for b in attrs))
                        print(' '.join(f'{b:3d}' for b in attrs))
                    
                    # Complete hex dump of entire record
                    print(f"\n--- COMPLETE RECORD HEX DUMP ({len(record)} bytes) ---")
                    for j in range(0, len(record), 16):
                        hex_part = ' '.join(f'{b:02x}' for b in record[j:j+16])
                        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in record[j:j+16])
                        print(f"{j:04x}: {hex_part:<48} | {ascii_part}")
                    
                    results.append({
                        'player': search_name,
                        'record_index': i,
                        'record_bytes': record,
                        'team_id': team_id,
                        'squad_num': squad_num
                    })
                    
                    break  # Found this player, move to next
            except:
                continue
        
        if not found:
            print(f"\n✗ NOT FOUND: {search_name['full']}")
    
    return results

def main():
    filepath = 'DBDAT/JUG98030.FDI'
    
    print("Premier Manager 99 - Known Player Record Extractor")
    print("=" * 80)
    print(f"Searching in: {filepath}")
    print(f"Players to find: {len(KNOWN_PLAYERS)}")
    
    results = find_player_records(filepath, KNOWN_PLAYERS)
    
    print(f"\n\n{'='*80}")
    print(f"SUMMARY: Found {len(results)}/{len(KNOWN_PLAYERS)} players")
    print(f"{'='*80}")
    
    if len(results) >= 2:
        print("\n\nCOMPARATIVE ANALYSIS:")
        print("="*80)
        
        # Compare post-name regions to find patterns
        print("\nSearching for position field patterns...")
        print("Expected: GK=?, DEF=?, MID=?, FWD=?")
        
        for res in results:
            player = res['player']
            record = res['record_bytes']
            print(f"\n{player['full']} ({player['pos']}):")
            
            # Try to find position-related bytes
            # Look for bytes in range 0-10 in post-name region
            if len(record) > 20:
                for offset in range(10, min(40, len(record)-10)):
                    byte_val = record[offset]
                    if 0 <= byte_val <= 10:
                        print(f"  Byte at +{offset}: {byte_val:3d} (0x{byte_val:02x}) <- Possible position field?")

if __name__ == '__main__':
    main()