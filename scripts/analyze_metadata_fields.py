#!/usr/bin/env python3
"""
Analyze metadata fields in the gap between position and attributes.
Based on handover: metadata (DOB, height, weight, nationality) are between position (+7) and attributes (-19)
"""

import struct
from pathlib import Path

# Known players with their real-world data for validation
KNOWN_PLAYERS = {
    "BECKHAM": {
        "dob": "02/05/1975",  # May 2, 1975
        "height": 183,  # cm
        "weight": 75,   # kg
        "nationality": "England"
    },
    "CAÑIZARES": {
        "dob": "18/12/1969",  # Dec 18, 1969
        "height": 182,
        "weight": 80,
        "nationality": "Spain"
    },
    "HIERRO": {
        "dob": "28/03/1968",  # Mar 28, 1968
        "height": 189,
        "weight": 85,
        "nationality": "Spain"
    },
    "MALDINI": {
        "dob": "26/06/1968",  # Jun 26, 1968
        "height": 186,
        "weight": 85,
        "nationality": "Italy"
    },
    "ZAMORANO": {
        "dob": "18/01/1967",  # Jan 18, 1967
        "height": 178,
        "weight": 78,
        "nationality": "Chile"
    }
}

def xor_decode(data: bytes, key: int = 0x61) -> bytes:
    """XOR decode data"""
    return bytes(b ^ key for b in data)

def find_player_record(file_data: bytes, surname: str) -> tuple:
    """Find a player record by surname"""
    separator = bytes([0xdd, 0x63, 0x60])
    pos = 0x400
    
    while pos < len(file_data) - 1000:
        try:
            length = struct.unpack_from("<H", file_data, pos)[0]
            
            if 50 < length < 100000:
                encoded = file_data[pos+2 : pos+2+length]
                decoded = xor_decode(encoded, 0x61)
                
                # Check if surname appears in this section
                if surname.encode('latin-1') in decoded or surname.upper().encode('latin-1') in decoded:
                    # Split by separator
                    if separator in decoded:
                        parts = decoded.split(separator)
                        for part in parts:
                            if 50 <= len(part) <= 200:
                                try:
                                    text = part.decode('latin-1', errors='ignore')
                                    if surname.upper() in text.upper():
                                        return (pos, part)
                                except:
                                    pass
                
                pos += length + 2
            else:
                pos += 1
        except:
            pos += 1
    
    return None

def analyze_metadata_region(record: bytes, player_name: str):
    """Analyze the metadata region between position and attributes"""
    print(f"\n{'='*80}")
    print(f"Analyzing: {player_name}")
    print(f"{'='*80}")
    print(f"Record length: {len(record)} bytes")
    
    # Find name-end marker (aaaa)
    name_end = None
    for i in range(20, min(60, len(record)-20)):
        if i+3 < len(record) and record[i:i+4] == bytes([0x61, 0x61, 0x61, 0x61]):
            name_end = i
            break
    
    if not name_end:
        print("ERROR: Could not find name-end marker!")
        return
    
    print(f"Name-end marker at: {name_end}")
    
    # Position is at name_end + 7
    pos_offset = name_end + 7
    if pos_offset < len(record):
        pos_byte = record[pos_offset]
        pos_value = pos_byte ^ 0x61
        positions = {0: "GK", 1: "DEF", 2: "MID", 3: "FWD"}
        print(f"Position offset: {pos_offset}, value: {pos_value} ({positions.get(pos_value, 'Unknown')})")
    
    # Attributes start at len(record) - 19
    attr_start = len(record) - 19
    print(f"Attributes start at: {attr_start}")
    
    # Metadata region
    metadata_start = pos_offset + 1
    metadata_end = attr_start
    metadata_size = metadata_end - metadata_start
    
    print(f"\nMetadata region: offset {metadata_start} to {metadata_end} ({metadata_size} bytes)")
    print(f"\nHex dump of metadata region:")
    
    metadata = record[metadata_start:metadata_end]
    
    # Print hex dump
    for i in range(0, len(metadata), 16):
        hex_part = ' '.join(f'{b:02x}' for b in metadata[i:i+16])
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in metadata[i:i+16])
        print(f"  {metadata_start+i:04x}: {hex_part:<48} {ascii_part}")
    
    print(f"\nDecoded (XOR 0x61) metadata region:")
    decoded_metadata = bytes(b ^ 0x61 for b in metadata)
    
    for i in range(0, len(decoded_metadata), 16):
        hex_part = ' '.join(f'{b:02x}' for b in decoded_metadata[i:i+16])
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in decoded_metadata[i:i+16])
        print(f"  {metadata_start+i:04x}: {hex_part:<48} {ascii_part}")
    
    # Look for patterns
    print(f"\nPattern analysis:")
    
    # Check for date-like patterns (could be packed BCD or binary)
    print(f"\nPossible date fields (various encodings):")
    for i in range(0, len(decoded_metadata) - 2):
        # Check for plausible day/month/year values
        b1, b2, b3 = decoded_metadata[i], decoded_metadata[i+1], decoded_metadata[i+2] if i+2 < len(decoded_metadata) else 0
        
        # Check if could be DD/MM/YY in BCD
        if 1 <= b1 <= 31 and 1 <= b2 <= 12:
            print(f"  Offset +{i}: {b1:02d}/{b2:02d}/{b3:02d} (might be day/month/year)")
        
        # Check if could be year in uint16
        if i+1 < len(decoded_metadata):
            year = struct.unpack_from("<H", decoded_metadata, i)[0] if i+1 < len(decoded_metadata) else 0
            if 1950 <= year <= 2000:
                print(f"  Offset +{i}: Year {year} (uint16 LE)")
    
    print(f"\nPossible height/weight fields (plausible ranges):")
    for i in range(0, len(decoded_metadata)):
        val = decoded_metadata[i]
        # Height typically 160-210 cm
        if 160 <= val <= 210:
            print(f"  Offset +{i}: {val} (could be height in cm)")
        # Weight typically 60-100 kg
        if 60 <= val <= 100:
            print(f"  Offset +{i}: {val} (could be weight in kg)")
    
    # Check for country codes or nationality IDs
    print(f"\nPossible nationality/country fields:")
    for i in range(0, len(decoded_metadata)):
        val = decoded_metadata[i]
        # Country IDs might be 1-255
        if 1 <= val <= 100:
            print(f"  Offset +{i}: {val} (could be country/nationality ID)")

def main():
    file_path = Path('DBDAT/JUG98030.FDI')
    
    if not file_path.exists():
        print(f"ERROR: {file_path} not found!")
        return
    
    file_data = file_path.read_bytes()
    print(f"Loaded {len(file_data)} bytes from {file_path}")
    
    # Analyze known players
    for surname, real_data in KNOWN_PLAYERS.items():
        result = find_player_record(file_data, surname)
        if result:
            offset, record = result
            analyze_metadata_region(record, surname)
            
            print(f"\nExpected values for {surname}:")
            print(f"  DOB: {real_data['dob']}")
            print(f"  Height: {real_data['height']} cm")
            print(f"  Weight: {real_data['weight']} kg")
            print(f"  Nationality: {real_data['nationality']}")
        else:
            print(f"\nWARNING: Could not find record for {surname}")
    
    print(f"\n{'='*80}")
    print("Analysis complete!")
    print(f"{'='*80}")

if __name__ == '__main__':
    main()