#!/usr/bin/env python3
"""
Locate Paolo MALDINI's record by searching for full name in decoded data
"""

from pathlib import Path
import struct

def xor_decode(data: bytes, key: int = 0x61) -> bytes:
    return bytes(b ^ key for b in data)

def main():
    file_path = 'DBDAT/JUG98030.FDI'
    if not Path(file_path).exists():
        print(f"File not found: {file_path}")
        return
    
    file_data = Path(file_path).read_bytes()
    target_name = b'Paolo MALDINI'  # Exact bytes for search
    
    print("🔍 Searching for exact 'Paolo MALDINI' in decoded sections...")
    
    pos = 0x400
    sections_found = 0
    maldini_found = False
    
    while pos < len(file_data) - 1000 and sections_found < 500:
        try:
            length = struct.unpack_from("<H", file_data, pos)[0]
            
            if 1000 < length < 100000:
                encoded = file_data[pos+2 : pos+2+length]
                decoded = xor_decode(encoded, 0x61)
                
                if target_name in decoded:
                    # Found it!
                    start_offset = decoded.find(target_name)
                    record_start = pos + 2 + start_offset
                    
                    print(f"\n🎯 FOUND Paolo MALDINI!")
                    print(f"Section offset: 0x{pos:08x}")
                    print(f"Name offset: 0x{record_start:08x}")
                    print(f"Record length: {length} bytes")
                    
                    # Extract surrounding record
                    # Look for separator before and after
                    separator = b'\xdd\xc3`'
                    before_sep = decoded.rfind(separator, 0, start_offset)
                    after_sep = decoded.find(separator, start_offset)
                    
                    if before_sep != -1 and after_sep != -1:
                        record_data = decoded[before_sep + 3 : after_sep]
                        record_offset = pos + 2 + before_sep + 3
                    else:
                        # Fallback: take 200 bytes around name
                        record_start = max(0, start_offset - 50)
                        record_end = min(len(decoded), start_offset + 150)
                        record_data = decoded[record_start:record_end]
                        record_offset = pos + 2 + record_start
                    
                    print(f"Extracted record length: {len(record_data)} bytes")
                    print(f"Record offset: 0x{record_offset:08x}")
                    
                    # Dump first 100 bytes of record
                    print(f"\n📊 Record Bytes 0-100 (Raw file bytes):")
                    print("Byte | Hex | Dec | XOR | ASCII")
                    print("-" * 40)
                    
                    for i in range(min(100, len(record_data))):
                        b = record_data[i]
                        xor_val = b ^ 0x61
                        ascii_char = chr(b) if 32 <= b <= 126 else '·'
                        print(f"{i:4d} | 0x{b:02x} | {b:3d} | {xor_val:3d} | {ascii_char}")
                    
                    # Save full record to file for analysis
                    with open('maldini_record.bin', 'wb') as f:
                        f.write(record_data)
                    print(f"\n💾 Full record saved to: maldini_record.bin")
                    
                    # Search for known values in this record
                    maldini_stats = [30, 89, 93, 92, 83, 91, 76, 99, 8, 82, 85, 70, 88, 73]  # Age, Rating, Attributes
                    print(f"\n🎯 Known Values Search in Record:")
                    for value in maldini_stats:
                        positions = []
                        for i, b in enumerate(record_data):
                            if b == value:
                                positions.append(f"{i}(raw)")
                            if (b ^ 0x61) == value:
                                positions.append(f"{i}(xor)")
                        if positions:
                            print(f"  {value}: {', '.join(positions[:5])}")
                    
                    maldini_found = True
                    break
                
                pos += length + 2
                sections_found += 1
            else:
                pos += 1
        except:
            pos += 1
    
    if not maldini_found:
        print("❌ Paolo MALDINI not found with exact match")
        print("Trying partial match...")
        
        # Fallback search
        pos = 0x400
        while pos < len(file_data) - 1000:
            try:
                length = struct.unpack_from("<H", file_data, pos)[0]
                if 1000 < length < 100000:
                    encoded = file_data[pos+2 : pos+2+length]
                    decoded = xor_decode(encoded, 0x61)
                    
                    # Look for "MALDINI" anywhere
                    if b'MALDINI' in decoded.upper():
                        start_offset = decoded.upper().find(b'MALDINI')
                        print(f"\n🔍 Partial match found at section 0x{pos:08x}, offset {start_offset}")
                        
                        # Extract 200 bytes around
                        extract_start = max(0, start_offset - 50)
                        extract_end = min(len(decoded), start_offset + 150)
                        extract_data = decoded[extract_start:extract_end]
                        
                        with open('maldini_partial.bin', 'wb') as f:
                            f.write(extract_data)
                        print(f"Extract saved to: maldini_partial.bin")
                        
                        # Show context
                        context = extract_data.decode('latin-1', errors='ignore')
                        print(f"Context around MALDINI:\n{context}")
                        break
                    
                    pos += length + 2
                else:
                    pos += 1
            except:
                pos += 1

if __name__ == '__main__':
    main()