#!/usr/bin/env python3
"""
Test GUI loading of coaches and teams
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from app.io import FDIFile
from app.models import TeamRecord
from app.coach_models import parse_coaches_from_record
from app.xor import decode_entry
from pathlib import Path
import pytest

def test_coach_loading():
    print("=== Testing Coach Loading ===")
    coach_file = Path('DBDAT/ENT98030.FDI')
    if not coach_file.exists():
        pytest.skip("Required data file not found: DBDAT/ENT98030.FDI")

    fdi = FDIFile(coach_file)
    fdi.load()

    coaches_found = []
    for entry, decoded, length in fdi.iter_decoded_directory_entries():
        coaches = parse_coaches_from_record(decoded)
        if coaches:
            coaches_found.extend(coaches)
            print(f"Found {len(coaches)} coaches at offset 0x{entry.offset:x}")

    # Also try sequential scanning
    if not coaches_found:
        print("No coaches from directory, trying sequential scan...")
        data = coach_file.read_bytes()
        pos = 0x400
        while pos < len(data) - 1000 and len(coaches_found) < 10:
            try:
                decoded, length = decode_entry(data, pos)
                if length > 100:
                    coaches = parse_coaches_from_record(decoded)
                    if coaches:
                        coaches_found.extend(coaches)
                        print(f"Found {len(coaches)} coaches at sequential pos 0x{pos:x}")
            except Exception:
                pass
            pos += 2 + (length if 'length' in locals() else 1)

    print(f"Total coaches found: {len(coaches_found)}")
    for i, c in enumerate(coaches_found[:5]):
        print(f"  {i+1}: {c.full_name}")

def test_team_loading():
    print("\n=== Testing Team Loading ===")
    team_file = Path('DBDAT/EQ98030.FDI')
    if not team_file.exists():
        pytest.skip("Required data file not found: DBDAT/EQ98030.FDI")

    fdi = FDIFile(team_file)
    fdi.load()

    teams_found = []
    for entry, decoded, length in fdi.iter_decoded_directory_entries():
        try:
            team = TeamRecord(decoded, entry.offset)
            if getattr(team, 'name', None) and team.name != "Unknown Team":
                teams_found.append(team)
                print(f"Found team '{team.name}' at offset 0x{entry.offset:x}")
        except Exception:
            pass

    # Also try sequential scanning
    if not teams_found:
        print("No teams from directory, trying sequential scan...")
        data = team_file.read_bytes()
        pos = 0x400
        while pos < len(data) - 1000 and len(teams_found) < 10:
            try:
                decoded, length = decode_entry(data, pos)
                if length > 50:
                    team = TeamRecord(decoded, pos)
                    if getattr(team, 'name', None) and team.name != "Unknown Team":
                        teams_found.append(team)
                        print(f"Found team '{team.name}' at sequential pos 0x{pos:x}")
            except Exception:
                pass
            pos += 2 + (length if 'length' in locals() else 1)

    print(f"Total teams found: {len(teams_found)}")
    for i, t in enumerate(teams_found[:5]):
        print(f"  {i+1}: {t.name}")

if __name__ == "__main__":
    test_coach_loading()
    test_team_loading()
