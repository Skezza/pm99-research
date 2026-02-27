#!/usr/bin/env python3
from pathlib import Path
import sys
# Ensure repository root is on sys.path so scripts can import package modules when run directly
root = Path(__file__).resolve().parents[1]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from app.io import FDIFile
import binascii

def inspect():
    f = Path("DBDAT/JUG98030.FDI")
    if not f.exists():
        print("MISSING", f)
        return
    fdi = FDIFile(f)
    fdi.load()
    matches = fdi.find_by_name("Hierro")
    print("matches count:", len(matches))
    if not matches:
        print("No matches in find_by_name.")
        return
    hierro = matches[0]
    raw = getattr(hierro, "raw_data", None)
    print("raw len:", len(raw) if raw else None)
    if raw is None:
        print("no raw_data")
        return
    # find name_end
    name_end = None
    for i in range(20, min(60, len(raw)-20)):
        if i + 3 < len(raw) and raw[i:i+4] == bytes([0x61,0x61,0x61,0x61]):
            name_end = i
            break
    print("name_end:", name_end)
    if name_end is None:
        print("no marker")
    else:
        for off in range(name_end, name_end+20):
            if off < len(raw):
                b = raw[off]
                print(f"off {off}: 0x{b:02x} -> decoded {b ^ 0x61}")
        # dump hex around name region
        start = max(0, name_end-10)
        end = min(len(raw), name_end+30)
        print("hex around name:", binascii.hexlify(raw[start:end]))
    # print full raw hex snippet
    print("raw (first 120):", binascii.hexlify(raw[:120]))
    print("record repr:", repr(hierro))

if __name__ == '__main__':
    inspect()
