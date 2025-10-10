import pytest
from app.scanner import find_player_records

def test_find_player_records_returns_non_empty(players_fdi_path):
    data = players_fdi_path.read_bytes()
    records = find_player_records(data)
    assert isinstance(records, list)
    assert len(records) > 0, "No records found by scanner"
    # Ensure first few records have names
    for offset, rec in records[:10]:
        assert hasattr(rec, "name")
        assert rec.name and isinstance(rec.name, str)
