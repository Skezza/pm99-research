"""
Analyze Memory Dump from Running Game
======================================

Address: 002D369C
This appears to be player records in memory format.
The structure may differ from disk format but reveals field positions.
"""

import re

# The hex dump provided by user
hex_dump = """
4D4C4D4C6B220D4F58594D230E0200412B140F080E13124D504D594D516B54524D534352523C4310003F3F3F3F3F2D00BC02013B42190E002D140812412904130F800F05041B1D002D3428324120131514130E412924332FA02F25243B412200131304920F0901090C0E00000053010103160CB007AF4958544E5550554F54280C0052525252521500BC02013C420107002D00081B000F120C002B141308412D20283B202F321100070810000000700106010601BB078C01433B3D453B3A3C35380C003B3840403A1A00BC02013D420107002A0E0D080F0A0E1100200D0419000F050413412A2E2D282F2A2E0C00010000000000700106001206B7078C0123281D21130E1619100700050F0A03041C00BC02013E420109003B040C0D080F120A1811002C080A0900080D413B242C2D282F322A380E0002060000000070010601150CB1078C01323A2F3B1B1F2528210A0039373B35392300BC02013F42010E00230D00060E0F0005041B0905080F13002E0D040641232D20262E2F2025243B2925282F0D00020600000000700106011005B5078C013B384842353A383C3A0700403A35413D1A00BC0201414201090032080D000600051B040F002D0417000F4132282D202620253B2404000506000000003E0101010408B8078C013D403A443E3B3A3D420E00403B463B451700BC0201434201080032150411000F0E170D0028060E134132352431202F2E370500060205000000700106011501B8078C01413F3F3A38383E403A0800393A3939392600BC02014542010D0033040A09170800120917080D081700200D0419000F0504134133242A29372820322937282D280600080A000000003E0106020608B6078C01413B3935373B3B363B05003D3F3C3E381B00BC0201464201080023000308020904171100370D0005080C081341232023282229243707000C0900000000700101021604B0078C01353A3E373E38393E3B10003A3A3A3A3A1B00BC02014742010900230D040805040D08121000280C000F151241232D242825242D28320800071008000000700106021008B7078C013A353C413E3A393C37090041323232453400BC020048420106003100090013120D002C001318000F413120292033321E00090000000000700101030508B8078C017006002D00151708001000320A0E0F150E4133080600414958584806002D00151708000100190100190100191D004B4127140D0D412D00151708000F41280F1504130F0015080E0F000D4F47004B413208060F040541070E1341320E141509000C11150E0F41080F41270403131400131841505858584D410015410041020E1215410E07415951514D51515141110E140F05124F3F004B412D00121541120400120E0F412C001318000F411600124111001315410E0741150904412D00151708000F411504000C4D41320A0E0F150E41330806004F1E0058564C58594D320A0E0F150E413308060041492D0015484D504D4C4D4C6B5D483943393B3E383F080131444431311900BC0201494201080020121500071804170F00370815000D184120323520273824370A00080A07000000700106020304B3078C013B39373F221D2B2C2307003A3A3A3A3A1900BC02014B42010800320E0D0E171804170F0032041306041841322E2D2E373824371200060503020000320101010304BA078C01343F383C3836392F39050033333333461A00BC02014C420108002C080A090E0D001110002C080A0900080D41
""".replace('\n', '').strip()

# Convert hex string to bytes
data = bytes.fromhex(hex_dump)

print("="*80)
print("MEMORY DUMP ANALYSIS - Player Records")
print("="*80)
print(f"Total bytes: {len(data)}")
print(f"Address: 002D369C\n")

# Look for text strings (printable ASCII)
print("="*80)
print("EXTRACTING TEXT STRINGS")
print("="*80)

# Find all printable text sequences
text_pattern = rb'[ -~]{4,}'  # 4+ printable ASCII chars
matches = list(re.finditer(text_pattern, data))

print(f"\nFound {len(matches)} text strings:\n")

for i, match in enumerate(matches[:50]):  # First 50 strings
    text = match.group().decode('ascii', errors='replace')
    offset = match.start()
    
    # Show hex context
    start = max(0, offset - 8)
    end = min(len(data), offset + len(text) + 8)
    context_hex = data[start:end].hex()
    
    print(f"[{i:2d}] @ 0x{offset:04x} ({offset:4d}): {text[:60]}")
    if len(text) > 60:
        print(f"                          ... (total {len(text)} chars)")

# Look for player names specifically
print(f"\n" + "="*80)
print("PLAYER NAMES DETECTED")
print("="*80)

# Pattern for names (Capital letter followed by letters)
name_pattern = rb'[A-Z][a-z]{2,15}(?:\s+[A-Z][a-z]{2,15})*'
name_matches = list(re.finditer(name_pattern, data))

print(f"\nFound {len(name_matches)} potential player names:\n")

for i, match in enumerate(name_matches):
    name = match.group().decode('ascii', errors='replace')
    offset = match.start()
    
    # Get surrounding bytes for analysis
    pre_bytes = data[max(0, offset-10):offset]
    post_bytes = data[offset+len(match.group()):min(len(data), offset+len(match.group())+20)]
    
    print(f"{i+1:2d}. @ 0x{offset:04x}: {name:<30s}")
    print(f"    Pre:  {pre_bytes.hex()}")
    print(f"    Post: {post_bytes.hex()}")
    
    # Try to interpret post-name bytes
    if len(post_bytes) >= 10:
        # Look for attribute-like values (0-100 range)
        attrs = [b for b in post_bytes[:10] if 0 <= b <= 100 and b != 0x61]
        if len(attrs) >= 5:
            print(f"    Potential attributes: {attrs[:10]}")
    print()

# Look for team names
print(f"="*80)
print("TEAM NAMES DETECTED")
print("="*80)

teams_found = []
for match in re.finditer(rb'[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*', data):
    text = match.group().decode('ascii', errors='replace')
    # Filter for likely team names (longer phrases)
    if len(text) > 10 and ' ' in text:
        teams_found.append((match.start(), text))

print(f"\nFound {len(teams_found)} potential team names:\n")
for offset, team in teams_found[:20]:
    print(f"  @ 0x{offset:04x}: {team}")

# Look for separators/markers
print(f"\n" + "="*80)
print("STRUCTURE ANALYSIS")
print("="*80)

# Look for repeated byte patterns
print("\nRepeated byte sequences:")

for pattern_len in [2, 3, 4]:
    pattern_counts = {}
    for i in range(len(data) - pattern_len):
        pattern = data[i:i+pattern_len]
        pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
    
    # Show most common patterns
    common = sorted(pattern_counts.items(), key=lambda x: -x[1])[:5]
    if common and common[0][1] > 3:
        print(f"\n{pattern_len}-byte patterns (count > 3):")
        for pattern, count in common:
            if count > 3:
                print(f"  {pattern.hex():12s}: {count:3d} occurrences")

# Analyze byte value distribution
print(f"\n" + "="*80)
print("BYTE VALUE DISTRIBUTION")
print("="*80)

from collections import Counter
byte_dist = Counter(data)

print("\nMost common byte values:")
for byte_val, count in byte_dist.most_common(20):
    percentage = (count / len(data)) * 100
    char = chr(byte_val) if 32 <= byte_val < 127 else '.'
    print(f"  0x{byte_val:02x} ({byte_val:3d}, '{char}'): {count:4d} times ({percentage:5.2f}%)")

# Look for field delimiters
print(f"\n" + "="*80)
print("POTENTIAL FIELD STRUCTURE")
print("="*80)

print("\nAnalyzing structure around player names...")

# Take first few player names and analyze their structure
for i, match in enumerate(name_matches[:5]):
    offset = match.start()
    name = match.group().decode('ascii', errors='replace')
    
    # Get 32 bytes before and after name
    start = max(0, offset - 32)
    end = min(len(data), offset + len(match.group()) + 64)
    segment = data[start:end]
    
    print(f"\n{'='*80}")
    print(f"Player {i+1}: {name}")
    print(f"{'='*80}")
    
    # Hex dump with positions
    for line_off in range(0, len(segment), 16):
        chunk = segment[line_off:line_off+16]
        hex_str = ' '.join(f'{b:02x}' for b in chunk)
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        abs_offset = start + line_off
        print(f"  {abs_offset:04x}: {hex_str:<48} | {ascii_str}")

print(f"\n" + "="*80)
print("RECOMMENDATIONS")
print("="*80)
print("""
Based on this memory dump analysis:

1. The in-memory format appears to have:
   - Text strings for names and teams
   - Numerical attributes
   - Potential structure markers

2. Next steps:
   - Identify exact byte positions of known fields
   - Map the relationship between memory format and disk format
   - Use this to validate disk format field positions

3. Key patterns to investigate:
   - Bytes immediately before/after player names
   - Repeated sequences that might be record separators
   - Attribute value ranges (0-100)
""")