"""
Complete Team-Player Correlation Script
========================================

Goal: Link all 8,866 players to their teams by finding the team ID field
in team records that matches player.team_id values.

Method:
1. Extract ALL player team_ids from JUG98030.FDI
2. Extract ALL team records from EQ98030.FDI  
3. Search each team record for 16-bit values matching player team_ids
4. Build correlation table: team_id -> team_name
5. Generate roster reports

Expected outcome: Confirm team ID field position in team records
"""

import struct
from pathlib import Path
import re
from collections import defaultdict, Counter

# File paths
PLAYER_FILE = Path('DBDAT/JUG98030.FDI')
TEAM_FILE = Path('DBDAT/EQ98030.FDI')

# Separators (after XOR decode)
PLAYER_SEPARATOR = bytes([0xdd, 0x63, 0x60])
TEAM_SEPARATOR = bytes([0x61, 0xdd, 0x63])


def extract_all_player_team_ids():
    """Extract team_id from all player records."""
    print("="*80)
    print("PHASE 1: EXTRACTING PLAYER TEAM IDs")
    print("="*80)
    
    data = PLAYER_FILE.read_bytes()
    player_team_ids = defaultdict(list)
    total_players = 0
    
    # Scan for XOR sections
    pos = 0x400
    while pos < len(data) - 1000:
        try:
            length = struct.unpack_from("<H", data, pos)[0]
            if 1000 < length < 100000:
                # Decode section
                encoded = data[pos+2 : pos+2+length]
                decoded = bytes(b ^ 0x61 for b in encoded)
                
                # Find all player records
                if PLAYER_SEPARATOR in decoded:
                    sep_pos = 0
                    while True:
                        sep_pos = decoded.find(PLAYER_SEPARATOR, sep_pos)
                        if sep_pos == -1:
                            break
                        
                        # Extract team_id (bytes 3-4 after separator)
                        if sep_pos + 5 <= len(decoded):
                            team_id = struct.unpack_from("<H", decoded, sep_pos + 3)[0]
                            
                            # Extract player name for validation
                            name_match = re.search(
                                rb'([A-Z][a-z]{2,15}(?:\s+[A-Z][a-z]{2,15})*)',
                                decoded[sep_pos+6:sep_pos+60]
                            )
                            player_name = "Unknown"
                            if name_match:
                                player_name = name_match.group().decode('latin1', errors='replace')
                            
                            player_team_ids[team_id].append({
                                'number': total_players + 1,
                                'name': player_name,
                                'offset': pos + 2 + sep_pos
                            })
                            total_players += 1
                        
                        sep_pos += 3
                
                pos += length + 2
            else:
                pos += 1
        except:
            pos += 1
    
    print(f"\n✅ Extracted {total_players} player records")
    print(f"✅ Found {len(player_team_ids)} unique team IDs")
    
    team_id_list = sorted(player_team_ids.keys())
    print(f"\n📊 Team ID Statistics:")
    print(f"   Range: {min(team_id_list)} (0x{min(team_id_list):04x}) to {max(team_id_list)} (0x{max(team_id_list):04x})")
    print(f"   High byte: 0x{min(team_id_list) >> 8:02x} (constant: {len(set(tid >> 8 for tid in team_id_list)) == 1})")
    print(f"   Low byte range: 0x{min(team_id_list) & 0xff:02x} to 0x{max(team_id_list) & 0xff:02x}")
    
    # Show top 10 teams by player count
    print(f"\n📋 Top 10 Teams by Player Count:")
    sorted_teams = sorted(player_team_ids.items(), key=lambda x: -len(x[1]))[:10]
    for team_id, players in sorted_teams:
        print(f"   Team ID {team_id:4d} (0x{team_id:04x}): {len(players):2d} players - e.g. {players[0]['name']}")
    
    return player_team_ids, total_players


def extract_all_team_records():
    """Extract all team records with metadata."""
    print("\n" + "="*80)
    print("PHASE 2: EXTRACTING TEAM RECORDS")
    print("="*80)
    
    data = TEAM_FILE.read_bytes()
    teams = []
    
    # Scan for XOR sections
    pos = 0x100
    section_num = 0
    while pos < len(data) - 1000:
        try:
            length = struct.unpack_from("<H", data, pos)[0]
            if 100 < length < 100000 and pos + 2 + length <= len(data):
                # Check if XOR section
                encoded = data[pos + 2 : pos + 2 + min(100, length)]
                decoded_sample = bytes(b ^ 0x61 for b in encoded)
                printable_count = sum(1 for b in decoded_sample if 32 <= b < 127 or b in [9, 10, 13])
                
                if printable_count > 40:
                    # Decode full section
                    encoded = data[pos + 2 : pos + 2 + length]
                    decoded = bytes(b ^ 0x61 for b in encoded)
                    
                    # Find team records
                    sep_pos = 0
                    while True:
                        sep_pos = decoded.find(TEAM_SEPARATOR, sep_pos)
                        if sep_pos == -1:
                            break
                        
                        # Extract team data
                        next_sep = decoded.find(TEAM_SEPARATOR, sep_pos + 3)
                        if next_sep == -1:
                            next_sep = min(sep_pos + 3000, len(decoded))
                        
                        record = decoded[sep_pos:next_sep]
                        
                        # Extract team name
                        name_match = re.search(rb'[\x20-\x7e]{5,50}', record[3:])
                        team_name = "Unknown Team"
                        if name_match:
                            text = name_match.group().decode('latin1', errors='replace')
                            # Find first capital letter
                            for j, c in enumerate(text):
                                if c.isupper():
                                    team_name = text[j:min(j+40, len(text))].strip()
                                    break
                        
                        teams.append({
                            'section': section_num,
                            'offset': pos + 2 + sep_pos,
                            'name': team_name,
                            'record': record,
                            'size': len(record)
                        })
                        
                        sep_pos = next_sep
                    
                    section_num += 1
                    pos += length + 2
                    continue
            pos += 1
        except:
            pos += 1
    
    print(f"\n✅ Extracted {len(teams)} team records")
    print(f"✅ From {section_num} XOR sections")
    print(f"\n📋 Sample Teams:")
    for i, team in enumerate(teams[:10]):
        print(f"   {i+1:3d}. {team['name'][:40]:<40s} ({team['size']:4d} bytes)")
    
    return teams


def search_team_ids_in_records(teams, player_team_ids):
    """Search each team record for player team_id values."""
    print("\n" + "="*80)
    print("PHASE 3: CORRELATING TEAM IDs")
    print("="*80)
    
    valid_team_ids = set(player_team_ids.keys())
    correlations = {}
    position_histogram = Counter()
    
    print(f"\nSearching for team IDs in range: {min(valid_team_ids)} to {max(valid_team_ids)}")
    print(f"Total valid team IDs to find: {len(valid_team_ids)}\n")
    
    for team_idx, team in enumerate(teams):
        record = team['record']
        found_ids = []
        
        # Search first 100 bytes for 16-bit values in player team_id range
        search_limit = min(100, len(record) - 1)
        for pos in range(0, search_limit, 2):
            if pos + 2 <= len(record):
                value = struct.unpack_from("<H", record, pos)[0]
                if value in valid_team_ids:
                    found_ids.append((pos, value))
                    position_histogram[pos] += 1
        
        if found_ids:
            # Most likely: the first occurrence or most common position
            team_id = found_ids[0][1]  # Take first match
            position = found_ids[0][0]
            
            correlations[team_id] = {
                'name': team['name'],
                'position': position,
                'all_matches': found_ids,
                'team_idx': team_idx,
                'players': player_team_ids[team_id]
            }
            
            status = "✓" if len(found_ids) == 1 else f"⚠({len(found_ids)} matches)"
            print(f"{status} Team {team_idx+1:3d}: ID {team_id:4d} @ pos +{position:2d} | {team['name'][:45]:<45s} | {len(player_team_ids[team_id])} players")
    
    print(f"\n✅ Correlated {len(correlations)} teams with player data")
    print(f"❌ Uncorrelated teams: {len(teams) - len(correlations)}")
    print(f"❌ Orphaned player team_ids: {len(valid_team_ids) - len(correlations)}")
    
    return correlations, position_histogram


def analyze_team_id_position(position_histogram, correlations):
    """Determine the most likely team ID field position."""
    print("\n" + "="*80)
    print("PHASE 4: TEAM ID FIELD POSITION ANALYSIS")
    print("="*80)
    
    if not position_histogram:
        print("❌ No correlations found - cannot determine field position")
        return None
    
    print(f"\n📊 Team ID Position Frequency:")
    sorted_positions = sorted(position_histogram.items(), key=lambda x: -x[1])
    for pos, count in sorted_positions[:15]:
        percentage = (count / len(correlations)) * 100
        bar = "█" * int(percentage / 2)
        print(f"   Position +{pos:2d}: {count:3d} occurrences ({percentage:5.1f}%) {bar}")
    
    # Determine most likely position
    most_common_pos, occurrences = sorted_positions[0]
    confidence = (occurrences / len(correlations)) * 100
    
    print(f"\n🎯 CONCLUSION:")
    print(f"   Team ID field is most likely at position +{most_common_pos}")
    print(f"   Confidence: {confidence:.1f}% ({occurrences}/{len(correlations)} teams)")
    
    if confidence < 50:
        print(f"   ⚠️  WARNING: Low confidence - team ID position may vary")
    elif confidence > 90:
        print(f"   ✅ HIGH CONFIDENCE - position is consistent")
    
    return most_common_pos


def generate_roster_report(correlations, output_file='team_rosters.txt'):
    """Generate detailed roster report."""
    print("\n" + "="*80)
    print("PHASE 5: GENERATING ROSTER REPORT")
    print("="*80)
    
    lines = []
    lines.append("="*80)
    lines.append("PREMIER MANAGER 99 - TEAM ROSTERS")
    lines.append("="*80)
    lines.append(f"\nTotal Teams: {len(correlations)}")
    lines.append(f"Total Players: {sum(len(c['players']) for c in correlations.values())}")
    lines.append("\n" + "="*80 + "\n")
    
    # Sort teams by name
    sorted_teams = sorted(correlations.items(), key=lambda x: x[1]['name'])
    
    for team_id, data in sorted_teams:
        lines.append(f"\n{'='*80}")
        lines.append(f"TEAM: {data['name']}")
        lines.append(f"Team ID: {team_id} (0x{team_id:04x})")
        lines.append(f"Squad Size: {len(data['players'])} players")
        lines.append(f"Team ID Position in Record: +{data['position']} bytes")
        lines.append(f"{'='*80}\n")
        
        # List all players
        for i, player in enumerate(data['players'], 1):
            lines.append(f"  {i:2d}. {player['name']}")
        
        lines.append("")  # Blank line between teams
    
    # Write to file
    report = '\n'.join(lines)
    Path(output_file).write_text(report, encoding='utf-8')
    print(f"\n✅ Roster report written to: {output_file}")
    print(f"   Total lines: {len(lines)}")
    
    return output_file


def main():
    """Execute complete correlation analysis."""
    print("\n" + "="*80)
    print("TEAM-PLAYER CORRELATION ANALYSIS")
    print("Premier Manager 99 Database Reverse Engineering")
    print("="*80)
    print(f"\nInput files:")
    print(f"  Players: {PLAYER_FILE}")
    print(f"  Teams:   {TEAM_FILE}")
    
    # Phase 1: Extract player team_ids
    player_team_ids, total_players = extract_all_player_team_ids()
    
    # Phase 2: Extract team records
    teams = extract_all_team_records()
    
    # Phase 3: Correlate
    correlations, position_histogram = search_team_ids_in_records(teams, player_team_ids)
    
    # Phase 4: Analyze position
    team_id_position = analyze_team_id_position(position_histogram, correlations)
    
    # Phase 5: Generate report
    if correlations:
        report_file = generate_roster_report(correlations)
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"""
✅ Players analyzed:        {total_players:,}
✅ Unique player team_ids:  {len(player_team_ids):,}
✅ Team records found:      {len(teams):,}
✅ Successful correlations: {len(correlations):,}
✅ Team ID field position:  +{team_id_position if team_id_position is not None else 'UNKNOWN'}

📊 Correlation rate: {len(correlations)/len(player_team_ids)*100:.1f}%

Next steps:
1. Review {report_file if correlations else 'roster report'}
2. Validate team ID position by examining hex dumps
3. Update REVERSE_ENGINEERING_HANDOVER.md with findings
4. Proceed to Phase 2: Position field discovery
""")


if __name__ == "__main__":
    main()