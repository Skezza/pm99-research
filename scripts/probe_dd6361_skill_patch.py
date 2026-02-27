#!/usr/bin/env python3
"""Patch dd6361 biography trailer stats on a copy of JUG98030.FDI.

This script operationalizes the verified finding that dd6361 biography trailers
encode the visible player stat block (core4 + 6 technical skills) after XOR with 0x61.

It is intentionally conservative:
- patches only fixed-size trailer bytes (no resizing)
- rewrites only touched FDI entries
- validates entry size is unchanged
- writes to a separate output file by default
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.xor import decode_entry, encode_entry  # type: ignore
from scripts import probe_bio_trailer_stats as bp  # type: ignore


TRAILER_INDEX_BY_FIELD = {name: idx for idx, name in enumerate(bp.TRAILER_STAT_ORDER)}


def _iter_entries_with_lengths(file_bytes: bytes) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    offset = 0x400
    data_len = len(file_bytes)
    while offset + 2 <= data_len:
        length = int.from_bytes(file_bytes[offset:offset + 2], "little")
        if length <= 0 or offset + 2 + length > data_len:
            offset += 1
            continue
        try:
            decoded, enc_len = decode_entry(file_bytes, offset)
        except Exception:
            offset += 1
            continue
        entries.append(
            {
                "offset": offset,
                "length": enc_len,
                "decoded": bytearray(decoded),
            }
        )
        offset += 2 + length
    return entries


def _collect_markers(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lightweight = [(int(e["offset"]), bytes(e["decoded"])) for e in entries]
    return bp._collect_bio_markers(lightweight)


def _assemble_continuation_with_spans(
    entries: list[dict[str, Any]],
    start_marker: dict[str, Any],
    next_marker: dict[str, Any],
) -> tuple[bytes, list[dict[str, int]]]:
    start_ei = int(start_marker["entry_idx"])
    next_ei = int(next_marker["entry_idx"])
    start_rel = int(start_marker["marker_rel"])
    next_rel = int(next_marker["marker_rel"])

    spans: list[dict[str, int]] = []
    chunks: list[bytes] = []
    global_pos = 0

    if start_ei == next_ei:
        chunk = bytes(entries[start_ei]["decoded"][start_rel:next_rel])
        chunks.append(chunk)
        spans.append(
            {
                "entry_idx": start_ei,
                "rel_start": start_rel,
                "rel_end": next_rel,
                "global_start": global_pos,
                "global_end": global_pos + len(chunk),
            }
        )
        return b"".join(chunks), spans

    # First partial entry.
    first_dec = entries[start_ei]["decoded"]
    chunk = bytes(first_dec[start_rel:])
    chunks.append(chunk)
    spans.append(
        {
            "entry_idx": start_ei,
            "rel_start": start_rel,
            "rel_end": len(first_dec),
            "global_start": global_pos,
            "global_end": global_pos + len(chunk),
        }
    )
    global_pos += len(chunk)

    # Middle full entries.
    for ei in range(start_ei + 1, next_ei):
        dec = entries[ei]["decoded"]
        chunk = bytes(dec)
        chunks.append(chunk)
        spans.append(
            {
                "entry_idx": ei,
                "rel_start": 0,
                "rel_end": len(dec),
                "global_start": global_pos,
                "global_end": global_pos + len(chunk),
            }
        )
        global_pos += len(chunk)

    # Final partial entry.
    last_dec = entries[next_ei]["decoded"]
    chunk = bytes(last_dec[:next_rel])
    chunks.append(chunk)
    spans.append(
        {
            "entry_idx": next_ei,
            "rel_start": 0,
            "rel_end": next_rel,
            "global_start": global_pos,
            "global_end": global_pos + len(chunk),
        }
    )

    return b"".join(chunks), spans


def _select_target_marker(
    markers: list[dict[str, Any]],
    query: str,
) -> tuple[int, dict[str, Any]]:
    q_norm = bp._norm_name(query)
    if not q_norm:
        raise ValueError("Empty query")

    candidates: list[tuple[int, dict[str, Any]]] = []
    for idx, m in enumerate(markers[:-1]):
        name = m.get("name")
        if not name:
            continue
        n = bp._norm_name(str(name))
        if n == q_norm:
            return idx, m
        if q_norm in n:
            candidates.append((idx, m))

    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        # surname fallback
        q_parts = q_norm.split()
        if q_parts:
            surname = q_parts[-1]
            surname_hits = []
            for idx, m in enumerate(markers[:-1]):
                name = m.get("name")
                if not name:
                    continue
                parts = bp._norm_name(str(name)).split()
                if parts and parts[-1] == surname:
                    surname_hits.append((idx, m))
            if len(surname_hits) == 1:
                return surname_hits[0]
            if surname_hits:
                names = [str(m.get("name")) for _, m in surname_hits]
                raise ValueError(f"Ambiguous surname match for {query!r}: {names}")
        raise ValueError(f"No dd6361 bio marker match for {query!r}")

    names = [str(m.get("name")) for _, m in candidates]
    raise ValueError(f"Ambiguous substring match for {query!r}: {names}")


def _parse_set_args(set_args: list[str]) -> dict[str, int]:
    updates: dict[str, int] = {}
    for item in set_args:
        if "=" not in item:
            raise ValueError(f"Invalid --set {item!r}; expected FIELD=VALUE")
        key, val = item.split("=", 1)
        key = key.strip().lower()
        if key not in TRAILER_INDEX_BY_FIELD:
            raise ValueError(
                f"Unsupported field {key!r}; supported fields: {', '.join(bp.TRAILER_STAT_ORDER)}"
            )
        try:
            ival = int(val.strip(), 10)
        except Exception as exc:
            raise ValueError(f"Invalid integer value for {key!r}: {val!r}") from exc
        if not (0 <= ival <= 255):
            raise ValueError(f"Value for {key!r} out of byte range: {ival}")
        updates[key] = ival
    if not updates:
        raise ValueError("At least one --set FIELD=VALUE is required")
    return updates


def parse_update_assignments(set_args: list[str]) -> dict[str, int]:
    """Public wrapper used by app.cli and tests."""
    return _parse_set_args(set_args)


def inspect_dd6361_trailer_stats(
    *,
    player_file: str | Path,
    name_query: str,
) -> dict[str, Any]:
    """
    Inspect the verified dd6361 trailer stat mapping for a player without patching.

    Returns a JSON-serializable payload aligned with the patch workflow's metadata so
    GUI/CLI tooling can prefill forms safely before applying changes.
    """
    in_path = Path(player_file)
    file_bytes = in_path.read_bytes()
    entries = _iter_entries_with_lengths(file_bytes)
    markers = _collect_markers(entries)
    marker_idx, marker = _select_target_marker(markers, name_query)
    next_marker = markers[marker_idx + 1]

    cont, _spans = _assemble_continuation_with_spans(entries, marker, next_marker)
    trailer_info = bp._extract_trailer_from_bio_continuation(cont)
    if trailer_info is None:
        raise RuntimeError("Could not extract dd6361 trailer for selected player")

    bio_name = str(marker.get("name"))
    mapped10 = dict(trailer_info["mapped10"])
    payload = {
        "input_file": str(in_path),
        "target_query": name_query,
        "resolved_bio_name": bio_name,
        "marker": {
            "entry_offset": int(marker["entry_offset"]),
            "marker_rel": int(marker["marker_rel"]),
            "next_entry_offset": int(next_marker["entry_offset"]),
            "next_marker_rel": int(next_marker["marker_rel"]),
        },
        "mapped10_order": list(bp.TRAILER_STAT_ORDER),
        "mapped10": mapped10,
        "decoded18": [int(v) for v in trailer_info["decoded18"]],
        "role_ratings5": dict(trailer_info.get("role_ratings5") or {}),
        "unknown_byte16_candidate": int(trailer_info["unknown_byte16_candidate"]),
        "trailer_location": {
            "bio_only_len": int(trailer_info["bio_only_len"]),
            "trailer_len": int(bp.TRAILER_LEN),
            "dd6360_pos_in_continuation": int(trailer_info["first_dd6360_in_continuation"])
            if trailer_info["first_dd6360_in_continuation"] is not None
            else -1,
            "continuation_len": len(cont),
        },
    }
    return payload


def build_dd6361_pid_stats_index(
    *,
    player_file: str | Path,
) -> dict[int, dict[str, Any]]:
    """
    Build a single-pass dd6361 PID->visible-stat index for parser-backed roster workflows.

    Each entry includes the resolved biography name plus the verified mapped10 trailer fields.
    """
    in_path = Path(player_file)
    file_bytes = in_path.read_bytes()
    entries = _iter_entries_with_lengths(file_bytes)
    markers = _collect_markers(entries)
    out: dict[int, dict[str, Any]] = {}
    for marker_idx, marker in enumerate(markers[:-1]):
        next_marker = markers[marker_idx + 1]
        entry_idx = int(marker["entry_idx"])
        marker_rel = int(marker["marker_rel"])
        decoded = entries[entry_idx]["decoded"]
        if marker_rel + 5 > len(decoded):
            continue
        pid = int((decoded[marker_rel + 3] ^ 0x61) | ((decoded[marker_rel + 4] ^ 0x61) << 8))
        if pid <= 0:
            continue
        cont, _spans = _assemble_continuation_with_spans(entries, marker, next_marker)
        trailer_info = bp._extract_trailer_from_bio_continuation(cont)
        if trailer_info is None:
            continue
        out[pid] = {
            "pid": pid,
            "resolved_bio_name": str(marker.get("name") or ""),
            "mapped10": dict(trailer_info["mapped10"]),
            "decoded18": [int(v) for v in trailer_info["decoded18"]],
            "role_ratings5": dict(trailer_info.get("role_ratings5") or {}),
            "unknown_byte16_candidate": int(trailer_info["unknown_byte16_candidate"]),
        }
    return out


def _apply_trailer_patch_to_entries(
    entries: list[dict[str, Any]],
    spans: list[dict[str, int]],
    cont_before: bytes,
    trailer_start: int,
    trailer_bytes_new: bytes,
) -> list[int]:
    cont_after = bytearray(cont_before)
    cont_after[trailer_start:trailer_start + len(trailer_bytes_new)] = trailer_bytes_new

    patch_start = trailer_start
    patch_end = trailer_start + len(trailer_bytes_new)
    touched_entry_indexes: set[int] = set()

    for span in spans:
        gs = int(span["global_start"])
        ge = int(span["global_end"])
        overlap_start = max(gs, patch_start)
        overlap_end = min(ge, patch_end)
        if overlap_start >= overlap_end:
            continue
        entry_idx = int(span["entry_idx"])
        rel_start = int(span["rel_start"]) + (overlap_start - gs)
        rel_end = rel_start + (overlap_end - overlap_start)
        entries[entry_idx]["decoded"][rel_start:rel_end] = cont_after[overlap_start:overlap_end]
        touched_entry_indexes.add(entry_idx)

    return sorted(touched_entry_indexes)


def _write_touched_entries_same_size(
    original_file_bytes: bytes,
    entries: list[dict[str, Any]],
    touched_entry_indexes: list[int],
) -> bytes:
    out = bytearray(original_file_bytes)
    for ei in sorted(touched_entry_indexes, reverse=True):
        e = entries[ei]
        offset = int(e["offset"])
        old_len = int(e["length"])
        encoded = encode_entry(bytes(e["decoded"]))
        expected_size = 2 + old_len
        if len(encoded) != expected_size:
            raise RuntimeError(
                f"Entry 0x{offset:x} size changed ({expected_size} -> {len(encoded)}), aborting"
            )
        out[offset:offset + expected_size] = encoded
    return bytes(out)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Patch dd6361 trailer stats on a copy of JUG98030.FDI")
    p.add_argument(
        "--player-file",
        default=str(REPO_ROOT / "DBDAT" / "JUG98030.FDI"),
        help="Path to JUG98030.FDI input",
    )
    p.add_argument("--name", required=True, help="Player name query (dd6361 biography name)")
    p.add_argument(
        "--set",
        dest="set_args",
        action="append",
        default=[],
        help=f"Set one mapped10 field (repeatable): {','.join(bp.TRAILER_STAT_ORDER)}",
    )
    p.add_argument(
        "--output-file",
        default=str(Path("/tmp") / "JUG98030.dd6361_patched.FDI"),
        help="Patched output file path (copy)",
    )
    p.add_argument("--json-output", help="Write JSON report to this path")
    return p.parse_args(argv)


def patch_dd6361_trailer_stats(
    *,
    player_file: str | Path,
    name_query: str,
    updates: dict[str, int],
    output_file: str | Path | None = None,
    in_place: bool = False,
    create_backup_before_write: bool = False,
    json_output: str | Path | None = None,
) -> dict[str, Any]:
    in_path = Path(player_file)
    if in_place:
        if output_file is not None and Path(output_file) != in_path:
            raise ValueError("--in-place cannot be combined with a different output_file")
        out_path = in_path
    else:
        if output_file is None:
            raise ValueError("output_file is required unless in_place=True")
        out_path = Path(output_file)
    updates_norm: dict[str, int] = {}
    for field, value in dict(updates).items():
        key = str(field).strip().lower()
        if key not in TRAILER_INDEX_BY_FIELD:
            raise ValueError(
                f"Unsupported field {field!r}; supported fields: {', '.join(bp.TRAILER_STAT_ORDER)}"
            )
        ival = int(value)
        if not (0 <= ival <= 255):
            raise ValueError(f"Value for {key!r} out of byte range: {ival}")
        updates_norm[key] = ival
    if not updates_norm:
        raise ValueError("At least one field update is required")

    file_bytes = in_path.read_bytes()
    entries = _iter_entries_with_lengths(file_bytes)
    markers = _collect_markers(entries)
    marker_idx, marker = _select_target_marker(markers, name_query)
    next_marker = markers[marker_idx + 1]

    cont, spans = _assemble_continuation_with_spans(entries, marker, next_marker)
    trailer_info = bp._extract_trailer_from_bio_continuation(cont)
    if trailer_info is None:
        raise RuntimeError("Could not extract dd6361 trailer for selected player")

    bio_name = str(marker.get("name"))
    decoded18_before = [int(v) for v in trailer_info["decoded18"]]
    mapped10_before = dict(trailer_info["mapped10"])
    dd60_pos = int(trailer_info["first_dd6360_in_continuation"]) if trailer_info["first_dd6360_in_continuation"] is not None else -1
    bio_only_len = int(trailer_info["bio_only_len"])
    trailer_start = bio_only_len - int(bp.TRAILER_LEN)
    if trailer_start < 0:
        raise RuntimeError("Invalid trailer start computed")

    decoded18_after = list(decoded18_before)
    for field, new_value in updates_norm.items():
        decoded18_after[TRAILER_INDEX_BY_FIELD[field]] = int(new_value)
    trailer_bytes_new = bytes(int(v) ^ 0x61 for v in decoded18_after)

    touched_entries = _apply_trailer_patch_to_entries(entries, spans, cont, trailer_start, trailer_bytes_new)
    patched_file = _write_touched_entries_same_size(file_bytes, entries, touched_entries)

    backup_path: str | None = None
    if create_backup_before_write:
        from app.file_writer import create_backup  # local import to keep script startup lightweight

        backup_path = create_backup(str(out_path))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(patched_file)

    # Verification pass on the patched output (same query).
    verify_entries = bp._iter_decoded_entries(out_path)
    verify_markers = bp._collect_bio_markers(verify_entries)
    verify_idx, verify_marker = _select_target_marker(verify_markers, bio_name)
    verify_cont = bp._assemble_bio_continuation(verify_entries, verify_marker, verify_markers[verify_idx + 1])
    verify_trailer = bp._extract_trailer_from_bio_continuation(verify_cont)
    if verify_trailer is None:
        raise RuntimeError("Verification failed: patched trailer could not be re-read")

    mapped10_after = dict(verify_trailer["mapped10"])

    payload = {
        "input_file": str(in_path),
        "output_file": str(out_path),
        "in_place": bool(in_place),
        "backup_path": backup_path,
        "target_query": name_query,
        "resolved_bio_name": bio_name,
        "marker": {
            "entry_offset": int(marker["entry_offset"]),
            "marker_rel": int(marker["marker_rel"]),
            "next_entry_offset": int(next_marker["entry_offset"]),
            "next_marker_rel": int(next_marker["marker_rel"]),
        },
        "trailer_location": {
            "bio_only_len": bio_only_len,
            "trailer_start_in_continuation": trailer_start,
            "trailer_len": int(bp.TRAILER_LEN),
            "dd6360_pos_in_continuation": dd60_pos,
            "continuation_len": len(cont),
            "touched_entry_indexes": touched_entries,
            "touched_entry_offsets": [int(entries[i]["offset"]) for i in touched_entries],
        },
        "updates_requested": updates_norm,
        "mapped10_order": list(bp.TRAILER_STAT_ORDER),
        "mapped10_before": mapped10_before,
        "mapped10_after": mapped10_after,
        "decoded18_before": decoded18_before,
        "decoded18_after": [int(v) for v in verify_trailer["decoded18"]],
        "verification": {
            "all_requested_fields_match": all(int(mapped10_after[k]) == int(v) for k, v in updates_norm.items()),
            "unchanged_unrequested_fields": {
                k: bool(mapped10_after[k] == mapped10_before[k])
                for k in bp.TRAILER_STAT_ORDER
                if k not in updates_norm
            },
        },
        "notes": [
            "This patches the raw dd6361 trailer bytes (stored XOR-encoded inside the decoded bio continuation).",
            "Only fixed-size trailer byte edits are supported; entry lengths must remain unchanged.",
            "Use on a copy first and validate in-game before integrating write support into the main editor UX.",
        ],
    }

    if json_output:
        Path(json_output).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    updates = _parse_set_args(args.set_args)
    payload = patch_dd6361_trailer_stats(
        player_file=args.player_file,
        name_query=args.name,
        updates=updates,
        output_file=args.output_file,
        in_place=False,
        create_backup_before_write=False,
        json_output=args.json_output,
    )
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
