import pytest
from pathlib import Path
from pm99_editor.scanner import find_player_records

def test_find_player_records_returns_non_empty():
    f = Path("DBDAT/JUG98030.FDI")
    assert f.exists(), "Test fixture missing: DBDAT/JUG98030.FDI"
    data = f.read_bytes()
    records = find_player_records(data)
    assert isinstance(records, list)
    assert len(records) > 0, "No records found by scanner"
    # Ensure first few records have names
    for offset, rec in records[:10]:
        assert hasattr(rec, "name")
        assert rec.name and isinstance(rec.name, str)