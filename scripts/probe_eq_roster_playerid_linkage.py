#!/usr/bin/env python3
"""Probe EQ98030.FDI roster-table linkage using dd6361 player-id headers.

This probe connects three independently discovered pieces:

1. `JUG98030.FDI` dd6361 biographies expose a stable 16-bit player-id candidate in the
   first two bytes after the dd6361 marker (XOR with 0x61, LE).
2. Lineup screenshots (Stoke + Man Utd currently) provide ground-truth team membership for
   a set of players and core4 stats for identity disambiguation.
3. `EQ98030.FDI` decoded entries contain XOR-encoded 5-byte roster slots of the form:
   [player_id_lo^0x61, player_id_hi^0x61, 0x61, 0x61, 0x61]

Goal: validate the linkage and localize the roster-id tables inside EQ entries.
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

from app.loaders import load_teams  # type: ignore
from app.xor import decode_entry  # type: ignore
from scripts import probe_bio_trailer_stats as bio_probe  # type: ignore
from scripts import probe_lineup_screenshot as lineup_probe  # type: ignore


DATASET_TEAM_NAME_HINTS = {
    "stoke": ["Stoke C", "Stoke City"],
    "manutd": ["Manchester Utd", "Manchester United"],
}


def _norm(text: str) -> str:
    text = " ".join((text or "").split())
    text = re.sub(r"[^A-Za-z0-9' ]+", " ", text)
    return " ".join(text.split()).upper()


def _lineup_name_match_candidates(lineup_name: str, indexed: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    q = _norm(lineup_name)
    q_parts = q.split()
    if not q_parts:
        return [], "empty"

    if len(q_parts) == 1:
        surname = q_parts[0]
        return [row for row in indexed if row["parts"] and row["parts"][-1] == surname], "surname"

    # PM99 lineup abbreviations: "Neville G." -> "NEVILLE G" after normalization.
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
    return [row for row in indexed if q_set and q_set.issubset(set(row["parts"]))], "subset"


def _core4_from_lineup_row(row: dict[str, Any]) -> tuple[int, int, int, int]:
    return (int(row["sp"]), int(row["st"]), int(row["ag"]), int(row["qu"]))


def _core4_from_dd6361(row: dict[str, Any]) -> tuple[int, int, int, int]:
    m = row.get("mapped10") or {}
    return (int(m.get("speed", -1)), int(m.get("stamina", -1)), int(m.get("aggression", -1)), int(m.get("quality", -1)))


def _iter_decoded_fdi_entries(file_path: Path) -> list[tuple[int, int, bytes]]:
    data = file_path.read_bytes()
    out: list[tuple[int, int, bytes]] = []
    offset = 0x400
    data_len = len(data)
    while offset + 2 <= data_len:
        length = int.from_bytes(data[offset:offset + 2], "little")
        if length <= 0 or offset + 2 + length > data_len:
            offset += 1
            continue
        try:
            decoded, _ = decode_entry(data, offset)
        except Exception:
            offset += 1
            continue
        out.append((offset, length, decoded))
        offset += length + 2
    return out


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
        entry_idx = int(marker["entry_idx"])
        entry_offset = int(marker["entry_offset"])
        marker_rel = int(marker["marker_rel"])
        decoded_entry = entries[entry_idx][1]
        header4_raw = decoded_entry[marker_rel + 3: marker_rel + 7]
        if len(header4_raw) < 4:
            continue
        header4_xor = [int(b ^ 0x61) for b in header4_raw]
        player_id_candidate = int(header4_xor[0] | (header4_xor[1] << 8))
        rows.append(
            {
                "name": str(name),
                "name_norm": _norm(str(name)),
                "parts": _norm(str(name)).split(),
                "mapped10": trailer_info["mapped10"],
                "entry_offset": entry_offset,
                "marker_rel": marker_rel,
                "header4_raw": list(header4_raw),
                "header4_xor": header4_xor,
                "dd6361_player_id_candidate": player_id_candidate,
                "dd6361_header_slot_candidate": int(header4_xor[2]),
                "dd6361_header_len_candidate": int(header4_xor[3]),
            }
        )
    return rows


def _pid_uniqueness_summary(dd6361_rows: list[dict[str, Any]]) -> dict[str, Any]:
    pid_to_names: dict[int, list[str]] = {}
    for row in dd6361_rows:
        pid = int(row["dd6361_player_id_candidate"])
        pid_to_names.setdefault(pid, []).append(str(row["name"]))
    duplicate_items = [
        {"pid": int(pid), "names": names}
        for pid, names in pid_to_names.items()
        if len(names) > 1
    ]
    duplicate_items.sort(key=lambda item: (-(len(item["names"])), int(item["pid"])))
    return {
        "dd6361_rows_with_pid": len(dd6361_rows),
        "unique_pid_count": len(pid_to_names),
        "duplicate_pid_count": len(duplicate_items),
        "duplicate_pid_examples": duplicate_items[:12],
    }


def _resolve_lineup_anchors(dataset_key: str, dd6361_rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = lineup_probe._dataset_rows(dataset_key)
    resolved: list[dict[str, Any]] = []
    summary = Counter()

    for row in rows:
        cands, strategy = _lineup_name_match_candidates(str(row["name"]), dd6361_rows)
        target_core4 = _core4_from_lineup_row(row)
        exact = [c for c in cands if _core4_from_dd6361(c) == target_core4]
        detail: dict[str, Any] = {
            "lineup_row": {
                "n": int(row["n"]),
                "name": str(row["name"]),
                "sp": int(row["sp"]),
                "st": int(row["st"]),
                "ag": int(row["ag"]),
                "qu": int(row["qu"]),
                "rol": int(row["rol"]),
                "pos": str(row["pos"]),
                "section": str(row.get("section", "")),
            },
            "match_strategy": strategy,
            "candidate_count": len(cands),
            "exact_core4_candidate_count": len(exact),
        }

        chosen = None
        status = "no_match"
        if len(exact) == 1:
            chosen = exact[0]
            status = "resolved_by_core4_exact"
        elif len(cands) == 1:
            chosen = cands[0]
            status = "name_unique_only"
        elif len(exact) > 1:
            status = "exact_core4_ambiguous"
        elif len(cands) > 1:
            status = "name_ambiguous"

        summary[status] += 1
        if chosen is not None:
            detail["resolved_dd6361"] = {
                "name": str(chosen["name"]),
                "entry_offset": int(chosen["entry_offset"]),
                "marker_rel": int(chosen["marker_rel"]),
                "dd6361_player_id_candidate": int(chosen["dd6361_player_id_candidate"]),
                "header4_raw": list(chosen["header4_raw"]),
                "header4_xor": list(chosen["header4_xor"]),
            }
        detail["status"] = status
        resolved.append(detail)

    return {
        "dataset_key": dataset_key,
        "lineup_row_count": len(rows),
        "summary": dict(summary),
        "rows": resolved,
    }


def _xor_le16_bytes(value: int) -> bytes:
    lo = value & 0xFF
    hi = (value >> 8) & 0xFF
    return bytes([lo ^ 0x61, hi ^ 0x61])


def _entry_hit_rows(
    eq_entries: list[tuple[int, int, bytes]],
    player_ids: list[int],
) -> list[dict[str, Any]]:
    patterns = {int(pid): _xor_le16_bytes(int(pid)) for pid in player_ids}
    out: list[dict[str, Any]] = []
    for entry_offset, length, decoded in eq_entries:
        hits: list[dict[str, Any]] = []
        for pid, pat in patterns.items():
            pos = decoded.find(pat)
            if pos != -1:
                row5 = decoded[pos:pos + 5]
                hits.append(
                    {
                        "pid": int(pid),
                        "pos": int(pos),
                        "row5_raw_hex": row5.hex(),
                        "row5_tail_is_616161": bool(len(row5) == 5 and row5[2:] == b"\x61\x61\x61"),
                        "row5_xor": [int(b ^ 0x61) for b in row5] if len(row5) == 5 else None,
                    }
                )
        if hits:
            hits.sort(key=lambda r: int(r["pos"]))
            out.append(
                {
                    "entry_offset": int(entry_offset),
                    "length": int(length),
                    "hit_count": len(hits),
                    "hits": hits,
                }
            )
    out.sort(key=lambda r: (-int(r["hit_count"]), int(r["entry_offset"])))
    return out


def _extract_stride5_window(decoded: bytes, hit_positions: list[int]) -> dict[str, Any]:
    if not hit_positions:
        return {"rows": [], "alignment_mod5": None}
    mod_counts = Counter(int(p) % 5 for p in hit_positions)
    align_mod = mod_counts.most_common(1)[0][0]
    min_hit = min(hit_positions)
    max_hit = max(hit_positions)

    start = min_hit
    while start % 5 != align_mod and start > 0:
        start -= 1
    end = max_hit
    while end % 5 != align_mod and end < len(decoded) - 1:
        end += 1

    rows: list[dict[str, Any]] = []
    for pos in range(start, min(len(decoded) - 4, end + 5), 5):
        row5 = decoded[pos:pos + 5]
        if len(row5) < 5:
            continue
        if row5[2:] != b"\x61\x61\x61":
            continue
        pid = (row5[0] ^ 0x61) | ((row5[1] ^ 0x61) << 8)
        rows.append(
            {
                "pos": int(pos),
                "row5_raw_hex": row5.hex(),
                "pid_candidate": int(pid),
                "is_empty_slot": bool(row5 == b"\x61\x61\x61\x61\x61"),
            }
        )
    return {
        "alignment_mod5": int(align_mod),
        "min_hit_pos": int(min_hit),
        "max_hit_pos": int(max_hit),
        "rows": rows,
    }


def _find_stride5_roster_runs(decoded: bytes, min_rows: int = 8) -> list[dict[str, Any]]:
    """Find contiguous stride-5 runs of row5 slots ending with 0x61 0x61 0x61."""
    positions = [pos for pos in range(0, max(0, len(decoded) - 4)) if decoded[pos + 2:pos + 5] == b"\x61\x61\x61"]
    pos_set = set(positions)
    seen: set[int] = set()
    runs: list[dict[str, Any]] = []

    for pos in positions:
        if pos in seen or (pos - 5) in pos_set:
            continue
        cur = pos
        row_positions: list[int] = []
        while cur in pos_set:
            seen.add(cur)
            row_positions.append(cur)
            cur += 5
        if len(row_positions) < min_rows:
            continue
        non_empty_count = 0
        for p in row_positions:
            row5 = decoded[p:p + 5]
            if row5 != b"\x61\x61\x61\x61\x61":
                non_empty_count += 1
        runs.append(
            {
                "start_pos": int(row_positions[0]),
                "end_pos": int(row_positions[-1]),
                "row_count": int(len(row_positions)),
                "non_empty_row_count": int(non_empty_count),
            }
        )
    return runs


def _find_team_record_matches(dataset_key: str, teams: list[tuple[int, Any]]) -> list[dict[str, Any]]:
    hints = DATASET_TEAM_NAME_HINTS.get(dataset_key, [])
    out: list[dict[str, Any]] = []
    for offset, team in teams:
        name = str(getattr(team, "name", "") or "")
        full = str(getattr(team, "full_club_name", "") or "")
        text = f"{name} {full}".lower()
        if hints and not any(h.lower() in text for h in hints):
            continue
        out.append(
            {
                "offset": int(offset),
                "name": name,
                "full_club_name": full or None,
                "team_id": int(getattr(team, "team_id", 0) or 0),
                "raw_len": len(bytes(getattr(team, "raw_data", b"") or b"")),
            }
        )
    return out


def _containing_entries(eq_entries: list[tuple[int, int, bytes]], file_offset: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry_offset, length, _decoded in eq_entries:
        if (entry_offset + 2) <= file_offset < (entry_offset + 2 + length):
            out.append({"entry_offset": int(entry_offset), "length": int(length)})
    return out


def _global_roster_run_entry_summary(
    eq_entries: list[tuple[int, int, bytes]],
    teams: list[tuple[int, Any]],
    min_run_rows: int = 8,
) -> list[dict[str, Any]]:
    """Summarize decoded EQ entries that look like roster-table containers."""
    entry_to_team_rows: dict[int, list[tuple[int, Any]]] = {}
    for team_offset, team in teams:
        for entry_offset, length, _decoded in eq_entries:
            if (entry_offset + 2) <= int(team_offset) < (entry_offset + 2 + int(length)):
                entry_to_team_rows.setdefault(int(entry_offset), []).append((int(team_offset), team))
                break

    out: list[dict[str, Any]] = []
    for entry_offset, length, decoded in eq_entries:
        runs = _find_stride5_roster_runs(decoded, min_rows=min_run_rows)
        if not runs:
            continue
        team_rows = entry_to_team_rows.get(int(entry_offset), [])
        team_names = [str(getattr(team, "name", "") or "") for (_off, team) in team_rows]
        out.append(
            {
                "entry_offset": int(entry_offset),
                "length": int(length),
                "roster_run_count": int(len(runs)),
                "roster_runs": runs,
                "team_subrecord_count": int(len(team_rows)),
                "team_subrecord_offsets": [int(off) for (off, _team) in team_rows],
                "team_subrecord_names_preview": team_names[:12],
            }
        )
    out.sort(key=lambda r: (-int(r["roster_run_count"]), int(r["entry_offset"])))
    return out


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Probe EQ roster ID tables using dd6361 player-id candidates")
    p.add_argument(
        "--player-file",
        default=str(REPO_ROOT / "DBDAT" / "JUG98030.FDI"),
        help="Path to JUG98030.FDI",
    )
    p.add_argument(
        "--team-file",
        default=str(REPO_ROOT / "DBDAT" / "EQ98030.FDI"),
        help="Path to EQ98030.FDI",
    )
    p.add_argument(
        "--lineup-dataset",
        action="append",
        default=[],
        help="Lineup dataset key(s) from probe_lineup_screenshot.py (default: stoke, manutd)",
    )
    p.add_argument("--json-output", help="Write JSON output to this path")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    player_file = Path(args.player_file)
    team_file = Path(args.team_file)
    if not player_file.exists():
        print(json.dumps({"error": f"Player file not found: {player_file}"}, indent=2))
        return 2
    if not team_file.exists():
        print(json.dumps({"error": f"Team file not found: {team_file}"}, indent=2))
        return 2

    dataset_keys = [str(k).strip().lower() for k in (args.lineup_dataset or []) if str(k).strip()]
    if not dataset_keys:
        dataset_keys = ["stoke", "manutd"]

    dd6361_rows = _build_dd6361_index(player_file)
    pid_uniqueness = _pid_uniqueness_summary(dd6361_rows)
    dd6361_pid_to_name = {
        int(row["dd6361_player_id_candidate"]): str(row["name"])
        for row in dd6361_rows
    }
    eq_entries = _iter_decoded_fdi_entries(team_file)
    teams = list(load_teams(str(team_file)))
    global_roster_run_summary = _global_roster_run_entry_summary(eq_entries, teams, min_run_rows=8)

    dataset_results: dict[str, Any] = {}
    for key in dataset_keys:
        anchor_data = _resolve_lineup_anchors(key, dd6361_rows)
        exact_rows = [
            row for row in anchor_data["rows"]
            if row.get("status") == "resolved_by_core4_exact" and isinstance(row.get("resolved_dd6361"), dict)
        ]
        pid_to_anchor: dict[int, dict[str, Any]] = {
            int(row["resolved_dd6361"]["dd6361_player_id_candidate"]): row for row in exact_rows
        }
        entry_hits = _entry_hit_rows(eq_entries, sorted(pid_to_anchor.keys()))

        top_entry_summary = None
        if entry_hits:
            top = entry_hits[0]
            entry_offset = int(top["entry_offset"])
            decoded = next(decoded for (off, _ln, decoded) in eq_entries if int(off) == entry_offset)
            hit_positions = [int(h["pos"]) for h in top["hits"]]
            stride_window = _extract_stride5_window(decoded, hit_positions)
            top_entry_summary = {
                "entry_offset": entry_offset,
                "entry_length": int(top["length"]),
                "hit_count": int(top["hit_count"]),
                "all_hits_tail_616161": all(bool(h["row5_tail_is_616161"]) for h in top["hits"]),
                "hits": [
                    {
                        **h,
                        "anchor_lineup_name": pid_to_anchor.get(int(h["pid"]), {}).get("lineup_row", {}).get("name"),
                        "anchor_lineup_n": pid_to_anchor.get(int(h["pid"]), {}).get("lineup_row", {}).get("n"),
                        "anchor_lineup_rol": pid_to_anchor.get(int(h["pid"]), {}).get("lineup_row", {}).get("rol"),
                        "anchor_lineup_pos": pid_to_anchor.get(int(h["pid"]), {}).get("lineup_row", {}).get("pos"),
                        "anchor_bio_name": pid_to_anchor.get(int(h["pid"]), {}).get("resolved_dd6361", {}).get("name"),
                    }
                    for h in top["hits"]
                ],
                "stride5_window": stride_window,
            }
            # Annotate stride rows with dd6361 names and anchor flags for easier inspection.
            anchor_pid_set = set(pid_to_anchor.keys())
            for stride_row in top_entry_summary["stride5_window"]["rows"]:
                pid = int(stride_row["pid_candidate"])
                stride_row["dd6361_name"] = dd6361_pid_to_name.get(pid)
                stride_row["is_anchor_pid"] = bool(pid in anchor_pid_set)
            # Positional stride evidence (expected 5-byte spacing in discovered roster list windows).
            pos_list = [int(r["pos"]) for r in top_entry_summary["stride5_window"]["rows"]]
            top_entry_summary["stride5_window"]["delta_positions"] = [
                int(pos_list[i + 1] - pos_list[i]) for i in range(len(pos_list) - 1)
            ]

        target_team_records = _find_team_record_matches(key, teams)
        for tr in target_team_records:
            tr["containing_entries"] = _containing_entries(eq_entries, int(tr["offset"]))
            raw = bytes(
                next(team.raw_data for (off, team) in teams if int(off) == int(tr["offset"]))  # type: ignore[attr-defined]
            )
            pats = [_xor_le16_bytes(pid) for pid in pid_to_anchor.keys()]
            tr["xor_pid_hit_count_in_team_raw_data"] = int(sum(1 for p in pats if p in raw))
            tr["raw_pid_hit_count_in_team_raw_data"] = int(sum(1 for pid in pid_to_anchor.keys() if int(pid).to_bytes(2, "little") in raw))

        dataset_results[key] = {
            "anchor_resolution": anchor_data,
            "exact_anchor_count": len(exact_rows),
            "eq_entry_hit_candidates_top10": [
                {
                    "entry_offset": int(r["entry_offset"]),
                    "length": int(r["length"]),
                    "hit_count": int(r["hit_count"]),
                }
                for r in entry_hits[:10]
            ],
            "top_eq_entry": top_entry_summary,
            "target_team_records": target_team_records,
        }

    payload = {
        "player_file": str(player_file),
        "team_file": str(team_file),
        "lineup_datasets": dataset_keys,
        "dd6361_bio_rows_indexed": len(dd6361_rows),
        "dd6361_pid_uniqueness": pid_uniqueness,
        "eq_decoded_entry_count": len(eq_entries),
        "global_roster_run_entry_summary_top20": global_roster_run_summary[:20],
        "dataset_results": dataset_results,
        "notes": [
            "dd6361 player-id candidate is derived from the first two bytes after dd6361, XOR with 0x61, little-endian.",
            "This probe only uses lineup rows that resolve to a unique dd6361 candidate by exact core4 match.",
            "EQ roster-table hits are searched as XOR-encoded LE16 player IDs.",
            "A strong signal is a decoded EQ row5 pattern ending with 0x61 0x61 0x61 (three padding bytes after the ID).",
            "A unique dd6361 PID across the corpus allows these roster-table rows to map back to dd6361 player names directly.",
            "global_roster_run_entry_summary lists decoded EQ entries containing long stride-5 roster-table runs and the team subrecords (if any) that share those entries.",
            "This localizes team roster membership tables, but generic team->roster-block mapping is still unresolved.",
        ],
    }

    text = json.dumps(payload, indent=2)
    if args.json_output:
        out_path = Path(args.json_output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
