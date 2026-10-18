#!/usr/bin/env python3
"""Create one byte-accounted mode-1 club identity probe.

The probe deliberately changes only the three variable-length display strings
and the parser-backed seated-capacity lane of an existing foreign EQ carrier.
It leaves the terminal roster graph, manager link and every opaque byte alone.
It is intended for a fresh PM99 preseason-picker runtime capture, not as a
bulk release writer.
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

from app.eq_jug_linked import parse_eq_external_team_roster_payload  # noqa: E402
from app.eq_team_indexed_metadata import (  # noqa: E402
    extract_indexed_team_payload_metadata,
    patch_indexed_team_seated_capacity,
)
from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from app.xor import xor_decode, xor_encode  # noqa: E402
from scripts.build_2015_english92_release import _rebuild_indexed, _rewrite_eq_strings  # noqa: E402


def _spans(before: bytes, after: bytes) -> list[dict[str, int]]:
    spans: list[dict[str, int]] = []
    start: int | None = None
    for offset, (left, right) in enumerate(zip(before, after)):
        if left != right and start is None:
            start = offset
        elif left == right and start is not None:
            spans.append({"offset": start, "length": offset - start})
            start = None
    if start is not None:
        spans.append({"offset": start, "length": len(before) - start})
    if len(after) > len(before):
        spans.append({"offset": len(before), "length": len(after) - len(before)})
    return spans


def _roster_bytes(payload: bytes) -> bytes:
    parsed = parse_eq_external_team_roster_payload(payload, {})
    if parsed is None or not parsed.rows:
        raise ValueError("EQ record has no parser-backed terminal roster")
    start = int(parsed.rows[0].raw_row_offset) - 1
    end = int(parsed.rows[-1].raw_row_offset) + 5
    if start < 0 or end != len(payload):
        raise ValueError("EQ roster tail is not a bounded terminal table")
    return payload[start:end]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbdat", required=True, type=Path)
    parser.add_argument("--eq-record-id", required=True, type=int)
    parser.add_argument("--expected-name", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--ground", required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--capacity", required=True, type=int)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args(argv)

    if not 0 <= args.capacity <= 2_147_483_647:
        parser.error("--capacity must fit a signed 32-bit EQ lane")
    for label, value in (("name", args.name), ("ground", args.ground), ("full-name", args.full_name)):
        try:
            encoded = value.strip().encode("cp1252")
        except UnicodeEncodeError as exc:
            parser.error(f"--{label} is not CP1252 encodable: {exc}")
        if not encoded or len(encoded) > 255:
            parser.error(f"--{label} must contain 1..255 CP1252 bytes")

    eq_path = args.dbdat / "EQ98030.FDI"
    before_file = eq_path.read_bytes()
    indexed = IndexedFDIFile.from_bytes(before_file)
    entry = next((item for item in indexed.entries if item.record_id == args.eq_record_id), None)
    if entry is None:
        parser.error(f"EQ carrier {args.eq_record_id} is absent")
    # EQ uses two layers in this area: the indexed container XOR is removed
    # for the compact name writer, while the parser-backed metadata and
    # terminal roster table use the original outer-encoded payload.
    before_decoded = entry.decode_payload(before_file)
    before = before_file[entry.payload_offset : entry.payload_offset + entry.payload_length]
    metadata_before = extract_indexed_team_payload_metadata(before)
    if int(metadata_before["record_mode"]) != 1:
        parser.error(f"EQ carrier {args.eq_record_id} is mode {metadata_before['record_mode']}, not mode 1")
    if metadata_before["short_name"] != args.expected_name:
        parser.error(
            f"EQ carrier {args.eq_record_id} name is {metadata_before['short_name']!r}, "
            f"not expected {args.expected_name!r}"
        )
    before_roster = _roster_bytes(before)

    after_decoded = _rewrite_eq_strings(
        before_decoded,
        short_name=args.name.strip(),
        stadium_name=args.ground.strip(),
        full_name=args.full_name.strip(),
    )
    after = patch_indexed_team_seated_capacity(xor_encode(after_decoded), args.capacity)
    after_roster = _roster_bytes(after)
    if after_roster != before_roster:
        raise SystemExit("identity probe changed the foreign roster graph")
    metadata_after = extract_indexed_team_payload_metadata(after)
    expected = (args.name.strip(), args.ground.strip(), args.full_name.strip(), args.capacity)
    observed = (
        metadata_after["short_name"],
        metadata_after["stadium_name"],
        metadata_after["full_club_name"],
        metadata_after["seated_capacity"],
    )
    if observed != expected:
        raise SystemExit(f"identity read-back failed: expected={expected!r} observed={observed!r}")

    after_decoded = xor_decode(after)
    after_file = _rebuild_indexed(before_file, indexed, {args.eq_record_id: after_decoded})
    rebuilt = IndexedFDIFile.from_bytes(after_file)
    rebuilt_entry = next(item for item in rebuilt.entries if item.record_id == args.eq_record_id)
    rebuilt_payload = rebuilt_entry.decode_payload(after_file)
    if rebuilt_payload != after_decoded:
        raise SystemExit("rebuilt indexed EQ record failed exact decoded read-back")
    eq_path.write_bytes(after_file)

    receipt = {
        "schema": "pm99-mode1-team-identity-probe/v1",
        "eq_record_id": args.eq_record_id,
        "before_sha256": hashlib.sha256(before_file).hexdigest(),
        "after_sha256": hashlib.sha256(after_file).hexdigest(),
        "before": {
            "short_name": metadata_before["short_name"],
            "stadium_name": metadata_before["stadium_name"],
            "full_club_name": metadata_before["full_club_name"],
            "seated_capacity": metadata_before["seated_capacity"],
            "payload_length": len(before),
        },
        "after": {
            "short_name": metadata_after["short_name"],
            "stadium_name": metadata_after["stadium_name"],
            "full_club_name": metadata_after["full_club_name"],
            "seated_capacity": metadata_after["seated_capacity"],
            "payload_length": len(after),
        },
        "invariants": {
            "record_mode": metadata_before["record_mode"],
            "record_size": metadata_before["record_size"],
            "roster_tail_sha256": hashlib.sha256(before_roster).hexdigest(),
            "roster_tail_preserved_exactly": after_roster == before_roster,
        },
        "record_changed_spans": _spans(before, after),
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
