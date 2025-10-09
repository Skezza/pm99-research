#!/usr/bin/env python3
import struct
from pathlib import Path
import pytest

from pm99_editor.file_writer import write_fdi_record
from pm99_editor.models import FDIHeader, DirectoryEntry


def _build_fdi_file(record_payloads):
    """
    Build a minimal FDI bytes blob containing a header, directory and contiguous records.
    record_payloads: list of decoded payload bytes (will be XOR-encoded with 0x61)
    Returns: (file_bytes, list_of_directory_entries)
    """
    header = FDIHeader(signature=b'DMFIv1.0', record_count=len(record_payloads), version=2, max_offset=0, dir_size=len(record_payloads)*8)
    # Placeholder header, will update max_offset after building records
    header_bytes = header.to_bytes()

    dir_bytes = bytearray()
    records_bytes = bytearray()

    current_offset = 0x20 + header.dir_size
    entries = []

    for i, payload in enumerate(record_payloads):
        encoded = bytes(b ^ 0x61 for b in payload)
        rec = struct.pack("<H", len(encoded)) + encoded
        # Create directory entry pointing at current_offset
        entry = DirectoryEntry(offset=current_offset, tag=ord('P'), index=i)
        dir_bytes.extend(entry.to_bytes())
        records_bytes.extend(rec)
        entries.append(entry)
        current_offset += len(rec)

    # Update header.max_offset to end of last record
    header.max_offset = current_offset
    header_bytes = header.to_bytes()

    file_bytes = header_bytes + bytes(dir_bytes) + bytes(records_bytes)
    return bytes(file_bytes), entries


def test_write_fdi_record_same_size(tmp_path):
    # Prepare a three-record FDI where the middle record will be replaced in-place
    payloads = [b'A' * 10, b'B' * 12, b'C' * 8]
    file_bytes, entries = _build_fdi_file(payloads)
    fpath = tmp_path / "test.fdi"
    fpath.write_bytes(file_bytes)

    second_offset = entries[1].offset
    # New payload has same length as old (12 bytes)
    new_payload = b'X' * len(payloads[1])

    ok = write_fdi_record(str(fpath), second_offset, new_payload)
    assert ok, "write_fdi_record failed"

    data = fpath.read_bytes()

    # Verify the payload was updated
    length = struct.unpack_from("<H", data, second_offset)[0]
    payload_enc = data[second_offset + 2: second_offset + 2 + length]
    decoded = bytes(b ^ 0x61 for b in payload_enc)
    assert decoded == new_payload

    # Directory offsets should be unchanged for same-size replacement
    e1 = DirectoryEntry.from_bytes(data, 0x20)
    e2 = DirectoryEntry.from_bytes(data, 0x28)
    e3 = DirectoryEntry.from_bytes(data, 0x30)
    assert e1.offset == entries[0].offset
    assert e2.offset == entries[1].offset
    assert e3.offset == entries[2].offset

    # Backup should be present
    backup = fpath.with_suffix(f"{fpath.suffix}.backup")
    assert backup.exists()


def test_write_fdi_record_expand_shrink(tmp_path):
    # Prepare a three-record FDI where the middle record will be expanded
    payloads = [b'A' * 10, b'B' * 8, b'C' * 6]
    file_bytes, entries = _build_fdi_file(payloads)
    fpath = tmp_path / "test2.fdi"
    fpath.write_bytes(file_bytes)

    second_offset = entries[1].offset

    # Expand the second record by +5 bytes
    new_payload = b'D' * (len(payloads[1]) + 5)

    ok = write_fdi_record(str(fpath), second_offset, new_payload)
    assert ok

    data = fpath.read_bytes()

    # Parse directory entries and confirm offsets after the changed record were adjusted
    e1 = DirectoryEntry.from_bytes(data, 0x20)
    e2 = DirectoryEntry.from_bytes(data, 0x28)
    e3 = DirectoryEntry.from_bytes(data, 0x30)

    old_size = 2 + len(bytes(b ^ 0x61 for b in payloads[1]))
    new_size = 2 + len(bytes(b ^ 0x61 for b in new_payload))
    delta = new_size - old_size

    assert e1.offset == entries[0].offset
    assert e2.offset == entries[1].offset
    # The third record should have moved forward by delta bytes
    assert e3.offset == entries[2].offset + delta

    # Header.max_offset should match end of last record
    header = FDIHeader.from_bytes(data)
    last_off = e3.offset
    last_len = struct.unpack_from("<H", data, last_off)[0]
    assert header.max_offset == last_off + 2 + last_len