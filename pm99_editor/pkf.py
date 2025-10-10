"""Lightweight PKF container helpers.

This module provides a conservative parser that can discover simple
entry tables inside PKF archives.  It intentionally avoids guessing at
resource-specific payload formats; instead it exposes raw entry bytes and a
registry so specialised decoders can be plugged in incrementally.

The implementation errs on the side of safety: if a PKF file does not match
our supported table layout we fall back to a single-entry representation.
This still lets tooling consume the file without making incorrect
assumptions about its structure, while enabling future improvements once the
format is better understood.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

Decoder = Callable[[bytes], Any]


class PKFDecoderError(RuntimeError):
    """Wrap decoder failures so callers can handle them uniformly."""


@dataclass
class PKFEntry:
    """Metadata wrapper for a single PKF entry."""

    index: int
    offset: int
    length: int
    raw_bytes: bytes
    name: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def preview(self, size: int = 16) -> bytes:
        """Return the first ``size`` bytes for quick inspection."""

        return self.raw_bytes[:size]


class PKFFile:
    """A conservative representation of a PKF container."""

    _decoder_registry: Dict[bytes, Decoder] = {}

    def __init__(
        self,
        name: str,
        raw_bytes: bytes,
        entries: Sequence[PKFEntry],
        *,
        format_hint: str,
    ) -> None:
        self.name = name
        self._raw_bytes = raw_bytes
        self._entries: List[PKFEntry] = list(entries)
        self._format_hint = format_hint
        self._dirty = False

    @property
    def format_hint(self) -> str:
        """Describe how the entries were parsed (e.g. ``toc32`` or ``raw``)."""

        return self._format_hint

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    @classmethod
    def from_bytes(cls, name: str, file_bytes: bytes) -> "PKFFile":
        """Parse raw bytes into a :class:`PKFFile` instance."""

        entries, format_hint = cls._parse_entries(file_bytes)
        return cls(name, file_bytes, entries, format_hint=format_hint)

    @staticmethod
    def _parse_entries(file_bytes: bytes) -> Tuple[List[PKFEntry], str]:
        """Attempt to parse a simple table-of-contents.

        The heuristic currently supports a layout of ``<count><offset><size>``
        triples using 32-bit little-endian integers.  If that check fails we
        gracefully fall back to representing the whole file as a single entry.
        """

        if len(file_bytes) >= 12:  # enough room for count + one entry
            try:
                count = struct.unpack_from("<I", file_bytes, 0)[0]
            except struct.error:
                count = 0
            else:
                table_size = 4 + count * 8
                if 0 < count < 4096 and table_size <= len(file_bytes):
                    entries: List[PKFEntry] = []
                    valid = True
                    for index in range(count):
                        base = 4 + index * 8
                        try:
                            offset, length = struct.unpack_from("<II", file_bytes, base)
                        except struct.error:
                            valid = False
                            break
                        if offset < table_size:
                            valid = False
                            break
                        if offset + length > len(file_bytes):
                            valid = False
                            break
                        raw = file_bytes[offset : offset + length]
                        entries.append(
                            PKFEntry(
                                index=index,
                                offset=offset,
                                length=length,
                                raw_bytes=raw,
                            )
                        )
                    if valid and len(entries) == count:
                        return entries, "toc32"

        # Fallback: treat the entire blob as one entry
        fallback_entry = PKFEntry(
            index=0,
            offset=0,
            length=len(file_bytes),
            raw_bytes=file_bytes,
        )
        return [fallback_entry], "raw"

    # ------------------------------------------------------------------
    # Registry management
    # ------------------------------------------------------------------
    @classmethod
    def register_decoder(cls, magic_prefix: bytes, decoder: Decoder) -> None:
        """Register a payload decoder for entries with ``magic_prefix``."""

        if not magic_prefix:
            raise ValueError("magic_prefix must be non-empty")
        if not callable(decoder):
            raise TypeError("decoder must be callable")
        cls._decoder_registry[magic_prefix] = decoder

    @classmethod
    def unregister_decoder(cls, magic_prefix: bytes) -> None:
        cls._decoder_registry.pop(magic_prefix, None)

    @classmethod
    def clear_decoders(cls) -> None:
        cls._decoder_registry.clear()

    # ------------------------------------------------------------------
    # Entry accessors
    # ------------------------------------------------------------------
    def list_entries(self) -> List[PKFEntry]:
        """Return copies of all entries."""

        return [
            PKFEntry(
                index=entry.index,
                offset=entry.offset,
                length=entry.length,
                raw_bytes=entry.raw_bytes,
                name=entry.name,
                meta=dict(entry.meta),
            )
            for entry in self._entries
        ]

    def get_entry(self, name_or_index: Any) -> PKFEntry:
        """Retrieve an entry by numeric index or optional name."""

        if isinstance(name_or_index, PKFEntry):
            target_index = name_or_index.index
        elif isinstance(name_or_index, int):
            target_index = name_or_index
        elif isinstance(name_or_index, str):
            # allow numeric strings
            if name_or_index.isdigit():
                target_index = int(name_or_index)
            else:
                for entry in self._entries:
                    if entry.name == name_or_index:
                        return PKFEntry(
                            index=entry.index,
                            offset=entry.offset,
                            length=entry.length,
                            raw_bytes=entry.raw_bytes,
                            name=entry.name,
                            meta=dict(entry.meta),
                        )
                raise KeyError(f"No entry named {name_or_index!r}")
        else:
            raise TypeError("name_or_index must be int, str or PKFEntry")

        if not 0 <= target_index < len(self._entries):
            raise IndexError(f"Entry index {target_index} out of range")
        entry = self._entries[target_index]
        return PKFEntry(
            index=entry.index,
            offset=entry.offset,
            length=entry.length,
            raw_bytes=entry.raw_bytes,
            name=entry.name,
            meta=dict(entry.meta),
        )

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------
    def replace_entry(self, name_or_index: Any, new_bytes: bytes) -> None:
        """Replace the payload for an entry."""

        if not isinstance(new_bytes, (bytes, bytearray)):
            raise TypeError("new_bytes must be bytes-like")
        entry_index = self._resolve_index(name_or_index)
        entry = self._entries[entry_index]
        entry.raw_bytes = bytes(new_bytes)
        entry.length = len(new_bytes)
        self._dirty = True

    def _resolve_index(self, name_or_index: Any) -> int:
        if isinstance(name_or_index, int):
            index = name_or_index
        elif isinstance(name_or_index, str) and name_or_index.isdigit():
            index = int(name_or_index)
        elif isinstance(name_or_index, PKFEntry):
            index = name_or_index.index
        else:
            raise TypeError("name_or_index must be an int, numeric str or PKFEntry")
        if not 0 <= index < len(self._entries):
            raise IndexError(f"Entry index {index} out of range")
        return index

    def to_bytes(self) -> bytes:
        """Serialise the file back to bytes."""

        if not self._dirty:
            return self._raw_bytes

        if self._format_hint == "raw":
            if len(self._entries) != 1:
                raise ValueError("raw format only supports a single entry")
            entry = self._entries[0]
            self._raw_bytes = entry.raw_bytes
            entry.offset = 0
            entry.length = len(entry.raw_bytes)
            self._dirty = False
            return self._raw_bytes

        if self._format_hint == "toc32":
            count = len(self._entries)
            header = bytearray(struct.pack("<I", count))
            offset = 4 + count * 8
            payload = bytearray()
            for entry in self._entries:
                data = entry.raw_bytes
                length = len(data)
                header.extend(struct.pack("<II", offset, length))
                payload.extend(data)
                entry.offset = offset
                entry.length = length
                offset += length
            self._raw_bytes = bytes(header + payload)
            self._dirty = False
            return self._raw_bytes

        raise NotImplementedError(f"Unsupported format hint: {self._format_hint}")

    # ------------------------------------------------------------------
    # Decoder helpers
    # ------------------------------------------------------------------
    @classmethod
    def decode_payload(cls, raw_bytes: bytes) -> Any:
        """Attempt to decode raw payload bytes using the registry."""

        # Sort by longest prefix first to allow specific matches
        for magic in sorted(cls._decoder_registry.keys(), key=len, reverse=True):
            if raw_bytes.startswith(magic):
                decoder = cls._decoder_registry[magic]
                try:
                    return decoder(raw_bytes)
                except Exception as exc:  # pragma: no cover - defensive
                    raise PKFDecoderError(str(exc)) from exc
        return raw_bytes

    def decode_entry(self, name_or_index: Any) -> Any:
        """Convenience wrapper around :meth:`decode_payload`."""

        entry = self.get_entry(name_or_index)
        return self.decode_payload(entry.raw_bytes)

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"PKFFile(name={self.name!r}, entries={len(self._entries)}, format={self._format_hint!r})"


__all__ = ["PKFDecoderError", "PKFEntry", "PKFFile"]
