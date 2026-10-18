#!/usr/bin/env python3
"""Read-only evidence for PM99's fixed foreign-carrier topology boundary.

This is deliberately *not* a foreign-league editor.  It checks a specific
foreign EQ carrier ID which has already been observed in a real PM99 draw and
answers the narrower storage question: does an indexed FDI payload contain a
database relationship pointing to that carrier?  If it does not, moving that
club between foreign competitions cannot be authorised as an FDI field write.

The useful, safe operation remains replacing the contents of an existing
carrier while preserving its EQ directory ID and place in the existing carrier
stream.  That is the operation used by historical world data packages.  It is
not permission to rewrite the game's untraced draw topology.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
EDITOR_ROOT = REPO_ROOT / "upstream" / "pm99-skezmod-db-editor"
if str(EDITOR_ROOT) not in sys.path:
    sys.path.insert(0, str(EDITOR_ROOT))

from app.fdi_indexed import IndexedFDIFile  # noqa: E402


FDI_NAMES = ("EQ98030.FDI", "JUG98030.FDI", "ENT98030.FDI")


@dataclass(frozen=True)
class Occurrence:
    file: str
    record_id: int | None
    offset: int
    region: str


def _all_offsets(data: bytes, pattern: bytes) -> list[int]:
    offsets: list[int] = []
    start = 0
    while True:
        found = data.find(pattern, start)
        if found < 0:
            return offsets
        offsets.append(found)
        start = found + 1


def _payload_occurrences(path: Path, record_id: int) -> tuple[IndexedFDIFile, list[Occurrence], list[Occurrence]]:
    """Return raw and decoded occurrences without changing a byte on disk."""
    file_bytes = path.read_bytes()
    indexed = IndexedFDIFile.from_bytes(file_bytes)
    pattern = int(record_id).to_bytes(2, "little")
    raw_occurrences: list[Occurrence] = []
    for offset in _all_offsets(file_bytes, pattern):
        region = "directory" if offset < indexed.index_end_offset else "encoded_payload_or_trailer"
        raw_occurrences.append(Occurrence(path.name, None, offset, region))

    decoded_occurrences: list[Occurrence] = []
    for entry in indexed.entries:
        decoded = entry.decode_payload(file_bytes)
        for offset in _all_offsets(decoded, pattern):
            decoded_occurrences.append(
                Occurrence(path.name, int(entry.record_id), offset, "decoded_payload")
            )
    return indexed, raw_occurrences, decoded_occurrences


def collect(dbdat: Path, record_id: int) -> dict[str, Any]:
    """Collect the fixed-carrier result, failing if the supplied data is incomplete."""
    if not 1 <= int(record_id) <= 65535:
        raise ValueError("record id must be from 1 through 65535")
    dbdat = dbdat.resolve()
    missing = [name for name in FDI_NAMES if not (dbdat / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing indexed FDI files under {dbdat}: {', '.join(missing)}")

    files: dict[str, dict[str, Any]] = {}
    eq_entry: dict[str, Any] | None = None
    decoded_reference_count = 0
    for name in FDI_NAMES:
        indexed, raw_occurrences, decoded_occurrences = _payload_occurrences(dbdat / name, record_id)
        decoded_reference_count += len(decoded_occurrences)
        entry = next((candidate for candidate in indexed.entries if int(candidate.record_id) == int(record_id)), None)
        files[name] = {
            "record_count": int(indexed.record_count),
            "index_end_offset": int(indexed.index_end_offset),
            "target_directory_entry": (
                {
                    "record_id": int(entry.record_id),
                    "directory_offset": int(entry.index_offset),
                    "payload_offset": int(entry.payload_offset),
                    "payload_length": int(entry.payload_length),
                    "key": entry.key,
                }
                if entry is not None
                else None
            ),
            "raw_occurrences": [asdict(item) for item in raw_occurrences],
            "decoded_payload_occurrences": [asdict(item) for item in decoded_occurrences],
        }
        if name == "EQ98030.FDI" and entry is not None:
            eq_entry = files[name]["target_directory_entry"]

    if eq_entry is None:
        raise ValueError(f"EQ record {record_id} is absent; it cannot be a fixed carrier proof")

    return {
        "read_only": True,
        "dbdat": str(dbdat),
        "record_id": int(record_id),
        "eq_directory_entry": eq_entry,
        "decoded_payload_reference_count": int(decoded_reference_count),
        "files": files,
        "result": (
            "fixed-carrier-no-payload-membership-reference"
            if decoded_reference_count == 0
            else "payload-reference-present-investigate-before-writing"
        ),
        "safe_writer_boundary": (
            "A historical package may replace supported data inside this existing EQ carrier, "
            "while preserving its directory record_id, directory position and unknown bytes. "
            "It must not infer or write a foreign league/country/draw-membership field."
        ),
        "interpretation": (
            "No decoded reference does not prove that MANAGPRE.EXE has no internal candidate-pool logic. "
            "It does prove that the supplied carrier ID is not represented by a decoded FDI payload "
            "relationship in the three editable database families."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbdat", required=True, type=Path)
    parser.add_argument("--record-id", required=True, type=int)
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    try:
        report = collect(args.dbdat, args.record_id)
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
