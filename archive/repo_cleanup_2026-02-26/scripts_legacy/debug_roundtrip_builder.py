#!/usr/bin/env python3
"""
Build an FDI from three PlayerRecord instances (like the integration test)
and inspect whether the resulting file loads and contains "Zidane".
This script ensures the repository root is on sys.path so it can be run
directly from the project workspace.
"""
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

import struct
import binascii

from app.models import PlayerRecord, FDIHeader, DirectoryEntry
from app.io import FDIFile
from app.xor import decode_entry

def build_and_inspect(tmp_path: Path = Path('.')):
    p1 = PlayerRecord(given_name="David", surname="Beckham", nationality=30, position_primary=3, position_secondary=3, birth_day=2, birth_month=5, birth_year=1975, height=180, weight=75, skills=[50]*10, version=700)
    p2 = PlayerRecord(given_name="Zinedine", surname="Zidane", nationality=3, position_primary=2, position_secondary=2, birth_day=23, birth_month=6, birth_year=1972, height=185, weight=78, skills=[60]*10, version=700)
    p3 = PlayerRecord(given_name="Alan", surname="Shearer", nationality=44, position_primary=3, position_secondary=3, birth_day=13, birth_month=8, birth_year=1970, height=183, weight=80, skills=[55]*10, version=700)

    records = [p1, p2, p3]
    header = FDIHeader(signature=b'DMFIv1.0', record_count=len(records), version=700, max_offset=0, dir_size=len(records)*8)
    dir_bytes = bytearray()
    rec_bytes = bytearray()
    current_offset = 0x20 + header.dir_size
    entries = []
    for i, rec in enumerate(records):
        entry_bytes = rec.to_bytes()
        entry_len = len(entry_bytes)
        dir_entry = DirectoryEntry(offset=current_offset, tag=ord('P'), index=i)
        dir_bytes.extend(dir_entry.to_bytes())
        rec_bytes.extend(entry_bytes)
        entries.append(dir_entry)
        current_offset += entry_len

    header.max_offset = current_offset
    header.record_count = len(records)
    header_bytes = header.to_bytes()
    file_bytes = header_bytes + bytes(dir_bytes) + bytes(rec_bytes)

    out_path = tmp_path / "roundtrip_debug.fdi"
    out_path.write_bytes(file_bytes)
    print("Wrote", out_path, "size", len(file_bytes))

    print("hex[0:200]:", binascii.hexlify(file_bytes[:200]))

    # Load via FDIFile and inspect parsed records
    fdi_file = FDIFile(out_path)
    fdi_file.load()
    print("Loaded records count:", len(fdi_file.records))
    for idx, r in enumerate(fdi_file.records):
        print(f"Record #{idx}: name={getattr(r,'name',None)} given={getattr(r,'given_name',None)} surname={getattr(r,'surname',None)}")
        raw = getattr(r, 'raw_data', None)
        if raw:
            name_end = None
            for i in range(20, min(60, len(raw)-20)):
                if i + 3 < len(raw) and raw[i:i+4] == bytes([0x61, 0x61, 0x61, 0x61]):
                    name_end = i
                    break
            print("  name_end:", name_end)
            if name_end is not None:
                for off in range(name_end, name_end + 16):
                    if off < len(raw):
                        print(f"   off {off}: 0x{raw[off]:02x} decoded {raw[off] ^ 0x61}")
    matches = fdi_file.find_by_name("Zidane")
    print("find_by_name('Zidane') ->", len(matches))
    if matches:
        m = matches[0]
        print(" matched raw len", len(getattr(m, 'raw_data', b'')))
        print(" match name:", getattr(m, 'name', None))

    return out_path

if __name__ == "__main__":
    build_and_inspect(Path.cwd())
