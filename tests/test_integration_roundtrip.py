#!/usr/bin/env python3
import struct
from pathlib import Path
import pytest

from app.models import PlayerRecord, FDIHeader, DirectoryEntry
from app.io import FDIFile
from app.file_writer import write_fdi_record
from app.xor import decode_entry


def _build_fdi_from_records(records):
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
    return file_bytes, entries


def test_integration_write_and_reload(tmp_path):
    # Create three player records with realistic fields so the parser can reinstantiate them
    p1 = PlayerRecord(given_name="David", surname="Beckham", nationality=30, position_primary=3, position_secondary=3, birth_day=2, birth_month=5, birth_year=1975, height=180, weight=75, skills=[50]*10, version=700)
    p2 = PlayerRecord(given_name="Zinedine", surname="Zidane", nationality=3, position_primary=2, position_secondary=2, birth_day=23, birth_month=6, birth_year=1972, height=185, weight=78, skills=[60]*10, version=700)
    p3 = PlayerRecord(given_name="Alan", surname="Shearer", nationality=44, position_primary=3, position_secondary=3, birth_day=13, birth_month=8, birth_year=1970, height=183, weight=80, skills=[55]*10, version=700)

    records = [p1, p2, p3]
    fbytes, entries = _build_fdi_from_records(records)

    fpath = tmp_path / "roundtrip_test.fdi"
    fpath.write_bytes(fbytes)

    # Load using FDIFile to ensure file is consumable
    fdi = FDIFile(fpath)
    fdi.load()

    # At least one loaded record should contain 'Zidane' (case-insensitive)
    assert any('ZIDAN' in getattr(r, 'surname', '').upper() or 'ZIDAN' in getattr(r, 'given_name', '').upper() or 'ZIDAN' in getattr(r, 'name', '').upper() for r in fdi.records)

    # Prepare a modified player record (change p2's name)
    new_p2 = PlayerRecord(given_name="Xavier", surname="Hernandez", nationality=8, position_primary=2, position_secondary=2, birth_day=25, birth_month=2, birth_year=1979, height=178, weight=70, skills=[65]*10, version=700)

    # Get decoded payload from the encoded bytes produced by to_bytes()
    encoded_entry = new_p2.to_bytes()
    decoded_payload, _ = decode_entry(encoded_entry, 0)

    # Apply rewrite to second record (use original directory offset)
    second_offset = entries[1].offset
    ok = write_fdi_record(str(fpath), second_offset, decoded_payload)
    assert ok, "write_fdi_record failed"

    # Reload file and verify the new name appears
    fdi2 = FDIFile(fpath)
    fdi2.load()

    assert any('HERNANDEZ' in getattr(r, 'surname', '').upper() or 'HERNANDEZ' in getattr(r, 'name', '').upper() for r in fdi2.records)

    # Ensure record count remains same
    assert len(fdi2.records) == 3


if __name__ == "__main__":
    pytest.main([__file__])
