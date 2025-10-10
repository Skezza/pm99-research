"""Tests for the conservative PKF parser."""

import struct
from typing import Iterable, Sequence

import pytest

from pm99_editor.pkf import (
    PKFDecoderError,
    PKFFile,
    PKFStringMatch,
    PKFStringSearcher,
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


def _build_pkf(entries: Sequence[bytes]) -> bytes:
    """Helper to build a simple PKF blob with the given payloads."""

    count = len(entries)
    header = bytearray(struct.pack("<I", count))
    table = bytearray()
    payload = bytearray()
    offset = 4 + count * 8

    for entry in entries:
        table.extend(struct.pack("<II", offset, len(entry)))
        payload.extend(entry)
        offset += len(entry)

    return bytes(header + table + payload)


def test_pkf_string_searcher_accepts_single_string():
    raw = _build_pkf([b"Hello World", b"No matches here"])
    pkf = PKFFile.from_bytes("sample.pkf", raw)
    matches = PKFStringSearcher(pkf).search("hello")

    assert matches
    first = matches[0]
    assert isinstance(first, PKFStringMatch)
    assert first.entry_index == 0
    assert first.match_offset == 0
    assert first.absolute_offset == pkf.get_entry(0).offset


def test_pkf_string_searcher_accepts_list():
    raw = _build_pkf([b"Alpha zone", b"Beta block", b"GammaAlpha"])
    pkf = PKFFile.from_bytes("test.pkf", raw)

    matches = pkf.search_strings(["alpha", "gamma"])

    needles = [(m.entry_index, m.needle, m.match_offset) for m in matches]
    assert needles == [
        (0, "alpha", 0),
        (2, "gamma", 0),
        (2, "alpha", 5),
    ]


def test_pkf_string_searcher_accepts_iterable_and_groups_results():
    raw = _build_pkf([b"alpha", b"gamma", b"alpha alpha"])
    pkf = PKFFile.from_bytes("iterable.pkf", raw)

    needles: Iterable[str] = (needle for needle in ["alpha", "gamma"])
    searcher = PKFStringSearcher(pkf)
    grouped = searcher.search_grouped(needles)

    assert set(grouped) == {"alpha", "gamma"}
    assert [m.absolute_offset for m in grouped["alpha"]] == [pkf.get_entry(0).offset, pkf.get_entry(2).offset, pkf.get_entry(2).offset + 6]
    assert grouped["gamma"][0].entry_index == 1


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
