#!/usr/bin/env python3
"""
Test strict filtering for coaches and teams
"""
import sys
import os

from pathlib import Path

import pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from pm99_editor.coach_models import parse_coaches_from_record
from pm99_editor.models import TeamRecord
from pm99_editor.xor import decode_entry

def test_coach_filtering():
    print("=== Testing Coach Filtering ===")
    coach_file = Path('DBDAT/ENT98030.FDI')
    if not coach_file.exists():
        pytest.skip("Required data file not found: DBDAT/ENT98030.FDI")

    data = coach_file.read_bytes()
    pos = 0x400
    seen_names = set()
    valid_coaches = []
    
    while pos < len(data) - 1000:
        try:
            decoded, length = decode_entry(data, pos)
            if length < 100 or length > 50000:
                pos += 2
                continue
            
            try:
                coaches = parse_coaches_from_record(decoded) or []
                for c in coaches:
                    name = getattr(c, 'full_name', '')
                    
                    # Strict validation
                    if not name or len(name) < 5:
                        continue
                    if not name[0].isupper():
                        continue
                    if ' ' not in name:
                        continue
                    
                    # ASCII ratio check
                    ascii_ratio = sum(1 for ch in name if 32 <= ord(ch) < 127) / len(name)
                    if ascii_ratio < 0.8:
                        continue
                    
                    # Too many 'a's check
                    if name.count('a') > len(name) * 0.7:
                        continue
                    
                    # Deduplicate
                    if name in seen_names:
                        continue
                    
                    seen_names.add(name)
                    valid_coaches.append(name)
            except Exception:
                pass
        except Exception:
            pass
        pos += 2 + (length if 'length' in locals() else 1)
    
    print(f"Total valid coaches found: {len(valid_coaches)}")
    for i, name in enumerate(valid_coaches[:20]):
        print(f"  {i+1}: {name}")

def test_team_filtering():
    print("\n=== Testing Team Filtering ===")
    team_file = Path('DBDAT/EQ98030.FDI')
    if not team_file.exists():
        pytest.skip("Required data file not found: DBDAT/EQ98030.FDI")

    data = team_file.read_bytes()
    pos = 0x400
    seen_names = set()
    valid_teams = []
    
    while pos < len(data) - 1000:
        try:
            decoded, length = decode_entry(data, pos)
            if length < 100 or length > 10000:
                pos += 2
                continue
            
            try:
                team = TeamRecord(decoded, pos)
                name = getattr(team, 'name', None)
                
                # Strict validation
                if not name or name in ("Unknown Team", "Parse Error", ""):
                    pos += 2 + length
                    continue
                
                if len(name) < 4 or not name[0].isupper():
                    pos += 2 + length
                    continue
                
                # ASCII ratio check
                ascii_ratio = sum(1 for c in name if 32 <= ord(c) < 127) / len(name)
                if ascii_ratio < 0.8:
                    pos += 2 + length
                    continue
                
                # Deduplicate
                if name in seen_names:
                    pos += 2 + length
                    continue
                
                seen_names.add(name)
                valid_teams.append(name)
            except Exception:
                pass
        except Exception:
            pass
        pos += 2 + (length if 'length' in locals() else 1)
    
    print(f"Total valid teams found: {len(valid_teams)}")
    for i, name in enumerate(valid_teams[:20]):
        print(f"  {i+1}: {name}")

if __name__ == "__main__":
    test_coach_filtering()
    test_team_filtering()