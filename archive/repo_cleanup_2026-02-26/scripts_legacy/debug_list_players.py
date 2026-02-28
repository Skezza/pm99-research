#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from pathlib import Path
from app.io import FDIFile

def main():
    path = Path("DBDAT/JUG98030.FDI")
    print("Exists:", path.exists())
    if not path.exists():
        sys.exit(1)
    fdi = FDIFile(path)
    fdi.load()
    recs = getattr(fdi, 'records_with_offsets', [(None, r) for r in getattr(fdi, 'records', [])])
    print("Total records found:", len(recs))
    for i, (off, r) in enumerate(recs[:100]):
        display = getattr(r, 'name', None)
        if not display:
            given = getattr(r, 'given_name', '')
            surname = getattr(r, 'surname', '')
            display = f"{given} {surname}".strip()
        raw_len = len(getattr(r, 'raw_data', b''))
        print(f"{i}: offset={hex(off) if off is not None else None} name={display!r} raw_len={raw_len}")
    matches = [r for o, r in recs if ('hierro' in (getattr(r,'name','') or '').lower()) or ('hierro' in (getattr(r,'given_name','') or '').lower()) or ('hierro' in (getattr(r,'surname','') or '').lower())]
    print("Matches for Hierro:", len(matches))
    for m in matches[:10]:
        print(" -", getattr(m, 'name', None))

if __name__ == "__main__":
    main()
