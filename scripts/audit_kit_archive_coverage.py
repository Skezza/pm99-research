#!/usr/bin/env python3
"""Audit PM99 carrier-keyed kit artwork without inferring its render surface.

The archive filename contract is ``EQ96<four-digit EQ id>.BMP``.  This audit
records which modern carriers have an asset in each archive and, importantly,
keeps archive presence separate from a claim that a particular game screen
uses that archive.  It is intended to prevent world compilers from asking a
foreign carrier to supply the stock English-only BIG* records.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.eq_team_indexed_metadata import extract_indexed_team_payload_metadata
from app.fdi_indexed import IndexedFDIFile
from app.minifoto_bitmap_archive import iter_obfuscated_bmp_records


ARCHIVES = ("BIGCAMP.PKF", "BIGESC.PKF", "MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")
NAME_RE = re.compile(r"^EQ96(?P<id>\d{4})\.BMP$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbdat", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def archive_ids(path: Path) -> set[int]:
    found: set[int] = set()
    for record in iter_obfuscated_bmp_records(path, file_name_pattern=r"^EQ96\d{4}\.BMP$"):
        match = NAME_RE.fullmatch(record.file_name)
        if match is None:
            raise RuntimeError(f"unexpected validated kit name: {record.file_name}")
        found.add(int(match.group("id")))
    return found


def main() -> int:
    args = parse_args()
    dbdat = args.dbdat.resolve()
    eq_path = dbdat / "EQ98030.FDI"
    if not eq_path.is_file():
        raise SystemExit(f"missing indexed team database: {eq_path}")

    eq_data = eq_path.read_bytes()
    indexed = IndexedFDIFile.from_bytes(eq_data)
    carrier_modes: dict[int, int] = {}
    for entry in indexed.entries:
        raw = eq_data[entry.payload_offset : entry.payload_offset + entry.payload_length]
        metadata = extract_indexed_team_payload_metadata(raw)
        carrier_modes[int(entry.record_id)] = int(metadata["record_mode"])
    carrier_ids = set(carrier_modes)

    details: dict[str, object] = {}
    archive_id_sets: dict[str, set[int]] = {}
    for archive_name in ARCHIVES:
        path = dbdat / archive_name
        if not path.is_file():
            raise SystemExit(f"missing kit archive: {path}")
        ids = archive_ids(path)
        archive_id_sets[archive_name] = ids
        covered = sorted(ids & carrier_ids)
        details[archive_name] = {
            "record_count": len(ids),
            "carrier_ids_present": covered,
            "modern_carrier_count": len(covered),
            "mode_0_carrier_count": sum(carrier_modes[item] == 0 for item in covered),
            "mode_1_carrier_count": sum(carrier_modes[item] == 1 for item in covered),
            "missing_modern_carrier_ids": sorted(carrier_ids - ids),
            "non_modern_or_dummy_ids": sorted(ids - carrier_ids),
        }

    compact = ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")
    compact_complete = set.intersection(*(archive_id_sets[name] for name in compact))
    result = {
        "schema": "pm99-kit-archive-coverage/v1",
        "source": {"dbdat": str(dbdat), "eq98030_bytes": len(eq_data)},
        "modern_carriers": {
            "count": len(carrier_ids),
            "mode_0_count": sum(mode == 0 for mode in carrier_modes.values()),
            "mode_1_count": sum(mode == 1 for mode in carrier_modes.values()),
        },
        "filename_contract": "EQ96<four-digit EQ carrier id>.BMP",
        "archive_presence_is_not_render_proof": True,
        "archives": details,
        "compact_ui_candidate_set": {
            "archives": list(compact),
            "carrier_ids_present_in_all_three": sorted(compact_complete & carrier_ids),
            "modern_carrier_count": len(compact_complete & carrier_ids),
            "missing_modern_carrier_ids": sorted(carrier_ids - compact_complete),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
