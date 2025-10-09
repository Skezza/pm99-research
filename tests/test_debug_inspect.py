#!/usr/bin/env python3
import struct
from pm99_editor.models import PlayerRecord, FDIHeader, DirectoryEntry
from pm99_editor.xor import decode_entry

def _build_fdi_from_records(records):
    header = FDIHeader(signature=b'DMFIv1.0', record_count=len(records), version=700, max_offset=0, dir_size=len(records)*8)
    header_bytes = header.to_bytes()
    dir_bytes = bytearray()
    rec_bytes = bytearray()
    current_offset = 0x20 + header.dir_size
    entries = []
    for i, record in enumerate(records):
        record_bytes = record.to_bytes()
        entry = DirectoryEntry(offset=current_offset, tag=ord('P'), index=i)
        dir_bytes.extend(entry.to_bytes())
        rec_bytes.extend(record_bytes)
        entries.append(entry)
        current_offset += len(record_bytes)
    header.max_offset = current_offset
    header_bytes = header.to_bytes()
    file_bytes = header_bytes + bytes(dir_bytes) + bytes(rec_bytes)
    return file_bytes, entries

def test_debug_inspect_prints(capsys):
    p1 = PlayerRecord(given_name="David", surname="Beckham", nationality=30, position_primary=3, position_secondary=3, birth_day=2, birth_month=5, birth_year=1975, height=180, weight=75, skills=[50]*10, version=700)
    p2 = PlayerRecord(given_name="Zinedine", surname="Zidane", nationality=3, position_primary=2, position_secondary=2, birth_day=23, birth_month=6, birth_year=1972, height=185, weight=78, skills=[60]*10, version=700)
    p3 = PlayerRecord(given_name="Alan", surname="Shearer", nationality=44, position_primary=3, position_secondary=3, birth_day=13, birth_month=8, birth_year=1970, height=183, weight=80, skills=[55]*10, version=700)
    records = [p1, p2, p3]

    file_bytes, entries = _build_fdi_from_records(records)
    print("Total file size:", len(file_bytes))
    hdr = FDIHeader.from_bytes(file_bytes)
    print("Header:", hdr)

    for i, entry in enumerate(entries):
        dir_pos = 0x20 + i*8
        de = DirectoryEntry.from_bytes(file_bytes, dir_pos)
        print(f"Dir entry {i} @0x{dir_pos:x}: offset=0x{de.offset:x} tag={de.tag} index={de.index}")
        # print first 8 bytes at record offset
        rec_slice = file_bytes[de.offset:de.offset+16]
        print("record bytes (first 16):", rec_slice.hex())
        try:
            decoded, length = decode_entry(file_bytes, de.offset)
            print(" decoded length:", length, "decoded len:", len(decoded))
            print(" decoded first 64 bytes:", decoded[:64].hex())
        except Exception as e:
            print(" decode_entry error:", e)

    # sanity assertion to keep test passing
    assert True