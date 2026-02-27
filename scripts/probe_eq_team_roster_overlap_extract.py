#!/usr/bin/env python3
"""Extract team rosters from EQ98030.FDI using same-entry overlap with roster-ID runs.

This probe builds on the validated discovery that many decoded EQ entries contain stride-5
roster tables with XOR-encoded dd6361 player IDs. For most teams, the team's parsed EQ
subrecord raw bytes contain the same XOR-encoded IDs for its roster table, allowing a
same-entry overlap match without lineup anchors.

Current intent:
- quantify same-entry extraction coverage across all parsed teams
- extract roster rows (player IDs + dd6361 names where available) for selected teams
- clearly surface split-entry / weak-match cases (e.g. Manchester Utd)
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import sys
from pathlib import Path
from statistics import median
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.editor_helpers import team_query_matches  # type: ignore
from app.loaders import load_teams  # type: ignore
from scripts import probe_eq_roster_playerid_linkage as eq_link  # type: ignore


def _xor_le16_bytes(value: int) -> bytes:
    lo = value & 0xFF
    hi = (value >> 8) & 0xFF
    return bytes([lo ^ 0x61, hi ^ 0x61])


def _extract_roster_rows_from_run(decoded: bytes, run: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = int(run["start_pos"])
    end = int(run["end_pos"])
    for pos in range(start, end + 1, 5):
        row5 = decoded[pos:pos + 5]
        if len(row5) < 5:
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
    return rows


def _team_name_matches_query(team: Any, query: str) -> bool:
    return team_query_matches(
        query,
        team_name=str(getattr(team, "name", "") or ""),
        full_club_name=str(getattr(team, "full_club_name", "") or ""),
    )


def _match_known_lineup_dataset_for_team(team_name: str, full_club_name: str | None) -> str | None:
    text = f"{team_name} {full_club_name or ''}".lower()
    for dataset_key, hints in eq_link.DATASET_TEAM_NAME_HINTS.items():
        if any(str(h).lower() in text for h in list(hints or [])):
            return str(dataset_key)
    return None


def _classify_match(top_hits: int, run_len: int, second_hits: int) -> str:
    if top_hits <= 0:
        return "no_same_entry_overlap_hits"
    if top_hits == run_len and top_hits > max(1, second_hits):
        return "perfect_same_entry_run_overlap"
    if top_hits >= max(8, run_len - 2) and (top_hits - second_hits) >= 2:
        return "strong_same_entry_run_overlap"
    if top_hits >= 5:
        return "moderate_same_entry_overlap"
    return "weak_same_entry_overlap"


def _build_dd6361_pid_map(player_file: Path) -> dict[int, str]:
    dd6361_rows = eq_link._build_dd6361_index(player_file)
    # Latest probe evidence shows uniqueness for extracted rows in this corpus.
    return {int(row["dd6361_player_id_candidate"]): str(row["name"]) for row in dd6361_rows}


def _build_entry_team_index(eq_entries: list[tuple[int, int, bytes]], teams: list[tuple[int, Any]]) -> dict[int, list[tuple[int, Any]]]:
    out: dict[int, list[tuple[int, Any]]] = {}
    for team_offset, team in teams:
        for entry_offset, length, _decoded in eq_entries:
            if (entry_offset + 2) <= int(team_offset) < (entry_offset + 2 + int(length)):
                out.setdefault(int(entry_offset), []).append((int(team_offset), team))
                break
    for entry_offset in list(out.keys()):
        out[entry_offset].sort(key=lambda item: item[0])
    return out


def _team_text(team: Any) -> str:
    name = str(getattr(team, "name", "") or "")
    full = str(getattr(team, "full_club_name", "") or "")
    stadium = str(getattr(team, "stadium", "") or "")
    return f"{name} {full} {stadium}".lower()


def _is_brandlike_upper_token(text: str) -> bool:
    s = (text or "").strip()
    if not s or len(s) > 28:
        return False
    if not re.fullmatch(r"[A-Z0-9 .&'/-]+", s):
        return False
    letters = sum(1 for c in s if c.isalpha())
    uppers = sum(1 for c in s if c.isupper())
    return letters > 0 and uppers >= max(1, letters - 1)


def _looks_club_like_text(text: str) -> bool:
    t = (text or "").lower()
    club_tokens = [
        "club",
        "united",
        "city",
        "town",
        "athletic",
        "rovers",
        "county",
        "hotspur",
        "wanderers",
        "fc",
        "c.f",
        "u.d",
        "real ",
        "sporting",
    ]
    return any(tok in t for tok in club_tokens)


def _is_obvious_pseudo_team_record(team: Any) -> bool:
    """
    Conservative classifier for parsed EQ subrecords that are not real club teams.

    Current local examples:
    - ELONEX (stadium field carries kit brand 'LOTTO')
    - SANDERSON ELECTRONICS (stadium field carries kit brand 'PUMA')
    - Free players (utility/non-club bucket)
    """
    name = str(getattr(team, "name", "") or "")
    full = str(getattr(team, "full_club_name", "") or "")
    stadium = str(getattr(team, "stadium", "") or "")
    capacity = int(getattr(team, "capacity", 0) or 0)
    chairman = getattr(team, "chairman", None)
    shirt_sponsor = getattr(team, "shirt_sponsor", None)
    kit_supplier = getattr(team, "kit_supplier", None)
    normalized_name = " ".join(name.lower().split())

    if normalized_name in {"free players", "free player"}:
        return True

    if capacity != 0:
        return False
    if any(v for v in (chairman, shirt_sponsor, kit_supplier)):
        return False
    if not _is_brandlike_upper_token(name):
        return False
    if not _is_brandlike_upper_token(stadium):
        return False
    if _looks_club_like_text(name):
        return False
    if full and _looks_club_like_text(full):
        return False
    return True


def _build_known_lineup_anchor_pid_sets(player_file: Path) -> dict[str, dict[str, Any]]:
    """
    Build small known anchor PID sets from transcribed lineup screenshot datasets.

    These are used only as heuristic guards for circular-shift candidate runs. They are not
    comprehensive and should never be treated as authoritative roster mappings.
    """
    out: dict[str, dict[str, Any]] = {}
    try:
        dd6361_rows = eq_link._build_dd6361_index(player_file)
        dataset_keys = sorted(eq_link.DATASET_TEAM_NAME_HINTS.keys())
        for dataset_key in dataset_keys:
            anchor_data = eq_link._resolve_lineup_anchors(dataset_key, dd6361_rows)
            pids = {
                int(row["resolved_dd6361"]["dd6361_player_id_candidate"])
                for row in list(anchor_data.get("rows") or [])
                if row.get("status") == "resolved_by_core4_exact" and isinstance(row.get("resolved_dd6361"), dict)
            }
            if not pids:
                continue
            out[str(dataset_key)] = {
                "pid_set": pids,
                "pid_count": len(pids),
                "team_hints": list(eq_link.DATASET_TEAM_NAME_HINTS.get(dataset_key, [])),
            }
    except Exception:
        # Keep extraction robust if the anchor helper path breaks; this is only a guardrail.
        return {}
    return out


def _build_known_lineup_anchor_assisted_match(
    *,
    dataset_key: str,
    player_file: Path,
    eq_entries: list[tuple[int, int, bytes]],
    dd6361_pid_to_name: dict[int, str],
    dd6361_rows_cache: dict[str, Any],
) -> dict[str, Any] | None:
    """Build an anchor-assisted roster window for a known lineup dataset (e.g. Man Utd)."""
    if "dd6361_rows" not in dd6361_rows_cache:
        dd6361_rows_cache["dd6361_rows"] = eq_link._build_dd6361_index(player_file)
    dd6361_rows = list(dd6361_rows_cache.get("dd6361_rows") or [])

    anchor_data = eq_link._resolve_lineup_anchors(dataset_key, dd6361_rows)
    exact_rows = [
        row
        for row in list(anchor_data.get("rows") or [])
        if row.get("status") == "resolved_by_core4_exact" and isinstance(row.get("resolved_dd6361"), dict)
    ]
    if not exact_rows:
        return None

    pid_to_anchor = {
        int(row["resolved_dd6361"]["dd6361_player_id_candidate"]): row
        for row in exact_rows
    }
    entry_hits = eq_link._entry_hit_rows(eq_entries, sorted(pid_to_anchor.keys()))
    if not entry_hits:
        return None

    top = dict(entry_hits[0])
    entry_offset = int(top["entry_offset"])
    decoded = next(decoded for (off, _ln, decoded) in eq_entries if int(off) == entry_offset)
    hit_positions = [int(h["pos"]) for h in list(top.get("hits") or [])]
    stride_window = eq_link._extract_stride5_window(decoded, hit_positions)
    anchor_pid_set = set(pid_to_anchor.keys())
    for stride_row in list(stride_window.get("rows") or []):
        pid = int(stride_row.get("pid_candidate", 0))
        stride_row["dd6361_name"] = dd6361_pid_to_name.get(pid)
        stride_row["is_anchor_pid"] = bool(pid in anchor_pid_set)
    pos_list = [int(r["pos"]) for r in list(stride_window.get("rows") or [])]
    stride_window["delta_positions"] = [int(pos_list[i + 1] - pos_list[i]) for i in range(len(pos_list) - 1)]

    return {
        "dataset_key": str(dataset_key),
        "selection_method": "known_lineup_anchor_assisted",
        "exact_anchor_count": int(len(exact_rows)),
        "anchor_resolution_summary": dict(anchor_data.get("summary") or {}),
        "entry_offset": int(entry_offset),
        "entry_length": int(top.get("length", 0)),
        "hit_count": int(top.get("hit_count", 0)),
        "all_hits_tail_616161": all(bool(h.get("row5_tail_is_616161")) for h in list(top.get("hits") or [])),
        "stride5_window": stride_window,
        "hits_preview": [
            {
                "pid": int(h.get("pid", 0)),
                "pos": int(h.get("pos", 0)),
                "anchor_lineup_name": pid_to_anchor.get(int(h.get("pid", 0)), {}).get("lineup_row", {}).get("name"),
                "anchor_bio_name": pid_to_anchor.get(int(h.get("pid", 0)), {}).get("resolved_dd6361", {}).get("name"),
            }
            for h in list(top.get("hits") or [])[:24]
        ],
    }


def _apply_circular_shift_same_entry_fallback(
    *,
    all_results: list[dict[str, Any]],
    teams: list[tuple[int, Any]],
    eq_entries: list[tuple[int, int, bytes]],
    entry_runs_index: dict[int, list[dict[str, Any]]],
    dd6361_pid_to_name: dict[int, str],
    known_lineup_anchor_pid_sets: dict[str, dict[str, Any]] | None = None,
) -> dict[str, int]:
    """
    Recover weak/no-hit same-entry teams when an entry follows a stable circular run-order shift.

    Many decoded EQ entries have team subrecords ordered the same way as roster runs, but with a
    one-slot circular offset (e.g. team_idx -> run_idx + 1, and the final team wraps to run 0).
    This fallback only applies when:
    - team count == roster-run count for the containing entry
    - perfect/strong anchors strongly support a single circular shift
    - the predicted run length looks plausible relative to anchored runs in the same entry
    """
    results_by_team_offset = {int(r.get("team_offset", -1)): r for r in all_results if isinstance(r.get("team_offset"), int)}
    decoded_by_entry = {int(off): decoded for (off, _ln, decoded) in eq_entries}
    entry_team_index = _build_entry_team_index(eq_entries, teams)
    anchored_statuses = {"perfect_same_entry_run_overlap", "strong_same_entry_run_overlap"}
    eligible_statuses = {"weak_same_entry_overlap", "no_same_entry_overlap_hits"}
    applied = 0
    flagged_anchor_collision = 0
    known_lineup_anchor_pid_sets = dict(known_lineup_anchor_pid_sets or {})

    for entry_offset, team_rows in entry_team_index.items():
        runs = list(entry_runs_index.get(int(entry_offset), []))
        if not runs:
            continue
        if len(team_rows) != len(runs):
            # Circular-shift fallback is only safe on one-team-per-run entries.
            continue
        decoded = decoded_by_entry.get(int(entry_offset))
        if decoded is None:
            continue

        seq_rows: list[dict[str, Any]] = []
        for team_idx, (team_offset, team) in enumerate(team_rows):
            result = results_by_team_offset.get(int(team_offset))
            if result is None:
                continue
            top = dict(result.get("top_run_match") or {})
            seq_rows.append(
                {
                    "team_idx": int(team_idx),
                    "team_offset": int(team_offset),
                    "team_obj": team,
                    "result": result,
                    "status": str(result.get("status") or ""),
                    "top_run_index": (int(top["run_index"]) if "run_index" in top else None),
                    "top_run_overlap_hits": int(top.get("overlap_hits_in_team_raw", 0)),
                    "top_run_non_empty_row_count": int(top.get("non_empty_row_count", 0)),
                }
            )

        anchors = [
            row for row in seq_rows
            if row["status"] in anchored_statuses and isinstance(row["top_run_index"], int)
        ]
        if len(anchors) < max(3, len(runs) // 3):
            continue

        # Find a shift k where run_idx ~= (team_idx + k) % n for nearly all anchors.
        run_count = len(runs)
        best_shift = 0
        best_score = -1
        for shift in range(run_count):
            score = sum(
                1
                for row in anchors
                if int(row["top_run_index"]) == ((int(row["team_idx"]) + shift) % run_count)
            )
            if score > best_score:
                best_score = score
                best_shift = shift
        if best_score < (len(anchors) - 1):
            continue

        anchor_sizes = [int(row["top_run_non_empty_row_count"]) for row in anchors if int(row["top_run_non_empty_row_count"]) > 0]
        anchor_median = int(median(anchor_sizes)) if anchor_sizes else 0
        min_plausible = max(8, anchor_median - 10)
        max_plausible = max(min_plausible, anchor_median + 10)

        anchor_run_indices = {int(row["top_run_index"]) for row in anchors}
        fallback_assigned_runs: set[int] = set()

        for row in seq_rows:
            if row["status"] not in eligible_statuses:
                continue
            # Avoid overriding moderate same-entry evidence; keep this fallback conservative.
            if int(row["top_run_overlap_hits"]) > 2:
                continue

            predicted_run_index = (int(row["team_idx"]) + best_shift) % run_count
            if predicted_run_index in anchor_run_indices or predicted_run_index in fallback_assigned_runs:
                continue

            predicted_run = runs[predicted_run_index]
            run_non_empty = int(predicted_run.get("non_empty_row_count", 0))
            if not (min_plausible <= run_non_empty <= max_plausible):
                continue

            team_obj = row["team_obj"]
            team_raw = bytes(getattr(team_obj, "raw_data", b"") or b"")
            candidate_pid_set: set[int] = set()
            roster_rows = []
            for rr in _extract_roster_rows_from_run(decoded, predicted_run):
                pid = int(rr["pid_candidate"])
                if not rr["is_empty_slot"]:
                    candidate_pid_set.add(pid)
                roster_rows.append(
                    {
                        **rr,
                        "dd6361_name": dd6361_pid_to_name.get(pid),
                        "xor_pid_found_in_team_raw": bool(_xor_le16_bytes(pid) in team_raw),
                    }
                )

            order_fallback_match = {
                "run_index": int(predicted_run_index),
                "start_pos": int(predicted_run.get("start_pos", 0)),
                "end_pos": int(predicted_run.get("end_pos", 0)),
                "row_count": int(predicted_run.get("row_count", 0)),
                "non_empty_row_count": run_non_empty,
                "rows": roster_rows,
                "selection_method": "circular_shift_same_entry",
                "predicted_from_team_index": int(row["team_idx"]),
                "entry_shift": int(best_shift),
            }
            warnings: list[dict[str, Any]] = []
            team_text = _team_text(team_obj)
            for dataset_key, meta in known_lineup_anchor_pid_sets.items():
                anchor_pid_set = set(meta.get("pid_set") or set())
                if not anchor_pid_set:
                    continue
                if any(str(h).lower() in team_text for h in list(meta.get("team_hints") or [])):
                    continue
                overlap = len(candidate_pid_set & anchor_pid_set)
                min_flag_overlap = max(6, min(int(meta.get("pid_count") or len(anchor_pid_set)), 12))
                if overlap >= min_flag_overlap:
                    warnings.append(
                        {
                            "type": "known_lineup_anchor_collision",
                            "dataset_key": str(dataset_key),
                            "anchor_pid_overlap": int(overlap),
                            "anchor_pid_count": int(meta.get("pid_count") or len(anchor_pid_set)),
                            "message": (
                                f"Candidate run overlaps known lineup anchor '{dataset_key}' "
                                f"({overlap}/{int(meta.get('pid_count') or len(anchor_pid_set))} anchor PIDs)"
                            ),
                        }
                    )

            result = row["result"]
            result["order_fallback_match"] = order_fallback_match
            result["circular_shift_candidate_match"] = order_fallback_match
            result["circular_shift_candidate_status"] = "order_fallback_circular_shift_same_entry_run"
            if warnings:
                result["heuristic_warnings"] = warnings
                flagged_anchor_collision += 1
            result["order_fallback_reason"] = {
                "method": "circular_shift_same_entry",
                "entry_offset": int(entry_offset),
                "entry_run_count": int(run_count),
                "entry_team_count": int(len(team_rows)),
                "entry_shift": int(best_shift),
                "shift_anchor_score": int(best_score),
                "shift_anchor_count": int(len(anchors)),
                "anchor_non_empty_row_median": int(anchor_median),
                "predicted_run_non_empty_row_count": int(run_non_empty),
            }
            fallback_assigned_runs.add(int(predicted_run_index))
            applied += 1

    return {
        "candidate_count": int(applied),
        "flagged_anchor_collision_count": int(flagged_anchor_collision),
    }


def _apply_adjacent_pseudo_team_reassignment_candidates(
    *,
    all_results: list[dict[str, Any]],
    teams: list[tuple[int, Any]],
    eq_entries: list[tuple[int, int, bytes]],
) -> dict[str, int]:
    """
    If an obvious pseudo-team record (e.g. sponsor brand) has a strong roster run match, attach that
    run as a provisional candidate to the immediately preceding real club in the same entry.

    This addresses parser artifacts like Wimbledon/ELONEX and Sheffield W/SANDERSON ELECTRONICS,
    where the pseudo record appears to consume the roster run that belongs to the adjacent club.
    """
    results_by_team_offset = {int(r.get("team_offset", -1)): r for r in all_results if isinstance(r.get("team_offset"), int)}
    team_by_offset = {int(off): team for (off, team) in teams}
    entry_team_index = _build_entry_team_index(eq_entries, teams)
    strong_statuses = {"perfect_same_entry_run_overlap", "strong_same_entry_run_overlap"}
    receiver_statuses = {"weak_same_entry_overlap", "no_same_entry_overlap_hits", "moderate_same_entry_overlap"}

    attached = 0
    pseudo_record_count = 0

    for _entry_offset, ordered_teams in entry_team_index.items():
        for idx, (team_offset, team_obj) in enumerate(ordered_teams):
            if not _is_obvious_pseudo_team_record(team_obj):
                continue
            pseudo_record_count += 1
            pseudo_result = results_by_team_offset.get(int(team_offset))
            if not pseudo_result:
                continue
            if str(pseudo_result.get("status") or "") not in strong_statuses:
                continue
            pseudo_top = dict(pseudo_result.get("top_run_match") or {})
            if not pseudo_top:
                continue
            if idx <= 0:
                continue
            prev_offset, prev_team_obj = ordered_teams[idx - 1]
            if _is_obvious_pseudo_team_record(prev_team_obj):
                continue
            prev_result = results_by_team_offset.get(int(prev_offset))
            if not prev_result:
                continue
            if str(prev_result.get("status") or "") not in receiver_statuses:
                continue
            # Avoid overwriting stronger paths that may already exist.
            if isinstance(prev_result.get("known_lineup_anchor_assisted_match"), dict):
                continue

            candidate = {
                **pseudo_top,
                "selection_method": "adjacent_pseudo_team_record_reassignment",
                "source_pseudo_team_name": str(getattr(team_obj, "name", "") or ""),
                "source_pseudo_team_offset": int(team_offset),
                "source_pseudo_team_stadium_field": (str(getattr(team_obj, "stadium", "") or "") or None),
            }
            prev_result["adjacent_pseudo_team_reassignment_candidate"] = candidate
            prev_warnings = list(prev_result.get("heuristic_warnings") or [])
            prev_warnings.append(
                {
                    "type": "adjacent_pseudo_team_record_reassignment",
                    "message": (
                        f"Adjacent pseudo-team record '{str(getattr(team_obj, 'name', '') or '')}' "
                        "has a strong roster match; candidate run copied for review"
                    ),
                    "source_pseudo_team_name": str(getattr(team_obj, "name", "") or ""),
                    "source_pseudo_team_offset": int(team_offset),
                }
            )
            prev_result["heuristic_warnings"] = prev_warnings

            pseudo_warnings = list(pseudo_result.get("heuristic_warnings") or [])
            pseudo_warnings.append(
                {
                    "type": "suspected_pseudo_team_record",
                    "message": "Likely sponsor/brand pseudo-team record (non-club); strong roster match may belong to adjacent club",
                }
            )
            pseudo_result["heuristic_warnings"] = pseudo_warnings
            pseudo_result["suspected_pseudo_team_record"] = True
            attached += 1

    return {
        "attached_candidate_count": int(attached),
        "pseudo_team_record_count": int(pseudo_record_count),
    }


def _apply_anchor_interval_monotonic_candidates(
    *,
    all_results: list[dict[str, Any]],
    teams: list[tuple[int, Any]],
    eq_entries: list[tuple[int, int, bytes]],
    entry_runs_index: dict[int, list[dict[str, Any]]],
    dd6361_pid_to_name: dict[int, str],
) -> dict[str, int]:
    """
    Assign provisional same-entry roster candidates inside bounded gaps between strong anchors.

    This is intended for clustered moderate-overlap cases where individual overlap scoring is noisy
    (e.g. several teams all partially hit the same nearby runs), but the surrounding perfect/strong
    teams establish a clear increasing team-order -> run-order mapping inside one decoded entry.
    """
    results_by_team_offset = {int(r.get("team_offset", -1)): r for r in all_results if isinstance(r.get("team_offset"), int)}
    decoded_by_entry = {int(off): decoded for (off, _ln, decoded) in eq_entries}
    entry_team_index = _build_entry_team_index(eq_entries, teams)
    anchor_statuses = {"perfect_same_entry_run_overlap", "strong_same_entry_run_overlap"}
    eligible_statuses = {"moderate_same_entry_overlap", "weak_same_entry_overlap", "no_same_entry_overlap_hits"}
    attached = 0

    for entry_offset, ordered_teams in entry_team_index.items():
        runs = list(entry_runs_index.get(int(entry_offset), []))
        if not runs:
            continue
        decoded = decoded_by_entry.get(int(entry_offset))
        if decoded is None:
            continue

        seq: list[dict[str, Any]] = []
        for team_idx, (team_offset, team_obj) in enumerate(ordered_teams):
            result = results_by_team_offset.get(int(team_offset))
            if result is None:
                continue
            top = dict(result.get("top_run_match") or {})
            seq.append(
                {
                    "team_idx": int(team_idx),
                    "team_offset": int(team_offset),
                    "team_obj": team_obj,
                    "result": result,
                    "status": str(result.get("status") or ""),
                    "top_run_index": (int(top["run_index"]) if "run_index" in top else None),
                }
            )

        anchors = [
            row for row in seq
            if row["status"] in anchor_statuses and isinstance(row["top_run_index"], int)
        ]
        if len(anchors) < 2:
            continue
        # Require anchors to be globally non-decreasing in this entry (skip wrap/circular entries).
        anchor_run_values = [int(row["top_run_index"]) for row in anchors]
        if any(anchor_run_values[i] >= anchor_run_values[i + 1] for i in range(len(anchor_run_values) - 1)):
            continue

        used_anchor_runs = {int(row["top_run_index"]) for row in anchors}
        seq_by_team_idx = {int(row["team_idx"]): row for row in seq}
        for left, right in zip(anchors, anchors[1:]):
            left_ti = int(left["team_idx"])
            right_ti = int(right["team_idx"])
            left_ri = int(left["top_run_index"])
            right_ri = int(right["top_run_index"])
            team_gap = right_ti - left_ti - 1
            run_gap = right_ri - left_ri - 1
            if team_gap <= 0 or run_gap <= 0:
                continue
            # Keep this conservative: require enough free runs inside the interval, and a small gap.
            if team_gap > run_gap or team_gap > 4:
                continue

            unresolved_rows: list[dict[str, Any]] = []
            for ti in range(left_ti + 1, right_ti):
                row = seq_by_team_idx.get(int(ti))
                if row is None:
                    unresolved_rows = []
                    break
                if row["status"] not in eligible_statuses:
                    unresolved_rows = []
                    break
                if isinstance(row["result"].get("adjacent_pseudo_team_reassignment_candidate"), dict):
                    unresolved_rows = []
                    break
                if _is_obvious_pseudo_team_record(row["team_obj"]):
                    unresolved_rows = []
                    break
                unresolved_rows.append(row)
            if not unresolved_rows:
                continue

            interval_runs = [ri for ri in range(left_ri + 1, right_ri) if ri not in used_anchor_runs]
            if len(interval_runs) < len(unresolved_rows):
                continue

            # Assign in order by interpolation onto the open interval.
            chosen_runs: list[int] = []
            available_runs = list(interval_runs)
            span_team = right_ti - left_ti
            span_run = right_ri - left_ri
            for row in unresolved_rows:
                ti = int(row["team_idx"])
                expected = left_ri + (span_run * ((ti - left_ti) / span_team))
                pick = min(available_runs, key=lambda ri: (abs(ri - expected), ri))
                chosen_runs.append(int(pick))
                available_runs.remove(int(pick))

            for row, run_index in zip(unresolved_rows, chosen_runs):
                team_obj = row["team_obj"]
                team_raw = bytes(getattr(team_obj, "raw_data", b"") or b"")
                predicted_run = runs[int(run_index)]
                roster_rows = []
                for rr in _extract_roster_rows_from_run(decoded, predicted_run):
                    pid = int(rr["pid_candidate"])
                    roster_rows.append(
                        {
                            **rr,
                            "dd6361_name": dd6361_pid_to_name.get(pid),
                            "xor_pid_found_in_team_raw": bool(_xor_le16_bytes(pid) in team_raw),
                        }
                    )
                candidate = {
                    "run_index": int(run_index),
                    "start_pos": int(predicted_run.get("start_pos", 0)),
                    "end_pos": int(predicted_run.get("end_pos", 0)),
                    "row_count": int(predicted_run.get("row_count", 0)),
                    "non_empty_row_count": int(predicted_run.get("non_empty_row_count", 0)),
                    "rows": roster_rows,
                    "selection_method": "anchor_interval_monotonic_same_entry",
                    "anchor_interval": {
                        "left_team_idx": int(left_ti),
                        "left_run_index": int(left_ri),
                        "right_team_idx": int(right_ti),
                        "right_run_index": int(right_ri),
                    },
                }
                result = row["result"]
                result["anchor_interval_monotonic_candidate"] = candidate
                warnings = list(result.get("heuristic_warnings") or [])
                warnings.append(
                    {
                        "type": "anchor_interval_monotonic_candidate",
                        "message": (
                            "Provisional same-entry roster candidate assigned from bounded anchor interval "
                            f"(runs {left_ri}->{right_ri})"
                        ),
                    }
                )
                contested = [
                    other
                    for other in seq
                    if int(other["team_idx"]) != int(row["team_idx"])
                    and isinstance(other.get("top_run_index"), int)
                    and int(other["top_run_index"]) == int(run_index)
                ]
                if contested:
                    warnings.append(
                        {
                            "type": "anchor_interval_contested_run",
                            "message": (
                                f"Assigned run {int(run_index)} is also the current best same-entry run for "
                                f"{len(contested)} other team(s)"
                            ),
                            "run_index": int(run_index),
                            "contested_team_names_preview": [
                                str((other.get("result") or {}).get("team_name") or "") for other in contested[:5]
                            ],
                        }
                    )
                result["heuristic_warnings"] = warnings
                attached += 1

    return {"attached_candidate_count": int(attached)}


def _analyze_team_same_entry_overlap(
    team_offset: int,
    team: Any,
    eq_entries: list[tuple[int, int, bytes]],
    entry_runs_index: dict[int, list[dict[str, Any]]],
    dd6361_pid_to_name: dict[int, str],
) -> dict[str, Any]:
    containing = eq_link._containing_entries(eq_entries, int(team_offset))
    if not containing:
        return {
            "team_offset": int(team_offset),
            "team_name": str(getattr(team, "name", "") or ""),
            "full_club_name": (str(getattr(team, "full_club_name", "") or "") or None),
            "status": "no_containing_eq_entry",
        }

    container = containing[0]
    entry_offset = int(container["entry_offset"])
    entry_length = int(container["length"])
    decoded = next(decoded for (off, _ln, decoded) in eq_entries if int(off) == entry_offset)
    runs = entry_runs_index.get(entry_offset, [])
    raw = bytes(getattr(team, "raw_data", b"") or b"")

    if not runs:
        return {
            "team_offset": int(team_offset),
            "team_name": str(getattr(team, "name", "") or ""),
            "full_club_name": (str(getattr(team, "full_club_name", "") or "") or None),
            "status": "entry_has_no_roster_runs",
            "containing_entry": {"entry_offset": entry_offset, "length": entry_length},
        }

    run_scores: list[dict[str, Any]] = []
    for run_idx, run in enumerate(runs):
        rows = _extract_roster_rows_from_run(decoded, run)
        non_empty_rows = [row for row in rows if not row["is_empty_slot"]]
        hits = 0
        for row in non_empty_rows:
            pid = int(row["pid_candidate"])
            if _xor_le16_bytes(pid) in raw:
                hits += 1
        run_scores.append(
            {
                "run_index": int(run_idx),
                "start_pos": int(run["start_pos"]),
                "end_pos": int(run["end_pos"]),
                "row_count": int(run["row_count"]),
                "non_empty_row_count": int(run["non_empty_row_count"]),
                "overlap_hits_in_team_raw": int(hits),
                "rows": rows,
            }
        )

    run_scores.sort(key=lambda r: (-int(r["overlap_hits_in_team_raw"]), int(r["run_index"])))
    top = run_scores[0]
    second_hits = int(run_scores[1]["overlap_hits_in_team_raw"]) if len(run_scores) > 1 else 0
    status = _classify_match(
        top_hits=int(top["overlap_hits_in_team_raw"]),
        run_len=int(top["non_empty_row_count"]),
        second_hits=second_hits,
    )

    roster_rows = []
    for row in top["rows"]:
        pid = int(row["pid_candidate"])
        roster_rows.append(
            {
                **row,
                "dd6361_name": dd6361_pid_to_name.get(pid),
                "xor_pid_found_in_team_raw": bool(_xor_le16_bytes(pid) in raw),
            }
        )

    return {
        "team_offset": int(team_offset),
        "team_name": str(getattr(team, "name", "") or ""),
        "full_club_name": (str(getattr(team, "full_club_name", "") or "") or None),
        "team_id": int(getattr(team, "team_id", 0) or 0),
        "status": status,
        "containing_entry": {"entry_offset": entry_offset, "length": entry_length},
        "top_run_match": {
            "run_index": int(top["run_index"]),
            "start_pos": int(top["start_pos"]),
            "end_pos": int(top["end_pos"]),
            "row_count": int(top["row_count"]),
            "non_empty_row_count": int(top["non_empty_row_count"]),
            "overlap_hits_in_team_raw": int(top["overlap_hits_in_team_raw"]),
            "second_best_overlap_hits": int(second_hits),
            "rows": roster_rows,
        },
        "top_run_candidates_preview": [
            {
                "run_index": int(r["run_index"]),
                "start_pos": int(r["start_pos"]),
                "end_pos": int(r["end_pos"]),
                "non_empty_row_count": int(r["non_empty_row_count"]),
                "overlap_hits_in_team_raw": int(r["overlap_hits_in_team_raw"]),
            }
            for r in run_scores[:8]
        ],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract EQ team rosters via same-entry overlap with roster-ID runs")
    p.add_argument(
        "--player-file",
        default=str(REPO_ROOT / "DBDAT" / "JUG98030.FDI"),
        help="Path to JUG98030.FDI (for dd6361 player-id -> name mapping)",
    )
    p.add_argument(
        "--team-file",
        default=str(REPO_ROOT / "DBDAT" / "EQ98030.FDI"),
        help="Path to EQ98030.FDI",
    )
    p.add_argument(
        "--team",
        action="append",
        default=[],
        help="Team name/full-club-name substring filter (repeatable). If omitted, only coverage summary is emitted.",
    )
    p.add_argument(
        "--top-examples",
        type=int,
        default=15,
        help="How many example strong matches to include in the global summary (default: 15)",
    )
    p.add_argument(
        "--include-fallbacks",
        action="store_true",
        help=(
            "Include investigation fallback mappings (anchor-assisted and heuristic candidates) "
            "in preferred roster selection. Default is authoritative-only same-entry mapping."
        ),
    )
    p.add_argument("--json-output", help="Write JSON output to this path")
    return p.parse_args(argv)


def extract_eq_team_rosters_same_entry_overlap(
    *,
    player_file: str,
    team_file: str,
    team_queries: list[str] | None = None,
    top_examples: int = 15,
    include_fallbacks: bool = False,
    json_output: str | None = None,
) -> dict[str, Any]:
    """Run same-entry EQ roster overlap extraction and return the JSON-able payload."""
    player_file_path = Path(player_file)
    team_file_path = Path(team_file)
    requested_queries = [str(q).strip() for q in (team_queries or []) if str(q).strip()]

    if not player_file_path.exists():
        raise FileNotFoundError(f"Player file not found: {player_file_path}")
    if not team_file_path.exists():
        raise FileNotFoundError(f"Team file not found: {team_file_path}")

    dd6361_pid_to_name = _build_dd6361_pid_map(player_file_path)
    known_lineup_anchor_pid_sets: dict[str, dict[str, Any]] = {}
    if include_fallbacks:
        known_lineup_anchor_pid_sets = _build_known_lineup_anchor_pid_sets(player_file_path)
    eq_entries = eq_link._iter_decoded_fdi_entries(team_file_path)
    teams = list(load_teams(str(team_file_path)))
    entry_runs_index: dict[int, list[dict[str, Any]]] = {}
    for entry_offset, _length, decoded in eq_entries:
        entry_runs_index[int(entry_offset)] = eq_link._find_stride5_roster_runs(decoded, min_rows=8)

    # Analyze all teams to build a coverage summary (fast enough for local use).
    all_results: list[dict[str, Any]] = []
    for team_offset, team in teams:
        all_results.append(
            _analyze_team_same_entry_overlap(
                int(team_offset),
                team,
                eq_entries,
                entry_runs_index,
                dd6361_pid_to_name,
            )
        )
    for team_offset, team in teams:
        result = next((r for r in all_results if int(r.get("team_offset", -1)) == int(team_offset)), None)
        if result is not None and _is_obvious_pseudo_team_record(team):
            result["suspected_pseudo_team_record"] = True

    circular_fallback_count = 0
    flagged_anchor_collision_count = 0
    pseudo_reassignment_count = 0
    pseudo_team_record_count = int(sum(1 for r in all_results if bool(r.get("suspected_pseudo_team_record"))))
    anchor_interval_candidate_count = 0
    if include_fallbacks:
        fallback_summary = _apply_circular_shift_same_entry_fallback(
            all_results=all_results,
            teams=teams,
            eq_entries=eq_entries,
            entry_runs_index=entry_runs_index,
            dd6361_pid_to_name=dd6361_pid_to_name,
            known_lineup_anchor_pid_sets=known_lineup_anchor_pid_sets,
        )
        circular_fallback_count = int(fallback_summary.get("candidate_count", 0))
        flagged_anchor_collision_count = int(fallback_summary.get("flagged_anchor_collision_count", 0))
        pseudo_reassignment_summary = _apply_adjacent_pseudo_team_reassignment_candidates(
            all_results=all_results,
            teams=teams,
            eq_entries=eq_entries,
        )
        pseudo_reassignment_count = int(pseudo_reassignment_summary.get("attached_candidate_count", 0))
        pseudo_team_record_count = int(pseudo_reassignment_summary.get("pseudo_team_record_count", 0))
        anchor_interval_summary = _apply_anchor_interval_monotonic_candidates(
            all_results=all_results,
            teams=teams,
            eq_entries=eq_entries,
            entry_runs_index=entry_runs_index,
            dd6361_pid_to_name=dd6361_pid_to_name,
        )
        anchor_interval_candidate_count = int(anchor_interval_summary.get("attached_candidate_count", 0))

    status_counts = Counter(str(r.get("status", "")) for r in all_results)
    total = len(all_results)
    covered = int(status_counts.get("perfect_same_entry_run_overlap", 0) + status_counts.get("strong_same_entry_run_overlap", 0))
    candidate_status_counts = Counter(
        str(r.get("circular_shift_candidate_status") or r.get("status") or "")
        for r in all_results
    )
    candidate_covered = int(covered + circular_fallback_count)
    guarded_candidate_covered = int(covered + max(0, circular_fallback_count - flagged_anchor_collision_count))

    strong_examples = []
    for r in all_results:
        if str(r.get("status")) not in {"perfect_same_entry_run_overlap", "strong_same_entry_run_overlap"}:
            continue
        top = r.get("top_run_match") or {}
        strong_examples.append(
            {
                "team_name": r.get("team_name"),
                "full_club_name": r.get("full_club_name"),
                "team_offset": r.get("team_offset"),
                "containing_entry_offset": (r.get("containing_entry") or {}).get("entry_offset"),
                "run_index": top.get("run_index"),
                "overlap_hits_in_team_raw": top.get("overlap_hits_in_team_raw"),
                "non_empty_row_count": top.get("non_empty_row_count"),
                "second_best_overlap_hits": top.get("second_best_overlap_hits"),
            }
        )
    strong_examples.sort(
        key=lambda row: (
            -(int(row.get("overlap_hits_in_team_raw") or 0)),
            int(row.get("second_best_overlap_hits") or 0),
            str(row.get("team_name") or ""),
        )
    )

    # Attach anchor-assisted split-entry roster windows for known lineup datasets (currently a small seed set).
    if include_fallbacks and all_results:
        dd6361_rows_cache: dict[str, Any] = {}
        anchor_assisted_cache: dict[str, dict[str, Any] | None] = {}
        for r in all_results:
            dataset_key = _match_known_lineup_dataset_for_team(
                str(r.get("team_name") or ""),
                (str(r.get("full_club_name") or "") or None),
            )
            if not dataset_key:
                continue
            if dataset_key not in anchor_assisted_cache:
                anchor_assisted_cache[dataset_key] = _build_known_lineup_anchor_assisted_match(
                    dataset_key=dataset_key,
                    player_file=player_file_path,
                    eq_entries=eq_entries,
                    dd6361_pid_to_name=dd6361_pid_to_name,
                    dd6361_rows_cache=dd6361_rows_cache,
                )
            assisted = anchor_assisted_cache.get(dataset_key)
            if assisted:
                r["known_lineup_anchor_assisted_match"] = assisted
    # Attach a unified preferred roster selection (with provenance) for downstream CLI/GUI/editor use.
    # Default mode is authoritative-only; investigation fallbacks are opt-in.
    authoritative_statuses = {"perfect_same_entry_run_overlap", "strong_same_entry_run_overlap"}
    for r in all_results:
        status = str(r.get("status") or "")
        top_run = dict(r.get("top_run_match") or {})
        candidate_run = dict(r.get("circular_shift_candidate_match") or {})
        heuristic_warnings = list(r.get("heuristic_warnings") or [])
        anchor_assisted = dict(r.get("known_lineup_anchor_assisted_match") or {})
        pseudo_adjacent = dict(r.get("adjacent_pseudo_team_reassignment_candidate") or {})
        anchor_interval_candidate = dict(r.get("anchor_interval_monotonic_candidate") or {})

        preferred: dict[str, Any] | None = None
        if status in authoritative_statuses and top_run:
            preferred = {
                "provenance": "same_entry_authoritative",
                "provisional": False,
                "rows": list(top_run.get("rows") or []),
                "row_count": int(top_run.get("non_empty_row_count", 0)),
                "source": {
                    "run_index": int(top_run.get("run_index", -1)),
                    "entry_offset": int((r.get("containing_entry") or {}).get("entry_offset", 0)),
                },
            }
        elif include_fallbacks and anchor_assisted:
            stride = dict(anchor_assisted.get("stride5_window") or {})
            rows = list(stride.get("rows") or [])
            preferred = {
                "provenance": "known_lineup_anchor_assisted",
                "provisional": False,
                "rows": rows,
                "row_count": int(sum(1 for row in rows if not row.get("is_empty_slot"))),
                "source": {
                    "dataset_key": str(anchor_assisted.get("dataset_key") or ""),
                    "entry_offset": int(anchor_assisted.get("entry_offset", 0)),
                    "hit_count": int(anchor_assisted.get("hit_count", 0)),
                    "exact_anchor_count": int(anchor_assisted.get("exact_anchor_count", 0)),
                },
            }
        elif include_fallbacks and pseudo_adjacent:
            preferred = {
                "provenance": "adjacent_pseudo_team_record_reassignment",
                "provisional": True,
                "rows": list(pseudo_adjacent.get("rows") or []),
                "row_count": int(pseudo_adjacent.get("non_empty_row_count", 0)),
                "source": {
                    "run_index": int(pseudo_adjacent.get("run_index", -1)),
                    "method": str(pseudo_adjacent.get("selection_method") or "adjacent_pseudo_team_record_reassignment"),
                    "source_pseudo_team_name": str(pseudo_adjacent.get("source_pseudo_team_name") or ""),
                    "source_pseudo_team_offset": int(pseudo_adjacent.get("source_pseudo_team_offset", 0)),
                },
            }
        elif include_fallbacks and anchor_interval_candidate:
            preferred = {
                "provenance": "anchor_interval_monotonic_same_entry",
                "provisional": True,
                "rows": list(anchor_interval_candidate.get("rows") or []),
                "row_count": int(anchor_interval_candidate.get("non_empty_row_count", 0)),
                "source": {
                    "run_index": int(anchor_interval_candidate.get("run_index", -1)),
                    "method": str(anchor_interval_candidate.get("selection_method") or "anchor_interval_monotonic_same_entry"),
                    "anchor_interval": dict(anchor_interval_candidate.get("anchor_interval") or {}),
                },
            }
        elif include_fallbacks and candidate_run and (not heuristic_warnings):
            preferred = {
                "provenance": "heuristic_circular_shift_candidate",
                "provisional": True,
                "rows": list(candidate_run.get("rows") or []),
                "row_count": int(candidate_run.get("non_empty_row_count", 0)),
                "source": {
                    "run_index": int(candidate_run.get("run_index", -1)),
                    "method": str(candidate_run.get("selection_method") or "circular_shift_same_entry"),
                    "entry_offset": int((r.get("containing_entry") or {}).get("entry_offset", 0)),
                },
            }

        if preferred:
            r["preferred_roster_match"] = preferred

    requested_results: list[dict[str, Any]] = []
    if requested_queries:
        for r in all_results:
            team_name = str(r.get("team_name") or "")
            full = str(r.get("full_club_name") or "")
            if any(
                team_query_matches(q, team_name=team_name, full_club_name=full)
                for q in requested_queries
            ):
                requested_results.append(r)
        requested_results.sort(key=lambda r: str(r.get("team_name") or ""))

    preferred_provenance_counts = Counter(
        str((r.get("preferred_roster_match") or {}).get("provenance") or "")
        for r in all_results
        if isinstance(r.get("preferred_roster_match"), dict)
    )
    preferred_count = int(sum(preferred_provenance_counts.values()))
    club_like_team_count = int(sum(1 for r in all_results if not bool(r.get("suspected_pseudo_team_record"))))
    club_like_preferred_count = int(
        sum(
            1
            for r in all_results
            if (not bool(r.get("suspected_pseudo_team_record"))) and isinstance(r.get("preferred_roster_match"), dict)
        )
    )
    uncovered_club_like_results = [
        r
        for r in all_results
        if (not bool(r.get("suspected_pseudo_team_record"))) and (not isinstance(r.get("preferred_roster_match"), dict))
    ]
    uncovered_by_entry: dict[int | None, list[dict[str, Any]]] = {}
    for r in uncovered_club_like_results:
        containing = dict(r.get("containing_entry") or {})
        entry_offset_value = containing.get("entry_offset")
        entry_offset: int | None = int(entry_offset_value) if isinstance(entry_offset_value, int) else None
        uncovered_by_entry.setdefault(entry_offset, []).append(r)
    uncovered_entry_clusters = []
    for entry_offset, rows in uncovered_by_entry.items():
        status_counts = Counter(str(row.get("status") or "") for row in rows)
        top_run_counts = Counter(
            int((row.get("top_run_match") or {}).get("run_index"))
            for row in rows
            if isinstance((row.get("top_run_match") or {}).get("run_index"), int)
        )
        uncovered_entry_clusters.append(
            {
                "entry_offset": entry_offset,
                "team_count": int(len(rows)),
                "status_counts": dict(status_counts),
                "top_run_index_counts": dict(top_run_counts),
                "team_names_preview": [str(row.get("team_name") or "") for row in rows[:8]],
            }
        )
    uncovered_entry_clusters.sort(
        key=lambda row: (
            -int(row.get("team_count") or 0),
            (10**12 if row.get("entry_offset") is None else int(row.get("entry_offset") or 0)),
        )
    )
    uncovered_team_rows = []
    for r in uncovered_club_like_results:
        containing = dict(r.get("containing_entry") or {})
        top = dict(r.get("top_run_match") or {})
        uncovered_team_rows.append(
            {
                "team_name": str(r.get("team_name") or ""),
                "full_club_name": (str(r.get("full_club_name") or "") or None),
                "status": str(r.get("status") or ""),
                "entry_offset": (int(containing.get("entry_offset")) if isinstance(containing.get("entry_offset"), int) else None),
                "top_run_index": (int(top.get("run_index")) if isinstance(top.get("run_index"), int) else None),
                "top_overlap_hits": int(top.get("overlap_hits_in_team_raw") or 0),
                "top_non_empty_row_count": int(top.get("non_empty_row_count") or 0),
                "top_second_best_overlap_hits": int(top.get("second_best_overlap_hits") or 0),
            }
        )
    uncovered_team_rows.sort(
        key=lambda row: (
            (10**12 if row.get("entry_offset") is None else int(row.get("entry_offset") or 0)),
            str(row.get("team_name") or ""),
        )
    )

    payload = {
        "player_file": str(player_file_path),
        "team_file": str(team_file_path),
        "selection_mode": ("investigation_fallbacks_enabled" if include_fallbacks else "authoritative_only"),
        "dd6361_pid_name_count": len(dd6361_pid_to_name),
        "eq_decoded_entry_count": len(eq_entries),
        "team_count": total,
        "same_entry_overlap_coverage": {
            "status_counts": dict(status_counts),
            "strong_or_better_count": covered,
            "strong_or_better_ratio": (covered / total) if total else 0.0,
        },
        "final_extraction_coverage": {
            "status_counts": dict(candidate_status_counts),
            "covered_count": int(candidate_covered),
            "covered_ratio": (candidate_covered / total) if total else 0.0,
            "guarded_covered_count": int(guarded_candidate_covered),
            "guarded_covered_ratio": (guarded_candidate_covered / total) if total else 0.0,
            "same_entry_anchor_count": int(covered),
            "circular_shift_fallback_count": int(circular_fallback_count),
            "circular_shift_flagged_anchor_collision_count": int(flagged_anchor_collision_count),
            "adjacent_pseudo_team_reassignment_candidate_count": int(pseudo_reassignment_count),
            "suspected_pseudo_team_record_count": int(pseudo_team_record_count),
            "anchor_interval_monotonic_candidate_count": int(anchor_interval_candidate_count),
        },
        "preferred_roster_coverage": {
            "covered_count": int(preferred_count),
            "covered_ratio": (preferred_count / total) if total else 0.0,
            "club_like_team_count": int(club_like_team_count),
            "club_like_covered_count": int(club_like_preferred_count),
            "club_like_covered_ratio": (club_like_preferred_count / club_like_team_count) if club_like_team_count else 0.0,
            "provenance_counts": dict(preferred_provenance_counts),
        },
        "uncovered_club_like_summary": {
            "uncovered_count": int(len(uncovered_club_like_results)),
            "entry_cluster_count": int(len(uncovered_entry_clusters)),
            "entry_clusters_top": uncovered_entry_clusters[:10],
            "teams": uncovered_team_rows,
        },
        "strong_match_examples_topN": strong_examples[: max(0, int(top_examples))],
        "requested_team_results": requested_results,
        "notes": [
            "Same-entry overlap uses XOR-encoded dd6361 player IDs found in EQ stride-5 roster rows.",
            "A perfect match means the team's raw EQ subrecord contains all roster-row IDs from the selected run.",
            "Weak/no-hit cases are often split-entry teams where roster tables live in a different EQ decoded entry than the parsed team metadata subrecord (e.g. Manchester Utd in current findings).",
            "dd6361_name may be null for player IDs lacking an extracted dd6361 biography row in the current corpus.",
            "Default selection mode is authoritative_only (same-entry strong/perfect matches).",
            "final_extraction_coverage is a heuristic candidate coverage metric that includes circular-shift same-entry fallback suggestions for weak/no-hit cases.",
            "Circular-shift fallback candidates are useful for investigation, but not yet authoritative (known false positives exist, e.g. hidden split-entry rosters such as Manchester Utd can appear in another team's entry).",
            "known_lineup_anchor_collision warnings flag candidates that strongly overlap a transcribed lineup anchor dataset for a different team (currently limited to available seed lineup datasets such as stoke/manutd).",
            "adjacent_pseudo_team_record_reassignment candidates copy strong roster runs from conservatively classified sponsor/brand pseudo-team records to the preceding real club (provisional, parser-artifact workaround).",
            "anchor_interval_monotonic_candidate assigns provisional same-entry runs only inside bounded gaps between strong anchors with increasing run order (used for clustered moderate-overlap cases).",
            "preferred_roster_coverage counts a single best-available roster per parsed record using provenance ordering: same-entry_authoritative > known_lineup_anchor_assisted > adjacent_pseudo_team_record_reassignment > anchor_interval_monotonic_same_entry > heuristic_circular_shift_candidate (unwarned only).",
            "uncovered_club_like_summary lists club-like parsed team records still lacking a preferred roster assignment after the current provenance pipeline, clustered by containing EQ entry for next-heuristic targeting.",
        ],
    }

    if json_output:
        out_path = Path(json_output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


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

    payload = extract_eq_team_rosters_same_entry_overlap(
        player_file=str(player_file),
        team_file=str(team_file),
        team_queries=list(args.team or []),
        top_examples=int(args.top_examples),
        include_fallbacks=bool(args.include_fallbacks),
        json_output=args.json_output,
    )
    text = json.dumps(payload, indent=2)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
