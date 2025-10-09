"""
Map Team IDs from Team Records and Link to Players
Extract team IDs and build player-team relationship
"""
import struct
from pathlib import Path
import re
from collections import defaultdict

# Load player file
player_data = Path('DBDAT/JUG98030.FDI').read_bytes()
# Load team file
team_data = Path('DBDAT/EQ98030.FDI').read_bytes()

print("="*80)
print("TEAM ID MAPPING AND PLAYER-TEAM RELATIONSHIP")
print("="*80)

# First, extract player team_ids
print("\n" + "="*80)
print("EXTRACTING PLAYER TEAM IDs")
print("="*80)

# Find player sections and decode them
player_separator = bytes([0xdd, 0x63, 0x60])
player_team_ids = defaultdict(list)
team_id_stats = {}
total_players = 0

# Scan for player data sections
pos = 0x400
while pos < len(player_data) - 1000:
    try:
        length = struct.unpack_from("<H", player_data, pos)[0]
        if 1000 < length < 100000:
            # Decode section
            encoded = player_data[pos+2 : pos+2+length]
            decoded = bytes(b ^ 0x61 for b in encoded)
            
            # Check if it has separator patterns
            if player_separator in decoded:
                # Find all player records in this section
                sep_pos = 0
                while sep_pos < len(decoded):
                    sep_pos = decoded.find(player_separator, sep_pos)
                    if sep_pos == -1:
                        break
                    
                    # Extract team_id (bytes 3-4 after separator)
                    if sep_pos + 5 <= len(decoded):
                        team_id = struct.unpack_from("<H", decoded, sep_pos + 3)[0]
                        
                        # Extract player name
                        name_match = re.search(rb'([A-Z][a-z]{2,15}(?:\s+[A-Z][a-z]{2,15})*)',
                                             decoded[sep_pos+6:sep_pos+50])
                        if name_match:
                            player_name = name_match.group().decode('latin1', errors='replace')
                            player_team_ids[team_id].append((total_players+1, player_name))
                            
                            if team_id not in team_id_stats:
                                team_id_stats[team_id] = 0
                            team_id_stats[team_id] += 1
                            total_players += 1
                    
                    sep_pos += 3
            
            pos += length + 2
        else:
            pos += 1
    except:
        pos += 1

print(f"Found {total_players} player records")

if team_id_stats:
    print(f"\nUnique team IDs found: {len(team_id_stats)}")
    print(f"Team ID range: {min(team_id_stats.keys())} to {max(team_id_stats.keys())}")
    print(f"\nMost common team IDs:")
    for team_id, count in sorted(team_id_stats.items(), key=lambda x: -x[1])[:10]:
        print(f"  Team ID {team_id:4d} (0x{team_id:04x}): {count:2d} players")
else:
    print("No team IDs found - check file format")
    print("\nExiting early - cannot proceed without player data")
    exit(1)

# Now analyze team records to find team ID field
print("\n" + "="*80)
print("ANALYZING TEAM RECORDS FOR TEAM ID FIELD")
print("="*80)

# Scan all XOR sections in team file
xor_sections = []
pos = 0x100
while pos < len(team_data) - 1000:
    try:
        length = struct.unpack_from("<H", team_data, pos)[0]
        if 100 < length < 100000 and pos + 2 + length <= len(team_data):
            encoded = team_data[pos + 2 : pos + 2 + min(100, length)]
            decoded_sample = bytes(b ^ 0x61 for b in encoded)
            printable_count = sum(1 for b in decoded_sample if 32 <= b < 127 or b in [9, 10, 13])
            if printable_count > 40:
                xor_sections.append((pos, length))
                pos += length + 2
                continue
        pos += 1
    except:
        pos += 1

print(f"Found {len(xor_sections)} XOR sections in team file")

# Analyze first few sections for team IDs
separator = bytes([0x61, 0xdd, 0x63])
teams_analyzed = []

for sec_num, (sec_offset, sec_length) in enumerate(xor_sections[:10]):  # First 10 sections
    encoded = team_data[sec_offset + 2 : sec_offset + 2 + sec_length]
    decoded = bytes(b ^ 0x61 for b in encoded)
    
    # Find team records
    positions = []
    pos = 0
    while pos < len(decoded):
        pos = decoded.find(separator, pos)
        if pos == -1:
            break
        positions.append(pos)
        pos += 3
    
    if not positions:
        continue
    
    print(f"\nSection {sec_num+1} @ 0x{sec_offset:08x}: {len(positions)} teams")
    
    # Analyze first 5 teams in this section
    for i in range(min(5, len(positions))):
        sep_pos = positions[i]
        next_sep = positions[i+1] if i+1 < len(positions) else min(sep_pos + 200, len(decoded))
        record = decoded[sep_pos:next_sep]
        
        # Extract team name
        name_match = re.search(rb'[\x20-\x7e]{5,50}', record[3:])
        team_name = "Unknown"
        if name_match:
            text = name_match.group().decode('latin1', errors='replace')
            for j, c in enumerate(text):
                if c.isupper():
                    team_name = text[j:min(j+30, len(text))]
                    break
        
        # Try to find team ID at various positions
        print(f"  Team {i+1}: {team_name[:30]:<30s}", end="")
        
        # Check multiple positions for 16-bit values
        potential_ids = []
        for check_pos in range(0, min(50, len(record)), 2):
            if check_pos + 2 <= len(record):
                val = struct.unpack_from("<H", record, check_pos)[0]
                # Look for values in reasonable range
                if 3000 < val < 5000:
                    potential_ids.append((check_pos, val))
        
        if potential_ids:
            # Show the first few potential IDs
            print(f" -> Potential IDs: {potential_ids[:3]}")
            teams_analyzed.append({
                'name': team_name[:30],
                'section': sec_num + 1,
                'ids': potential_ids
            })
        else:
            print(" -> No IDs in expected range")

# Look for patterns in team ID positions
print("\n" + "="*80)
print("TEAM ID POSITION ANALYSIS")
print("="*80)

if teams_analyzed:
    # Check if team IDs appear at consistent positions
    position_frequency = defaultdict(int)
    for team in teams_analyzed:
        for pos, val in team['ids']:
            position_frequency[pos] += 1
    
    print(f"\nMost common positions for potential team IDs:")
    for pos, count in sorted(position_frequency.items(), key=lambda x: -x[1])[:10]:
        print(f"  Position +{pos:2d}: {count:3d} occurrences")

# Try to correlate player team_ids with actual teams
print("\n" + "="*80)
print("ATTEMPTING PLAYER-TEAM CORRELATION")
print("="*80)

print(f"\nPlayer team_ids found: {sorted(team_id_stats.keys())}")
print(f"\nExample players and their team_ids:")
for team_id in sorted(team_id_stats.keys())[:5]:
    players = player_team_ids[team_id][:3]  # First 3 players
    print(f"\n  Team ID {team_id} (0x{team_id:04x}):")
    for player_num, player_name in players:
        print(f"    Player {player_num}: {player_name}")

print("\n" + "="*80)
print("HYPOTHESIS")
print("="*80)
print("""
Based on analysis:

1. Player team_ids are in range 3712-3807 (~96 unique values)
2. Team records contain potential IDs in similar range
3. Need to:
   a) Identify exact position of team ID in team record
   b) Extract all team IDs from all 543 teams
   c) Map player team_ids to team records

The team ID is likely stored:
- As a 16-bit little-endian value
- Within first 50 bytes of team record
- Possibly at a fixed offset from separator

Next step: Systematically check each team record for values matching
player team_id range and build correlation table.
""")

print("\n" + "="*80)
print("RECOMMENDATION")
print("="*80)
print("""
To complete the mapping:

1. Extract ALL player team_ids (all 8,866 players)
2. Extract ALL team records (all 543 teams)
3. For each team, check positions 0-50 for values in player team_id range
4. Build lookup table: team_id -> team_name
5. Validate by checking if all player team_ids have corresponding teams

This will enable:
- Viewing which team each player belongs to
- Listing all players on a team (roster view)
- Player transfers (changing player.team_id)
""")