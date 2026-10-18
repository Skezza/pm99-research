#!/usr/bin/env python3
"""Create a byte-minimal, receipt-backed mode-0 finance probe EQ file.

This is deliberately narrower than the editor's team-edit command.  It exists
for controlled runtime experiments where only the two already-traced opening
finance integers may change.  The source EQ file is never modified in place.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.eq_team_indexed_metadata import (  # noqa: E402
    extract_indexed_team_payload_metadata,
    patch_indexed_team_mode0_starting_finance,
)
from app.fdi_indexed import IndexedFDIFile  # noqa: E402


SCHEMA = "pm99-byte-minimal-mode0-finance-probe-v1"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-eq", required=True, type=Path)
    parser.add_argument("--output-eq", required=True, type=Path)
    parser.add_argument("--carrier-id", required=True, type=int)
    parser.add_argument("--finance", required=True, type=int)
    parser.add_argument("--receipt", required=True, type=Path)
    return parser.parse_args()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = _parse_args()
    source_path = args.source_eq.resolve()
    output_path = args.output_eq.resolve()
    receipt_path = args.receipt.resolve()
    if source_path == output_path:
        raise SystemExit("--output-eq must differ from --source-eq; probes never write in place")
    if not source_path.is_file():
        raise SystemExit(f"source EQ file is missing: {source_path}")

    original = source_path.read_bytes()
    indexed = IndexedFDIFile.from_bytes(original)
    entries = {entry.record_id: entry for entry in indexed.entries}
    entry = entries.get(int(args.carrier_id))
    if entry is None:
        raise SystemExit(f"carrier {args.carrier_id} is absent from {source_path}")
    original_payload = original[entry.payload_offset : entry.payload_offset + entry.payload_length]
    before = extract_indexed_team_payload_metadata(original_payload)
    patched_payload = patch_indexed_team_mode0_starting_finance(original_payload, int(args.finance))
    after = extract_indexed_team_payload_metadata(patched_payload)
    if len(patched_payload) != len(original_payload):
        raise SystemExit("finance probe unexpectedly changed the payload length")

    lane_offsets = [
        before.get("dbasepre_mode0_budget_raw_offset"),
        before.get("dbasepre_mode0_finance_aux_raw_offset"),
    ]
    if any(not isinstance(offset, int) for offset in lane_offsets):
        raise SystemExit("carrier has no parser-backed mode-0 finance lane")
    expected_offsets = {
        entry.payload_offset + int(offset) + byte_index
        for offset in lane_offsets
        for byte_index in range(4)
    }
    patched = bytearray(original)
    patched[entry.payload_offset : entry.payload_offset + entry.payload_length] = patched_payload
    changed_offsets = [index for index, (old, new) in enumerate(zip(original, patched)) if old != new]
    unexpected_offsets = [offset for offset in changed_offsets if offset not in expected_offsets]
    if unexpected_offsets:
        raise SystemExit(f"finance probe changed an unexpected byte at 0x{unexpected_offsets[0]:x}")
    if not changed_offsets:
        raise SystemExit("finance probe did not change any bytes")
    reparsed = extract_indexed_team_payload_metadata(
        bytes(patched[entry.payload_offset : entry.payload_offset + entry.payload_length])
    )
    if int(reparsed["dbasepre_mode0_finance_display_currency"]) != int(args.finance):
        raise SystemExit("patched finance did not reparse to the requested display amount")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(bytes(patched))
    _write_json(
        receipt_path,
        {
            "schema": SCHEMA,
            "source_eq": str(source_path),
            "output_eq": str(output_path),
            "carrier_id": int(args.carrier_id),
            "finance": {
                "before_display_currency": before["dbasepre_mode0_finance_display_currency"],
                "after_display_currency": reparsed["dbasepre_mode0_finance_display_currency"],
            },
            "payload": {
                "offset": entry.payload_offset,
                "length": entry.payload_length,
                "record_mode": before["record_mode"],
                "finance_lane_payload_offsets": lane_offsets,
                "finance_lane_file_offsets": sorted(expected_offsets),
            },
            "byte_diff": {
                "changed_count": len(changed_offsets),
                "changed_file_offsets": changed_offsets,
                "unexpected_file_offsets": unexpected_offsets,
            },
            "sha256": {"source": _sha256(original), "output": _sha256(bytes(patched))},
        },
    )
    print(json.dumps({"carrier_id": int(args.carrier_id), "changed_count": len(changed_offsets), "success": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
