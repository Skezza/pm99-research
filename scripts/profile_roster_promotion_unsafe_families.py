#!/usr/bin/env python3
"""Profile linked-roster fixed-name unsafe subfamilies and compare snapshots.

This script exercises the shared promotion contract across many linked rosters,
collects `fixed_name_unsafe` diagnostics, ranks exact subfamilies, and can emit
before/after deltas when a previous snapshot is supplied.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.editor_actions import _build_indexed_player_name_stage_record
from app.editor_helpers import _normalize_text
from app.eq_jug_linked import load_eq_linked_team_rosters
from app.fdi_indexed import IndexedFDIFile


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _canonical_detail_token(token: str) -> str:
    normalized = str(token or "").strip()
    if not normalized:
        return ""
    return normalized.split("(", 1)[0].strip()


def _extract_unsafe_subfamily(reason_message: str) -> tuple[str, str, str, str]:
    """Return (subfamily, primary_token, parser_token, detail)."""
    message = str(reason_message or "").strip()
    detail = ""
    if "[" in message and message.endswith("]"):
        detail = message.split("[", 1)[1][:-1].strip()

    parts = [part.strip() for part in detail.split(";") if part.strip()]
    primary = _canonical_detail_token(parts[0]) if parts else "no_detail"

    parser_token = ""
    for part in parts:
        if part.startswith("parser_candidate:"):
            parser_token = _canonical_detail_token(part)
            break

    spill_token = ""
    for part in parts:
        if part.startswith("parser_candidate:text_spill_"):
            spill_token = _canonical_detail_token(part)
            break

    if spill_token:
        return spill_token, primary, parser_token, detail
    if parser_token:
        return parser_token, primary, parser_token, detail
    return primary, primary, parser_token, detail


def _run_snapshot(
    *,
    team_file: str,
    player_file: str,
    target_names: list[str],
    slot_limit: int,
    team_limit: int | None,
    sample_limit: int,
) -> dict[str, Any]:
    rosters = load_eq_linked_team_rosters(team_file=team_file, player_file=player_file)
    if team_limit is not None and team_limit > 0:
        rosters = rosters[:team_limit]

    player_bytes = Path(player_file).read_bytes()
    indexed = IndexedFDIFile.from_bytes(player_bytes)
    entry_by_id = {int(entry.record_id): entry for entry in list(getattr(indexed, "entries", []) or [])}

    reason_counts: Counter[str] = Counter()
    safe_family_counts: Counter[str] = Counter()
    subfamily_counts: Counter[str] = Counter()
    primary_counts: Counter[str] = Counter()
    parser_counts: Counter[str] = Counter()
    detail_counts: Counter[str] = Counter()

    samples_by_subfamily: dict[str, list[dict[str, Any]]] = defaultdict(list)

    profile_runs = 0
    fixed_name_unsafe_total = 0
    skipped_total = 0
    safe_total = 0

    decoded_cache: dict[tuple[int, int], bytes] = {}

    for roster in rosters:
        team_name = str(getattr(roster, "short_name", "") or "")
        eq_record_id = int(getattr(roster, "eq_record_id", 0) or 0)
        rows = list(getattr(roster, "rows", []) or [])
        max_slots = min(len(rows), max(1, int(slot_limit)))

        for target_name in target_names:
            profile_runs += 1
            normalized_target = _normalize_text(str(target_name))

            for slot_index in range(max_slots):
                row = rows[slot_index]
                slot_number = slot_index + 1
                current_name = str(getattr(row, "player_name", "") or "").strip()
                pid = int(getattr(row, "player_record_id", 0) or 0)

                if current_name and normalized_target and _normalize_text(current_name) == normalized_target:
                    skipped_total += 1
                    reason_counts["already_target"] += 1
                    continue

                reason_code = ""
                reason_message = ""
                mutation_family = ""

                try:
                    if pid <= 0:
                        raise ValueError("Selected linked roster slot has an invalid player_record_id")

                    indexed_entry = entry_by_id.get(pid)
                    if indexed_entry is None:
                        raise ValueError(
                            f"Linked roster slot maps to player_record_id={pid}, but that ID was not found in {player_file}"
                        )

                    cache_key = (int(indexed_entry.payload_offset), int(indexed_entry.payload_length))
                    decoded = decoded_cache.get(cache_key)
                    if decoded is None:
                        decoded = indexed_entry.decode_payload(player_bytes)
                        decoded_cache[cache_key] = decoded

                    _record, _name_changed, _applied_name, _was_truncated, mutation_family = _build_indexed_player_name_stage_record(
                        decoded_payload=decoded,
                        payload_offset=int(indexed_entry.payload_offset),
                        payload_length=int(indexed_entry.payload_length),
                        new_name=str(target_name),
                        fixed_name_bytes=True,
                    )
                except Exception as exc:
                    reason_message = str(exc).strip() or "unknown error"
                    reason_code = "promotion_error"
                    if "Fixed-length rename could not produce a safe name mutation candidate" in reason_message:
                        reason_code = "fixed_name_unsafe"

                if reason_code:
                    skipped_total += 1
                    reason_counts[reason_code] += 1

                    if reason_code != "fixed_name_unsafe":
                        continue

                    fixed_name_unsafe_total += 1
                    subfamily, primary, parser_token, detail = _extract_unsafe_subfamily(reason_message)
                    subfamily_counts[subfamily] += 1
                    primary_counts[primary] += 1
                    if parser_token:
                        parser_counts[parser_token] += 1
                    detail_counts[detail or "no_detail"] += 1

                    sample_rows = samples_by_subfamily[subfamily]
                    if len(sample_rows) < sample_limit:
                        sample_rows.append(
                            {
                                "team": team_name,
                                "eq_record_id": eq_record_id,
                                "slot": int(slot_number),
                                "pid": int(pid),
                                "player_name": current_name,
                                "target_name": str(target_name),
                                "reason_message": reason_message,
                            }
                        )
                    continue

                safe_total += 1
                family = str(mutation_family or "").strip()
                if family:
                    safe_family_counts[family] += 1

    ranked_subfamilies = [
        {
            "subfamily": key,
            "count": int(count),
            "samples": list(samples_by_subfamily.get(key, [])),
        }
        for key, count in sorted(subfamily_counts.items(), key=lambda item: (-int(item[1]), str(item[0])))
    ]

    ranked_primary = [
        {"primary": key, "count": int(count)}
        for key, count in sorted(primary_counts.items(), key=lambda item: (-int(item[1]), str(item[0])))
    ]
    ranked_parser = [
        {"parser_token": key, "count": int(count)}
        for key, count in sorted(parser_counts.items(), key=lambda item: (-int(item[1]), str(item[0])))
    ]
    ranked_details = [
        {"detail": key, "count": int(count)}
        for key, count in sorted(detail_counts.items(), key=lambda item: (-int(item[1]), str(item[0])))
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "team_file": team_file,
            "player_file": player_file,
            "target_names": list(target_names),
            "slot_limit": int(slot_limit),
            "team_limit": int(team_limit) if team_limit is not None else None,
            "sample_limit": int(sample_limit),
        },
        "totals": {
            "linked_teams_profiled": len(rosters),
            "profile_runs": int(profile_runs),
            "safe_total": int(safe_total),
            "skipped_total": int(skipped_total),
            "fixed_name_unsafe_total": int(fixed_name_unsafe_total),
        },
        "reason_counts": {k: int(v) for k, v in sorted(reason_counts.items(), key=lambda item: (-int(item[1]), str(item[0])))},
        "safe_family_counts": {k: int(v) for k, v in sorted(safe_family_counts.items(), key=lambda item: (-int(item[1]), str(item[0])))},
        "fixed_name_unsafe": {
            "subfamily_ranking": ranked_subfamilies,
            "primary_ranking": ranked_primary,
            "parser_token_ranking": ranked_parser,
            "detail_ranking": ranked_details,
        },
    }


def _extract_snapshot_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Snapshot JSON must be an object")
    if "after" in data and isinstance(data.get("after"), dict):
        return dict(data["after"])
    return dict(data)


def _ranked_counter_delta(before: dict[str, Any], after: dict[str, Any], key: str, label: str) -> list[dict[str, Any]]:
    before_counts = dict(before.get(key, {}) or {})
    after_counts = dict(after.get(key, {}) or {})
    all_keys = sorted(set(before_counts.keys()) | set(after_counts.keys()))
    rows: list[dict[str, Any]] = []
    for item_key in all_keys:
        before_value = int(before_counts.get(item_key, 0) or 0)
        after_value = int(after_counts.get(item_key, 0) or 0)
        rows.append(
            {
                label: str(item_key),
                "before": before_value,
                "after": after_value,
                "delta": after_value - before_value,
            }
        )
    rows.sort(key=lambda item: (-abs(int(item["delta"])), -int(item["after"]), str(item[label])))
    return rows


def _build_before_after(before_snapshot: dict[str, Any], after_snapshot: dict[str, Any]) -> dict[str, Any]:
    before_fixed = dict((before_snapshot.get("fixed_name_unsafe") or {}))
    after_fixed = dict((after_snapshot.get("fixed_name_unsafe") or {}))

    before_subfamily_counts = {
        str(item.get("subfamily", "")): int(item.get("count", 0) or 0)
        for item in list(before_fixed.get("subfamily_ranking", []) or [])
        if str(item.get("subfamily", ""))
    }
    after_subfamily_counts = {
        str(item.get("subfamily", "")): int(item.get("count", 0) or 0)
        for item in list(after_fixed.get("subfamily_ranking", []) or [])
        if str(item.get("subfamily", ""))
    }

    before_totals = dict(before_snapshot.get("totals", {}) or {})
    after_totals = dict(after_snapshot.get("totals", {}) or {})

    all_subfamilies = sorted(set(before_subfamily_counts.keys()) | set(after_subfamily_counts.keys()))
    subfamily_delta = []
    for subfamily in all_subfamilies:
        before_value = int(before_subfamily_counts.get(subfamily, 0) or 0)
        after_value = int(after_subfamily_counts.get(subfamily, 0) or 0)
        subfamily_delta.append(
            {
                "subfamily": subfamily,
                "before": before_value,
                "after": after_value,
                "delta": after_value - before_value,
            }
        )
    subfamily_delta.sort(key=lambda item: (-abs(int(item["delta"])), -int(item["after"]), str(item["subfamily"])))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "before_fixed_name_unsafe_total": int(before_totals.get("fixed_name_unsafe_total", 0) or 0),
        "after_fixed_name_unsafe_total": int(after_totals.get("fixed_name_unsafe_total", 0) or 0),
        "fixed_name_unsafe_delta": int(after_totals.get("fixed_name_unsafe_total", 0) or 0)
        - int(before_totals.get("fixed_name_unsafe_total", 0) or 0),
        "before_safe_total": int(before_totals.get("safe_total", 0) or 0),
        "after_safe_total": int(after_totals.get("safe_total", 0) or 0),
        "safe_total_delta": int(after_totals.get("safe_total", 0) or 0) - int(before_totals.get("safe_total", 0) or 0),
        "safe_family_deltas": _ranked_counter_delta(before_snapshot, after_snapshot, "safe_family_counts", "family"),
        "reason_deltas": _ranked_counter_delta(before_snapshot, after_snapshot, "reason_counts", "reason_code"),
        "fixed_name_unsafe_subfamily_deltas": subfamily_delta,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Profile fixed-name unsafe linked-roster diagnostics and emit before/after JSON deltas",
    )
    parser.add_argument("team_file", nargs="?", default="DBDAT/EQ98030.FDI", help="Path to EQ file")
    parser.add_argument("--player-file", default="DBDAT/JUG98030.FDI", help="Path to JUG file")
    parser.add_argument(
        "--name",
        dest="target_names",
        action="append",
        default=[],
        help="Target player name to profile (repeatable). Defaults to Joe Skerratt when omitted.",
    )
    parser.add_argument("--slot-limit", type=int, default=25, help="Max slots per linked roster (default: 25)")
    parser.add_argument("--team-limit", type=int, default=None, help="Optional cap on linked teams to profile")
    parser.add_argument("--sample-limit", type=int, default=5, help="Max samples per unsafe subfamily")
    parser.add_argument("--before-json", help="Optional baseline snapshot JSON path for before/after comparison")
    parser.add_argument("--output-json", help="Optional report output path")
    parser.add_argument("--print-top", type=int, default=10, help="Number of top subfamilies to print")
    args = parser.parse_args()

    target_names = [str(item).strip() for item in list(args.target_names or []) if str(item).strip()]
    if not target_names:
        target_names = ["Joe Skerratt"]

    after_snapshot = _run_snapshot(
        team_file=str(args.team_file),
        player_file=str(args.player_file),
        target_names=target_names,
        slot_limit=max(1, int(args.slot_limit or 1)),
        team_limit=(None if args.team_limit is None else max(1, int(args.team_limit))),
        sample_limit=max(0, int(args.sample_limit or 0)),
    )

    payload: dict[str, Any]
    if args.before_json:
        before_path = Path(str(args.before_json))
        before_raw = json.loads(before_path.read_text(encoding="utf-8"))
        before_snapshot = _extract_snapshot_payload(before_raw)
        payload = {
            "before": before_snapshot,
            "after": after_snapshot,
            "delta": _build_before_after(before_snapshot, after_snapshot),
        }
    else:
        payload = {"after": after_snapshot}

    if args.output_json:
        Path(str(args.output_json)).write_text(json.dumps(_jsonable(payload), indent=2) + "\n", encoding="utf-8")

    top_n = max(0, int(args.print_top or 0))
    totals = after_snapshot.get("totals", {})
    print(
        "Roster promotion unsafe profile: "
        f"teams={int(totals.get('linked_teams_profiled', 0) or 0)} "
        f"runs={int(totals.get('profile_runs', 0) or 0)} "
        f"safe={int(totals.get('safe_total', 0) or 0)} "
        f"fixed_name_unsafe={int(totals.get('fixed_name_unsafe_total', 0) or 0)}"
    )

    subfamilies = list((after_snapshot.get("fixed_name_unsafe", {}) or {}).get("subfamily_ranking", []) or [])
    if top_n and subfamilies:
        print("Top unsafe subfamilies:")
        for item in subfamilies[:top_n]:
            print(f"  {int(item.get('count', 0) or 0):6d}  {item.get('subfamily', '')}")

    if args.before_json:
        delta = payload.get("delta", {})
        print(
            "Delta: "
            f"fixed_name_unsafe={int(delta.get('fixed_name_unsafe_delta', 0) or 0)} "
            f"safe_total={int(delta.get('safe_total_delta', 0) or 0)}"
        )

    if args.output_json:
        print(f"Wrote JSON report: {args.output_json}")


if __name__ == "__main__":
    main()
