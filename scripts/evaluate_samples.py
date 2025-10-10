#!/usr/bin/env python3
"""
Evaluate sample players against the real PM99 database.

Inputs:
- CSV (default: tests/fixtures/players_sample.csv)
  Columns: full_name, club(optional), nationality(optional), expected_pos(GK/DF/MF/FW or 0-3), birth_date(optional DD/MM/YYYY), height_cm(optional)

- FDI path (default: DBDAT/JUG98030.FDI)

Outputs (stdout):
- Coverage summary (found %, position accuracy if provided)
- Per-sample diagnostics (first 20 misses by default)

Usage:
  python scripts/evaluate_samples.py [CSV_PATH] [FDI_PATH]
"""

from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

# Ensure project root on sys.path when running from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.io import FDIFile  # noqa: E402


POS_MAP_STR = {
    # Goalkeeper
    "0": 0, "gk": 0, "g": 0, "keeper": 0, "goalkeeper": 0, "k": 0,
    # Defender
    "1": 1, "df": 1, "d": 1, "defender": 1, "cb": 1, "lb": 1, "rb": 1, "sweeper": 1, "fullback": 1, "centreback": 1,
    # Midfielder
    "2": 2, "mf": 2, "m": 2, "midfielder": 2, "cm": 2, "dm": 2, "am": 2, "lm": 2, "rm": 2, "winger": 2, "playmaker": 2,
    # Forward
    "3": 3, "fw": 3, "f": 3, "forward": 3, "attacker": 3, "striker": 3, "st": 3, "cf": 3, "ss": 3,
}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def tokenize_name(s: str) -> List[str]:
    return [t for t in re.split(r"[^\wÀ-ÿ]+", s.strip()) if t]


def pos_to_code(v: Optional[str]) -> Optional[int]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    key = s.lower()
    return POS_MAP_STR.get(key, None)


@dataclass
class SampleRow:
    full_name: str
    club: Optional[str]
    nationality: Optional[str]
    expected_pos: Optional[int]
    birth_date: Optional[str]
    height_cm: Optional[int]

    @staticmethod
    def from_csv_row(row: Dict[str, str]) -> "SampleRow":
        def get(field: str) -> Optional[str]:
            return row.get(field) or row.get(field.lower()) or row.get(field.upper())

        full_name = norm(get("full_name") or get("name") or "")
        club = norm(get("club") or "") or None
        nationality = norm(get("nationality") or "") or None
        expected_pos = pos_to_code(get("expected_pos"))
        birth_date = norm(get("birth_date") or "") or None
        height_raw = norm(get("height_cm") or "") or None
        try:
            height_cm = int(height_raw) if height_raw else None
        except ValueError:
            height_cm = None

        if not full_name:
            raise ValueError("Missing full_name in CSV row")

        return SampleRow(
            full_name=full_name,
            club=club,
            nationality=nationality,
            expected_pos=expected_pos,
            birth_date=birth_date,
            height_cm=height_cm,
        )


def best_match(full_name: str, candidates: List[Any], expected_pos: Optional[int] = None) -> Optional[Any]:
    """
    Choose the best candidate based on:
    - token overlap with target full name
    - name length proximity
    - non-biography team_id preference
    - expected position match (if provided)
    """
    if not candidates:
        return None
    target_tokens = set(t.lower() for t in tokenize_name(full_name))
    best = None
    best_score = -1
    for r in candidates:
        name = f"{r.given_name} {r.surname}".strip()
        cand_tokens = set(t.lower() for t in tokenize_name(name))
        common = len(target_tokens & cand_tokens)
        score = common * 100 + min(len(name), len(full_name))
        # Prefer non-biography team_id where possible
        score += 5 if getattr(r, "team_id", 0) != 0 else 0
        # Prefer expected position when provided
        pos = getattr(r, "position_primary", None)
        if expected_pos is not None and pos is not None:
            if pos == expected_pos:
                score += 200
            else:
                score -= 50
        if score > best_score:
            best_score = score
            best = r
    return best


def evaluate_samples(csv_path: Path, fdi_path: Path, max_detail: int = 20) -> Dict[str, Any]:
    if not fdi_path.exists():
        raise FileNotFoundError(f"FDI not found: {fdi_path}")

    samples: List[SampleRow] = []
    if not csv_path.exists():
        print(f"[WARN] Sample CSV not found: {csv_path} (skipping evaluation).")
        return {"status": "missing_csv", "csv": str(csv_path)}

    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 1):
            try:
                samples.append(SampleRow.from_csv_row(row))
            except Exception as e:
                print(f"[WARN] Skipping row {i}: {e}")

    if not samples:
        return {"status": "no_samples", "csv": str(csv_path)}

    fdi = FDIFile(fdi_path)
    fdi.load()

    results: List[Dict[str, Any]] = []
    found_cnt = 0
    pos_total = 0
    pos_match_cnt = 0

    for s in samples:
        # Primary search: use the surname as a robust key (bypass dedup to keep all candidates)
        tokens = tokenize_name(s.full_name)
        surname = tokens[-1] if tokens else s.full_name

        # Gather raw candidates directly from all records to avoid premature dedup
        all_names = lambda r: f"{r.given_name} {r.surname}".strip().lower()
        raw_candidates = [r for r in fdi.records if surname.lower() in all_names(r)]

        # Fallback to API dedup search if nothing found
        candidates = raw_candidates if raw_candidates else fdi.find_by_name(surname)

        # Pick best match with expected position bias (if provided)
        match = best_match(s.full_name, candidates, expected_pos=s.expected_pos)

        found = match is not None
        found_cnt += 1 if found else 0

        matched_name = f"{match.given_name} {match.surname}".strip() if match else None
        matched_pos = getattr(match, "position_primary", None) if match else None
        matched_team = getattr(match, "team_id", None) if match else None

        pos_ok = None
        if s.expected_pos is not None:
            pos_total += 1
            if matched_pos is not None:
                pos_ok = (matched_pos == s.expected_pos)
                pos_match_cnt += 1 if pos_ok else 0

        results.append({
            "full_name": s.full_name,
            "found": found,
            "matched_name": matched_name,
            "expected_pos": s.expected_pos,
            "matched_pos": matched_pos,
            "pos_match": pos_ok,
            "team_id": matched_team,
        })

    summary = {
        "total": len(samples),
        "found": found_cnt,
        "found_pct": round(100.0 * found_cnt / max(1, len(samples)), 2),
        "pos_checked": pos_total,
        "pos_correct": pos_match_cnt,
        "pos_accuracy_pct": round(100.0 * pos_match_cnt / max(1, pos_total), 2) if pos_total else None,
    }

    # Print report
    print("=" * 80)
    print("PM99 Sample Evaluation Report")
    print("=" * 80)
    print(f"CSV: {csv_path}")
    print(f"FDI: {fdi_path}")
    print(f"Totals: {summary['total']} samples")
    print(f"Found:  {summary['found']} ({summary['found_pct']}%)")
    if summary["pos_checked"]:
        print(f"Pos OK: {summary['pos_correct']}/{summary['pos_checked']} ({summary['pos_accuracy_pct']}%)")
    else:
        print("Pos OK: N/A (no expected_pos provided)")
    print()

    # Show first N misses/mismatches
    misses = [r for r in results if not r["found"]]
    mismatches = [r for r in results if r["pos_match"] is False]
    if misses:
        print(f"First {min(max_detail, len(misses))} misses:")
        for r in misses[:max_detail]:
            print(f"- Not found: {r['full_name']}")
        print()
    if mismatches:
        print(f"First {min(max_detail, len(mismatches))} position mismatches:")
        for r in mismatches[:max_detail]:
            print(f"- {r['full_name']} → matched {r['matched_name']} pos={r['matched_pos']} expected={r['expected_pos']}")
        print()

    # Save machine-readable output next to CSV
    out_json = csv_path.with_suffix(".results.json")
    try:
        out_json.write_text(json.dumps({"summary": summary, "results": results}, indent=2), encoding="utf-8")
        print(f"Wrote JSON results: {out_json}")
    except Exception as e:
        print(f"[WARN] Failed to write JSON results: {e}")

    return {"summary": summary, "results": results}


def main():
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/players_sample.csv")
    fdi_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("DBDAT/JUG98030.FDI")
    evaluate_samples(csv_path, fdi_path)


if __name__ == "__main__":
    main()
