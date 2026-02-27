#!/usr/bin/env python3
"""
Minimal extractor stub for Premier Manager 99 FDI / TEXTOS entries.

The binary loader (MANAGPRE.EXE.decode_data_xor61 at 0x00677e30) expects each
segment to start with a little-endian uint16 length, followed by `length` bytes
XOR'd with 0x61. This script emulates that routine so we can decode a single
entry straight from disk for validation.

Example:
    python decode_one.py DBDAT/JUG98030.FDI 0x410 --preview
    python decode_one.py DBDAT/TEXTOS.PKF 0x0 --out decoded.bin --hexdump
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path
from typing import Tuple


def decode_data_xor61(blob: bytes, offset: int) -> Tuple[bytes, int]:
    """Return (decoded_bytes_with_terminator, encoded_length)."""
    if offset < 0 or offset + 2 > len(blob):
        raise ValueError(f"Offset 0x{offset:x} outside file bounds ({len(blob)} bytes)")
    length = struct.unpack_from("<H", blob, offset)[0]
    start = offset + 2
    end = start + length
    if end > len(blob):
        raise ValueError(
            f"Encoded segment at 0x{offset:x} (length 0x{length:x}) overruns file"
        )

    encoded = blob[start:end]
    decoded = bytearray(encoded)
    # Apply the same 0x61 XOR used by MANAGPRE.EXE.decode_data_xor61.
    for idx in range(len(decoded)):
        decoded[idx] ^= 0x61

    decoded.append(0)  # match the helper's null terminator write-back
    return bytes(decoded), length


def format_hexdump(data: bytes, limit: int = 128) -> str:
    slices = []
    for i in range(0, min(len(data), limit), 16):
        chunk = data[i : i + 16]
        hexpart = " ".join(f"{b:02x}" for b in chunk)
        asciipart = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        slices.append(f"{i:04x}: {hexpart:<47} {asciipart}")
    return "\n".join(slices)


def parse_offset(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid offset '{value}'") from exc


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Decode a single PM99 FDI/TEXTOS entry (XOR 0x61)."
    )
    parser.add_argument("path", type=Path, help="Input file (e.g., DBDAT/JUG98030.FDI)")
    parser.add_argument(
        "offset",
        type=parse_offset,
        help="Entry start offset (0x-prefixed hex or decimal). Points to the 16-bit length.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional output file for the decoded payload (without the terminal 0x00).",
    )
    parser.add_argument(
        "--hexdump",
        action="store_true",
        help="Print first 128 bytes of encoded/decoded data (like verify.txt).",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Print CP1252 preview of the decoded payload (first 256 bytes).",
    )
    args = parser.parse_args()

    raw = args.path.read_bytes()
    decoded, encoded_len = decode_data_xor61(raw, args.offset)

    print(f"file: {args.path}")
    print(f"offset: 0x{args.offset:06x}")
    print(f"encoded length: 0x{encoded_len:04x} ({encoded_len} bytes)")
    print(f"decoded size (incl. terminator): {len(decoded)} bytes")

    if args.hexdump:
        encoded_slice = raw[args.offset + 2 : args.offset + 2 + encoded_len]
        print("\nencoded first 128")
        print(format_hexdump(encoded_slice))
        print("\ndecoded first 128")
        print(format_hexdump(decoded))

    if args.preview:
        preview = decoded[:-1][:256]  # drop terminator for readability
        try:
            text = preview.decode("cp1252")
        except UnicodeDecodeError:
            text = preview.decode("cp1252", errors="replace")
        print("\nCP1252 preview:")
        print(text)

    if args.out:
        args.out.write_bytes(decoded[:-1])  # strip helper-added 0x00
        print(f"\nDecoded payload written to {args.out}")


if __name__ == "__main__":
    main()