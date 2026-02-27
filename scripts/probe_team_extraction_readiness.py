#!/usr/bin/env python3
"""Quantify how close we are to programmatic team-player extraction.

This probe measures two different paths using known lineup rows (currently Stoke + Man Utd):

1) Direct strict parser path (`dd6360`-style player records via `gather_player_records_strict`)
2) Hybrid identity path (`dd6361` biographies + lineup core4 stats for disambiguation)

The goal is to provide a data-backed answer to:
"Can we extract all players for a team programmatically yet, and how close are we?"
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.editor_sources import gather_player_records_strict  # type: ignore
from scripts import probe_bio_trailer_stats as bio_probe  # type: ignore
from scripts import probe_lineup_screenshot as lineup_probe  # type: ignore


def _norm(text: str) -> str:
    text = " ".join((text or "").split())
    text = re.sub(r"[^A-Za-z0-9' ]+", " ", text)
    return " ".join(text.split()).upper()


def _record_display_name(record: Any) -> str:
    name = (getattr(record, "name", None) or "").strip()
    if not name:
        given = (getattr(record, "given_name", None) or "").strip()
        surname = (getattr(record, "surname", None) or "").strip()
        name = f"{given} {surname}".strip()
    return name


def _lineup_name_match_candidates(
    lineup_name: str,
    indexed: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    """Match lineup display names (surname-only or surname+initial abbreviations)."""
    q = _norm(lineup_name)
    q_parts = q.split()
    if not q_parts:
        return [], "empty"

    # Surname-only (most lineup rows).
    if len(q_parts) == 1:
        surname = q_parts[0]
        out = [row for row in indexed if row["parts"] and row["parts"][-1] == surname]
        return out, "surname"

    # PM99 lineup abbreviations like "Neville G." become "NEVILLE G" after normalization.
    if len(q_parts) == 2 and len(q_parts[1]) == 1:
        surname, initial = q_parts
        out = [
            row
            for row in indexed
            if len(row["parts"]) >= 2 and row["parts"][-1] == surname and row["parts"][0].startswith(initial)
        ]
        if out:
            return out, "surname+initial"

    q_set = set(q_parts)
    out = [row for row in indexed if q_set and q_set.issubset(set(row["parts"]))]
    return out, "subset"


def _core4_from_lineup_row(row: dict[str, Any]) -> tuple[int, int, int, int]:
    return (int(row["sp"]), int(row["st"]), int(row["ag"]), int(row["qu"]))


def _core4_from_dd6361(row: dict[str, Any]) -> tuple[int, int, int, int]:
    m = row.get("mapped10") or {}
    return (int(m.get("speed", -1)), int(m.get("stamina", -1)), int(m.get("aggression", -1)), int(m.get("quality", -1)))


def _l1(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    return sum(abs(int(x) - int(y)) for x, y in zip(a, b))


def _build_dd6361_index(player_file: Path) -> list[dict[str, Any]]:
    entries = bio_probe._iter_decoded_entries(player_file)
    markers = bio_probe._collect_bio_markers(entries)
    rows: list[dict[str, Any]] = []
    for idx, marker in enumerate(markers[:-1]):
        name = marker.get("name")
        if not name:
            continue
        cont = bio_probe._assemble_bio_continuation(entries, marker, markers[idx + 1])
        trailer_info = bio_probe._extract_trailer_from_bio_continuation(cont)
        if trailer_info is None:
            continue
        n = str(name)
        rows.append(
            {
                "name": n,
                "name_norm": _norm(n),
                "parts": _norm(n).split(),
                "mapped10": trailer_info["mapped10"],
                "entry_offset": int(marker["entry_offset"]),
                "marker_rel": int(marker["marker_rel"]),
            }
        )
    return rows


def _build_strict_index(player_file: Path) -> dict[str, Any]:
    valid, uncertain = gather_player_records_strict(str(player_file), require_team_id=False, include_subrecords=True)
    rows: list[dict[str, Any]] = []
    for entry in valid + uncertain:
        name = _record_display_name(entry.record).strip()
        if not name:
            continue
        rows.append(
            {
                "offset": int(entry.offset),
                "source": str(entry.source),
                "name": name,
                "name_norm": _norm(name),
                "parts": _norm(name).split(),
                "team_id": int(getattr(entry.record, "team_id", 0) or 0),
                "squad_number": int(getattr(entry.record, "squad_number", 0) or 0),
            }
        )
    return {
        "valid_count": len(valid),
        "uncertain_count": len(uncertain),
        "rows": rows,
    }


def _assess_strict_path(lineup_rows: list[dict[str, Any]], strict_index: dict[str, Any]) -> dict[str, Any]:
    strict_rows = strict_index["rows"]
    summary = Counter()
    details: list[dict[str, Any]] = []

    for row in lineup_rows:
        cands, strategy = _lineup_name_match_candidates(str(row["name"]), strict_rows)
        item = {
            "lineup_name": str(row["name"]),
            "dataset": str(row.get("dataset_key", "")),
            "match_strategy": strategy,
            "candidate_count": len(cands),
            "candidates": [
                {
                    "name": c["name"],
                    "team_id": int(c["team_id"]),
                    "source": c["source"],
                    "squad_number": int(c["squad_number"]),
                    "offset": int(c["offset"]),
                }
                for c in cands[:12]
            ],
        }

        if not cands:
            summary["no_match"] += 1
            item["status"] = "no_match"
        elif len(cands) == 1:
            summary["unique_match"] += 1
            item["status"] = "unique_match"
        else:
            summary["ambiguous_match"] += 1
            item["status"] = "ambiguous_match"

        if cands:
            if any(int(c["team_id"]) != 0 for c in cands):
                summary["rows_with_nonzero_team_id_candidate"] += 1
            else:
                summary["rows_with_only_zero_team_id_candidates"] += 1
        details.append(item)

    return {
        "strict_parser_counts": {
            "valid": int(strict_index["valid_count"]),
            "uncertain": int(strict_index["uncertain_count"]),
            "total": int(strict_index["valid_count"] + strict_index["uncertain_count"]),
        },
        "summary": dict(summary),
        "details": details,
    }


def _assess_dd6361_hybrid(lineup_rows: list[dict[str, Any]], dd6361_rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = Counter()
    details: list[dict[str, Any]] = []

    for row in lineup_rows:
        cands, strategy = _lineup_name_match_candidates(str(row["name"]), dd6361_rows)
        target_core4 = _core4_from_lineup_row(row)
        item: dict[str, Any] = {
            "lineup_name": str(row["name"]),
            "dataset": str(row.get("dataset_key", "")),
            "match_strategy": strategy,
            "target_core4": {
                "speed": target_core4[0],
                "stamina": target_core4[1],
                "aggression": target_core4[2],
                "quality": target_core4[3],
            },
            "candidate_count": len(cands),
        }

        if not cands:
            summary["no_name_match"] += 1
            item["status"] = "no_name_match"
            item["candidates"] = []
            details.append(item)
            continue

        summary["name_matched"] += 1
        if len(cands) == 1:
            summary["name_unique"] += 1
            chosen = cands[0]
            core4_exact = (_core4_from_dd6361(chosen) == target_core4)
            if core4_exact:
                summary["name_unique_core4_exact"] += 1
            else:
                summary["name_unique_core4_mismatch"] += 1
            item["status"] = "name_unique"
            item["resolved_name"] = chosen["name"]
            item["resolved_core4_exact"] = core4_exact
            details.append(item)
            continue

        summary["name_ambiguous"] += 1
        exact = [c for c in cands if _core4_from_dd6361(c) == target_core4]
        cand_payload = []
        for c in cands[:12]:
            core4 = _core4_from_dd6361(c)
            cand_payload.append(
                {
                    "name": c["name"],
                    "core4": {
                        "speed": core4[0],
                        "stamina": core4[1],
                        "aggression": core4[2],
                        "quality": core4[3],
                    },
                    "core4_l1_distance": int(_l1(target_core4, core4)),
                }
            )
        item["candidates"] = cand_payload

        if len(exact) == 1:
            summary["resolved_by_core4_exact"] += 1
            item["status"] = "resolved_by_core4_exact"
            item["resolved_name"] = exact[0]["name"]
        elif len(exact) > 1:
            summary["core4_still_ambiguous"] += 1
            item["status"] = "core4_still_ambiguous"
            item["exact_core4_candidates"] = [c["name"] for c in exact]
        else:
            summary["core4_no_exact_match"] += 1
            item["status"] = "core4_no_exact_match"
        details.append(item)

    return {
        "summary": dict(summary),
        "details": details,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Quantify readiness for programmatic team-player extraction")
    p.add_argument(
        "--player-file",
        default=str(REPO_ROOT / "DBDAT" / "JUG98030.FDI"),
        help="Path to JUG98030.FDI",
    )
    p.add_argument(
        "--datasets",
        nargs="*",
        default=["stoke", "manutd"],
        help="Lineup datasets from scripts/probe_lineup_screenshot.py (default: stoke manutd)",
    )
    p.add_argument("--json-output", help="Write JSON artifact to this path")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    player_file = Path(args.player_file)

    lineup_rows: list[dict[str, Any]] = []
    dataset_counts: dict[str, int] = {}
    for key in args.datasets:
        rows = lineup_probe._dataset_rows(key)
        for row in rows:
            row_copy = dict(row)
            row_copy["dataset_key"] = key
            lineup_rows.append(row_copy)
        dataset_counts[key] = len(rows)

    strict_index = _build_strict_index(player_file)
    dd6361_rows = _build_dd6361_index(player_file)

    strict_assessment = _assess_strict_path(lineup_rows, strict_index)
    dd6361_assessment = _assess_dd6361_hybrid(lineup_rows, dd6361_rows)

    payload = {
        "player_file": str(player_file),
        "datasets": dataset_counts,
        "lineup_row_count_total": len(lineup_rows),
        "strict_path": strict_assessment,
        "dd6361_hybrid_path": dd6361_assessment,
        "interpretation_notes": [
            "strict_path measures direct player-record extraction using the current dd6360-oriented strict parser",
            "dd6361_hybrid_path measures identity resolution only (biography names + mapped core4), not team membership extraction",
            "A high dd6361_hybrid score means name/stat identity extraction is close if team membership can be supplied by another source (PDF/team parser/state record)",
            "A low strict_path/nonzero-team-id score means authoritative direct team roster extraction from current strict parser is not yet close",
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
    raise SystemExit(main(sys.argv[1:]))
