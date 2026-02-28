#!/usr/bin/env python3
"""
Extract complete clean player records (without biographies).
Focus on players with records < 200 bytes.
"""

def xor_decode(data):
    return bytes(b ^ 0x61 for b in data)

def main():
    filepath = 'DBDAT/JUG98030.FDI'
    
    with open(filepath, 'rb') as f:
        encoded_data = f.read()
    
    decoded_data = xor_decode(encoded_data)
    separator = bytes([0xdd, 0x63, 0x60])
    
    # Split into records
    parts = decoded_data.split(separator)
    
    print("Searching for clean player records (< 200 bytes)...")
    print("="*100)
    
    clean_records = []
    
    for i, record in enumerate(parts):
        # Look for small records (clean, no biography)
        if 50 < len(record) < 200:
            # Check if it looks like a player record (has alphabetic text)
            try:
                text = record.decode('latin-1', errors='ignore')
                alpha_count = sum(1 for c in text if c.isalpha())
                
                # Should have reasonable amount of text (name)
                if alpha_count > 10:
                    # Extract basic info
                    team_id = int.from_bytes(record[0:2], 'little') if len(record) >= 2 else 0
                    squad_num = record[2] if len(record) >= 3 else 0
                    
                    # Get the text content
                    text_clean = ''.join(c if c.isprintable() else '.' for c in text[:80])
                    
                    clean_records.append({
                        'index': i,
                        'length': len(record),
                        'team_id': team_id,
                        'squad_num': squad_num,
                        'text': text_clean,
                        'record': record
                    })
            except:
                continue
    
    print(f"Found {len(clean_records)} clean records\n")
    
    # Show first 20 clean records
    for rec in clean_records[:20]:
        print(f"\nRecord #{rec['index']} - {rec['length']} bytes - Team 0x{rec['team_id']:04x} Squad {rec['squad_num']}")
        print(f"Text: {rec['text']}")
        print(f"Full hex dump:")
        
        record = rec['record']
        for j in range(0, len(record), 16):
            hex_part = ' '.join(f'{b:02x}' for b in record[j:j+16])
            dec_part = ' '.join(f'{b:3d}' for b in record[j:j+16])
            ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in record[j:j+16])
            print(f"  {j:04x}: {hex_part:<48} | {ascii_part}")
        
        print("="*100)
    
    # Save clean records to file for analysis
    with open('clean_players.txt', 'w', encoding='utf-8') as f:
        for rec in clean_records:
            f.write(f"Record #{rec['index']} - {rec['length']} bytes\n")
            f.write(f"Team: 0x{rec['team_id']:04x} Squad: {rec['squad_num']}\n")
            f.write(f"Text: {rec['text']}\n")
            f.write(f"Hex: {' '.join(f'{b:02x}' for b in rec['record'])}\n")
            f.write("\n")
    
    print(f"\nSaved {len(clean_records)} clean records to clean_players.txt")

if __name__ == '__main__':
    main()