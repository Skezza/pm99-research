import struct

import pytest
from pathlib import Path

from pm99_editor.scanner import find_player_records, PlayerScanError


@pytest.mark.skipif(
    not Path("DBDAT/JUG98030.FDI").exists(),
    reason="Fixture DBDAT/JUG98030.FDI not available",
)

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


def test_find_player_records_strict_mode_surfaces_parse_errors(monkeypatch):
    from pm99_editor import scanner

    def boom(cls, data: bytes, offset: int):
        raise ValueError("boom")

    monkeypatch.setattr(scanner.PlayerRecord, "from_bytes", classmethod(boom))

    length = 1100
    buffer = bytearray(b"\x00" * (0x400 + 2 + length + 16))
    struct.pack_into("<H", buffer, 0x400, length)

    separator = bytes([0xdd, 0x63, 0x60])
    part = bytearray(b"\x00" * 80)
    part[10:14] = b"\x61\x61\x61\x61"
    decoded = bytearray(b"\x00" * length)
    start = 40
    decoded[start : start + len(separator)] = separator
    decoded[start + len(separator) : start + len(separator) + len(part)] = part
    decoded[start + len(separator) + len(part) : start + len(separator) * 2 + len(part)] = separator
    encoded = bytes(b ^ 0x61 for b in decoded)
    buffer[0x402 : 0x402 + length] = encoded

    with pytest.raises(PlayerScanError) as excinfo:
        find_player_records(bytes(buffer))

    assert excinfo.value.issues


def test_find_player_records_quarantine_collects_issues(monkeypatch):
    from pm99_editor import scanner

    def boom(cls, data: bytes, offset: int):
        raise ValueError("boom")

    monkeypatch.setattr(scanner.PlayerRecord, "from_bytes", classmethod(boom))

    length = 1100
    buffer = bytearray(b"\x00" * (0x400 + 2 + length + 16))
    struct.pack_into("<H", buffer, 0x400, length)

    separator = bytes([0xdd, 0x63, 0x60])
    part = bytearray(b"\x00" * 80)
    part[10:14] = b"\x61\x61\x61\x61"
    decoded = bytearray(b"\x00" * length)
    start = 40
    decoded[start : start + len(separator)] = separator
    decoded[start + len(separator) : start + len(separator) + len(part)] = part
    decoded[start + len(separator) + len(part) : start + len(separator) * 2 + len(part)] = separator
    encoded = bytes(b ^ 0x61 for b in decoded)
    buffer[0x402 : 0x402 + length] = encoded

    quarantine = []
    records = find_player_records(bytes(buffer), strict=False, quarantine=quarantine)

    assert records == []
    assert quarantine


def test_find_player_records_extracts_separated_chunks(monkeypatch):
    from pm99_editor import scanner

    class DummyPlayer:
        def __init__(self, name: str):
            self.name = name
            self.team_id = 123
            self.attributes = [50] * 12
            self.position = 1
            self.suppressed = True
            self.confidence = 0

    def fake_from_bytes(cls, data: bytes, offset: int):
        return DummyPlayer("Test Player")

    monkeypatch.setattr(
        scanner.PlayerRecord, "from_bytes", classmethod(fake_from_bytes)
    )

    length = 1200
    buffer = bytearray(b"\x00" * (0x400 + 2 + length + 16))
    struct.pack_into("<H", buffer, 0x400, length)

    separator = bytes([0xdd, 0x63, 0x60])
    part = bytearray(b"\x00" * 80)
    part[10:14] = b"\x61\x61\x61\x61"

    decoded = bytearray(b"\x00" * length)
    start = 100
    decoded[start : start + len(separator)] = separator
    decoded[
        start + len(separator) : start + len(separator) + len(part)
    ] = part
    decoded[
        start + len(separator) + len(part) : start + len(separator) * 2 + len(part)
    ] = separator

    encoded = bytes(b ^ 0x61 for b in decoded)
    buffer[0x402 : 0x402 + length] = encoded

    records = find_player_records(bytes(buffer))

    assert len(records) == 1
    offset, record = records[0]
    assert isinstance(record, DummyPlayer)
    assert record.name == "Test Player"
    assert record.confidence == 95
    assert record.suppressed is False
    assert offset >= 0x400
