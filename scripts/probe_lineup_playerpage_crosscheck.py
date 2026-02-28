#!/usr/bin/env python3
"""Cross-check lineup-table screenshots against player-page screenshots and dd6361 bios.

This probe connects three evidence sources:
- manually transcribed lineup-table screenshots (`probe_lineup_screenshot.py`)
- user-provided player-page screenshots/OCR text (`ExamplePlayerData.txt`)
- decoded `dd6361` biography trailers from `JUG98030.FDI`

The goal is to validate which lineup columns are stable/static vs context-dependent and
to provide a reproducible artifact for name disambiguation cases (notably `Keane`).
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

from scripts import probe_bio_trailer_stats as trailer_probe  # type: ignore
from scripts import probe_lineup_screenshot as lineup_probe  # type: ignore
from scripts import probe_screenshot_rol_boxes as rol_box_probe  # type: ignore


LINEUP_TO_PLAYERSTILLS_FULL_NAME_HINTS = {
    # Stoke screenshot overlap
    "Kavanagh": "Graham KAVANAGH",
    # Man Utd screenshot overlaps
    "Schmeichel": "Peter Boleslaw SCHMEICHEL",
    "Beckham": "David Robert BECKHAM",
    "Scholes": "Paul SCHOLES",
    "Stam": "Jaap STAM",
    "Cole": "Andrew Alexander COLE",
    "Giggs": "Ryan Joseph GIGGS",
    "Yorke": "Dwight YORKE",
}


def _norm(text: str) -> str:
    return trailer_probe._norm_name(text)


def _build_dd6361_rows(player_file: Path) -> list[dict[str, Any]]:
    entries = trailer_probe._iter_decoded_entries(player_file)
    markers = trailer_probe._collect_bio_markers(entries)

    out: list[dict[str, Any]] = []
    for idx, marker in enumerate(markers[:-1]):
        name = marker.get("name")
        if not name:
            continue
        cont = trailer_probe._assemble_bio_continuation(entries, marker, markers[idx + 1])
        trailer_info = trailer_probe._extract_trailer_from_bio_continuation(cont)
        if trailer_info is None:
            continue
        out.append(
            {
                "name": str(name),
                "entry_offset": int(marker["entry_offset"]),
                "marker_rel": int(marker["marker_rel"]),
                **trailer_info,
            }
        )
    return out


def _index_dd6361_rows(rows: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    by_norm_full: dict[str, dict[str, Any]] = {}
    by_surname: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        full = _norm(str(row.get("name", "")))
        if full:
            by_norm_full.setdefault(full, row)
            parts = full.split()
            if parts:
                by_surname.setdefault(parts[-1], []).append(row)
    for surname in by_surname:
        by_surname[surname] = sorted(by_surname[surname], key=lambda r: str(r.get("name", "")))
    return by_norm_full, by_surname


def _find_example_entry_for_lineup_row(
    lineup_row: dict[str, Any],
    example_map: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    lineup_name = str(lineup_row.get("name", "")).strip()
    if not lineup_name:
        return None

    # Try explicit hints first for known screenshot overlaps.
    hinted = LINEUP_TO_PLAYERSTILLS_FULL_NAME_HINTS.get(lineup_name)
    if hinted:
        exact = example_map.get(_norm(hinted))
        if exact is not None:
            return exact

    # Exact normalized name.
    exact = example_map.get(_norm(lineup_name))
    if exact is not None:
        return exact

    # Surname fallback.
    q_parts = _norm(lineup_name).split()
    if not q_parts:
        return None
    surname = q_parts[-1]
    for key in sorted(example_map.keys()):
        parts = key.split()
        if parts and parts[-1] == surname:
            return example_map[key]
    return None


def _manual_player_page_rol_num(example_entry: dict[str, Any], manual_map: dict[str, int]) -> int | None:
    full_name = str(example_entry.get("name", "")).strip()
    if full_name in manual_map:
        return int(manual_map[full_name])

    surname = _norm(full_name).split()[-1] if _norm(full_name).split() else ""
    for k, v in manual_map.items():
        parts = _norm(str(k)).split()
        if parts and surname and parts[-1] == surname:
            return int(v)
    return None


def _core4_from_lineup(row: dict[str, Any]) -> dict[str, int]:
    return {
        "speed": int(row["sp"]),
        "stamina": int(row["st"]),
        "aggression": int(row["ag"]),
        "quality": int(row["qu"]),
    }


def _core6_from_lineup(row: dict[str, Any]) -> dict[str, int]:
    return {
        "speed": int(row["sp"]),
        "stamina": int(row["st"]),
        "aggression": int(row["ag"]),
        "quality": int(row["qu"]),
        "fitness": int(row["fi"]),
        "moral": int(row["mo"]),
    }


def _core4_equal(a: dict[str, int], b: dict[str, int]) -> bool:
    return all(int(a[k]) == int(b[k]) for k in ("speed", "stamina", "aggression", "quality"))


def _core6_mismatches(lineup_row: dict[str, Any], example_entry: dict[str, Any]) -> dict[str, dict[str, int]]:
    core = example_entry.get("core") or {}
    mapping = {
        "sp": "speed",
        "st": "stamina",
        "ag": "aggression",
        "qu": "quality",
        "fi": "fitness",
        "mo": "moral",
    }
    out: dict[str, dict[str, int]] = {}
    for lineup_key, core_key in mapping.items():
        try:
            got = int(lineup_row[lineup_key])
            exp = int(core[core_key])
        except Exception:
            continue
        if got != exp:
            out[core_key] = {"lineup": got, "player_page": exp}
    return out


def _find_dd6361_exact_or_surname_candidates(
    lineup_row: dict[str, Any],
    example_entry: dict[str, Any] | None,
    by_norm_full: dict[str, dict[str, Any]],
    by_surname: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    # Prefer exact full-name from the player-page screenshot entry (strongest identifier).
    if example_entry is not None:
        full_name = str(example_entry.get("name", "")).strip()
        exact = by_norm_full.get(_norm(full_name))
        surname = _norm(full_name).split()[-1] if _norm(full_name).split() else ""
        return exact, list(by_surname.get(surname, []))

    lineup_name = str(lineup_row.get("name", "")).strip()
    surname = _norm(lineup_name).split()[-1] if _norm(lineup_name).split() else ""
    return None, list(by_surname.get(surname, []))


def _keane_candidate_summary(
    lineup_row: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    target = _core4_from_lineup(lineup_row)
    out: list[dict[str, Any]] = []
    for row in candidates:
        mapped10 = row.get("mapped10") or {}
        cand_core4 = {
            "speed": int(mapped10.get("speed", -1)),
            "stamina": int(mapped10.get("stamina", -1)),
            "aggression": int(mapped10.get("aggression", -1)),
            "quality": int(mapped10.get("quality", -1)),
        }
        l1 = sum(abs(int(target[k]) - int(cand_core4[k])) for k in target)
        out.append(
            {
                "dd6361_name": row.get("name"),
                "mapped10_core4": cand_core4,
                "lineup_core4_exact_match": _core4_equal(target, cand_core4),
                "core4_l1_distance": int(l1),
                "unknown_byte16_candidate": row.get("unknown_byte16_candidate"),
                "entry_offset": row.get("entry_offset"),
                "marker_rel": row.get("marker_rel"),
            }
        )
    out.sort(key=lambda r: (0 if r["lineup_core4_exact_match"] else 1, int(r["core4_l1_distance"]), str(r["dd6361_name"])))
    return out


def _dataset_crosscheck(
    dataset_key: str,
    rows: list[dict[str, Any]],
    example_map: dict[str, dict[str, Any]],
    manual_rol_map: dict[str, int],
    by_norm_full: dict[str, dict[str, Any]],
    by_surname: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    validation = lineup_probe._validate_rows(rows)

    overlaps: list[dict[str, Any]] = []
    example_overlap_count = 0
    core6_match_count = 0
    av_eq_rating_count = 0
    rol_num_comp_count = 0
    rol_num_eq_count = 0
    dd6361_core4_exact_count = 0

    for row in rows:
        example_entry = _find_example_entry_for_lineup_row(row, example_map)
        dd6361_exact, dd6361_surname_candidates = _find_dd6361_exact_or_surname_candidates(
            row, example_entry, by_norm_full, by_surname
        )

        record: dict[str, Any] = {
            "lineup_row": {
                "dataset": dataset_key,
                "n": int(row["n"]),
                "name": str(row["name"]),
                "section": str(row["section"]),
                "pos": str(row["pos"]),
                "rol": int(row["rol"]),
                "en": int(row["en"]),
                "sp": int(row["sp"]),
                "st": int(row["st"]),
                "ag": int(row["ag"]),
                "qu": int(row["qu"]),
                "fi": int(row["fi"]),
                "mo": int(row["mo"]),
                "av": int(row["av"]),
            },
            "dd6361_surname_candidate_count": len(dd6361_surname_candidates),
            "dd6361_surname_candidates": [
                {
                    "name": c.get("name"),
                    "mapped10_core4": {
                        "speed": int((c.get("mapped10") or {}).get("speed", -1)),
                        "stamina": int((c.get("mapped10") or {}).get("stamina", -1)),
                        "aggression": int((c.get("mapped10") or {}).get("aggression", -1)),
                        "quality": int((c.get("mapped10") or {}).get("quality", -1)),
                    },
                }
                for c in dd6361_surname_candidates[:8]
            ],
        }

        if dd6361_exact is not None:
            dd_core4 = {
                "speed": int((dd6361_exact.get("mapped10") or {}).get("speed", -1)),
                "stamina": int((dd6361_exact.get("mapped10") or {}).get("stamina", -1)),
                "aggression": int((dd6361_exact.get("mapped10") or {}).get("aggression", -1)),
                "quality": int((dd6361_exact.get("mapped10") or {}).get("quality", -1)),
            }
            lineup_core4 = _core4_from_lineup(row)
            dd_core4_match = _core4_equal(lineup_core4, dd_core4)
            if dd_core4_match:
                dd6361_core4_exact_count += 1
            record["dd6361_exact"] = {
                "name": dd6361_exact.get("name"),
                "entry_offset": dd6361_exact.get("entry_offset"),
                "marker_rel": dd6361_exact.get("marker_rel"),
                "mapped10_core4": dd_core4,
                "role_ratings5": dd6361_exact.get("role_ratings5"),
                "unknown_byte16_candidate": dd6361_exact.get("unknown_byte16_candidate"),
                "lineup_core4_exact_match": dd_core4_match,
            }

        if example_entry is None:
            continue

        example_overlap_count += 1
        core_mismatches = _core6_mismatches(row, example_entry)
        core6_match = not core_mismatches
        if core6_match:
            core6_match_count += 1

        player_page_rol_num = _manual_player_page_rol_num(example_entry, manual_rol_map)
        rol_num_eq = None
        if player_page_rol_num is not None:
            rol_num_comp_count += 1
            rol_num_eq = int(player_page_rol_num) == int(row["rol"])
            if rol_num_eq:
                rol_num_eq_count += 1

        try:
            example_rating = int(example_entry.get("rating")) if example_entry.get("rating") is not None else None
        except Exception:
            example_rating = None
        av_eq_rating = (example_rating is not None) and (int(row["av"]) == int(example_rating))
        if av_eq_rating:
            av_eq_rating_count += 1

        # If OCR/player-page text mismatches a lineup core stat but the exact dd6361 core4 matches,
        # this is strong evidence the lineup transcription is correct and the OCR text is wrong.
        likely_ocr_issue = False
        if core_mismatches and "dd6361_exact" in record:
            dd_match = bool(record["dd6361_exact"].get("lineup_core4_exact_match"))
            mismatch_keys = sorted(core_mismatches.keys())
            if dd_match and all(k in {"speed", "stamina", "aggression", "quality"} for k in mismatch_keys):
                likely_ocr_issue = True

        record["player_page"] = {
            "name": example_entry.get("name"),
            "position": example_entry.get("position"),
            "role_label": example_entry.get("role_label"),
            "core6": example_entry.get("core"),
            "rating": example_rating,
            "rol_num_manual": player_page_rol_num,
            "lineup_core6_matches_player_page": core6_match,
            "lineup_core6_mismatches": core_mismatches,
            "lineup_av_equals_player_page_rating": av_eq_rating,
            "lineup_rol_equals_player_page_rol_num": rol_num_eq,
            "likely_ocr_issue_if_mismatch": likely_ocr_issue,
        }
        overlaps.append(record)

    summary = {
        "dataset_key": dataset_key,
        "lineup_row_count": len(rows),
        "lineup_validation": validation,
        "player_page_overlap_count": example_overlap_count,
        "player_page_core6_exact_match_count": core6_match_count,
        "player_page_av_equals_rating_count": av_eq_rating_count,
        "player_page_rol_num_comparison_count": rol_num_comp_count,
        "player_page_rol_num_equal_count": rol_num_eq_count,
        "player_page_rol_num_not_equal_count": (rol_num_comp_count - rol_num_eq_count),
        "dd6361_exact_core4_match_count_within_overlaps": dd6361_core4_exact_count,
    }
    return {
        "summary": summary,
        "player_page_overlaps": overlaps,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cross-check lineup screenshots vs player-page screenshots and dd6361 bios")
    p.add_argument(
        "--player-file",
        default=str(REPO_ROOT / "DBDAT" / "JUG98030.FDI"),
        help="Path to JUG98030.FDI",
    )
    p.add_argument(
        "--example-data",
        default=str(REPO_ROOT / ".local" / "PlayerStills" / "ExamplePlayerData.txt"),
        help="OCR/text scrape of player-page screenshots",
    )
    p.add_argument(
        "--json-output",
        help="Write JSON output to this path",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    player_file = Path(args.player_file)
    example_file = Path(args.example_data)

    example_map = trailer_probe._parse_example_player_data(example_file) if example_file.exists() else {}
    manual_rol_map = dict(rol_box_probe.DEFAULT_MANUAL_READINGS)

    dd6361_rows = _build_dd6361_rows(player_file)
    by_norm_full, by_surname = _index_dd6361_rows(dd6361_rows)

    stoke_rows = lineup_probe._dataset_rows("stoke")
    manutd_rows = lineup_probe._dataset_rows("manutd")

    stoke_cross = _dataset_crosscheck("stoke", stoke_rows, example_map, manual_rol_map, by_norm_full, by_surname)
    manutd_cross = _dataset_crosscheck("manutd", manutd_rows, example_map, manual_rol_map, by_norm_full, by_surname)

    keane_row = next((r for r in manutd_rows if str(r.get("name")) == "Keane"), None)
    keane_candidates = []
    if keane_row is not None:
        keane_candidates = _keane_candidate_summary(
            keane_row,
            by_surname.get("KEANE", []),
        )

    payload = {
        "player_file": str(player_file),
        "example_data": str(example_file),
        "dd6361_bio_row_count": len(dd6361_rows),
        "manual_player_page_rol_source": "scripts.probe_screenshot_rol_boxes.DEFAULT_MANUAL_READINGS",
        "datasets": {
            "stoke": stoke_cross,
            "manutd": manutd_cross,
        },
        "manutd_keane_disambiguation": {
            "lineup_row": {
                "n": int(keane_row["n"]) if keane_row else None,
                "name": str(keane_row["name"]) if keane_row else None,
                "section": str(keane_row["section"]) if keane_row else None,
                "pos": str(keane_row["pos"]) if keane_row else None,
                "sp": int(keane_row["sp"]) if keane_row else None,
                "st": int(keane_row["st"]) if keane_row else None,
                "ag": int(keane_row["ag"]) if keane_row else None,
                "qu": int(keane_row["qu"]) if keane_row else None,
                "fi": int(keane_row["fi"]) if keane_row else None,
                "mo": int(keane_row["mo"]) if keane_row else None,
                "av": int(keane_row["av"]) if keane_row else None,
                "rol": int(keane_row["rol"]) if keane_row else None,
            },
            "dd6361_keane_candidates": keane_candidates,
            "best_candidate": keane_candidates[0] if keane_candidates else None,
        },
        "notes": [
            "Lineup rows come from manual transcriptions in scripts/probe_lineup_screenshot.py.",
            "Player-page ROL numeric values come from manual readings captured in scripts/probe_screenshot_rol_boxes.py.",
            "dd6361 biographies provide mapped10 core/skill values but do not currently explain lineup ROL/EN/FI/MO state semantics.",
            "A lineup vs player-page mismatch flagged as likely_ocr_issue_if_mismatch means dd6361 core4 agrees with the lineup but the OCR/text scrape does not.",
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
