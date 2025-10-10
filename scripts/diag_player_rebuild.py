#!/usr/bin/env python3
import sys, binascii
sys.path.insert(0, '.')

from app.models import PlayerRecord
from app.xor import decode_entry

def diag():
    base = PlayerRecord(
        given_name="Mikel",
        surname="Lasa",
        team_id=42,
        squad_number=7,
        nationality=34,
        position_primary=1,
        birth_day=9,
        birth_month=9,
        birth_year=1971,
        height=178,
        skills=[80,75,70,65,60,55,50,45,40,35],
        version=700,
    )

    enc = base.to_bytes()
    decoded, _ = decode_entry(enc, 0)
    orig = PlayerRecord.from_bytes(decoded, 0, 700)

    print("orig.raw_data is None:", orig.raw_data is None)
    if orig.raw_data:
        print("orig.raw_data len:", len(orig.raw_data))
        print("orig.raw_data hex[:80]:", binascii.hexlify(orig.raw_data[:80]).decode())
        print("orig.raw_data contains 'Mikel':", b"Mikel" in orig.raw_data)
    print("orig.name:", getattr(orig, 'name', None))
    print("orig.given_name, surname:", orig.given_name, orig.surname)
    print("orig.name_dirty:", getattr(orig, 'name_dirty', None))
    print("calling set_name...")
    orig.set_name("Manuel Lasa")
    print("after set_name name_dirty:", getattr(orig, 'name_dirty', None))
    print("after set_name raw_data is None:", orig.raw_data is None)
    if orig.raw_data:
        print("new raw_data len:", len(orig.raw_data))
        print("new raw_data hex[:200]:", binascii.hexlify(orig.raw_data[:200]).decode())
        try:
            s = orig.raw_data.decode('latin-1', errors='replace')
            print("new raw_data decoded (first200):", s[:200])
        except Exception as e:
            print("decode raw error", e)

    updated = orig.to_bytes()
    print("updated len:", len(updated))
    if len(updated) >= 2:
        lp = int.from_bytes(updated[:2], 'little')
        print("length prefix:", lp, "len-2:", len(updated)-2)
        print("starts with prefix? ", lp == len(updated)-2)
    try:
        s2 = updated.decode('latin-1', errors='replace')
        print("updated decoded (first200):", s2[:200])
        print("'Manuel' in updated decoded?", "Manuel" in s2, "'LASA' in updated decoded?", "LASA" in s2)
    except Exception as e:
        print("can't decode updated", e)
    print("hex updated[:200]:", binascii.hexlify(updated)[:400])

if __name__ == '__main__':
    diag()