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
    Read and decode a null-terminated XOR-encrypted string.

    Args:
        data: Raw file bytes
        offset: Starting position (points to uint16 length)

    Returns:
        Tuple of (decoded_string, total_bytes_consumed)
    """
    decoded, length = decode_entry(data, offset)

    # Strip null terminator if present
    if decoded and decoded[-1] == 0:
        decoded = decoded[:-1]

    # Decode as Windows-1252 (CP1252)
    try:
        text = decoded.decode('cp1252')
    except UnicodeDecodeError:
        text = decoded.decode('cp1252', errors='replace')

    # Return string and total bytes consumed (2 for length + encoded length)
    return text, 2 + length


def write_string(text: str) -> bytes:
    """
    Encode a string for PM99 format (CP1252 + XOR).

    Args:
        text: String to encode

    Returns:
        Encoded entry with length prefix
    """
    # Encode as Windows-1252
    raw = text.encode('cp1252')

    # Apply XOR and add length prefix
    return encode_entry(raw)


# Compatibility aliases (legacy code sometimes uses xor_encode/xor_decode)
def xor_decode(data: bytes, key: int = 0x61) -> bytes:
    """XOR decode entire data block (compatibility helper)"""
    return bytes(b ^ key for b in data)


def xor_encode(data: bytes, key: int = 0x61) -> bytes:
    """XOR encode entire data block (compatibility helper)"""
    return bytes(b ^ key for b in data)