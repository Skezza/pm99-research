"""Tests for the conservative PKF parser."""

import struct
from pathlib import Path
from typing import Iterable, Sequence

import pytest

from app.pkf import (
    ArchiveStringMatch,
    ArchiveStringSearcher,
    PKFDecoderError,
    PKFFile,
    PKFStringMatch,
    PKFStringSearcher,
)
from app.models import FDIHeader
from app.xor import encode_entry


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


def _build_fdi(entries: Sequence[bytes]) -> bytes:
    """Create a minimal FDI image with provided decoded payloads."""

    header = FDIHeader(record_count=len(entries), version=2, max_offset=0, dir_size=len(entries) * 8)
    header_bytes = header.to_bytes()
    directory = bytearray()
    payload = bytearray()
    offset = len(header_bytes) + len(entries) * 8

    for idx, decoded in enumerate(entries):
        encoded = encode_entry(decoded)
        directory.extend(struct.pack("<IHH", offset, ord("P"), idx))
        payload.extend(encoded)
        offset += len(encoded)

    return header_bytes + bytes(directory) + bytes(payload)


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


def test_archive_string_searcher_scans_pkf_and_fdi(tmp_path: Path):
    pkf_path = tmp_path / "sample.pkf"
    pkf_path.write_bytes(_build_pkf([b"Alpha hero", b"Beta block"]))

    fdi_path = tmp_path / "sample.fdi"
    fdi_path.write_bytes(_build_fdi([b"Coach Alpha", b"Club Beta"]))

    searcher = ArchiveStringSearcher(case_sensitive=False)
    matches = searcher.search([tmp_path], ["alpha", "beta"])

    assert matches  # ensure we found something
    pkf_hits = [m for m in matches if m.path == pkf_path]
    fdi_hits = [m for m in matches if m.path == fdi_path]

    assert any(m.file_type == "PKF" and m.needle == "alpha" for m in pkf_hits)
    assert any(m.file_type == "PKF" and m.needle == "beta" for m in pkf_hits)
    assert any(m.file_type == "FDI" and m.needle == "alpha" for m in fdi_hits)
    assert any(m.file_type == "FDI" and m.needle == "beta" for m in fdi_hits)

    grouped = searcher.search_grouped([tmp_path], ["alpha", "beta"])
    assert set(grouped) == {"alpha", "beta"}
    assert all(isinstance(m, ArchiveStringMatch) for group in grouped.values() for m in group)


def test_archive_string_searcher_records_missing_paths(tmp_path: Path):
    searcher = ArchiveStringSearcher()
    missing = tmp_path / "does_not_exist"
    matches = searcher.search([missing], "alpha")

    assert matches == []
    assert searcher.errors and searcher.errors[0][0] == missing

