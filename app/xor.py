"""XOR encoding/decoding utilities for PM99 database files.

Implements the encode_entry/decode_entry and string helpers used across the project.
"""

import struct
from typing import Tuple


def decode_entry(data: bytes, offset: int) -> Tuple[bytes, int]:
    """
    Decode a single XOR-encrypted entry from PM99 FDI/PKF format.

    Reproduces the game's simple XOR-0x61 decode used by the project.

    Args:
        data: Raw file bytes
        offset: Starting position (points to uint16 length field)

    Returns:
        Tuple of (decoded_bytes, encoded_length)

    Raises:
        ValueError: If offset is invalid or data is truncated
    """
    if offset < 0 or offset + 2 > len(data):
        raise ValueError(f"Offset 0x{offset:x} outside file bounds")

    # Read little-endian uint16 length
    length = struct.unpack_from("<H", data, offset)[0]
    start = offset + 2
    end = start + length

    if end > len(data):
        raise ValueError(
            f"Entry at 0x{offset:x} (length=0x{length:x}) overruns file"
        )

    # XOR decode (byte-by-byte)
    encoded = data[start:end]
    decoded = bytearray(b ^ 0x61 for b in encoded)

    return bytes(decoded), length


def encode_entry(data: bytes) -> bytes:
    """
    Encode data for PM99 FDI/PKF format (XOR with 0x61).

    Inverse of decode_entry. Prepends uint16 length field.

    Args:
        data: Raw bytes to encode (without length prefix)

    Returns:
        Complete encoded entry: uint16 length + XOR'd data

    Raises:
        ValueError: If data exceeds max uint16 size
    """
    length = len(data)
    if length > 0xFFFF:
        raise ValueError(f"Data too large: {length} bytes (max 65535)")

    # XOR encode
    encoded = bytearray(b ^ 0x61 for b in data)

    # Prepend little-endian uint16 length
    return struct.pack("<H", length) + bytes(encoded)


def read_string(data: bytes, offset: int) -> Tuple[str, int]:
    """
    Read and decode a length-prefixed string from the buffer at `offset`.

    Supports two formats:
      - Raw length-prefixed bytes (2-byte LE length + CP1252 bytes) used inside
        decoded payloads built in-memory.
      - Encoded entry (length-prefixed + XOR'd payload) as stored on-disk.

    The function tries the raw interpretation first and falls back to the encoded
    entry interpretation when necessary. Returns (decoded_text, bytes_consumed).
    """
    if offset + 2 > len(data):
        raise ValueError("Offset out of bounds for read_string")

    # Inspect presumed raw length
    possible_len = struct.unpack_from("<H", data, offset)[0]
    raw_end = offset + 2 + possible_len
    if raw_end <= len(data):
        raw = data[offset + 2:raw_end]
        try:
            text = raw.decode('cp1252')
            # Strip trailing null if present
            if text and text.endswith('\x00'):
                text = text[:-1]
            return text, 2 + possible_len
        except Exception:
            # Fall through to encoded-entry interpretation
            pass

    # Fallback: treat as encoded entry in file-format (length + XOR'd payload)
    decoded, length = decode_entry(data, offset)
    if decoded and decoded[-1] == 0:
        decoded = decoded[:-1]
    try:
        text = decoded.decode('cp1252')
    except UnicodeDecodeError:
        text = decoded.decode('cp1252', errors='replace')
    return text, 2 + length


def write_string(text: str) -> bytes:
    """
    Create a length-prefixed RAW string (CP1252) suitable for inclusion in a
    decoded payload.

    This returns: <uint16 length><raw bytes> (NO XOR). Callers that need the
    on-disk representation should pass the assembled payload to
    `encode_entry()` which will XOR the payload and prepend the file-level
    length prefix.
    """
    raw = text.encode('cp1252')
    return struct.pack("<H", len(raw)) + raw


def pack_string(text: str) -> bytes:
    """
    Return a length-prefixed raw byte sequence (CP1252 encoded) without XOR.
    Use this when constructing decoded payloads that will later be XOR-encoded
    by the caller (e.g. encode_entry()).
    """
    raw = text.encode('cp1252')
    return struct.pack("<H", len(raw)) + raw


# Compatibility aliases (legacy code sometimes uses xor_encode/xor_decode)
def xor_decode(data: bytes, key: int = 0x61) -> bytes:
    """XOR decode entire data block (compatibility helper)"""
    return bytes(b ^ key for b in data)


def xor_encode(data: bytes, key: int = 0x61) -> bytes:
    """XOR encode entire data block (compatibility helper)"""
    return bytes(b ^ key for b in data)