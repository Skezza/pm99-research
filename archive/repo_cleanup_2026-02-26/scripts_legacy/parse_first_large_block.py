"""
Parse the first large block (35KB) at 0x402 which contains player data
"""
import struct
from pathlib import Path

def decode_string_32bit(blob: bytes, offset: int) -> tuple[str, int]:
    """Decode string using 32-bit XOR (FUN_00677e30 style)"""
    if offset + 2 > len(blob):
        return "", 0
    
    length = struct.unpack_from("<H", blob, offset)[0]
    if length > 500 or offset + 2 + length > len(blob):
        return "", 0
    
    encoded = blob[offset+2 : offset+2+length]
    decoded = bytearray()
    
    p = 0
    while p + 4 <= len(encoded):
        dword = struct.unpack_from("<I", encoded, p)[0]
        decoded.extend(struct.pack("<I", dword ^ 0x61616161))
        p += 4
    if p + 2 <= len(encoded):
        word = struct.unpack_from("<H", encoded, p)[0]
        decoded.extend(struct.pack("<H", word ^ 0x6161))
        p += 2
    if p < len(encoded):
        decoded.append(encoded[p] ^ 0x61)
    
    if b'\x00' in decoded:
        decoded = decoded[:decoded.index(b'\x00')]
    
    try:
        return bytes(decoded).decode('cp1252', errors='replace'), 2 + length
    except:
        return "", 2 + length

data = Path('DBDAT/JUG98030.FDI').read_bytes()

# Decode the entire first block
first_block_start = 0x402
first_block_length = struct.unpack_from("<H", data, first_block_start)[0]
first_block_encoded = data[first_block_start+2 : first_block_start+2+first_block_length]
first_block = bytes(b ^ 0x61 for b in first_block_encoded)

print(f"=== First Large Block Analysis ===")
print(f"Start: 0x{first_block_start:06x}")
print(f"Length: {first_block_length} bytes")
print(f"Decoded size: {len(first_block)} bytes\n")

# The offset 0x410 is at 0x410 - 0x402 = 0xE into the FILE
# But the first 2 bytes are the length prefix, so it's at:
offset_in_block = 0x410 - (first_block_start + 2)
print(f"Offset 0x410 is at byte {offset_in_block} (0x{offset_in_block:x}) in the decoded block\n")

# Try parsing from different starting points
for start_offset in [0, offset_in_block]:
    print(f"\n--- Trying to parse from offset {start_offset} (0x{start_offset:x}) ---")
    
    pos = start_offset
    
    # Skip region byte if at start
    if pos < len(first_block):
        region = first_block[pos]
        print(f"Byte at {pos}: 0x{region:02x} ({region})")
        if region in [0, 0x61, 97]:  # Common region codes
            pos += 1
    
    # Try reading 3 strings
    for i in range(3):
        if pos >= len(first_block):
            break
        
        text, consumed = decode_string_32bit(first_block, pos)
        if consumed > 0 and text:
            print(f"  String {i} at {pos}: '{text}'")
            pos += consumed
        else:
            print(f"  String {i} at {pos}: FAILED (bytes: {first_block[pos:pos+16].hex()})")
            break