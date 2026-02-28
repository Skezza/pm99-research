#!/usr/bin/env python3
"""Probe and validate a PM99 lineup screenshot (team roster table).

Current scope (seeded with Stoke City opening-day lineup screenshot):
- stores a manually transcribed row set from the screenshot
- validates the `AV` column against the discovered formula:
  floor((SP + ST + AG + QU + FI + MO) / 6)
- records `ROL.` numeric codes visible in the lineup table for future linkage work

This script is intentionally data-first and reproducible; it preserves the exact values used
for reverse-engineering notes instead of relying on one-off terminal transcripts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


# Seed transcription from `.local/StokeCityLineup.png` (opening-day Stoke City lineup screenshot).
# Columns in screenshot order: N., PLAYER, EN, SP, ST, AG, QU, FI, MO, AV, ROL., POS
STOKE_LINEUP_ROWS: list[dict[str, Any]] = [
    {"n": 1, "name": "Muggleton", "en": 99, "sp": 60, "st": 62, "ag": 60, "qu": 57, "fi": 70, "mo": 99, "av": 68, "rol": 3, "pos": "GOAL", "section": "starters"},
    {"n": 2, "name": "Clarke", "en": 99, "sp": 50, "st": 51, "ag": 49, "qu": 49, "fi": 70, "mo": 99, "av": 61, "rol": 0, "pos": "DEF", "section": "starters"},
    {"n": 3, "name": "Small", "en": 99, "sp": 69, "st": 65, "ag": 67, "qu": 50, "fi": 70, "mo": 99, "av": 70, "rol": 0, "pos": "DEF", "section": "starters"},
    {"n": 4, "name": "Sigurdsson", "en": 99, "sp": 65, "st": 68, "ag": 72, "qu": 64, "fi": 70, "mo": 83, "av": 70, "rol": 0, "pos": "DEF", "section": "starters"},
    {"n": 5, "name": "Short", "en": 99, "sp": 65, "st": 67, "ag": 68, "qu": 58, "fi": 70, "mo": 88, "av": 69, "rol": 4, "pos": "DEF", "section": "starters"},
    {"n": 6, "name": "Forsyth", "en": 99, "sp": 61, "st": 63, "ag": 65, "qu": 61, "fi": 70, "mo": 81, "av": 66, "rol": 6, "pos": "MID", "section": "starters"},
    {"n": 7, "name": "Keen", "en": 99, "sp": 62, "st": 76, "ag": 69, "qu": 75, "fi": 70, "mo": 90, "av": 73, "rol": 4, "pos": "MID", "section": "starters"},
    {"n": 8, "name": "Wallace", "en": 99, "sp": 70, "st": 61, "ag": 59, "qu": 58, "fi": 70, "mo": 85, "av": 67, "rol": 0, "pos": "DEF", "section": "starters"},
    {"n": 9, "name": "Thorne", "en": 99, "sp": 66, "st": 63, "ag": 74, "qu": 64, "fi": 70, "mo": 85, "av": 70, "rol": 8, "pos": "FOR", "section": "starters"},
    {"n": 10, "name": "Robinson", "en": 99, "sp": 63, "st": 66, "ag": 69, "qu": 59, "fi": 70, "mo": 85, "av": 68, "rol": 6, "pos": "MID", "section": "starters"},
    {"n": 11, "name": "Kavanagh", "en": 99, "sp": 72, "st": 65, "ag": 67, "qu": 69, "fi": 70, "mo": 99, "av": 73, "rol": 6, "pos": "MID", "section": "starters"},
    {"n": 12, "name": "Lightbourne", "en": 99, "sp": 76, "st": 59, "ag": 55, "qu": 70, "fi": 70, "mo": 99, "av": 71, "rol": 8, "pos": "FOR", "section": "subs"},
    {"n": 13, "name": "Fraser", "en": 99, "sp": 52, "st": 49, "ag": 47, "qu": 52, "fi": 70, "mo": 99, "av": 61, "rol": 2, "pos": "GOAL", "section": "subs"},
    {"n": 14, "name": "Crowe", "en": 99, "sp": 64, "st": 58, "ag": 59, "qu": 62, "fi": 70, "mo": 99, "av": 68, "rol": 8, "pos": "FOR", "section": "subs"},
    {"n": 15, "name": "Oldfield", "en": 99, "sp": 63, "st": 73, "ag": 76, "qu": 61, "fi": 70, "mo": 96, "av": 73, "rol": 6, "pos": "MID", "section": "reserves"},
    {"n": 16, "name": "Sturridge", "en": 99, "sp": 65, "st": 68, "ag": 69, "qu": 48, "fi": 70, "mo": 99, "av": 69, "rol": 8, "pos": "FOR", "section": "reserves"},
    {"n": 17, "name": "Woods", "en": 99, "sp": 60, "st": 58, "ag": 59, "qu": 54, "fi": 70, "mo": 99, "av": 66, "rol": 0, "pos": "DEF", "section": "reserves"},
    {"n": 18, "name": "McKenzie", "en": 99, "sp": 56, "st": 52, "ag": 53, "qu": 47, "fi": 70, "mo": 99, "av": 62, "rol": 6, "pos": "MID", "section": "reserves"},
    {"n": 19, "name": "Petty", "en": 99, "sp": 58, "st": 49, "ag": 54, "qu": 57, "fi": 70, "mo": 99, "av": 64, "rol": 0, "pos": "DEF", "section": "reserves"},
    {"n": 20, "name": "Heath", "en": 99, "sp": 65, "st": 56, "ag": 59, "qu": 64, "fi": 70, "mo": 99, "av": 68, "rol": 6, "pos": "MID", "section": "reserves"},
]


# Seed transcription from `.local/ManUtd.png` (opening-day lineup screenshot provided by user).
# Visible rows include starters, substitutes, and visible reserves (20 rows total).
MANUTD_LINEUP_ROWS: list[dict[str, Any]] = [
    {"n": 1, "name": "Schmeichel", "en": 99, "sp": 90, "st": 86, "ag": 86, "qu": 91, "fi": 70, "mo": 99, "av": 87, "rol": 3, "pos": "GOAL", "section": "starters"},
    {"n": 2, "name": "Neville G.", "en": 99, "sp": 81, "st": 79, "ag": 80, "qu": 72, "fi": 70, "mo": 99, "av": 80, "rol": 0, "pos": "DEF", "section": "starters"},
    {"n": 3, "name": "Irwin", "en": 99, "sp": 80, "st": 84, "ag": 82, "qu": 83, "fi": 70, "mo": 99, "av": 83, "rol": 0, "pos": "DEF", "section": "starters"},
    {"n": 21, "name": "Berg", "en": 99, "sp": 86, "st": 84, "ag": 83, "qu": 84, "fi": 70, "mo": 94, "av": 83, "rol": 0, "pos": "DEF", "section": "starters"},
    {"n": 6, "name": "Stam", "en": 99, "sp": 81, "st": 82, "ag": 80, "qu": 77, "fi": 70, "mo": 99, "av": 81, "rol": 0, "pos": "DEF", "section": "starters"},
    {"n": 8, "name": "Butt", "en": 99, "sp": 79, "st": 83, "ag": 91, "qu": 72, "fi": 70, "mo": 99, "av": 82, "rol": 6, "pos": "MID", "section": "starters"},
    {"n": 7, "name": "Beckham", "en": 99, "sp": 90, "st": 85, "ag": 85, "qu": 90, "fi": 70, "mo": 99, "av": 86, "rol": 4, "pos": "MID", "section": "starters"},
    {"n": 9, "name": "Cole", "en": 99, "sp": 87, "st": 86, "ag": 84, "qu": 75, "fi": 70, "mo": 99, "av": 83, "rol": 8, "pos": "FOR", "section": "starters"},
    {"n": 19, "name": "Yorke", "en": 99, "sp": 96, "st": 74, "ag": 83, "qu": 87, "fi": 70, "mo": 99, "av": 84, "rol": 8, "pos": "FOR", "section": "starters"},
    {"n": 18, "name": "Scholes", "en": 99, "sp": 85, "st": 81, "ag": 80, "qu": 81, "fi": 70, "mo": 99, "av": 82, "rol": 6, "pos": "MID", "section": "starters"},
    {"n": 11, "name": "Giggs", "en": 99, "sp": 94, "st": 85, "ag": 82, "qu": 89, "fi": 70, "mo": 99, "av": 86, "rol": 6, "pos": "MID", "section": "starters"},
    {"n": 5, "name": "Johnsen", "en": 99, "sp": 85, "st": 79, "ag": 81, "qu": 78, "fi": 70, "mo": 99, "av": 82, "rol": 0, "pos": "DEF", "section": "subs"},
    {"n": 17, "name": "Van der Gouw", "en": 99, "sp": 81, "st": 79, "ag": 79, "qu": 80, "fi": 70, "mo": 99, "av": 81, "rol": 2, "pos": "GOAL", "section": "subs"},
    {"n": 12, "name": "Neville P.", "en": 99, "sp": 83, "st": 82, "ag": 83, "qu": 73, "fi": 70, "mo": 99, "av": 81, "rol": 0, "pos": "DEF", "section": "subs"},
    {"n": 15, "name": "Blomqvist", "en": 99, "sp": 84, "st": 79, "ag": 76, "qu": 85, "fi": 70, "mo": 99, "av": 82, "rol": 4, "pos": "MID", "section": "subs"},
    {"n": 20, "name": "Solskjaer", "en": 99, "sp": 87, "st": 83, "ag": 81, "qu": 84, "fi": 70, "mo": 99, "av": 84, "rol": 8, "pos": "FOR", "section": "subs"},
    {"n": 4, "name": "May", "en": 99, "sp": 81, "st": 81, "ag": 81, "qu": 75, "fi": 70, "mo": 99, "av": 81, "rol": 0, "pos": "DEF", "section": "reserves"},
    {"n": 16, "name": "Keane", "en": 99, "sp": 88, "st": 93, "ag": 99, "qu": 87, "fi": 70, "mo": 99, "av": 89, "rol": 4, "pos": "MID", "section": "reserves"},
    {"n": 10, "name": "Sheringham", "en": 99, "sp": 78, "st": 72, "ag": 70, "qu": 86, "fi": 70, "mo": 99, "av": 79, "rol": 8, "pos": "FOR", "section": "reserves"},
    {"n": 13, "name": "Curtis", "en": 99, "sp": 82, "st": 81, "ag": 81, "qu": 76, "fi": 70, "mo": 99, "av": 81, "rol": 0, "pos": "DEF", "section": "reserves"},
]


def _validate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    av_checks: list[dict[str, Any]] = []
    av_all_match = True
    en_values = []
    fi_values = []
    rol_by_pos: dict[str, set[int]] = {}
    rol_counts: dict[int, int] = {}
    mo_values = []

    for row in rows:
        sp = int(row["sp"])
        st = int(row["st"])
        ag = int(row["ag"])
        qu = int(row["qu"])
        fi = int(row["fi"])
        mo = int(row["mo"])
        av = int(row["av"])
        calc_av = (sp + st + ag + qu + fi + mo) // 6
        match = calc_av == av
        av_all_match = av_all_match and match
        av_checks.append(
            {
                "n": int(row["n"]),
                "name": row["name"],
                "display_av": av,
                "calc_av_floor_mean_sp_st_ag_qu_fi_mo": calc_av,
                "match": match,
            }
        )

        en_values.append(int(row["en"]))
        fi_values.append(fi)
        mo_values.append(mo)

        rol = int(row["rol"])
        pos = str(row["pos"])
        rol_by_pos.setdefault(pos, set()).add(rol)
        rol_counts[rol] = rol_counts.get(rol, 0) + 1

    return {
        "row_count": len(rows),
        "av_formula": "floor((SP + ST + AG + QU + FI + MO) / 6)",
        "av_all_match": av_all_match,
        "av_checks": av_checks,
        "en_unique_values": sorted(set(en_values)),
        "fi_unique_values": sorted(set(fi_values)),
        "mo_min": min(mo_values) if mo_values else None,
        "mo_max": max(mo_values) if mo_values else None,
        "rol_codes_present": sorted(rol_counts.keys()),
        "rol_code_counts": {str(k): int(v) for k, v in sorted(rol_counts.items())},
        "rol_codes_by_pos": {pos: sorted(vals) for pos, vals in sorted(rol_by_pos.items())},
    }


def _dataset_rows(dataset: str) -> list[dict[str, Any]]:
    key = dataset.strip().lower()
    if key in ("stoke", "stokecity", "stoke_city"):
        return list(STOKE_LINEUP_ROWS)
    if key in ("manutd", "man_utd", "manchester_united", "manchesterunited", "man-u"):
        return list(MANUTD_LINEUP_ROWS)
    raise ValueError(f"Unknown dataset: {dataset}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate/transcribe a PM99 lineup screenshot row set")
    p.add_argument(
        "--screenshot",
        default=str(Path(".local") / "StokeCityLineup.png"),
        help="Source screenshot path (for provenance only; no OCR performed)",
    )
    p.add_argument(
        "--dataset",
        default="stoke",
        help="Dataset key to emit (`stoke` or `manutd`)",
    )
    p.add_argument("--json-output", help="Write JSON artifact to this path")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    rows = _dataset_rows(args.dataset)
    validation = _validate_rows(rows)
    dataset_label = {
        "stoke": "Stoke City first lineup (opening day) - manual transcription from screenshot",
        "manutd": "Manchester Utd first lineup (opening day) - manual transcription from screenshot",
    }.get(str(args.dataset).strip().lower(), str(args.dataset))
    payload = {
        "screenshot_path": str(Path(args.screenshot)),
        "dataset": dataset_label,
        "dataset_key": str(args.dataset),
        "columns": ["n", "name", "en", "sp", "st", "ag", "qu", "fi", "mo", "av", "rol", "pos", "section"],
        "rows": rows,
        "validation": validation,
        "notes": [
            "Rows are transcribed from the provided `.local/StokeCityLineup.png` screenshot.",
            "ROL values are the visible numeric codes in the lineup table, not role labels.",
            "This artifact is for reverse-engineering validation (AV/EN/FI/MO/ROL behavior).",
        ],
    }

    text = json.dumps(payload, indent=2)
    if args.json_output:
        out = Path(args.json_output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
