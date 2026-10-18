#!/usr/bin/env python3
"""Quantify usable 2015/16 world-content inputs without writing PM99 data.

The fixed-carrier registry describes PM99 capacity, not historic football
membership.  This tool keeps that distinction explicit: it reports what a
local player-data snapshot could *help research*, never chooses a carrier,
reorders a roster, or writes an EQ/JUG/ENT file.

In particular, a normalised present-name match is only a candidate for a
future, sourced carrier decision.  It is not evidence that the same PM99 slot
should represent that club in 2015/16.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import world_fixed_carrier_ledger_v2 as ledger


SCHEMA = "pm99-world-2015-source-coverage-v1"
CORE_PLAYER_COLUMNS = (
    "name",
    "club",
    "nationality",
    "height",
    "weight",
    "birthdate",
    "rating",
    "sprint_speed",
    "stamina",
    "aggression",
    "short_pass",
    "stand_tackle",
    "heading",
    "finishing",
    "dribbling",
    "gk_handling",
)
OPTIONAL_CANDIDATE_COLUMNS = ("preferred_positions", "club_kit_number", "headshot_url")
MISSING_VALUES = {"", "na", "n/a", "null", "none"}


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _write_canonical_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json_bytes(value))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_present(value: object) -> bool:
    return str(value or "").strip().casefold() not in MISSING_VALUES


def _ascii_tokens(value: object) -> list[str]:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.findall(r"[a-z0-9]+", text.casefold().replace("&", " and "))


def strict_club_key(value: object) -> str:
    """Normalise harmless F.C./C.F. spelling only; retain all club initials."""

    tokens = _ascii_tokens(value)
    result: list[str] = []
    index = 0
    while index < len(tokens):
        if index + 1 < len(tokens) and {tokens[index], tokens[index + 1]} == {"f", "c"}:
            index += 2
            continue
        if tokens[index] not in {"fc", "cf", "club", "football", "futebol", "soccer", "calcio"}:
            result.append(tokens[index])
        index += 1
    return " ".join(result)


def loose_club_key(value: object) -> str:
    """Produce a discovery-only key for abbreviated historical display names.

    This deliberately strips common prefixes/suffixes such as R.C.D. or F.C.
    so an auditor can see potential source rows.  The output is never a
    carrier assignment and must not be fed into the compiler directly.
    """

    ignored = {
        "fc", "cf", "f", "c", "club", "football", "futebol", "soccer", "calcio", "deportivo",
        "athletic", "athletico", "rc", "rcd", "ac", "as", "ss", "us", "sk", "bk", "if", "fk",
        "sc", "cd", "sd", "ud",
    }
    return " ".join(token for token in _ascii_tokens(value) if token not in ignored)


def _read_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("player CSV has no header")
        fields = list(reader.fieldnames)
        missing = sorted(set(CORE_PLAYER_COLUMNS + OPTIONAL_CANDIDATE_COLUMNS) - set(fields))
        if missing:
            raise ValueError("player CSV misses required candidate column(s): " + ", ".join(missing))
        return [dict(row) for row in reader], fields


def _club_index(rows: Iterable[dict[str, str]], key_function: Any) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = key_function(row.get("club"))
        if key:
            result[key].append(row)
    return dict(result)


def _candidate_matches(
    *, registry: dict[str, Any], club_index: dict[str, list[dict[str, str]]], key_function: Any
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for carrier in registry["carriers"]:
        club = carrier["baseline_club"]
        key = key_function(club.get("name"))
        source_rows = club_index.get(key, []) if key else []
        if not source_rows:
            continue
        source_names = sorted({str(row["club"]) for row in source_rows})
        matches.append(
            {
                "carrier_id": int(carrier["carrier_id"]),
                "baseline_club_name": club.get("name"),
                "candidate_key": key,
                "fixed_roster_slot_count": len(carrier["roster_slots"]),
                "candidate_source_player_count": len(source_rows),
                "candidate_source_club_names": source_names,
                "source_rows_meet_fixed_slot_count": len(source_rows) >= len(carrier["roster_slots"]),
            }
        )
    return matches


def _match_summary(matches: list[dict[str, Any]]) -> dict[str, int]:
    sufficient = [row for row in matches if row["source_rows_meet_fixed_slot_count"]]
    return {
        "candidate_carrier_count": len(matches),
        "candidate_fixed_roster_slot_count": sum(int(row["fixed_roster_slot_count"]) for row in matches),
        "candidate_source_player_rows": sum(int(row["candidate_source_player_count"]) for row in matches),
        "candidate_carriers_with_enough_rows": len(sufficient),
        "candidate_slots_in_rows_sufficient_carriers": sum(int(row["fixed_roster_slot_count"]) for row in sufficient),
    }


def build_coverage(*, registry: dict[str, Any], ledger_data: dict[str, Any], player_csv: Path) -> dict[str, Any]:
    ledger.validate_registry(registry)
    ledger.validate_ledger(registry=registry, ledger=ledger_data)
    rows, fields = _read_rows(player_csv)
    strict_matches = _candidate_matches(
        registry=registry, club_index=_club_index(rows, strict_club_key), key_function=strict_club_key
    )
    loose_matches = _candidate_matches(
        registry=registry, club_index=_club_index(rows, loose_club_key), key_function=loose_club_key
    )
    ledger_audit = ledger.audit_ledger(registry=registry, ledger=ledger_data)
    missing_by_column = {column: sum(not _is_present(row.get(column)) for row in rows) for column in CORE_PLAYER_COLUMNS + OPTIONAL_CANDIDATE_COLUMNS}
    club_names = {str(row.get("club") or "").strip() for row in rows if _is_present(row.get("club"))}
    roster_slots = [slot for carrier in registry["carriers"] for slot in carrier["roster_slots"]]
    complete_sources = len(ledger_data["sources"])
    content_status = {
        "ledger_source_count": complete_sources,
        "ledger_carrier_update_count": len(ledger_data["carrier_updates"]),
        "complete_world_carrier_count": int(ledger_audit["coverage"]["carrier_status_counts"].get("complete", 0)),
        "complete_world_roster_slot_count": int(ledger_audit["coverage"]["complete_player_slot_count"]),
        "kit_disposition_count": sum(ledger_audit["coverage"]["kit_status_counts"].values()),
        "portrait_disposition_count": sum(ledger_audit["coverage"]["portrait_status_counts"].values()),
    }
    return {
        "schema_version": SCHEMA,
        "result": "not-ready-for-world-compile",
        "registry_sha256": hashlib.sha256(_canonical_json_bytes(registry)).hexdigest(),
        "ledger_sha256": hashlib.sha256(_canonical_json_bytes(ledger_data)).hexdigest(),
        "fixed_carrier_capacity": {
            "carrier_count": len(registry["carriers"]),
            "roster_slot_count": len(roster_slots),
            "player_families": dict(sorted(Counter(str(slot["family"]) for slot in roster_slots).items())),
            "shared_player_carrier_count": len(registry["known_baseline_duplicate_player_carriers"]),
            "shared_player_carrier_occurrence_count": sum(
                len(row["occurrences"]) for row in registry["known_baseline_duplicate_player_carriers"]
            ),
        },
        "authoritative_world_content": content_status,
        "candidate_player_snapshot": {
            "path": str(player_csv),
            "sha256": _sha256_file(player_csv),
            "row_count": len(rows),
            "club_count": len(club_names),
            "declared_seasons": dict(sorted(Counter(str(row.get("season") or "") for row in rows).items())),
            "declared_years": dict(sorted(Counter(str(row.get("year") or "") for row in rows).items())),
            "fields": fields,
            "missing_value_count_by_field": missing_by_column,
            "strict_present_name_candidates": _match_summary(strict_matches),
            "loose_abbreviation_candidates": _match_summary(loose_matches),
            "strict_present_name_candidate_rows": strict_matches,
            "guardrail": "Candidate matches are discovery aids only. They are not historic carrier assignments, membership evidence, roster decisions, asset captures, or compiler input.",
        },
        "release_blockers": ledger_audit["blockers"],
        "scope_exclusions": ledger_audit["scope_exclusions"],
        "safe_next_actions": [
            "Capture dated club, manager, squad, kit and portrait sources for a carrier before adding a ledger update.",
            "Use the player snapshot only to prefill a review queue for core player facts and rating candidates.",
            "Derive a strict season package only after every selected carrier has explicit source evidence and an approved fixed-slot assignment.",
            "Preserve country, division, draw-pool and competition membership by release policy; do not turn a like-for-like historical update into a game-rules rewrite.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--player-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    registry, _ = ledger.read_canonical_json(args.registry, label="fixed-carrier registry")
    ledger_data, _ = ledger.read_canonical_json(args.ledger, label="world season ledger")
    report = build_coverage(registry=registry, ledger_data=ledger_data, player_csv=args.player_csv)
    _write_canonical_json(args.output, report)
    print(json.dumps({"output": str(args.output), "result": report["result"], **report["authoritative_world_content"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
