#!/usr/bin/env python3
"""Audit the structural mode-1 EQ -> ENT manager-link contract.

This receipt deliberately distinguishes a complete structural corpus scan from
runtime proof.  It confirms the stored link table and ENT targets for every
mode-1 carrier; the linked visible-manager semantics are runtime-proven by the
separate F.C. Barcelona fixtures only.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from app.ent_manager_profiles import parse_indexed_ent_manager_profile
from app.eq_team_manager_links import parse_indexed_eq_manager_links
from app.fdi_indexed import IndexedFDIFile
from app.xor import xor_decode


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbdat", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def _team_label(raw_payload: bytes) -> str:
    if len(raw_payload) < 0x2C:
        return ""
    length = int.from_bytes(raw_payload[0x2A:0x2C], "little")
    start = 0x2C
    end = start + length
    if length <= 0 or end > len(raw_payload):
        return ""
    return xor_decode(raw_payload[start:end]).decode("cp1252", errors="replace").rstrip("\x00")


def main() -> int:
    args = _args()
    dbdat = args.dbdat.resolve()
    eq_path = dbdat / "EQ98030.FDI"
    ent_path = dbdat / "ENT98030.FDI"
    if not eq_path.is_file() or not ent_path.is_file():
        raise SystemExit("both EQ98030.FDI and ENT98030.FDI are required")

    eq_data = eq_path.read_bytes()
    ent_data = ent_path.read_bytes()
    ent_index = IndexedFDIFile.from_bytes(ent_data)
    ent_profiles: dict[int, dict[str, str]] = {}
    for entry in ent_index.entries:
        raw = ent_data[entry.payload_offset : entry.payload_offset + entry.payload_length]
        try:
            profile = parse_indexed_ent_manager_profile(raw, record_id=entry.record_id)
        except ValueError:
            continue
        ent_profiles[entry.record_id] = {
            "format": profile.format,
            "display_name": profile.display_name,
        }

    rows: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    link_counts: Counter[int] = Counter()
    for entry in IndexedFDIFile.from_bytes(eq_data).entries:
        raw = eq_data[entry.payload_offset : entry.payload_offset + entry.payload_length]
        if len(raw) < 0x2A or raw[0x29] != 1:
            continue
        try:
            parsed = parse_indexed_eq_manager_links(raw)
        except ValueError as exc:
            errors.append({"eq_record_id": entry.record_id, "error": str(exc)})
            continue
        missing = [record_id for record_id in parsed.manager_record_ids if record_id not in ent_profiles]
        row = {
            "eq_record_id": entry.record_id,
            "club": _team_label(raw),
            "link_count": parsed.link_count,
            "manager_record_ids": list(parsed.manager_record_ids),
            "active_manager_record_id": parsed.active_manager_record_id,
            "active_manager": ent_profiles.get(parsed.active_manager_record_id or -1),
            "missing_ent_record_ids": missing,
        }
        rows.append(row)
        link_counts[parsed.link_count] += 1
        if missing:
            errors.append({"eq_record_id": entry.record_id, "missing_ent_record_ids": missing})

    result = {
        "schema": "pm99-mode1-manager-link-audit/v1",
        "scope": {
            "structural": "all indexed 700-byte mode-1 EQ carriers",
            "runtime": "F.C. Barcelona only: ENT-1069 name and final EQ link mutations",
            "not_claimed": "a separate visible dashboard check for every individual foreign club",
        },
        "mode1_carrier_count": len(rows),
        "link_count_distribution": {str(count): total for count, total in sorted(link_counts.items())},
        "all_active_links_resolve_to_parsed_ent_profiles": not errors,
        "errors": errors,
        "carriers": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in result if key != "carriers"}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
