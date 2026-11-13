#!/usr/bin/env python3
"""Add a diagnostic DLL import to a disposable EXE; never a release patch."""
try:
    from scripts import json_storage_io_v1 as storage_io
except ModuleNotFoundError:
    import sys as _storage_sys
    from pathlib import Path as _StoragePath
    _storage_sys.path.insert(0, str(next(p for p in _StoragePath(__file__).resolve().parents if (p / 'scripts/json_storage_io_v1.py').is_file())))
    from scripts import json_storage_io_v1 as storage_io

import argparse
import hashlib
import json
from pathlib import Path
import struct


def add_import(source: bytes) -> bytes:
    blob = bytearray(source)
    pe = struct.unpack_from("<I", blob, 0x3c)[0]
    if blob[pe:pe + 4] != b"PE\0\0":
        raise ValueError("not a PE executable")
    count, optional_size = struct.unpack_from("<H12xH", blob, pe + 6)
    optional = pe + 24
    if struct.unpack_from("<H", blob, optional)[0] != 0x10b:
        raise ValueError("requires PE32")
    section_alignment, file_alignment = struct.unpack_from("<II", blob, optional + 32)
    sections = optional + optional_size
    rows = [struct.unpack_from("<8sIIII16x", blob, sections + i * 40) for i in range(count)]
    def offset(rva):
        for _, size, va, raw_size, raw in rows:
            if va <= rva < va + max(size, raw_size):
                return raw + rva - va
        raise ValueError("RVA outside section")
    if sections + (count + 1) * 40 > min(row[4] for row in rows):
        raise ValueError("no room for diagnostic section header")
    import_rva = struct.unpack_from("<I", blob, optional + 104)[0]
    cursor = offset(import_rva)
    descriptors = bytearray()
    while any(blob[cursor:cursor + 20]):
        descriptors.extend(blob[cursor:cursor + 20])
        cursor += 20
    align = lambda value, multiple: (value + multiple - 1) // multiple * multiple
    va = align(max(row[2] + max(row[1], row[3]) for row in rows), section_alignment)
    raw = align(len(blob), file_alignment)
    data = descriptors + bytes(40)
    names = len(data)
    data.extend(b"ddraw.dll\0")
    symbol = len(data)
    data.extend(b"\0\0DirectDrawCreate\0")
    data.extend(bytes((-len(data)) % 4))
    thunk = len(data)
    data.extend(struct.pack("<II", va + symbol, 0))
    iat = len(data)
    data.extend(struct.pack("<II", va + symbol, 0))
    struct.pack_into("<IIIII", data, len(descriptors), va + thunk, 0, 0, va + names, va + iat)
    raw_size = align(len(data), file_alignment)
    struct.pack_into("<8sIIIIIIHHI", blob, sections + count * 40,
                     b".trace\0\0", len(data), va, raw_size, raw, 0, 0, 0, 0, 0xc0000040)
    struct.pack_into("<H", blob, pe + 6, count + 1)
    struct.pack_into("<I", blob, optional + 56, align(va + len(data), section_alignment))
    struct.pack_into("<II", blob, optional + 104, va, len(descriptors) + 40)
    blob.extend(bytes(raw - len(blob)))
    blob.extend(data + bytes(raw_size - len(data)))
    return bytes(blob)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = storage_io.resolve(Path(__file__)).parents[1] / ".local/crash04-diagnostics-v1"
    if not storage_io.resolve(args.output).is_relative_to(root) or storage_io.exists(args.output):
        parser.error("requires a fresh output within the crash diagnostics directory")
    source = storage_io.read_bytes(args.source)
    candidate = add_import(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    storage_io.write_bytes(args.output, candidate)
    print(json.dumps({"diagnostic_only": True, "source_sha256": hashlib.sha256(source).hexdigest(),
                      "output_sha256": hashlib.sha256(candidate).hexdigest()}))
