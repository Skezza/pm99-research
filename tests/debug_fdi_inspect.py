#!/usr/bin/env python3
import struct
from pathlib import Path
from app.models import PlayerRecord, FDIHeader, DirectoryEntry
from app.xor import decode_entry, encode_entry, read_string, write_string

def build_fdi(records):
    header = FDIHeader(signature=b'DMFIv1.0', record_count=len(records), version=700, max_offset=0, dir_size=len(records)*8)
    dir_bytes = bytearray()
    rec_bytes = bytearray()
    current_offset = 0x20 + header.dir_size
    entries=[]
    for i, rec in enumerate(records):
        entry_bytes = rec.to_bytes()
        entry_len = len(entry_bytes)
        dir_entry = DirectoryEntry(offset=current_offset,tag=ord('P'),index=i)
        dir_bytes.extend(dir_entry.to_bytes())
        rec_bytes.extend(entry_bytes)
        entries.append(dir_entry)
        current_offset += entry_len
    header.max_offset=current_offset
    header_bytes = header.to_bytes()
    return header_bytes + bytes(dir_bytes) + bytes(rec_bytes), entries

def hexdump(b):
    return ' '.join(f'{x:02x}' for x in b)

p1 = PlayerRecord(given_name="David", surname="Beckham", nationality=30, position_primary=3, position_secondary=3, birth_day=2, birth_month=5, birth_year=1975, height=180, weight=75, skills=[50]*10, version=700)
p2 = PlayerRecord(given_name="Zinedine", surname="Zidane", nationality=3, position_primary=2, position_secondary=2, birth_day=23, birth_month=6, birth_year=1972, height=185, weight=78, skills=[60]*10, version=700)
p3 = PlayerRecord(given_name="Alan", surname="Shearer", nationality=44, position_primary=3, position_secondary=3, birth_day=13, birth_month=8, birth_year=1970, height=183, weight=80, skills=[55]*10, version=700)
records=[p1,p2,p3]
fbytes, entries = build_fdi(records)
fpath = Path('tests/debug_roundtrip.fdi')
fpath.write_bytes(fbytes)

print(f'Wrote debug file: {fpath} size {len(fbytes)} bytes')
hdr = FDIHeader.from_bytes(fbytes)
print('Header:', hdr)
print('Dir size:', hdr.dir_size, 'record_count', hdr.record_count, 'max_offset', hdr.max_offset)

for i, entry in enumerate(entries):
    off = entry.offset
    print(f'\nEntry {i}: dir_offset? writing offset {off}, dir_entry_bytes@{0x20 + i*8}: {hexdump(fbytes[0x20 + i*8: 0x20 + i*8 +8])}')
    first32 = fbytes[off: off+32]
    print(f'file[{off:02x}:{off+32:02x}] = {hexdump(first32)}')
    try:
        decoded, length = decode_entry(fbytes, off)
        print('decoded length', length, 'decoded payload len', len(decoded))
        print('decoded payload hexdump first 128 bytes', hexdump(decoded[:128]))
        if len(decoded) > 0:
            print('region_code', decoded[0])
            pos = 1
            try:
                s1, consumed = read_string(decoded, pos)
                print('given_name:', s1, 'consumed', consumed)
                pos += consumed
                s2, consumed2 = read_string(decoded, pos)
                print('surname:', s2, 'consumed', consumed2)
            except Exception as e2:
                print('read_string failed:', e2)
    except Exception as e:
        print('decode_entry failed:', e)

for i, entry in enumerate(entries):
    try:
        rec = PlayerRecord.from_bytes(fbytes, entry.offset, version=700)
        print(f'PlayerRecord.from_bytes succeeded for entry {i}: {rec.given_name} {rec.surname}')
    except Exception as e:
        print(f'PlayerRecord.from_bytes failed for entry {i}:', e)
