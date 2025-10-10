"""Test coach parsing."""

import struct
from pathlib import Path

import pytest

from pm99_editor.coach_models import parse_coaches_from_record

COACH_FILE = Path('DBDAT/ENT98030.FDI')

if not COACH_FILE.exists():
    pytest.skip("Required data file not found: DBDAT/ENT98030.FDI", allow_module_level=True)

data = COACH_FILE.read_bytes()

# The coach record is at 0x026cf6
pos = 0x026cf6

# Decode outer XOR
length = struct.unpack_from("<H", data, pos)[0]
encoded = data[pos+2 : pos+2+length]
decoded = bytes(b ^ 0x61 for b in encoded)

print(f"=== Testing Coach Parser ===\n")
print(f"Decoded record: {len(decoded)} bytes\n")

# Parse coaches
coaches = parse_coaches_from_record(decoded)

print(f"Found {len(coaches)} coaches:\n")

for i, coach in enumerate(coaches):
    print(f"{i+1}. {coach}")
    print(f"   Surname: '{coach.surname}'")
    print(f"   Given: '{coach.given_name}'")
    print(f"   Full: '{coach.full_name}'")
    print()

if coaches:
    print("✓ Coach parsing successful!")
else:
    print("✗ No coaches parsed")