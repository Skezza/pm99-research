#!/usr/bin/env python3
"""Extract and inspect dd6361 bio trailer stats from PM99 player biographies.

Current reverse-engineering finding:
- Biography subrecords (`dd6361`) end with an 18-byte trailer before the next bio/player marker.
- After XOR with 0x61, trailer bytes 0..9 map directly to visible player stats:
  speed, stamina, aggression, quality, heading, dribbling, passing, shooting, tackling, handling

This script automates extraction and optional comparison against screenshot/OCR text data.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.xor import decode_entry  # type: ignore


BIO_MARKER = bytes([0xDD, 0x63, 0x61])
PLAYER_MARKER = bytes([0xDD, 0x63, 0x60])
TRAILER_LEN = 18
TRAILER_STAT_ORDER = [
    "speed",
    "stamina",
    "aggression",
    "quality",
    "heading",
    "dribbling",
    "passing",
    "shooting",
    "tackling",
    "handling",
]
TRAILER_ROLE_VECTOR_ORDER = ["role_1", "role_2", "role_3", "role_4", "role_5"]

BIO_FULL_NAME_RE = re.compile(
    r"([A-Z][a-z'\-]+(?:\s+\([^)]+\))?(?:\s+[A-Z][a-z'\-]+){0,4}\s+[A-Z][A-Z'\-]{2,}(?:\s+[A-Z][A-Z'\-]{2,}){0,2})"
)


def _normalize_spaces(value: str) -> str:
    return " ".join((value or "").split())


def _norm_name(value: str) -> str:
    text = _normalize_spaces(value)
    text = re.sub(r"[^A-Za-z0-9' ]+", " ", text)
    return _normalize_spaces(text).upper()


def _iter_decoded_entries(player_file: Path) -> list[tuple[int, bytes]]:
    data = player_file.read_bytes()
    entries: list[tuple[int, bytes]] = []
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
        entries.append((offset, decoded))
        offset += length + 2
    return entries


def _extract_bio_name(segment: bytes) -> str | None:
    text = segment.decode("latin-1", errors="ignore")
    head = text[:260]
    matches = list(BIO_FULL_NAME_RE.finditer(head))
    if not matches:
        return None
    return _normalize_spaces(matches[-1].group(1))


def _collect_bio_markers(entries: list[tuple[int, bytes]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry_idx, (entry_offset, decoded) in enumerate(entries):
        pos = decoded.find(BIO_MARKER)
        while pos != -1:
            seg = decoded[pos:min(len(decoded), pos + 640)]
            out.append(
                {
                    "entry_idx": entry_idx,
                    "entry_offset": entry_offset,
                    "marker_rel": pos,
                    "name": _extract_bio_name(seg),
                }
            )
            pos = decoded.find(BIO_MARKER, pos + 1)
    return out


def _assemble_bio_continuation(
    entries: list[tuple[int, bytes]],
    start_marker: dict[str, Any],
    next_marker: dict[str, Any],
) -> bytes:
    start_ei = int(start_marker["entry_idx"])
    next_ei = int(next_marker["entry_idx"])
    start_rel = int(start_marker["marker_rel"])
    next_rel = int(next_marker["marker_rel"])

    if start_ei == next_ei:
        return entries[start_ei][1][start_rel:next_rel]

    chunks: list[bytes] = [entries[start_ei][1][start_rel:]]
    for ei in range(start_ei + 1, next_ei):
        chunks.append(entries[ei][1])
    chunks.append(entries[next_ei][1][:next_rel])
    return b"".join(chunks)


def _extract_trailer_from_bio_continuation(cont: bytes) -> dict[str, Any] | None:
    # Some biographies terminate immediately before a dd6360 block, so only inspect the bio portion.
    dd60_pos = cont.find(PLAYER_MARKER, 3)
    bio_only = cont[:dd60_pos] if dd60_pos != -1 else cont

    if not bio_only:
        return None

    last_nl = max(bio_only.rfind(b"\n"), bio_only.rfind(b"\r"))
    suffix = bio_only[last_nl + 1:] if last_nl != -1 else bio_only[-64:]
    if len(suffix) < TRAILER_LEN:
        return None

    trailer = suffix[-TRAILER_LEN:]
    decoded_vals = [int(b ^ 0x61) for b in trailer]
    mapped10 = {name: decoded_vals[idx] for idx, name in enumerate(TRAILER_STAT_ORDER)}
    role_ratings5 = {name: decoded_vals[11 + idx] for idx, name in enumerate(TRAILER_ROLE_VECTOR_ORDER)}
    return {
        "bio_continuation_len": len(cont),
        "bio_only_len": len(bio_only),
        "first_dd6360_in_continuation": dd60_pos,
        "suffix_text_preview": suffix.decode("latin-1", errors="ignore"),
        "suffix_len": len(suffix),
        "trailer_hex": trailer.hex(),
        "decoded18": decoded_vals,
        "mapped10": mapped10,
        "role_ratings5": role_ratings5,
        "unknown_byte16_candidate": decoded_vals[16],
        "unknown_tail": decoded_vals[10:18],
    }


def _parse_example_player_data(example_file: Path) -> dict[str, dict[str, Any]]:
    """Parse the user-provided OCR-ish text file from screenshots.

    We detect player blocks by the pattern:
    <name line>
    Position: ...
    """
    text = example_file.read_text(encoding="utf-8", errors="ignore")
    lines = [ln.rstrip("\n") for ln in text.splitlines()]

    starts: list[int] = []
    for idx in range(len(lines)):
        header = lines[idx].strip()
        if not header:
            continue
        # Find the next non-empty line; OCR file inserts blank lines between most lines.
        j = idx + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines):
            continue
        nxt = lines[j].strip()
        if not nxt.startswith("Position:"):
            continue
        # Heuristic: player title line contains an uppercase surname token.
        if re.search(r"\b[A-Z][A-Z'\-]{2,}\b", header):
            starts.append(idx)

    parsed: dict[str, dict[str, Any]] = {}
    for s_idx, start in enumerate(starts):
        end = starts[s_idx + 1] if s_idx + 1 < len(starts) else len(lines)
        header = lines[start].strip()
        block = "\n".join(lines[start:end])

        core_m = re.search(
            r"Core attributes:\s*Speed\s*(\d+),\s*Stamina\s*(\d+),\s*Aggression\s*(\d+),\s*Quality\s*(\d+),\s*Fitness\s*(\d+),\s*Moral\s*(\d+)",
            block,
            flags=re.IGNORECASE,
        )
        rating_m = re.search(r"Rating:\s*(\d+)", block, flags=re.IGNORECASE)
        if not core_m:
            continue

        skills: dict[str, int] = {}
        for label in ("Handling", "Passing", "Dribbling", "Heading", "Tackling", "Shooting"):
            m = re.search(rf"{label}[^\n]*\((\d+)\)", block, flags=re.IGNORECASE)
            if m:
                skills[label.lower()] = int(m.group(1))

        core = list(map(int, core_m.groups()))
        pos_m = re.search(r"Position:\s*([^\n]+)", block, flags=re.IGNORECASE)
        role_m = re.search(r"Role \(ROL\.\):\s*([^\n]+)", block, flags=re.IGNORECASE)
        entry = {
            "name": header,
            "position": pos_m.group(1).strip() if pos_m else None,
            "role_label": role_m.group(1).strip() if role_m else None,
            "core": {
                "speed": core[0],
                "stamina": core[1],
                "aggression": core[2],
                "quality": core[3],
                "fitness": core[4],
                "moral": core[5],
            },
            "skills": skills,
        }
        if rating_m:
            entry["rating"] = int(rating_m.group(1))
        parsed[_norm_name(header)] = entry

    return parsed


def _compare_against_example(
    bio_name: str,
    mapped10: dict[str, int],
    example_map: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    # Prefer exact normalized name, then surname fallback.
    exact = example_map.get(_norm_name(bio_name))
    candidate = exact

    if candidate is None:
        bio_last = _norm_name(bio_name).split()[-1] if _norm_name(bio_name).split() else ""
        for key, val in example_map.items():
            parts = key.split()
            if parts and parts[-1] == bio_last:
                candidate = val
                break
    if candidate is None:
        return None

    expected = {
        "speed": int(candidate["core"]["speed"]),
        "stamina": int(candidate["core"]["stamina"]),
        "aggression": int(candidate["core"]["aggression"]),
        "quality": int(candidate["core"]["quality"]),
        "heading": int(candidate["skills"].get("heading", -1)),
        "dribbling": int(candidate["skills"].get("dribbling", -1)),
        "passing": int(candidate["skills"].get("passing", -1)),
        "shooting": int(candidate["skills"].get("shooting", -1)),
        "tackling": int(candidate["skills"].get("tackling", -1)),
        "handling": int(candidate["skills"].get("handling", -1)),
    }
    mismatches = {}
    for key, exp in expected.items():
        got = mapped10.get(key)
        if exp != -1 and got != exp:
            mismatches[key] = {"expected": exp, "decoded": got}

    example_rating_formula = (
        int(candidate["core"]["speed"])
        + int(candidate["core"]["stamina"])
        + int(candidate["core"]["aggression"])
        + int(candidate["core"]["quality"])
        + int(candidate["core"]["fitness"])
        + int(candidate["core"]["moral"])
    ) // 6
    mixed_rating_formula = (
        int(mapped10["speed"])
        + int(mapped10["stamina"])
        + int(mapped10["aggression"])
        + int(mapped10["quality"])
        + int(candidate["core"]["fitness"])
        + int(candidate["core"]["moral"])
    ) // 6

    return {
        "example_name": candidate["name"],
        "matches_all_mapped10": not mismatches,
        "mismatches": mismatches,
        "example_position": candidate.get("position"),
        "example_role_label": candidate.get("role_label"),
        "example_fitness": candidate["core"].get("fitness"),
        "example_moral": candidate["core"].get("moral"),
        "example_rating": candidate.get("rating"),
        "rating_formula_floor_mean_core6_example": example_rating_formula,
        "rating_formula_floor_mean_core6_using_trailer_mapped_core4_plus_example_fi_mo": mixed_rating_formula,
    }


def _summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Build corpus-level summaries for unresolved trailer bytes and role vectors."""
    if not results:
        return {
            "result_count": 0,
            "role_vector_all_equal_count": 0,
            "role_vector_non_equal_count": 0,
            "role_vector_all_equal_ratio": 0.0,
            "byte16_distribution_top20": [],
            "byte16_min": None,
            "byte16_max": None,
            "same_static_role_sig_different_byte16_examples": [],
        }

    byte16_vals: list[int] = []
    role_equal_count = 0
    role_shape_counter: Counter[str] = Counter()

    # Signature excludes byte16 (decoded18[16]) so we can test whether byte16 varies
    # independently for otherwise identical trailer stats + role vectors.
    by_static_role_sig: dict[tuple[int, ...], list[dict[str, Any]]] = defaultdict(list)

    for row in results:
        decoded18 = row.get("decoded18") or []
        if len(decoded18) < 18:
            continue
        try:
            decoded18_ints = [int(v) for v in decoded18]
        except Exception:
            continue

        byte16_vals.append(decoded18_ints[16])
        role_vals = decoded18_ints[11:16]
        if len(set(role_vals)) == 1:
            role_equal_count += 1
            role_shape_counter["all_equal"] += 1
        else:
            role_shape_counter["non_equal"] += 1

        static_sig = tuple(decoded18_ints[:16])  # excludes byte16 and trailing zero byte17
        by_static_role_sig[static_sig].append(
            {
                "name": row.get("name"),
                "entry_offset": row.get("entry_offset"),
                "marker_rel": row.get("marker_rel"),
                "decoded18": decoded18_ints,
                "mapped10": row.get("mapped10"),
                "role_ratings5": row.get("role_ratings5"),
                "unknown_byte16_candidate": decoded18_ints[16],
            }
        )

    varying_byte16_examples: list[dict[str, Any]] = []
    for sig_rows in by_static_role_sig.values():
        vals = sorted({int(r["unknown_byte16_candidate"]) for r in sig_rows})
        if len(vals) <= 1:
            continue
        varying_byte16_examples.append(
            {
                "count": len(sig_rows),
                "byte16_values": vals,
                "examples": [
                    {
                        "name": r.get("name"),
                        "entry_offset": r.get("entry_offset"),
                        "marker_rel": r.get("marker_rel"),
                    }
                    for r in sig_rows[:6]
                ],
                # Include one representative decoded18 to anchor the claim.
                "representative_decoded18": sig_rows[0].get("decoded18"),
                "representative_mapped10": sig_rows[0].get("mapped10"),
                "representative_role_ratings5": sig_rows[0].get("role_ratings5"),
            }
        )

    varying_byte16_examples.sort(
        key=lambda item: (-int(item.get("count", 0)), -len(item.get("byte16_values", [])))
    )
    byte16_counter = Counter(byte16_vals)

    total = len(results)
    role_non_equal_count = total - role_equal_count

    return {
        "result_count": total,
        "role_vector_all_equal_count": role_equal_count,
        "role_vector_non_equal_count": role_non_equal_count,
        "role_vector_all_equal_ratio": (role_equal_count / total) if total else 0.0,
        "role_vector_shape_counts": dict(role_shape_counter),
        "byte16_distribution_top20": [
            {"value": int(v), "count": int(c)} for v, c in byte16_counter.most_common(20)
        ],
        "byte16_min": min(byte16_vals) if byte16_vals else None,
        "byte16_max": max(byte16_vals) if byte16_vals else None,
        "same_static_role_sig_different_byte16_example_count": len(varying_byte16_examples),
        "same_static_role_sig_different_byte16_examples": varying_byte16_examples[:12],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Probe dd6361 biography trailers and decode stat bytes")
    p.add_argument(
        "--player-file",
        default=str(REPO_ROOT / "DBDAT" / "JUG98030.FDI"),
        help="Path to JUG98030.FDI",
    )
    p.add_argument(
        "--name",
        action="append",
        default=[],
        help="Player full-name query (repeatable). Matches exact dd6361 extracted name first, then substring.",
    )
    p.add_argument(
        "--example-data",
        default=str(REPO_ROOT / ".local" / "PlayerStills" / "ExamplePlayerData.txt"),
        help="Optional OCR/screenshot text file for comparison (skip with --no-example-compare)",
    )
    p.add_argument(
        "--no-example-compare",
        action="store_true",
        help="Disable comparison against the example screenshot text file",
    )
    p.add_argument("--json-output", help="Write JSON output to this path")
    p.add_argument(
        "--include-corpus-summary",
        action="store_true",
        help="Add corpus-level summaries (role-vector shapes, byte16 distribution, and same-static/different-byte16 evidence)",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    player_file = Path(args.player_file)
    if not player_file.exists():
        print(json.dumps({"error": f"Player file not found: {player_file}"}, indent=2))
        return 2

    entries = _iter_decoded_entries(player_file)
    markers = _collect_bio_markers(entries)

    example_map: dict[str, dict[str, Any]] = {}
    if not args.no_example_compare:
        example_file = Path(args.example_data)
        if example_file.exists():
            example_map = _parse_example_player_data(example_file)

    queries = [_normalize_spaces(q) for q in args.name if _normalize_spaces(q)]
    query_norms = [_norm_name(q) for q in queries]

    results: list[dict[str, Any]] = []
    for idx, marker in enumerate(markers[:-1]):
        name = marker.get("name")
        if not name:
            continue
        if query_norms:
            n = _norm_name(name)
            if not any((q == n) or (q in n) for q in query_norms):
                continue

        next_marker = markers[idx + 1]
        cont = _assemble_bio_continuation(entries, marker, next_marker)
        trailer_info = _extract_trailer_from_bio_continuation(cont)
        if trailer_info is None:
            continue

        row = {
            "name": name,
            "entry_offset": int(marker["entry_offset"]),
            "marker_rel": int(marker["marker_rel"]),
            "next_marker": {
                "entry_offset": int(next_marker["entry_offset"]),
                "marker_rel": int(next_marker["marker_rel"]),
                "name": next_marker.get("name"),
            },
            **trailer_info,
        }
        if example_map:
            cmp = _compare_against_example(name, trailer_info["mapped10"], example_map)
            if cmp is not None:
                row["example_compare"] = cmp
        results.append(row)

    payload = {
        "player_file": str(player_file),
        "decoded_entry_count": len(entries),
        "bio_marker_count": len(markers),
        "mapped10_order": TRAILER_STAT_ORDER,
        "notes": [
            "Trailer bytes are XOR-decoded with 0x61.",
            "mapped10 covers visible static skill/quality attributes but not fitness/moral.",
            "role_ratings5 (decoded18[11:16]) are likely role/suitability values or another derived rating family.",
            "unknown_byte16_candidate (decoded18[16]) is unresolved and may be dynamic state (e.g. energy) or a code.",
            "Bytes decoded18[10:18] remain unresolved in this probe.",
        ],
        "results": results,
    }
    if args.include_corpus_summary:
        payload["corpus_summary"] = _summarize_results(results)

    text = json.dumps(payload, indent=2)
    if args.json_output:
        out_path = Path(args.json_output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
