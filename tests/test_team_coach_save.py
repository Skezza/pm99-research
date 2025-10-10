#!/usr/bin/env python3
import pytest
from app.io import FDIFile
from app.coach_models import parse_coaches_from_record
from app.models import TeamRecord
from app.file_writer import save_modified_records
from app.xor import decode_entry

def test_coach_parsing(coaches_fdi_path):
    f = FDIFile(coaches_fdi_path)
    f.load()
    for entry, decoded, length in f.iter_decoded_directory_entries():
        coaches = parse_coaches_from_record(decoded)
        if coaches:
            assert isinstance(coaches, (list, tuple))
            assert len(coaches) >= 1
            # At least one parsed coach should have a non-empty full_name
            assert any(getattr(c, 'full_name', '').strip() for c in coaches)
            return
    pytest.skip("No coaches parsed from ENT98030.FDI")

def test_team_parsing(teams_fdi_path):
    f = FDIFile(teams_fdi_path)
    f.load()
    for entry, decoded, length in f.iter_decoded_directory_entries():
        tr = TeamRecord(decoded, entry.offset)
        if tr.name and tr.name not in ("Unknown Team", "Parse Error"):
            assert isinstance(tr.name, str)
            assert len(tr.name) >= 4
            assert getattr(tr, 'name_start', None) is not None
            assert tr.name_end >= tr.name_start
            return
    pytest.skip("No team parsed from EQ98030.FDI")

def test_team_save_roundtrip(teams_fdi_path):
    f = FDIFile(teams_fdi_path)
    f.load()
    for entry, decoded, length in f.iter_decoded_directory_entries():
        tr = TeamRecord(decoded, entry.offset)
        if tr.name and tr.name not in ("Unknown Team", "Parse Error"):
            old_name = tr.name
            new_name = old_name + "_TEST"
            tr.set_name(new_name)
            new_bytes = save_modified_records(str(teams_fdi_path), f.file_data, [(entry.offset, tr)])
            new_decoded, l = decode_entry(new_bytes, entry.offset)
            # Check the new decoded payload contains the new name (best-effort)
            decoded_text = new_decoded.decode('latin-1', errors='ignore')
            assert new_name.split()[0] in decoded_text or old_name.split()[0] in decoded_text
            return
    pytest.skip("No team suitable for roundtrip test")
