"""
Parse player records and extract names
"""
import struct
from pathlib import Path

def decode_xor61(data: bytes, offset: int) -> tuple[bytes, int]:
    """Decode XOR-0x61 field"""
    length = struct.unpack_from("<H", data, offset)[0]
    if offset + 2 + length > len(data):
        return b"", 0
    encoded = data[offset+2 : offset+2+length]
    decoded = bytes(b ^ 0x61 for b in encoded)
    return decoded, 2 + length

def decode_inner_string(blob: bytes, offset: int) -> tuple[str, int]:
    """Decode string from inside blob using 32-bit XOR"""
    if offset + 2 > len(blob):
        return "", 0
    
    length = struct.unpack_from("<H", blob, offset)[0]
    
    # Sanity check
    if length > 1000 or offset + 2 + length > len(blob):
        return f"<bad_len={length}>", 0
    
    encoded = blob[offset+2 : offset+2+length]
    decoded_str = bytearray()
    
    # 32-bit XOR matching FUN_00677e30
    p = 0
    while p + 4 <= len(encoded):
        dword = struct.unpack_from("<I", encoded, p)[0]
        decoded_str.extend(struct.pack("<I", dword ^ 0x61616161))
        p += 4
    if p + 2 <= len(encoded):
        word = struct.unpack_from("<H", encoded, p)[0]
        decoded_str.extend(struct.pack("<H", word ^ 0x6161))
        p += 2
    if p < len(encoded):
        decoded_str.append(encoded[p] ^ 0x61)
    
    # Remove null terminator
    if b'\x00' in decoded_str:
        decoded_str = decoded_str[:decoded_str.index(b'\x00')]
    
    try:
        text = bytes(decoded_str).decode('cp1252', errors='replace')
        return text, 2 + length
    except:
        return f"<error>", 2 + length

data = Path('DBDAT/JUG98030.FDI').read_bytes()

print("=== Parsing Player Names ===\n")
print(f"File size: {len(data):,} bytes\n")

pos = 0x410
record_num = 0
successful_parses = 0

for i in range(20):  # Try first 20 records
    if pos >= len(data):
        break
    
    # Decode the outer XOR layer
    decoded, consumed = decode_xor61(data, pos)
    
    if consumed == 0 or consumed < 10:  # Skip tiny/empty records
        pos += max(consumed, 2)
        continue
    
    print(f"Record {record_num} @ 0x{pos:06x} ({consumed} bytes total):")
    
    # Parse inner structure
    inner_pos = 0
    
    # First byte might be region code (often 0x00 which XORs to 0x61)
    if inner_pos < len(decoded):
        region = decoded[inner_pos]
        inner_pos += 1
    
    # Try to extract name strings
    given_name, c1 = decode_inner_string(decoded, inner_pos)
    if c1 > 0:
        inner_pos += c1
        surname, c2 = decode_inner_string(decoded, inner_pos)
        if c2 > 0:
            inner_pos += c2
            common_name, c3 = decode_inner_string(decoded, inner_pos)
            
            # Display
            full_name = f"{given_name} {surname}".strip()
            if common_name and common_name != given_name:
                full_name += f" ({common_name})"
            
            print(f"  Name: {full_name}")
            print(f"  Consumed inner: {inner_pos} bytes of {len(decoded)}")
            
            if given_name and given_name != "<bad_len=24877>":
                successful_parses += 1
        else:
            print(f"  Given: {given_name} (surname parse failed)")
    else:
        print(f"  Parse failed - blob starts: {decoded[:32].hex()}")
    
    pos += consumed
    record_num += 1
    print()

print(f"=== Summary ===")
print(f"Total records processed: {record_num}")
print(f"Successfully parsed names: {successful_parses}")
print(f"Final position: 0x{pos:06x}")
print(f"Bytes consumed: {pos - 0x410:,}")