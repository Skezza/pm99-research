"""Debug coach loader to see what's happening."""

from pathlib import Path
from app.loaders import decode_entry
from app.coach_models import parse_coaches_from_record

coach_file = "DBDAT/ENT98030.FDI"
data = Path(coach_file).read_bytes()
pos = 0x400
count = 0
valid_count = 0

print(f"File size: {len(data)} bytes")
print(f"Starting scan from offset 0x{pos:x}")

while pos < len(data) - 1000 and count < 20:
    try:
        decoded, length = decode_entry(data, pos)
        
        if length >= 100 and length <= 50000:
            count += 1
            print(f"\n[{count}] Offset: 0x{pos:x}, Length: {length}")
            
            try:
                coaches = parse_coaches_from_record(decoded) or []
                print(f"  Parsed {len(coaches)} coaches")
                
                for i, c in enumerate(coaches):
                    name = getattr(c, 'full_name', '')
                    print(f"    Coach {i+1}: '{name}'")
                    
                    # Check validation
                    if not name:
                        print(f"      ✗ No name")
                        continue
                    if len(name) < 6:
                        print(f"      ✗ Too short: {len(name)} chars")
                        continue
                    if len(name) > 40:
                        print(f"      ✗ Too long: {len(name)} chars")
                        continue
                    if not name[0].isupper():
                        print(f"      ✗ Doesn't start with uppercase")
                        continue
                    if ' ' not in name:
                        print(f"      ✗ No space")
                        continue
                    
                    parts = name.split()
                    if len(parts) < 2:
                        print(f"      ✗ Less than 2 parts")
                        continue
                    
                    print(f"      ✓ VALID - {len(parts)} parts")
                    valid_count += 1
                    
            except Exception as e:
                print(f"  Error parsing: {e}")
        
        pos += 2 + length if length > 0 else 1
        
    except Exception as e:
        pos += 1

print(f"\n\nTotal entries checked: {count}")
print(f"Valid coaches found: {valid_count}")
