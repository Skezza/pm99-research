"""Tests for the conservative PKF parser."""

import struct

import pytest

from pm99_editor.pkf import PKFDecoderError, PKFFile


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


def test_replace_entry_roundtrip_for_toc32():
    raw = build_toc32_pkf([b"foo", b"bar"])
    pkf = PKFFile.from_bytes("test.pkf", raw)

    pkf.replace_entry(1, b"baz")
    rebuilt = pkf.to_bytes()

    reparsed = PKFFile.from_bytes("test.pkf", rebuilt)
    assert reparsed.get_entry(1).raw_bytes == b"baz"
    # First entry should remain untouched
    assert reparsed.get_entry(0).raw_bytes == b"foo"


def test_fallback_single_entry_and_replace():
    raw = b"no table present"
    pkf = PKFFile.from_bytes("raw.pkf", raw)

    assert len(pkf) == 1
    assert pkf.get_entry(0).raw_bytes == raw

    pkf.replace_entry(0, b"changed")
    assert pkf.to_bytes() == b"changed"


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
