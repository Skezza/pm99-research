#!/usr/bin/env python3
import struct
import pytest

from app.xor import decode_entry, encode_entry, read_string, write_string
from app.models import FDIHeader, DirectoryEntry

SEPARATOR = bytes([0xdd, 0x63, 0x60])

def test_encode_decode_entry_roundtrip():
    payload = b'HELLO' + SEPARATOR + b'WORLD'
    entry = encode_entry(payload)
    data = b'\x00' * 64 + entry + b'\x00'
    decoded, length = decode_entry(data, 64)
    assert decoded == payload
    assert length == len(payload)

def test_decode_entry_bounds():
    # length overruns available bytes
    with pytest.raises(ValueError):
        decode_entry(b'\x05\x00' + b'\x00', 0)
    # invalid offset
    with pytest.raises(ValueError):
        decode_entry(b'\x00\x00', 2)

def test_read_write_string_roundtrip():
    text = "Jose CAÑIZARES"
    entry = write_string(text)
    decoded, consumed = read_string(entry, 0)
    assert decoded == text
    assert consumed == len(entry)

def test_fdi_header_roundtrip():
    header = FDIHeader(signature=b'DMFIv1.0', record_count=123, version=2, max_offset=0x12345678, dir_size=16)
    data = header.to_bytes()
    parsed = FDIHeader.from_bytes(data)
    assert parsed.signature == header.signature
    assert parsed.record_count == header.record_count
    assert parsed.version == header.version
    assert parsed.max_offset == header.max_offset
    assert parsed.dir_size == header.dir_size

def test_fdi_header_invalid_signature():
    bad = bytearray(0x20)
    bad[0:8] = b'BADSIG!!'
    with pytest.raises(ValueError):
        FDIHeader.from_bytes(bytes(bad))

def test_directory_entry_roundtrip():
    entry = DirectoryEntry(offset=0x1000, tag=ord('P'), index=42)
    blob = entry.to_bytes()
    parsed = DirectoryEntry.from_bytes(blob, 0)
    assert parsed.offset == 0x1000
    assert parsed.tag == ord('P')
    assert parsed.index == 42

def test_parse_directory_block():
    header = FDIHeader(signature=b'DMFIv1.0', record_count=2, version=2, max_offset=0x300, dir_size=2*8)
    header_bytes = header.to_bytes()
    e1 = DirectoryEntry(offset=0x100, tag=ord('P'), index=0).to_bytes()
    e2 = DirectoryEntry(offset=0x200, tag=ord('N'), index=1).to_bytes()
    file_bytes = header_bytes + e1 + e2 + b'\x00' * 64
    parsed_header = FDIHeader.from_bytes(file_bytes)
    assert parsed_header.dir_size == 16
    d1 = DirectoryEntry.from_bytes(file_bytes, 0x20)
    d2 = DirectoryEntry.from_bytes(file_bytes, 0x28)
    assert (d1.offset, d1.tag, d1.index) == (0x100, ord('P'), 0)
    assert (d2.offset, d2.tag, d2.index) == (0x200, ord('N'), 1)

def test_decoded_separator_split():
    payload = b'A' * 10 + SEPARATOR + b'B' * 5 + SEPARATOR + b'C' * 3
    entry = encode_entry(payload)
    data = b'\x00' * 128 + entry
    decoded, _ = decode_entry(data, 128)
    parts = decoded.split(SEPARATOR)
    assert len(parts) == 3
    assert parts[0] == b'A' * 10
    assert parts[1] == b'B' * 5
    assert parts[2] == b'C' * 3
# Additional tests: validate dynamic position parsing and attribute decoding
def build_sample_record(name: str, pos_code: int, attributes: list, total_length: int = 80) -> bytes:
    import struct
    # Header: team_id (2) + squad (1) + unknown (2) = 5 bytes
    header = struct.pack("<H", 12) + bytes([7]) + b'\x00\x00'
    name_bytes = name.encode('latin-1')

    # Ensure the name-end marker is found by the parser (marker search starts at index >= 20)
    if len(name_bytes) < 16:
        name_bytes = name_bytes + b' ' * (16 - len(name_bytes))

    marker = bytes([0x61]) * 4
    filler_before_pos = b'\x00' * 3  # bytes between marker and position
    pos_byte = bytes([pos_code ^ 0x61])  # stored encoded position

    core = header + name_bytes + marker + filler_before_pos + pos_byte

    # Attributes live at total_length - 19 .. total_length - 7 (12 bytes)
    attr_start = total_length - 19
    if len(core) > attr_start:
        raise ValueError("Name too long for chosen total_length")

    pre_attr = b'\x00' * (attr_start - len(core))

    if len(attributes) != 12:
        raise ValueError("attributes must be a list of 12 integers")

    attr_encoded = bytes([a ^ 0x61 for a in attributes])
    trailing = b'\x00' * 7  # trailing bytes after attributes

    record = core + pre_attr + attr_encoded + trailing
    assert len(record) == total_length
    return record


def test_player_position_parsing():
    from pm99_database_editor import PlayerRecord

    # Build a canonical 80-byte record with position=3 (Forward)
    attrs = [10] * 12
    rec = build_sample_record("DAVID ROBERT BECK", 3, attrs, total_length=80)
    p = PlayerRecord(rec, 0)

    # Parser should find the 'aaaa' marker and decode position correctly
    assert p.position == 3
    assert p.get_position_name() == "Forward"


def test_player_attributes_parsing():
    from pm99_database_editor import PlayerRecord

    # Varied attribute values (0-99) encoded in the tail of the record
    attrs = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 99, 5]
    rec = build_sample_record("DAVID ROBERT BECK", 1, attrs, total_length=90)
    p = PlayerRecord(rec, 0)

    # Attributes should be decoded and match the supplied list
    assert p.attributes == attrs
