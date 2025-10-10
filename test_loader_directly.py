"""Test the loader directly with debug output."""

from pathlib import Path

import pytest

from app.loaders import load_coaches

COACH_FILE = Path("DBDAT/ENT98030.FDI")

if not COACH_FILE.exists():
    pytest.skip("Required data file not found: DBDAT/ENT98030.FDI", allow_module_level=True)

coaches = load_coaches(str(COACH_FILE))
print(f"Loaded {len(coaches)} coaches")

if len(coaches) > 0:
    print("\nFirst 20 coaches:")
    for i, (offset, coach) in enumerate(coaches[:20]):
        name = getattr(coach, 'full_name', '')
        print(f"  {i+1}. {name} (offset: 0x{offset:x})")
else:
    print("\nNo coaches loaded - checking why...")
    
    # Add inline debugging
    from pathlib import Path
    from app.loaders import decode_entry
    from app.coach_models import parse_coaches_from_record
    
    data = COACH_FILE.read_bytes()
    pos = 0x1504  # Known good offset from earlier debug
    
    decoded, length = decode_entry(data, pos)
    print(f"\nDecoding entry at 0x{pos:x}, length={length}")
    
    coaches_parsed = parse_coaches_from_record(decoded) or []
    print(f"Parsed {len(coaches_parsed)} coach records")
    
    if len(coaches_parsed) > 0:
        c = coaches_parsed[0]
        name = getattr(c, 'full_name', '')
        print(f"\nFirst coach: '{name}'")
        print(f"  Length: {len(name)}")
        print(f"  Starts with uppercase: {name[0].isupper()}")
        print(f"  Has space: {' ' in name}")
        print(f"  Parts: {name.split()}")
        
        # Check phrase filtering
        common_phrases = [
            'premier league', 'first division', 'second division', 'third division', 'fourth division',
            'league cup', 'european cup', 'world cup', 'french cup', 'spanish cup', 'italian cup',
            'cup winner', 'cup winners', 'champions league', 'uefa cup',
            'french league', 'spanish league', 'italian league', 'german league',
            'head coach', 'technical advisor', 'national team',
            'paris saint', 'manchester utd', 'old trafford', 'san siro',
            'football league', 'scottish league', 'scottish cup',
            'division champion', 'division runner', 'league championship'
        ]
        
        name_lower = name.lower()
        matches = [p for p in common_phrases if p in name_lower]
        if matches:
            print(f"  Matched phrases: {matches}")
        else:
            print(f"  No phrase matches")
