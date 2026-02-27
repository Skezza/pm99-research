#!/usr/bin/env python3
"""Inspect dd6360/dd6361 marker neighborhoods in JUG98030.FDI.

This script builds a combined marker stream across decoded FDI entries:
- `dd6360` (strict-player-like subrecord separator)
- `dd6361` (biography subrecord separator)

It is intended to validate linkage assumptions, e.g. whether a player's `dd6361`
biography sits near a matching `dd6360` player subrecord in marker order.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.models import PlayerRecord  # type: ignore
from scripts import probe_bio_trailer_stats as trailer_probe  # type: ignore


DD60 = trailer_probe.PLAYER_MARKER
DD61 = trailer_probe.BIO_MARKER


def _norm(value: str | None) -> str:
    text = (value or "").upper()
    text = re.sub(r"[^A-Z0-9' ]+", " ", text)
    return " ".join(text.split())


def _surname(value: str | None) -> str:
    parts = _norm(value).split()
    return parts[-1] if parts else ""


def _build_marker_stream(entries: list[tuple[int, bytes]]) -> list[dict[str, Any]]:
    stream: list[dict[str, Any]] = []
    for ei, (entry_offset, decoded) in enumerate(entries):
        pos = decoded.find(DD60)
        while pos != -1:
            stream.append(
                {
                    "type": "dd6360",
                    "entry_idx": ei,
                    "entry_offset": entry_offset,
                    "rel": pos,
                }
            )
            pos = decoded.find(DD60, pos + 1)

        pos = decoded.find(DD61)
        while pos != -1:
            seg = decoded[pos:min(len(decoded), pos + 640)]
            stream.append(
                {
                    "type": "dd6361",
                    "entry_idx": ei,
                    "entry_offset": entry_offset,
                    "rel": pos,
                    "bio_name": trailer_probe._extract_bio_name(seg),
                }
            )
            pos = decoded.find(DD61, pos + 1)

    stream.sort(key=lambda row: (row["entry_idx"], row["rel"], 0 if row["type"] == "dd6360" else 1))
    return stream


def _segment_between_markers(
    entries: list[tuple[int, bytes]],
    cur: dict[str, Any],
    nxt: dict[str, Any],
) -> bytes:
    cur_ei = int(cur["entry_idx"])
    nxt_ei = int(nxt["entry_idx"])
    cur_rel = int(cur["rel"])
    nxt_rel = int(nxt["rel"])
    if cur_ei == nxt_ei:
        return entries[cur_ei][1][cur_rel:nxt_rel]
    chunks: list[bytes] = [entries[cur_ei][1][cur_rel:]]
    for ei in range(cur_ei + 1, nxt_ei):
        chunks.append(entries[ei][1])
    chunks.append(entries[nxt_ei][1][:nxt_rel])
    return b"".join(chunks)


def _enrich_stream(entries: list[tuple[int, bytes]], stream: list[dict[str, Any]]) -> None:
    for idx, row in enumerate(stream[:-1]):
        nxt = stream[idx + 1]
        seg = _segment_between_markers(entries, row, nxt)
        row["stream_idx"] = idx
        row["seg_len_to_next_marker"] = len(seg)
        row["seg_preview"] = seg[:64].decode("latin-1", errors="ignore").replace("\n", "\\n").replace("\r", "\\r")
        if row["type"] == "dd6360":
            try:
                parsed = PlayerRecord.from_bytes(seg, int(row["entry_offset"]) + 2 + int(row["rel"]))
                row["parsed_name"] = (getattr(parsed, "name", None) or "").strip()
                row["parsed_team_id"] = getattr(parsed, "team_id", None)
                row["parsed_position"] = getattr(parsed, "position_primary", None)
                row["parsed_attrs12"] = list(getattr(parsed, "attributes", []) or [])
            except Exception as exc:
                row["parse_error"] = str(exc)
    if stream:
        stream[-1]["stream_idx"] = len(stream) - 1


def _find_bio_marker_for_query(stream: list[dict[str, Any]], query: str) -> tuple[int, dict[str, Any]] | None:
    q_norm = _norm(query)
    for idx, row in enumerate(stream):
        if row["type"] != "dd6361":
            continue
        if _norm(str(row.get("bio_name") or "")) == q_norm:
            return idx, row
    for idx, row in enumerate(stream):
        if row["type"] != "dd6361":
            continue
        if q_norm and q_norm in _norm(str(row.get("bio_name") or "")):
            return idx, row
    return None


def _compact_marker_row(row: dict[str, Any]) -> dict[str, Any]:
    out = {
        "stream_idx": row.get("stream_idx"),
        "type": row.get("type"),
        "entry_idx": row.get("entry_idx"),
        "entry_offset": row.get("entry_offset"),
        "rel": row.get("rel"),
        "seg_len_to_next_marker": row.get("seg_len_to_next_marker"),
    }
    if row.get("type") == "dd6361":
        out["bio_name"] = row.get("bio_name")
    else:
        out["parsed_name"] = row.get("parsed_name")
        out["parsed_team_id"] = row.get("parsed_team_id")
        out["parsed_position"] = row.get("parsed_position")
    return out


def _nearest_marker(stream: list[dict[str, Any]], start_idx: int, marker_type: str, direction: int) -> tuple[int, dict[str, Any]] | None:
    j = start_idx + direction
    while 0 <= j < len(stream):
        if stream[j]["type"] == marker_type:
            return j, stream[j]
        j += direction
    return None


def _marker_relation(anchor_idx: int, anchor: dict[str, Any], other_idx: int, other: dict[str, Any]) -> dict[str, Any]:
    return {
        **_compact_marker_row(other),
        "delta_markers": abs(int(other_idx) - int(anchor_idx)),
        "delta_entries": abs(int(other["entry_idx"]) - int(anchor["entry_idx"])),
        "same_entry": int(other["entry_idx"]) == int(anchor["entry_idx"]),
        "surname_match": _surname(str(other.get("parsed_name") or "")) == _surname(str(anchor.get("bio_name") or "")),
    }


def _nearest_dd60_same_surname(stream: list[dict[str, Any]], anchor_idx: int, anchor: dict[str, Any], max_marker_distance: int) -> dict[str, Any] | None:
    target_surname = _surname(str(anchor.get("bio_name") or ""))
    if not target_surname:
        return None
    best: tuple[int, int, dict[str, Any]] | None = None
    for d in range(1, max_marker_distance + 1):
        for j in (anchor_idx - d, anchor_idx + d):
            if not (0 <= j < len(stream)):
                continue
            row = stream[j]
            if row.get("type") != "dd6360":
                continue
            if _surname(str(row.get("parsed_name") or "")) != target_surname:
                continue
            best = (d, j, row)
            break
        if best is not None:
            break
    if best is None:
        return None
    _, j, row = best
    return _marker_relation(anchor_idx, anchor, j, row)


def _has_nameish_dd60(row: dict[str, Any]) -> bool:
    name = str(row.get("parsed_name") or "").strip()
    return bool(name and name not in ("Unknown Player", "Parse Error"))


def _compute_corpus_surname_summary(
    stream: list[dict[str, Any]],
    windows: list[int],
    example_limit: int = 5,
) -> dict[str, Any]:
    named_bio_indices = [
        i for i, row in enumerate(stream)
        if row.get("type") == "dd6361" and str(row.get("bio_name") or "").strip()
    ]
    summary: dict[int, dict[str, int]] = {
        w: {"same_surname": 0, "exact_name": 0, "same_entry_dd6360": 0}
        for w in windows
    }
    examples: dict[int, dict[str, list[dict[str, Any]]]] = {
        w: {"exact": [], "surname": [], "no_match": []}
        for w in windows
    }

    for idx in named_bio_indices:
        bio = stream[idx]
        bio_name = str(bio.get("bio_name") or "")
        bio_surname = _surname(bio_name)
        if not bio_surname:
            continue

        for w in windows:
            found_same_entry = False
            found_surname = False
            found_exact = False
            for j in range(max(0, idx - w), min(len(stream), idx + w + 1)):
                if j == idx:
                    continue
                row = stream[j]
                if row.get("type") != "dd6360" or not _has_nameish_dd60(row):
                    continue
                if int(row["entry_idx"]) == int(bio["entry_idx"]):
                    found_same_entry = True
                parsed_name = str(row.get("parsed_name") or "")
                if _surname(parsed_name) == bio_surname:
                    found_surname = True
                    if _norm(parsed_name) == _norm(bio_name):
                        found_exact = True
                        break
            summary[w]["same_entry_dd6360"] += int(found_same_entry)
            summary[w]["same_surname"] += int(found_surname)
            summary[w]["exact_name"] += int(found_exact)

            # Collect a few examples for interpretability.
            bucket = examples[w]
            if (
                len(bucket["exact"]) >= example_limit
                and len(bucket["surname"]) >= example_limit
                and len(bucket["no_match"]) >= example_limit
            ):
                continue

            best_exact: tuple[int, dict[str, Any]] | None = None
            best_surname: tuple[int, dict[str, Any]] | None = None
            for d in range(1, w + 1):
                for j in (idx - d, idx + d):
                    if not (0 <= j < len(stream)):
                        continue
                    row = stream[j]
                    if row.get("type") != "dd6360" or not _has_nameish_dd60(row):
                        continue
                    parsed_name = str(row.get("parsed_name") or "")
                    if _norm(parsed_name) == _norm(bio_name):
                        best_exact = (d, row)
                        break
                    if best_surname is None and _surname(parsed_name) == bio_surname:
                        best_surname = (d, row)
                if best_exact is not None:
                    break

            if best_exact is not None and len(bucket["exact"]) < example_limit:
                d, row = best_exact
                bucket["exact"].append(
                    {
                        "bio_name": bio_name,
                        "match_name": row.get("parsed_name"),
                        "delta_markers": d,
                        "entry_idx": row.get("entry_idx"),
                        "rel": row.get("rel"),
                    }
                )
            elif best_surname is not None and len(bucket["surname"]) < example_limit:
                d, row = best_surname
                bucket["surname"].append(
                    {
                        "bio_name": bio_name,
                        "match_name": row.get("parsed_name"),
                        "delta_markers": d,
                        "entry_idx": row.get("entry_idx"),
                        "rel": row.get("rel"),
                    }
                )
            elif best_exact is None and best_surname is None and len(bucket["no_match"]) < example_limit:
                bucket["no_match"].append(
                    {
                        "bio_name": bio_name,
                        "entry_idx": bio.get("entry_idx"),
                        "rel": bio.get("rel"),
                    }
                )

    total = len(named_bio_indices)
    return {
        "named_dd6361_bio_count": total,
        "windows": windows,
        "summary": {
            str(w): {
                "same_surname_count": summary[w]["same_surname"],
                "same_surname_ratio": (summary[w]["same_surname"] / total) if total else 0.0,
                "exact_name_count": summary[w]["exact_name"],
                "exact_name_ratio": (summary[w]["exact_name"] / total) if total else 0.0,
                "has_any_same_entry_dd6360_count": summary[w]["same_entry_dd6360"],
                "has_any_same_entry_dd6360_ratio": (summary[w]["same_entry_dd6360"] / total) if total else 0.0,
            }
            for w in windows
        },
        "examples": {str(w): examples[w] for w in windows},
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Probe dd6360/dd6361 marker neighborhoods for player biographies")
    p.add_argument(
        "--player-file",
        default=str(REPO_ROOT / "DBDAT" / "JUG98030.FDI"),
        help="Path to JUG98030.FDI",
    )
    p.add_argument(
        "--name",
        action="append",
        default=[],
        help="Target biography player name query (repeatable; exact dd6361 bio-name preferred, then substring)",
    )
    p.add_argument("--window", type=int, default=8, help="Marker rows to include before/after each matched dd6361 marker")
    p.add_argument(
        "--same-surname-window",
        type=int,
        default=200,
        help="Marker distance window when searching for nearest dd6360 with the same surname",
    )
    p.add_argument("--json-output", help="Write JSON output to this path")
    p.add_argument(
        "--corpus-surname-summary",
        action="store_true",
        help="Add corpus-wide dd6361->nearby dd6360 name/surname match-rate summary",
    )
    p.add_argument(
        "--summary-windows",
        default="10,25,50,100,200,500",
        help="Comma-separated marker windows for --corpus-surname-summary (default: 10,25,50,100,200,500)",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    player_file = Path(args.player_file)
    if not player_file.exists():
        print(json.dumps({"error": f"Player file not found: {player_file}"}, indent=2))
        return 2

    entries = trailer_probe._iter_decoded_entries(player_file)
    stream = _build_marker_stream(entries)
    _enrich_stream(entries, stream)

    queries = [q for q in (args.name or []) if str(q).strip()]
    selected: list[dict[str, Any]] = []
    for query in queries:
        match = _find_bio_marker_for_query(stream, query)
        if match is None:
            selected.append({"query": query, "error": "No matching dd6361 bio marker found"})
            continue

        anchor_idx, anchor = match
        prev_dd60 = _nearest_marker(stream, anchor_idx, "dd6360", -1)
        next_dd60 = _nearest_marker(stream, anchor_idx, "dd6360", +1)
        local_rows = [
            _compact_marker_row(stream[j])
            for j in range(max(0, anchor_idx - int(args.window)), min(len(stream), anchor_idx + int(args.window) + 1))
        ]

        selected.append(
            {
                "query": query,
                "anchor": _compact_marker_row(anchor),
                "prev_dd6360": (
                    _marker_relation(anchor_idx, anchor, prev_dd60[0], prev_dd60[1]) if prev_dd60 is not None else None
                ),
                "next_dd6360": (
                    _marker_relation(anchor_idx, anchor, next_dd60[0], next_dd60[1]) if next_dd60 is not None else None
                ),
                "nearest_dd6360_same_surname": _nearest_dd60_same_surname(
                    stream, anchor_idx, anchor, int(args.same_surname_window)
                ),
                "neighborhood": local_rows,
            }
        )

    dd60_count = sum(1 for row in stream if row["type"] == "dd6360")
    dd61_count = sum(1 for row in stream if row["type"] == "dd6361")

    payload = {
        "player_file": str(player_file),
        "decoded_entry_count": len(entries),
        "marker_stream_count": len(stream),
        "dd6360_count": dd60_count,
        "dd6361_count": dd61_count,
        "window": int(args.window),
        "same_surname_window": int(args.same_surname_window),
        "notes": [
            "The marker stream is sorted by (decoded entry index, marker offset within entry).",
            "dd6360 segments are parsed with PlayerRecord.from_bytes against the bytes up to the next marker.",
            "A missing same-surname dd6360 nearby does not prove no linked player record exists elsewhere in the file.",
        ],
        "results": selected,
    }
    if getattr(args, "corpus_surname_summary", False):
        windows: list[int] = []
        for part in str(getattr(args, "summary_windows", "")).split(","):
            part = part.strip()
            if not part:
                continue
            try:
                val = int(part)
            except Exception:
                continue
            if val > 0:
                windows.append(val)
        if not windows:
            windows = [10, 25, 50, 100, 200, 500]
        payload["corpus_surname_summary"] = _compute_corpus_surname_summary(stream, sorted(set(windows)))

    text = json.dumps(payload, indent=2)
    if args.json_output:
        out_path = Path(args.json_output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
