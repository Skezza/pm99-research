#!/usr/bin/env python3
"""Audit the native MANAGPRE dd6360 player cursor without writing a DB.

The generic ``PlayerRecord`` parser locates its marker after the two compact
native strings.  That marker is three or four bytes after the point at which
MANAGPRE starts consuming the six fine-position bytes.  Treating the marker
as the metadata start therefore gives credible-but-wrong field values.

This utility records the corpus result for the actual native cursor used by
the player loader.  It is deliberately read-only and keeps the two exceptional
legacy birth-year encodings visible instead of normalising them away.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

from app.editor_actions import (  # type: ignore[import-not-found]
    _indexed_variable_name_compact_segments,
    _native_dd6360_fine_role_window_start,
    _native_dd6360_role_start,
    _read_native_dd6360_fields,
)
from app.fdi_indexed import IndexedFDIFile  # type: ignore[import-not-found]
from app.models import PlayerRecord  # type: ignore[import-not-found]


def _comparison(generic: PlayerRecord, native: dict[str, Any]) -> dict[str, bool]:
    return {
        "nationality": int(generic.nationality) == int(native["visible_nationality_code"]),
        "position": int(generic.position) == int(native["visible_position_code"]),
        "birth_day": int(generic.birth_day) == int(native["birth_day"]),
        "birth_month": int(generic.birth_month) == int(native["birth_month"]),
        "birth_year": int(generic.birth_year) == int(native["birth_year"]),
        "height": int(generic.height) == int(native["height_cm"]),
    }


def audit(player_file: Path) -> dict[str, Any]:
    file_bytes = player_file.read_bytes()
    indexed = IndexedFDIFile.from_bytes(file_bytes)
    by_gap: dict[int, Counter[str]] = {3: Counter(), 4: Counter()}
    birth_year_anomalies: list[dict[str, Any]] = []
    fine_role_outliers: list[dict[str, Any]] = []
    fine_role_codes: Counter[int] = Counter()
    parser_errors: list[dict[str, Any]] = []
    total = 0

    for entry in indexed.entries:
        payload = entry.decode_payload(file_bytes)
        if payload[2:5] != b"\xdd\x63\x60":
            continue
        total += 1
        try:
            segments = _indexed_variable_name_compact_segments(payload)
            if segments is None:
                raise ValueError("compact dd6360 segments unresolved")
            gap = int(segments["pre_marker_gap_bytes"])
            role_start = _native_dd6360_role_start(payload)
            if role_start != int(segments["full_name_end"]):
                raise ValueError(
                    f"native role cursor {role_start} does not equal compact-name end "
                    f"{segments['full_name_end']}"
                )
            native = _read_native_dd6360_fields(payload, role_start)
            fine_role_start = _native_dd6360_fine_role_window_start(payload)
            roles = [int(value) for value in native["fine_role_codes"]]
            fine_role_codes.update(roles)
            invalid_roles = [value for value in roles if value not in {*range(18), 98}]
            if invalid_roles:
                fine_role_outliers.append(
                    {
                        "record_id": int(entry.record_id),
                        "key": str(entry.key),
                        "name": str(PlayerRecord.from_bytes(payload, 0).name),
                        "fine_role_window_start": fine_role_start,
                        "fine_role_codes": roles,
                        "unsupported_codes": invalid_roles,
                    }
                )
            generic = PlayerRecord.from_bytes(payload, 0)
            by_gap.setdefault(gap, Counter())["records"] += 1
            for field, matches in _comparison(generic, native).items():
                by_gap[gap][f"generic_{field}_{'match' if matches else 'mismatch'}"] += 1
            if not 1850 <= int(native["birth_year"]) <= 2050:
                birth_year_anomalies.append(
                    {
                        "record_id": int(entry.record_id),
                        "key": str(entry.key),
                        "name": str(generic.name),
                        "native_birth_day": int(native["birth_day"]),
                        "native_birth_month": int(native["birth_month"]),
                        "native_birth_year": int(native["birth_year"]),
                    }
                )
        except Exception as exc:  # A report must retain any unsafe shape.
            parser_errors.append(
                {
                    "record_id": int(entry.record_id),
                    "key": str(entry.key),
                    "error": str(exc),
                }
            )

    return {
        "schema_version": 1,
        "source_file": str(player_file),
        "purpose": "Read-only validation of the native dd6360 compact-string cursor.",
        "dd6360_records": total,
        "native_cursor_contract": {
            "string_start": 8,
            "string_count": 2,
            "role_start": "end of the second XOR/u16 compact string",
            "fine_role_window": "role_start + 1 through role_start + 6",
            "opaque_control_bytes": ["role_start", "role_start + 7"],
            "generic_marker_offset": "three or four bytes later; not a metadata cursor",
        },
        "by_pre_marker_gap": {str(gap): dict(sorted(counts.items())) for gap, counts in sorted(by_gap.items())},
        "parser_errors": parser_errors,
        "legacy_birth_year_anomalies": birth_year_anomalies,
        "fine_role_code_distribution": {
            str(code): count for code, count in sorted(fine_role_codes.items())
        },
        "legacy_fine_role_outliers": fine_role_outliers,
        "result": "pass" if not parser_errors else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--player-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.player_file)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
