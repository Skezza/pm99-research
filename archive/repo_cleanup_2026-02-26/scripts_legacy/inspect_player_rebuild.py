#!/usr/bin/env python3
from app.models import PlayerRecord
from app.xor import decode_entry
import binascii, re

def inspect():
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
    dec, _ = decode_entry(enc, 0)
    orig = PlayerRecord.from_bytes(dec, 0, 700)

    orig.set_position(1)
    orig.set_nationality(97)
    orig.set_dob(9,9,1971)
    orig.set_height(178)
    baseline_skills = [80,75,70,65,60,55,50,45,40,35]
    for idx,val in enumerate(baseline_skills):
        orig.set_attribute(idx, val)

    orig.set_name("Manuel Lasa")
    updated_payload = orig.to_bytes()
    s = updated_payload.decode("latin-1", errors="replace")

    print("len updated_payload:", len(updated_payload))
    print("contains 'Manuel':", "Manuel" in s)
    print("contains 'MANUEL':", "MANUEL" in s)
    print("contains 'LASA':", "LASA" in s)
    print("\nfirst 200 chars (decoded):")
    print(s[:200])
    print("\nhex first 200 bytes:")
    print(binascii.hexlify(updated_payload)[:200])

    runs = re.findall(r'[\x20-\x7e]{4,60}', s)
    print("\nprintable runs (first 10):", runs[:10])

if __name__ == '__main__':
    inspect()