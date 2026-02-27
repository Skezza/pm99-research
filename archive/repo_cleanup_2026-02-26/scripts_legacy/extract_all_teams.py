"""
Extract ALL teams from both sections
"""
import struct
from pathlib import Path
import re

# Load team file
data = Path('DBDAT/EQ98030.FDI').read_bytes()

print("="*80)
print("COMPLETE TEAM EXTRACTION - ALL SECTIONS")
print("="*80)

# Section 1: 0x201, 11520 bytes
# Section 2: 0x2f04, 42496 bytes

sections = [
    (0x201, 11520, "Section 1"),
    (0x2f04, 42496, "Section 2"),
]

all_teams = []

for section_offset, section_length, section_name in sections:
    print(f"\n{'='*80}")
    print(f"{section_name} @ 0x{section_offset:08x} ({section_length:,} bytes)")
    print(f"{'='*80}")
    
    # Read length prefix and decode
    length_prefix = struct.unpack_from("<H", data, section_offset)[0]
    encoded = data[section_offset + 2 : section_offset + 2 + length_prefix]
    decoded = bytes(b ^ 0x61 for b in encoded)
    
    print(f"Length prefix: {length_prefix} bytes")
    print(f"Decoded: {len(decoded)} bytes")
    
    # Search for separator pattern
    separator = bytes([0x61, 0xdd, 0x63])
    positions = []
    pos = 0
    while pos < len(decoded):
        pos = decoded.find(separator, pos)
        if pos == -1:
            break
        positions.append(pos)
        pos += 3
    
    print(f"Found {len(positions)} separator patterns")
    
    if not positions:
        print("No separators found in this section")
        continue
    
    # Extract teams
    print(f"\nExtracting teams from {section_name}:\n")
    
    for i in range(len(positions)):
        sep_pos = positions[i]
        next_sep = positions[i+1] if i+1 < len(positions) else len(decoded)
        record_size = next_sep - sep_pos
        
        # Extract record
        record = decoded[sep_pos:next_sep]
        
        # Look for team name (text after separator + prefix bytes)
        # Pattern: 61 dd 63 61 60 XX 61 <TEAM NAME>
        # After separator (3 bytes), there's usually: 61 60 XX 61 prefix
        text_start = 3  # Skip separator
        
        # Find the actual team name - skip prefix bytes
        match = re.search(rb'[\x20-\x7e]{5,100}', record[text_start:])
        if match:
            text = match.group().decode('latin1', errors='replace')
            # Remove prefix like "a`qa" - find first capital letter
            for j, c in enumerate(text):
                if c.isupper():
                    text = text[j:]
                    break
            
            # Clean up - team name usually ends at stadium/description
            # Split on common separators
            if 'a' in text[5:]:  # Skip first few chars
                parts = text.split('a')
                if len(parts) > 0 and len(parts[0]) > 3:
                    text = parts[0]
            
            team_info = {
                'section': section_name,
                'offset': sep_pos,
                'size': record_size,
                'name': text.strip()
            }
            all_teams.append(team_info)
            
            print(f"  {len(all_teams):3d}. {text[:50]:<50s} ({record_size:5d} bytes)")

print("\n" + "="*80)
print("SUMMARY")
print("="*80)
print(f"\nTotal teams extracted: {len(all_teams)}")
print(f"\nTeams by section:")

for section_name in ["Section 1", "Section 2"]:
    section_teams = [t for t in all_teams if t['section'] == section_name]
    print(f"  {section_name}: {len(section_teams)} teams")

print(f"\nFirst 30 team names:")
print("-"*80)
for i, team in enumerate(all_teams[:30]):
    print(f"  {i+1:3d}. {team['name']}")

print(f"\nKnown teams found:")
known_teams = ["Real Madrid", "Barcelona", "Valencia", "Milan", "Juventus", 
               "Arsenal", "Liverpool", "Manchester", "Bayern"]
for known in known_teams:
    matches = [t for t in all_teams if known.lower() in t['name'].lower()]
    if matches:
        for match in matches:
            print(f"  ✓ {known}: '{match['name']}'")

# Save team list
with open('team_names.txt', 'w', encoding='utf-8') as f:
    f.write("="*80 + "\n")
    f.write("EXTRACTED TEAM NAMES\n")
    f.write("="*80 + "\n\n")
    for i, team in enumerate(all_teams):
        f.write(f"{i+1:3d}. {team['name']}\n")

print(f"\n✓ Team names saved to team_names.txt")

print(f"\n" + "="*80)
print("NEXT STEPS")
print("="*80)
print("""
1. We found {0} teams total (not 544 as initially thought)
2. Section 1 has {1} teams
3. Section 2 has {2} teams
4. Each team record is ~2000 bytes (contains full team data)
5. Need to map team ID field to link with players
6. Player team_ids (3712-3807) need to be correlated with these teams
""".format(len(all_teams),
           len([t for t in all_teams if t['section'] == 'Section 1']),
           len([t for t in all_teams if t['section'] == 'Section 2'])))