#!/usr/bin/env python3
import struct
from pathlib import Path
from app.models import PlayerRecord, FDIHeader, DirectoryEntry
from app.xor import decode_entry

def build_fdi(records):
    header = FDIHeader(signature=b'DMFIv1.0', record_count=len(records), version=700, max_offset=0, dir_size=len(records)*8)
    dir_bytes = bytearray()
    rec_bytes = bytearray()
    current_offset = 0x20 + header.dir_size
    entries=[]
    for i, rec in enumerate(records):
        entry_bytes = rec.to_bytes()
        rec_bytes.extend(entry_bytes)
        dir_entry = DirectoryEntry(offset=current_offset, tag=ord('P'), index=i)
        dir_bytes.extend(dir_entry.to_bytes())
        entries.append(dir_entry)
        current_offset += len(entry_bytes)
    header.max_offset = current_offset
    header_bytes = header.to_bytes()
    fbytes = header_bytes + bytes(dir_bytes) + bytes(rec_bytes)
    return fbytes, entries

p1 = PlayerRecord(given_name="David", surname="Beckham", nationality=30, position_primary=3, position_secondary=3, birth_day=2, birth_month=5, birth_year=1975, height=180, weight=75, skills=[50]*10, version=700)
p2 = PlayerRecord(given_name="Zinedine", surname="Zidane", nationality=3, position_primary=2, position_secondary=2, birth_day=23, birth_month=6, birth_year=1972, height=185, weight=78, skills=[60]*10, version=700)
p3 = PlayerRecord(given_name="Alan", surname="Shearer", nationality=44, position_primary=3, position_secondary=3, birth_day=13, birth_month=8, birth_year=1970, height=183, weight=80, skills=[55]*10, version=700)
records = [p1, p2, p3]

fbytes, entries = build_fdi(records)
path = Path('debug_fdi.bin')
path.write_bytes(fbytes)
print("Wrote", path, "size", len(fbytes))

hdr = FDIHeader.from_bytes(fbytes)
print("Header:", hdr)

def hexdump(b, n=64):
    return ' '.join(f"{x:02x}" for x in b[:n])

print("First 64 bytes:", hexdump(fbytes, 64))
for i, entry in enumerate(entries):
    entry_pos = 0x20 + i*8
    dir_entry = DirectoryEntry.from_bytes(fbytes, entry_pos)
    print(f"\nDirectory entry {i} @0x{entry_pos:x}: offset=0x{dir_entry.offset:x} tag={dir_entry.tag} index={dir_entry.index}")
    two = fbytes[dir_entry.offset: dir_entry.offset+2]
    print(" two bytes raw:", two.hex(), " => int:", struct.unpack_from('<H', fbytes, dir_entry.offset)[0] if len(two)>=2 else None)
    try:
        decoded, length = decode_entry(fbytes, dir_entry.offset)
        print(f" decoded length: {length}, decoded bytes len: {len(decoded)}")
        print(" decoded first 128 bytes:", hexdump(decoded, 128))
    except Exception as e:
        print(" decode_entry error:", e)
