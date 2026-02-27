"""
Structured parser for PM99 `main.dat` save files.

This is intentionally partial but roundtrip-safe:

- the confirmed prefix is parsed into typed fields
- the confirmed full-save prelude is parsed when present
- the unresolved payload is preserved byte-for-byte

That lets us move toward a real parser-backed editor without inventing field
semantics for blocks that are still under reverse engineering.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path


EXPECTED_MAIN_DAT_HEADER = 0x1E
MIN_MAIN_DAT_FORMAT_GUARD = 9
MAIN_DAT_FLAG_COUNT = 10


class MainDatParseError(ValueError):
    """Raised when a `main.dat` payload is truncated or internally inconsistent."""


class _Cursor:
    __slots__ = ("_view", "offset")

    def __init__(self, data: bytes | bytearray | memoryview):
        self._view = memoryview(data)
        self.offset = 0

    def remaining(self) -> int:
        return len(self._view) - self.offset

    def read_bytes(self, size: int) -> bytes:
        if size < 0:
            raise MainDatParseError(f"Negative read size requested: {size}")
        end = self.offset + size
        if end > len(self._view):
            raise MainDatParseError(
                f"Unexpected end of data while reading {size} byte(s) at offset 0x{self.offset:08X}"
            )
        out = self._view[self.offset:end].tobytes()
        self.offset = end
        return out

    def read_u8(self) -> int:
        return self.read_bytes(1)[0]

    def read_u16le(self) -> int:
        return int.from_bytes(self.read_bytes(2), "little")

    def read_u32le(self) -> int:
        return int.from_bytes(self.read_bytes(4), "little")

    def read_to_end(self) -> bytes:
        return self.read_bytes(self.remaining())


def _encode_text(value: str, *, encoding: str = "latin-1") -> bytes:
    try:
        return (value or "").encode(encoding)
    except UnicodeEncodeError as exc:
        raise ValueError(f"Text cannot be encoded as {encoding}: {value!r}") from exc


def _decode_text(value: bytes, *, encoding: str = "latin-1") -> str:
    return value.decode(encoding)


def encode_pm99_u16_xor_string(value: str, *, encoding: str = "latin-1") -> bytes:
    """
    Encode the `FUN_00678350` / `FUN_00677ef0` string format.

    Format:
    - `u16` length
    - `length` bytes, each XOR-obfuscated with `(length + index - 0x40) & 0xFF`
    """

    raw = _encode_text(value, encoding=encoding)
    if len(raw) > 0xFFFF:
        raise ValueError(f"u16 XOR string too long: {len(raw)} byte(s)")

    out = bytearray(len(raw).to_bytes(2, "little"))
    for index, byte in enumerate(raw):
        mask = (len(raw) + index - 0x40) & 0xFF
        out.append(byte ^ mask)
    return bytes(out)


def decode_pm99_u16_xor_string(data: bytes, *, encoding: str = "latin-1") -> str:
    cursor = _Cursor(data)
    return read_pm99_u16_xor_string(cursor, encoding=encoding)


def read_pm99_u16_xor_string(cursor: _Cursor, *, encoding: str = "latin-1") -> str:
    length = cursor.read_u16le()
    raw = bytearray(cursor.read_bytes(length))
    for index, byte in enumerate(raw):
        mask = (length + index - 0x40) & 0xFF
        raw[index] = byte ^ mask
    return _decode_text(bytes(raw), encoding=encoding)


def encode_pm99_u8_xor_string(value: str, *, encoding: str = "latin-1") -> bytes:
    """
    Encode the `FUN_00678270` / `FUN_00677e90` short-string format.

    Format:
    - `u8` length (truncated by the game writer at 0xFF)
    - `length` bytes XORed with `0x61`
    """

    raw = _encode_text(value, encoding=encoding)
    if len(raw) > 0xFF:
        raw = raw[:0xFF]

    out = bytearray([len(raw)])
    for byte in raw:
        out.append(byte ^ 0x61)
    return bytes(out)


def decode_pm99_u8_xor_string(data: bytes, *, encoding: str = "latin-1") -> str:
    cursor = _Cursor(data)
    return read_pm99_u8_xor_string(cursor, encoding=encoding)


def read_pm99_u8_xor_string(cursor: _Cursor, *, encoding: str = "latin-1") -> str:
    length = cursor.read_u8()
    raw = bytearray(cursor.read_bytes(length))
    for index, byte in enumerate(raw):
        raw[index] = byte ^ 0x61
    return _decode_text(bytes(raw), encoding=encoding)


@dataclass(frozen=True)
class PM99PackedDate:
    day: int
    month: int
    year: int

    def to_bytes(self) -> bytes:
        return bytes((self.day & 0xFF, self.month & 0xFF)) + int(self.year).to_bytes(2, "little", signed=False)


def read_pm99_packed_date(cursor: _Cursor) -> PM99PackedDate:
    # The game serializes this as day, month, year (little-endian u16).
    day = cursor.read_u8()
    month = cursor.read_u8()
    year = cursor.read_u16le()
    return PM99PackedDate(day=day, month=month, year=year)


@dataclass(frozen=True)
class PM99MainDatPrefix:
    header_version: int
    format_version: int
    primary_label: str
    secondary_label: str
    save_date: PM99PackedDate
    hour: int
    minute: int
    flag_bytes: tuple[int, ...]
    scalar_byte: int


@dataclass(frozen=True)
class PM99MainDatExtendedPrelude:
    global_byte_a: int
    global_byte_b: int
    secondary_date: PM99PackedDate


@dataclass(frozen=True)
class PM99MainDatFile:
    prefix: PM99MainDatPrefix
    extended_prelude: PM99MainDatExtendedPrelude | None = None
    opaque_tail: bytes = b""
    source_size: int = 0

    @property
    def header_matches_expected(self) -> bool:
        return int(self.prefix.header_version) == EXPECTED_MAIN_DAT_HEADER

    @property
    def format_passes_guard(self) -> bool:
        return int(self.prefix.format_version) >= MIN_MAIN_DAT_FORMAT_GUARD

    @property
    def has_extended_payload(self) -> bool:
        return self.extended_prelude is not None or bool(self.opaque_tail)

    def to_bytes(self) -> bytes:
        out = bytearray()
        out.extend(int(self.prefix.header_version).to_bytes(4, "little", signed=False))
        out.extend(int(self.prefix.format_version).to_bytes(4, "little", signed=False))
        out.extend(encode_pm99_u16_xor_string(self.prefix.primary_label))
        out.extend(encode_pm99_u16_xor_string(self.prefix.secondary_label))
        out.extend(self.prefix.save_date.to_bytes())
        out.append(int(self.prefix.hour) & 0xFF)
        out.append(int(self.prefix.minute) & 0xFF)

        flags = tuple(int(value) & 0xFF for value in self.prefix.flag_bytes)
        if len(flags) != MAIN_DAT_FLAG_COUNT:
            raise ValueError(f"Expected {MAIN_DAT_FLAG_COUNT} flag byte(s), got {len(flags)}")
        out.extend(flags)
        out.append(int(self.prefix.scalar_byte) & 0xFF)

        if self.extended_prelude is not None:
            out.append(int(self.extended_prelude.global_byte_a) & 0xFF)
            out.append(int(self.extended_prelude.global_byte_b) & 0xFF)
            out.extend(self.extended_prelude.secondary_date.to_bytes())

        out.extend(bytes(self.opaque_tail))
        return bytes(out)


def parse_main_dat(data: bytes | bytearray | memoryview) -> PM99MainDatFile:
    cursor = _Cursor(data)

    header_version = cursor.read_u32le()
    format_version = cursor.read_u32le()
    primary_label = read_pm99_u16_xor_string(cursor)
    secondary_label = read_pm99_u16_xor_string(cursor)
    save_date = read_pm99_packed_date(cursor)
    hour = cursor.read_u8()
    minute = cursor.read_u8()
    flag_bytes = tuple(cursor.read_u8() for _ in range(MAIN_DAT_FLAG_COUNT))
    scalar_byte = cursor.read_u8()

    prefix = PM99MainDatPrefix(
        header_version=header_version,
        format_version=format_version,
        primary_label=primary_label,
        secondary_label=secondary_label,
        save_date=save_date,
        hour=hour,
        minute=minute,
        flag_bytes=flag_bytes,
        scalar_byte=scalar_byte,
    )

    extended_prelude = None
    if cursor.remaining() >= 6:
        global_byte_a = cursor.read_u8()
        global_byte_b = cursor.read_u8()
        secondary_date = read_pm99_packed_date(cursor)
        extended_prelude = PM99MainDatExtendedPrelude(
            global_byte_a=global_byte_a,
            global_byte_b=global_byte_b,
            secondary_date=secondary_date,
        )

    opaque_tail = cursor.read_to_end()
    return PM99MainDatFile(
        prefix=prefix,
        extended_prelude=extended_prelude,
        opaque_tail=opaque_tail,
        source_size=len(data),
    )


def load_main_dat(path: str | Path) -> PM99MainDatFile:
    file_path = Path(path)
    return parse_main_dat(file_path.read_bytes())


def save_main_dat(path: str | Path, parsed: PM99MainDatFile) -> Path:
    file_path = Path(path)
    file_path.write_bytes(parsed.to_bytes())
    return file_path


def update_main_dat(
    parsed: PM99MainDatFile,
    *,
    primary_label: str | None = None,
    secondary_label: str | None = None,
    day: int | None = None,
    month: int | None = None,
    year: int | None = None,
    hour: int | None = None,
    minute: int | None = None,
    scalar_byte: int | None = None,
    flag_updates: dict[int, int] | None = None,
) -> PM99MainDatFile:
    """
    Return a copy of `parsed` with confirmed prefix fields updated.

    Unknown tail blocks are preserved byte-for-byte.
    """

    def _require_u8(name: str, value: int) -> int:
        value = int(value)
        if not 0 <= value <= 0xFF:
            raise ValueError(f"{name} must be in range 0..255 (got {value})")
        return value

    def _require_u16(name: str, value: int) -> int:
        value = int(value)
        if not 0 <= value <= 0xFFFF:
            raise ValueError(f"{name} must be in range 0..65535 (got {value})")
        return value

    new_flags = list(parsed.prefix.flag_bytes)
    if len(new_flags) != MAIN_DAT_FLAG_COUNT:
        raise ValueError(f"Expected {MAIN_DAT_FLAG_COUNT} flag byte(s), got {len(new_flags)}")

    if flag_updates:
        for index, value in flag_updates.items():
            idx = int(index)
            if not 0 <= idx < MAIN_DAT_FLAG_COUNT:
                raise ValueError(
                    f"flag index must be in range 0..{MAIN_DAT_FLAG_COUNT - 1} (got {idx})"
                )
            new_flags[idx] = _require_u8(f"flag[{idx}]", value)

    new_date = parsed.prefix.save_date
    if any(value is not None for value in (day, month, year)):
        new_date = replace(
            parsed.prefix.save_date,
            day=_require_u8("day", day) if day is not None else parsed.prefix.save_date.day,
            month=_require_u8("month", month) if month is not None else parsed.prefix.save_date.month,
            year=_require_u16("year", year) if year is not None else parsed.prefix.save_date.year,
        )

    new_prefix = replace(
        parsed.prefix,
        primary_label=parsed.prefix.primary_label if primary_label is None else str(primary_label),
        secondary_label=parsed.prefix.secondary_label if secondary_label is None else str(secondary_label),
        save_date=new_date,
        hour=parsed.prefix.hour if hour is None else _require_u8("hour", hour),
        minute=parsed.prefix.minute if minute is None else _require_u8("minute", minute),
        flag_bytes=tuple(new_flags),
        scalar_byte=parsed.prefix.scalar_byte
        if scalar_byte is None
        else _require_u8("scalar_byte", scalar_byte),
    )

    return replace(parsed, prefix=new_prefix)


__all__ = [
    "EXPECTED_MAIN_DAT_HEADER",
    "MIN_MAIN_DAT_FORMAT_GUARD",
    "MAIN_DAT_FLAG_COUNT",
    "MainDatParseError",
    "PM99PackedDate",
    "PM99MainDatPrefix",
    "PM99MainDatExtendedPrelude",
    "PM99MainDatFile",
    "decode_pm99_u16_xor_string",
    "decode_pm99_u8_xor_string",
    "encode_pm99_u16_xor_string",
    "encode_pm99_u8_xor_string",
    "load_main_dat",
    "parse_main_dat",
    "read_pm99_packed_date",
    "save_main_dat",
    "update_main_dat",
]
