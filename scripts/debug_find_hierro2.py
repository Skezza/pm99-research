#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from pm99_editor.io import FDIFile
from pathlib import Path

def main():
    p = Path('DBDAT/JUG98030.FDI')
    if not p.exists():
        print("File missing")
        return 1
    f = FDIFile(p)
    f.load()
    matches = f.find_by_name("Hierro")
    print("find_by_name returned:", len(matches))
    for i, m in enumerate(matches):
        name = getattr(m, 'name', None)
        given = getattr(m, 'given_name', None)
        surname = getattr(m, 'surname', None)
        raw = getattr(m, 'raw_data', None)
        print(i, "name:", name, "given:", given, "surname:", surname, "raw_len:", len(raw) if raw else None)
        if raw:
            marker_pos = None
            for j in range(20, min(60, len(raw)-20)):
                if raw[j:j+4] == bytes([0x61,0x61,0x61,0x61]):
                    marker_pos = j
                    break
            print("  marker_pos:", marker_pos)
            print("  raw preview:", raw[:120])
    # embedded candidates:
    if hasattr(f, '_embedded_candidates'):
        print("embedded candidates:", len(f._embedded_candidates))
        for off, rec in f._embedded_candidates[:10]:
            print("  candidate off", hex(off), "name", getattr(rec,'name',None), "raw_len", len(getattr(rec,'raw_data',b'')))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())