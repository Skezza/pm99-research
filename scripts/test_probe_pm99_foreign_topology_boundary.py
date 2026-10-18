from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("probe_pm99_foreign_topology_boundary.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("foreign_topology_boundary_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _indexed_file(entries: list[tuple[int, bytes]]) -> bytes:
    """Build the smallest valid indexed DMFI fixture with XOR payloads."""
    directory_size = sum(4 + 1 + len(f"R{record_id}".encode("ascii")) + 8 for record_id, _ in entries)
    payload_offset = 0x14 + directory_size
    directory = bytearray()
    payloads = bytearray()
    for record_id, payload in entries:
        key = f"R{record_id}".encode("ascii")
        encoded = bytes(value ^ 0x61 for value in payload)
        directory += struct.pack("<I", record_id) + bytes((len(key),)) + key
        directory += struct.pack("<II", payload_offset + len(payloads), len(encoded))
        payloads += encoded
    return b"DMFIv1.0" + struct.pack("<III", 0, 0, len(entries)) + directory + payloads


def _write_dbdat(root: Path, *, include_reference: bool) -> None:
    root.mkdir()
    target = 2151
    (root / "EQ98030.FDI").write_bytes(_indexed_file([(target, b"Valletta payload")]))
    jug_payload = b"contains \x67\x08" if include_reference else b"no relation"
    (root / "JUG98030.FDI").write_bytes(_indexed_file([(10, jug_payload)]))
    (root / "ENT98030.FDI").write_bytes(_indexed_file([(20, b"coach payload")]))


def test_collect_reports_directory_but_no_decoded_payload_reference(tmp_path: Path) -> None:
    module = _load_module()
    dbdat = tmp_path / "DBDAT"
    _write_dbdat(dbdat, include_reference=False)

    report = module.collect(dbdat, 2151)

    assert report["result"] == "fixed-carrier-no-payload-membership-reference"
    assert report["decoded_payload_reference_count"] == 0
    assert report["eq_directory_entry"]["record_id"] == 2151
    assert any(item["region"] == "directory" for item in report["files"]["EQ98030.FDI"]["raw_occurrences"])


def test_collect_refuses_to_treat_a_decoded_reference_as_safe(tmp_path: Path) -> None:
    module = _load_module()
    dbdat = tmp_path / "DBDAT"
    _write_dbdat(dbdat, include_reference=True)

    report = module.collect(dbdat, 2151)

    assert report["result"] == "payload-reference-present-investigate-before-writing"
    assert report["decoded_payload_reference_count"] == 1
    assert report["files"]["JUG98030.FDI"]["decoded_payload_occurrences"][0]["record_id"] == 10
