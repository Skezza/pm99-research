#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from pathlib import Path
from pm99_editor.io import FDIFile
from pm99_editor.models import PlayerRecord

def main():
    p = Path('DBDAT/JUG98030.FDI')
    print('Exists:', p.exists())
    if not p.exists():
        return 1
    f = FDIFile(p)
    f.load()
    matches = []
    for entry, decoded, length in f.iter_decoded_directory_entries():
        try:
            if b'hierro' in decoded.lower():
                matches.append((entry.offset, entry.tag, len(decoded), decoded))
        except Exception:
            continue

    print('Found in directory entries:', len(matches))
    for off, tag, l, decoded in matches:
        s = decoded.decode('latin-1', errors='replace')
        idx = s.lower().find('hierro')
        start = max(0, idx - 30) if idx >= 0 else 0
        end = min(len(s), idx + 50) if idx >= 0 else len(s)
        snippet = s[start:end]
        print(f'offset=0x{off:x} tag={tag} len={l} snippet={snippet!r}')
        try:
            pr = PlayerRecord.from_bytes(decoded, off)
            print('  PlayerRecord parsed name:', getattr(pr, 'name', None), 'given', getattr(pr, 'given_name', None), 'surname', getattr(pr, 'surname', None))
        except Exception as e:
            print('  parsing error:', e)

    # Also search raw bytes in file
    fb = p.read_bytes()
    raw_matches = []
    needle = b'hierro'
    lb = fb.lower()
    pos = lb.find(needle)
    while pos != -1:
        raw_matches.append(pos)
        pos = lb.find(needle, pos + 1)

    print('Found in raw bytes total:', len(raw_matches))
    for pos in raw_matches[:20]:
        start = max(0, pos - 40)
        end = min(len(fb), pos + 60)
        chunk = fb[start:end]
        print('raw pos', hex(pos), 'ascii snippet:', chunk.decode('latin-1', errors='replace')[:120])

    return 0

if __name__ == "__main__":
    raise SystemExit(main())