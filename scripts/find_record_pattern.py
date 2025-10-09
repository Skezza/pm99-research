"""
Work from known offset 0x410 and find the pattern
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

data = Path('DBDAT/JUG98030.FDI').read_bytes()

print("=== Finding Player Record Pattern ===\n")

# We know 0x410 is a player record (from verify.txt)
print("Starting at documented offset 0x410:")

pos = 0x410
record_num = 0

# Try to find multiple consecutive records
for i in range(5):  # Try to find 5 records
    if pos >= len(data):
        break
    
    print(f"\n--- Record {record_num} at 0x{pos:06x} ---")
    
    # Try decoding
    decoded, consumed = decode_xor61(data, pos)
    
    if consumed == 0:
        print(f"Failed to decode - invalid length")
        break
    
    print(f"Decoded blob: {consumed-2} bytes (total consumed: {consumed})")
    print(f"First 32 bytes (hex): {decoded[:32].hex()}")
    
    # Try to find strings in the decoded blob using 32-bit XOR
    # This matches FUN_00677e30
    def decode_inner_string(blob: bytes, offset: int) -> tuple[str, int]:
        if offset + 2 > len(blob):
            return "", 0
        length = struct.unpack_from("<H", blob, offset)[0]
        if length > 1000 or offset + 2 + length > len(blob):
            return f"<bad len={length}>", 0
        
        encoded = blob[offset+2 : offset+2+length]
        decoded_str = bytearray()
        
        # 32-bit XOR
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
            text = bytes(decoded_str).decode('cp1252')
            return text, 2 + length
        except:
            return "<decode error>", 2 + length
    
    # Try parsing fields from the decoded blob
    inner_pos = 0
    
    # First byte might be region
    if inner_pos < len(decoded):
        region = decoded[inner_pos]
        print(f"  Byte 0: {region} (possible region code)")
        inner_pos += 1
    
    # Try reading strings
    for field_num in range(3):
        if inner_pos >= len(decoded):
            break
        text, consumed_inner = decode_inner_string(decoded, inner_pos)
        if consumed_inner > 0:
            print(f"  String {field_num} at offset {inner_pos}: '{text[:50]}'")
            inner_pos += consumed_inner
        else:
            break
    
    # Move to next record
    pos += consumed
    record_num += 1
    
    print(f"Next record would be at: 0x{pos:06x}")

print(f"\n=== Summary ===")
print(f"Successfully parsed {record_num} records")
print(f"Final position: 0x{pos:06x}")
if record_num > 1:
    avg_size = (pos - 0x410) / record_num
    print(f"Average record size: {avg_size:.1f} bytes")
    print(f"Estimated total for 1218 records: {1218 * avg_size / 1024:.1f} KB")