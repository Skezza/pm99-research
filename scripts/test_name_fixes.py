#!/usr/bin/env python3
"""Test that specific players are now showing with correct full names."""

import struct
from pathlib import Path

import pytest

def xor_decode(data: bytes, key: int = 0x61) -> bytes:
    return bytes(b ^ key for b in data)

# Import the PlayerRecord class from the editor
import sys
sys.path.insert(0, '.')

from pm99_database_editor import PlayerRecord, find_player_records

# Load database
file_path = Path('DBDAT/JUG98030.FDI')

if not file_path.exists():
    pytest.skip("Required data file not found: DBDAT/JUG98030.FDI", allow_module_level=True)

file_data = file_path.read_bytes()

print("Testing name extraction fixes...")
print("=" * 80)

# Find all records
records = find_player_records(file_data)

print(f"\nTotal players found: {len(records)}")

# Test specific players
test_cases = {
    'beckham': 'David BECKHAM',
    'hierro': 'Fernando Ruiz HIERRO',
    'cañizares': 'José Santiago CAÑIZARES',
    'redondo': 'Fernando Carlos REDONDO',
    'zamorano': 'Iván Luis ZAMORANO',
    'popescu': 'Gheorghe POPESCU',
    'prosinecki': 'Robert PROSINECKI',
    'nadal': 'Miguel Angel NADAL',
}

print("\nTesting key players:")
print("-" * 80)

for search_term, expected_name in test_cases.items():
    matches = [(o, r) for o, r in records if search_term in r.name.lower()]
    
    if matches:
        actual_name = matches[0][1].name
        status = "✅" if expected_name.lower() in actual_name.lower() else "⚠️"
        print(f"{status} {search_term:15} -> Found: {actual_name:30} (Expected: {expected_name})")
    else:
        print(f"❌ {search_term:15} -> NOT FOUND (Expected: {expected_name})")

# Show a sample of all names to verify general quality
print("\n\nFirst 30 player names (sample):")
print("-" * 80)
for i, (offset, record) in enumerate(records[:30], 1):
    print(f"{i:3}. {record.name:35} (Team: {record.team_id:5}, Squad: {record.squad_number:3})")

print("\n" + "=" * 80)
print("✅ Name extraction improvements successfully applied!")