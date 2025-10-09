"""
Parse coach names from the decoded structure
The names are PLAIN TEXT after XOR decode, not nested XOR!
"""
import struct
from pathlib import Path

data = Path('DBDAT/ENT98030.FDI').read_bytes()

# The coach records start at 0x026cf6
pos = 0x026cf6

# Decode outer XOR
length = struct.unpack_from("<H", data, pos)[0]
encoded = data[pos+2 : pos+2+length]
decoded = bytes(b ^ 0x61 for b in encoded)

print(f"=== Coach Record Structure ===")
print(f"Total decoded: {len(decoded)} bytes\n")

# The decoded data contains multiple coach entries
# Looking at the pattern, it seems to be:
# [metadata] surname [sep] [metadata] given_name full_name [padding]

# Let's find all occurrences of readable text
import re

# Find all sequences of printable ASCII that look like names
name_pattern = rb'[A-Z][a-z]{2,15}'
matches = list(re.finditer(name_pattern, decoded))

print(f"Found {len(matches)} potential name strings:\n")

for i, match in enumerate(matches[:20]):  # Show first 20
    name = match.group().decode('ascii')
    offset = match.start()
    
    # Show context around the name
    start = max(0, offset - 5)
    end = min(len(decoded), offset + len(name) + 10)
    context = decoded[start:end]
    
    print(f"[{i}] @ offset {offset:3d}: '{name}'")
    print(f"     Context (hex): {context.hex()}")
    print(f"     Context (txt): {''.join(chr(b) if 32<=b<127 else '.' for b in context)}")
    print()

# Try to identify the separator pattern
print("\n=== Pattern Analysis ===")
print("Looking for repeating structure...")

# The pattern seems to be entries separated by specific bytes
# Let's find the separator
sep_candidates = []
for i in range(len(decoded) - 1):
    if decoded[i] == 0x61 and decoded[i+1] == 0xdd:
        sep_candidates.append(i)

print(f"Found {len(sep_candidates)} potential separators at 0x61 0xdd")
if sep_candidates:
    print(f"Separator positions: {sep_candidates[:10]}")
    
    # Calculate spacing
    if len(sep_candidates) > 1:
        spacings = [sep_candidates[i+1] - sep_candidates[i] for i in range(len(sep_candidates)-1)]
        print(f"Spacings between separators: {spacings[:10]}")