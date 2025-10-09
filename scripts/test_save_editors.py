#!/usr/bin/env python3
# Ensure package imports work when running as a script
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
"""
Test save for coach and team records using in-memory save_modified_records.
"""
from pathlib import Path
from pm99_editor.io import FDIFile
from pm99_editor.coach_models import parse_coaches_from_record, EditableCoachRecord
from pm99_editor.models import TeamRecord
from pm99_editor.file_writer import save_modified_records
import traceback
import sys

def test_coach():
    fp = 'DBDAT/ENT98030.FDI'
    data = Path(fp).read_bytes()
    f = FDIFile(fp)
    f.load()
    for entry, decoded, length in f.iter_decoded_directory_entries():
        coaches = parse_coaches_from_record(decoded)
        if not coaches:
            continue
        c = coaches[0]
        editable = EditableCoachRecord(decoded, entry.offset, getattr(c, 'given_name', ''), getattr(c, 'surname', ''))
        new_given = (editable.given_name or "Coach") + '_X'
        editable.set_name(new_given, editable.surname)
        new_bytes = save_modified_records(fp, data, [(entry.offset, editable)])
        print("COACH UPDATED:", fp, "offset", hex(entry.offset), "orig_len", len(data), "new_len", len(new_bytes), "delta", len(new_bytes)-len(data))
        return True
    print("NO COACH MATCH")
    return False

def test_team():
    fp = 'DBDAT/EQ98030.FDI'
    data = Path(fp).read_bytes()
    f = FDIFile(fp)
    f.load()
    for entry, decoded, length in f.iter_decoded_directory_entries():
        tr = TeamRecord(decoded, entry.offset)
        if tr.name and tr.name not in ("Unknown Team", "Parse Error"):
            try:
                oldname = tr.name
                newname = oldname + "_X"
                tr.set_name(newname)
                new_bytes = save_modified_records(fp, data, [(entry.offset, tr)])
                print("TEAM UPDATED:", fp, "offset", hex(entry.offset), "oldname", oldname, "new_len", len(new_bytes), "delta", len(new_bytes)-len(data))
                return True
            except Exception as e:
                print("TEAM MODIFY FAILED", e)
                traceback.print_exc()
                return False
    print("NO TEAM MATCH")
    return False

def main():
    ok1 = False
    ok2 = False
    try:
        ok1 = test_coach()
    except Exception:
        print("COACH TEST EXCEPTION")
        traceback.print_exc()
    try:
        ok2 = test_team()
    except Exception:
        print("TEAM TEST EXCEPTION")
        traceback.print_exc()
    sys.exit(0 if (ok1 and ok2) else 2)

if __name__ == '__main__':
    main()