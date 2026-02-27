#!/usr/bin/env python3
"""
Analyze player names in the database to identify parsing issues
"""

import struct
from pathlib import Path

def xor_decode(data: bytes, key: int = 0x61) -> bytes:
    """XOR decode entire data block"""
    return bytes(b ^ key for b in data)

def extract_name(data: bytes) -> str:
    """Extract player name from bytes 5-40 using NEW improved logic"""
    try:
        # Name region bytes 5-45
        name_region = data[5:45]
        
        import re
        
        # Decode the region - use latin-1 to preserve accented characters
        text = name_region.decode('latin-1', errors='ignore')
        
        # The name format is: [abbreviated]<separator>[FULL NAME]
        # Separators are typically 2 chars like }a, ta, ua, va, etc.
        # Strategy: Find all name candidates and prefer the longest/most complete one
        
        # Split on common separators to find the full name portion
        # Look for patterns like }a, ta, ua, va, wa, xa, ya, za followed by uppercase
        separator_pattern = r'[a-z]{1,2}a(?=[A-Z])'
        parts = re.split(separator_pattern, text)
        
        candidates = []
        
        for part in parts:
            # Pattern: Given name + Surname (various formats)
            # Examples: "José Santiago CAÑIZARES", "David BECKHAM", "Fernando Ruiz HIERRO"
            patterns = [
                # Full format: Given [Middle] SURNAME [More]
                r'([A-ZÀ-ÿ][a-zà-ÿ]{1,15}(?:\s+[A-ZÀ-ÿ][a-zà-ÿ]{1,15})?)\s+([A-ZÀ-ÿ]{2,}(?:[A-ZÀ-ÿ]{2,})?)',
                # Simple format: Given SURNAME
                r'([A-ZÀ-ÿ][a-zà-ÿ]{2,15})\s+([A-ZÀ-ÿ]{3,20})',
                # Mixed case: Given Surname
                r'([A-ZÀ-ÿ][a-zà-ÿ]{2,15})\s+([A-ZÀ-ÿ][a-zà-ÿ]{2,20})'
            ]
            
            for pattern in patterns:
                matches = re.finditer(pattern, part)
                for match in matches:
                    given = match.group(1).strip()
                    surname = match.group(2).strip()
                    
                    # Clean surname: remove trailing lowercase garbage
                    # Keep only: ALL CAPS, or Mixed case up to first garbage sequence
                    clean_surname = ''
                    words = surname.split()
                    
                    for word in words:
                        # Check if word is valid (all caps or proper mixed case)
                        if word.isupper():
                            clean_surname += word + ' '
                        elif word[0].isupper() and len(word) > 1:
                            # Mixed case - check for garbage at end
                            valid_part = word[0]
                            for i in range(1, len(word)):
                                # Stop at sequences of 2+ lowercase that look like garbage
                                if i < len(word) - 1 and word[i].islower() and word[i+1].islower():
                                    # Check if rest is all lowercase (garbage)
                                    if all(c.islower() or not c.isalpha() for c in word[i:]):
                                        break
                                valid_part += word[i]
                            clean_surname += valid_part + ' '
                    
                    clean_surname = clean_surname.strip()
                    
                    if clean_surname:
                        full_name = f"{given} {clean_surname}".strip()
                        
                        # Validate: reasonable length, contains space
                        if 5 <= len(full_name) <= 40 and ' ' in full_name:
                            # Score candidates: prefer longer, more uppercase
                            score = len(full_name) + (sum(1 for c in clean_surname if c.isupper()) * 2)
                            candidates.append((score, full_name))
        
        # Return best candidate
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1], text, name_region.hex()
        
        return None, text, name_region.hex()
        
    except Exception as e:
        return None, str(e), ""

# Load database
file_path = 'DBDAT/JUG98030.FDI'
file_data = Path(file_path).read_bytes()

separator = bytes([0xdd, 0x63, 0x60])
pos = 0x400
found_players = []

print("Analyzing player names in database...\n")
print("=" * 100)

while pos < len(file_data) - 1000 and len(found_players) < 50:
    try:
        length = struct.unpack_from("<H", file_data, pos)[0]
        
        if 1000 < length < 100000:
            encoded = file_data[pos+2 : pos+2+length]
            decoded = xor_decode(encoded, 0x61)
            
            if separator in decoded:
                parts = decoded.split(separator)
                
                for part in parts:
                    if 50 <= len(part) <= 200:
                        team_id = struct.unpack_from("<H", part, 0)[0]
                        squad_num = part[2]
                        
                        name, raw_text, hex_bytes = extract_name(part)
                        
                        if name:
                            found_players.append({
                                'name': name,
                                'team_id': team_id,
                                'squad': squad_num,
                                'raw_text': raw_text,
                                'hex': hex_bytes
                            })
            
            pos += length + 2
        else:
            pos += 1
    except:
        pos += 1

# Display results
for i, player in enumerate(found_players[:30], 1):
    print(f"\n{i}. {player['name']}")
    print(f"   Team ID: {player['team_id']}, Squad: {player['squad']}")
    print(f"   Raw text in name region: {repr(player['raw_text'][:60])}")
    
    # Show hex if there are special characters
    if any(ord(c) > 127 or c == '' for c in player['raw_text']):
        print(f"   Hex (first 20 bytes): {player['hex'][:40]}")
    
    # Check for common issues
    issues = []
    if '' in player['name']:
        issues.append("Contains replacement character ()")
    if len(player['name'].split()) > 3:
        issues.append("Too many name parts")
    if any(c.islower() and i > 0 for i, c in enumerate(player['name'].split()[-1])):
        issues.append("Surname has lowercase letters (possible garbage)")
    
    if issues:
        print(f"   ⚠️  Issues: {', '.join(issues)}")

print("\n" + "=" * 100)
print(f"\nTotal players found: {len(found_players)}")

# Look for specific problem patterns
print("\n\nLooking for specific issues:")
print("-" * 100)

garbled = [p for p in found_players if '' in p['name'] or '' in p['raw_text']]
if garbled:
    print(f"\n{len(garbled)} players with garbled/replacement characters:")
    for p in garbled[:10]:
        print(f"  - {p['name']}: {repr(p['raw_text'][:40])}")

multi_part = [p for p in found_players if len(p['name'].split()) > 2]
if multi_part:
    print(f"\n{len(multi_part)} players with 3+ name parts:")
    for p in multi_part[:10]:
        print(f"  - {p['name']}")