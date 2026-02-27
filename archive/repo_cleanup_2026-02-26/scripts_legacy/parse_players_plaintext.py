"""
Parse JUG98030.FDI using the CORRECT format discovered from coaches:
After XOR decode, names are PLAIN TEXT (not nested XOR)
"""
import struct
import re
from pathlib import Path

data = Path('DBDAT/JUG98030.FDI').read_bytes()

print("=== JUG98030.FDI Player File Analysis ===\n")

# Start at the data section
pos = 0x402

# Decode first record
length = struct.unpack_from("<H", data, pos)[0]
print(f"First record length: {length} bytes\n")

encoded = data[pos+2 : pos+2+length]
decoded = bytes(b ^ 0x61 for b in encoded)

print(f"Decoded size: {len(decoded)} bytes\n")

# Search for English names (pattern: Capital letter + lowercase letters)
name_pattern = rb'[A-Z][a-z]{2,15}'
matches = list(re.finditer(name_pattern, decoded))

print(f"Found {len(matches)} potential name strings:\n")

# Show first 30 matches
for i, match in enumerate(matches[:30]):
    name = match.group().decode('ascii', errors='replace')
    offset = match.start()
    
    # Show context
    start = max(0, offset - 5)
    end = min(len(decoded), offset + len(name) + 10)
    context = decoded[start:end]
    context_str = ''.join(chr(b) if 32<=b<127 else '.' for b in context)
    
    print(f"[{i:2d}] @ {offset:5d}: '{name:15s}' | {context_str}")

# Look for separator pattern (same as coaches)
print(f"\n=== Looking for separator pattern 0x61 0xdd 0x63 0x61 ===")
sep_count = 0
sep_positions = []
for i in range(len(decoded) - 3):
    if decoded[i:i+4] == b'\x61\xdd\x63\x61':
        sep_positions.append(i)
        sep_count += 1

print(f"Found {sep_count} separators")
if sep_positions:
    print(f"First 10 positions: {sep_positions[:10]}")
    
    # Calculate spacing
    if len(sep_positions) > 1:
        spacings = [sep_positions[i+1] - sep_positions[i] for i in range(min(10, len(sep_positions)-1))]
        print(f"Spacings: {spacings}")