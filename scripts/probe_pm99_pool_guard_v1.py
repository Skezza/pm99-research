#!/usr/bin/env python3
"""Build a disposable null-lookup guard for the observed spare-player crash."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pm99_calendar_patcher import PEImage


def guard(source: bytes) -> bytes:
    image = PEImage(bytearray(source))
    expected = bytes.fromhex("e8 6b f5 ff ff 33 d2 66 8b 90 90 00 00 00")
    if image.read(0x4b7860, len(expected)) != expected:
        raise ValueError("unsupported spare-player count instructions")
    if image.read(0x4b7884, 12) != bytes([0x90] * 12):
        raise ValueError("unsupported spare-player function alignment padding")
    # Preserve the original successful lookup path. A missing player skips
    # only this list entry; the next loop iteration remains unchanged.
    image.write(0x4b7865, bytes.fromhex("eb 1d"))
    image.write(0x4b7884, bytes.fromhex("85 c0 74 eb 33 d2 eb db"))
    return bytes(image.blob)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=lambda value: int(value, 0))
    parser.add_argument("--control", action="store_true", help="Keep the bug; only pin the random seed")
    args = parser.parse_args()
    if args.output.exists() or not args.output.resolve().is_relative_to(ROOT / ".local/crash04-diagnostics-v1"):
        parser.error("requires fresh diagnostic output")
    source = args.source.read_bytes()
    candidate = source if args.control else guard(source)
    if args.seed is not None:
        import struct
        image = PEImage(bytearray(candidate))
        for va in (0x409256, 0x40aa4e):
            if image.read(va, 7) != bytes.fromhex("8d 04 c8 8d 14 40 52"):
                raise ValueError("unsupported random seed call")
            image.write(va, b"\x68" + struct.pack("<I", args.seed) + b"\x90\x90")
        candidate = bytes(image.blob)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    print(json.dumps({"diagnostic_only": True, "source_sha256": hashlib.sha256(source).hexdigest(),
                      "candidate_sha256": hashlib.sha256(candidate).hexdigest()}))
