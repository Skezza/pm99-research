#!/usr/bin/env python3
"""
Test script to find specific players like BECKHAM and THORNE
"""

from pm99_database_editor import find_player_records
from pathlib import Path

def main():
    file_path = 'DBDAT/JUG98030.FDI'
    if not Path(file_path).exists():
        print(f"File not found: {file_path}")
        return
    
    file_data = Path(file_path).read_bytes()
    records = find_player_records(file_data)
    
    print(f"Found {len(records)} total records")
    
    # Search for specific players
    targets = ['BECKHAM', 'THORNE', 'HIERRO', 'ZIDANE', 'RONALDO']
    
    found = {}
    for target in targets:
        matches = [r for _, r in records if target.lower() in r.name.lower()]
        found[target] = matches
        print(f"\n{target}: {len(matches)} matches")
        for match in matches[:3]:  # Show first 3
            print(f"  - {match.name} (Team: {match.team_id}, Pos: {match.get_position_name()})")
    
    # Summary
    print(f"\n=== SUMMARY ===")
    total_found = sum(len(m) for m in found.values())
    print(f"Total target players found: {total_found}")
    if total_found < len(targets):
        print("Some players missing - may be in biography records not fully parsed")

if __name__ == '__main__':
    main()