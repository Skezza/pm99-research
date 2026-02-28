"""Binary-backed parser for DMFIv1.0 indexed FDI containers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import List

from app.xor import xor_decode

_FDI_SIGNATURE = b"DMFIv1.0"
_FDI_INDEX_START = 0x14


@dataclass(frozen=True)
class IndexedFDIEntry:
    """One indexed payload entry in a DMFI container."""

    record_id: int
    key: str
    payload_offset: int
    payload_length: int
    index_offset: int

    def decode_payload(self, file_bytes: bytes) -> bytes:
        """Return the XOR-decoded payload bytes for this entry."""
        end = self.payload_offset + self.payload_length
        if self.payload_offset < 0 or end > len(file_bytes):
            raise ValueError(
                f"Indexed payload 0x{self.payload_offset:x}+0x{self.payload_length:x} is outside file bounds"
            )
        return xor_decode(file_bytes[self.payload_offset:end])


@dataclass(frozen=True)
class IndexedFDIFile:
    """Parsed DMFIv1.0 file using the DBASEPRE.EXE indexed container layout."""

    reserved_a: int
    reserved_b: int
    record_count: int
    entries: List[IndexedFDIEntry]
    index_end_offset: int

    @classmethod
    def from_bytes(cls, data: bytes) -> "IndexedFDIFile":
        """Parse a DMFIv1.0 file whose payloads are addressed by an inline index."""
        if len(data) < _FDI_INDEX_START:
            raise ValueError("File too small for indexed FDI header")
        if data[:8] != _FDI_SIGNATURE:
            raise ValueError(f"Invalid indexed FDI signature: {data[:8]!r}")

        reserved_a = struct.unpack_from("<I", data, 0x08)[0]
        reserved_b = struct.unpack_from("<I", data, 0x0C)[0]
        record_count = struct.unpack_from("<I", data, 0x10)[0]

        entries: List[IndexedFDIEntry] = []
        pos = _FDI_INDEX_START
        for _ in range(record_count):
            index_offset = pos
            if pos + 9 > len(data):
                raise ValueError(f"Truncated indexed FDI directory entry at 0x{pos:x}")

            record_id = struct.unpack_from("<I", data, pos)[0]
            pos += 4

            key_length = data[pos]
            pos += 1
            if pos + key_length + 8 > len(data):
                raise ValueError(
                    f"Indexed FDI entry 0x{index_offset:x} overruns file (key length {key_length})"
                )

            key_bytes = data[pos : pos + key_length]
            pos += key_length
            payload_offset = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            payload_length = struct.unpack_from("<I", data, pos)[0]
            pos += 4

            end = payload_offset + payload_length
            if payload_offset < 0 or end > len(data):
                raise ValueError(
                    f"Indexed payload for record {record_id} points outside file "
                    f"(0x{payload_offset:x}+0x{payload_length:x})"
                )

            try:
                key = key_bytes.decode("cp1252")
            except UnicodeDecodeError:
                key = key_bytes.decode("cp1252", errors="replace")

            entries.append(
                IndexedFDIEntry(
                    record_id=record_id,
                    key=key,
                    payload_offset=payload_offset,
                    payload_length=payload_length,
                    index_offset=index_offset,
                )
            )

        return cls(
            reserved_a=reserved_a,
            reserved_b=reserved_b,
            record_count=record_count,
            entries=entries,
            index_end_offset=pos,
        )

    @classmethod
    def from_path(cls, file_path: str | Path) -> "IndexedFDIFile":
        """Load and parse an indexed FDI file from disk."""
        return cls.from_bytes(Path(file_path).read_bytes())
