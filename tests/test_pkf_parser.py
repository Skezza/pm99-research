"""Tests for the conservative PKF parser."""

import json
import struct

import pytest

from pm99_editor.pkf import (
    PKFDecoderError,
    PKFEntryKind,
    PKFFile,
    PKFTableValidationError,
)


def build_toc32_pkf(chunks):
    count = len(chunks)
    header = bytearray(struct.pack("<I", count))
    offset = 4 + count * 8
    payload = bytearray()
    for chunk in chunks:
        data = bytes(chunk)
        header.extend(struct.pack("<II", offset, len(data)))
        payload.extend(data)
        offset += len(data)
    return bytes(header + payload)


def test_parse_simple_table_of_contents():
    raw = build_toc32_pkf([b"ABC", b"DEFG", b"HI"])
    pkf = PKFFile.from_bytes("sample.pkf", raw)

    entries = pkf.list_entries()
    assert len(entries) == 3
    assert entries[0].raw_bytes == b"ABC"
    assert entries[1].offset > entries[0].offset
    assert entries[2].length == 2
    assert entries[0].kind == PKFEntryKind.STRING_TABLE


def test_replace_entry_roundtrip_for_toc32():
    raw = build_toc32_pkf([b"foo", b"bar"])
    pkf = PKFFile.from_bytes("test.pkf", raw)

    pkf.replace_entry(1, b"baz")
    rebuilt = pkf.to_bytes()

    reparsed = PKFFile.from_bytes("test.pkf", rebuilt)
    assert reparsed.get_entry(1).raw_bytes == b"baz"
    # First entry should remain untouched
    assert reparsed.get_entry(0).raw_bytes == b"foo"


def test_raw_fallback_requires_opt_in():
    raw = b"no table present"
    with pytest.raises(PKFTableValidationError):
        PKFFile.from_bytes("raw.pkf", raw)

    pkf = PKFFile.from_bytes(
        "raw.pkf", raw, strict=False, allow_raw_fallback=True
    )

    assert len(pkf) == 1
    assert pkf.get_entry(0).raw_bytes == raw

    pkf.replace_entry(0, b"changed")
    assert pkf.to_bytes() == b"changed"


def test_parse_detects_non_contiguous_payload():
    # Build a PKF blob with two entries and an unexpected gap between them.
    table_size = 4 + 2 * 8
    total_size = table_size + 4 + 4 + 6  # include a gap before the second payload
    raw = bytearray(total_size)

    struct.pack_into("<I", raw, 0, 2)  # entry count
    struct.pack_into("<II", raw, 4, table_size, 4)  # first entry (contiguous)
    struct.pack_into("<II", raw, 12, table_size + 10, 4)  # second entry starts late

    raw[table_size : table_size + 4] = b"AAAA"
    raw[table_size + 10 : table_size + 14] = b"BBBB"

    with pytest.raises(PKFTableValidationError) as excinfo:
        PKFFile.from_bytes("gap.pkf", bytes(raw))

    assert "expected 0x" in str(excinfo.value)


def test_decoder_registry():
    PKFFile.clear_decoders()

    def decoder(data: bytes) -> str:
        return data.decode("ascii")

    PKFFile.register_decoder(b"TXT", decoder)

    raw = build_toc32_pkf([b"TXTpayload", b"BINARY"])
    pkf = PKFFile.from_bytes("sample.pkf", raw)

    assert pkf.decode_entry(0) == "TXTpayload"
    # Second entry should fall back to raw bytes
    assert pkf.decode_entry(1) == b"BINARY"

    # Decoder errors should be wrapped
    def bad_decoder(data: bytes):
        raise ValueError("boom")

    PKFFile.register_decoder(b"BAD", bad_decoder)
    with pytest.raises(PKFDecoderError):
        PKFFile.decode_payload(b"BADxxx")

    PKFFile.clear_decoders()


def test_validation_failures_are_logged(tmp_path, monkeypatch):
    monkeypatch.setenv("PM99_DIAGNOSTICS_DIR", str(tmp_path))

    raw = bytearray(12)
    struct.pack_into("<I", raw, 0, 1)
    struct.pack_into("<II", raw, 4, 4, 0)

    with pytest.raises(PKFTableValidationError):
        PKFFile.from_bytes("broken.pkf", bytes(raw))

    log_path = tmp_path / "pkf_table_validation.log"
    assert log_path.exists()

    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line]
    assert lines
    entry = json.loads(lines[-1])
    assert entry["kind"] == "pkf_table_validation"
    assert entry["details"]["file"] == "broken.pkf"
    assert entry["details"]["issues"]
