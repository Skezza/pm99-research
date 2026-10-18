#!/usr/bin/env python3
"""Materialise a dated-person queue from unresolved first-fixture starters.

The dated squad capture is a season-list source. A player named in the first
league fixture but absent from that list is not interchangeable with a
later-season squad member. This source-only stage keeps that player as a
separate, hash-bound opening-date addition. It does not allocate a PM99
carrier, replace a roster row, or invent ratings, role, formation or bench.

Where the independently captured Transfermarkt profile is available, its
published full name and date of birth travel with the queue row. A missing
profile fact remains an explicit source gap rather than a guessed identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SCHEMA = "pm99-transfermarkt-opening-fixture-player-additions-v1"
LINEUP_SCHEMA = "pm99-transfermarkt-opening-lineup-source-v1"
LINEUP_SCHEMAS = {LINEUP_SCHEMA, "pm99-composed-opening-lineup-source-v1"}
RECONCILIATION_SCHEMA = "pm99-transfermarkt-opening-lineup-reconciliation-v1"
PERSON_EVIDENCE_SCHEMA = "pm99-transfermarkt-lineup-person-evidence-v1"


class AdditionQueueError(ValueError):
    """Inputs do not form one immutable source chain."""


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _load(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdditionQueueError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise AdditionQueueError(f"{label} must be a JSON object")
    return value, hashlib.sha256(payload).hexdigest()


def _selector(value: Mapping[str, Any]) -> tuple[str, str, str]:
    result = tuple(str(value.get(field) or "").strip() for field in ("country_catalog", "competition_catalog", "club_name"))
    if not all(result):
        raise AdditionQueueError("source selector lacks country_catalog, competition_catalog or club_name")
    return result  # type: ignore[return-value]


def _index_starting_players(lineup: Mapping[str, Any]) -> dict[tuple[tuple[str, str, str], str], dict[str, Any]]:
    if lineup.get("schema_version") not in LINEUP_SCHEMAS:
        raise AdditionQueueError(f"lineup capture must have one of {sorted(LINEUP_SCHEMAS)}")
    result: dict[tuple[tuple[str, str, str], str], dict[str, Any]] = {}
    for club in lineup.get("clubs") or []:
        if not isinstance(club, dict) or not isinstance(club.get("source_selector"), dict):
            raise AdditionQueueError("lineup capture has a malformed club")
        selector = _selector(club["source_selector"])
        for player in club.get("starting_xi") or []:
            if not isinstance(player, dict):
                raise AdditionQueueError("lineup capture has a malformed starter")
            player_id = str(player.get("source_player_id") or "").strip()
            if not player_id:
                raise AdditionQueueError("lineup starter lacks source_player_id")
            key = (selector, player_id)
            if key in result:
                raise AdditionQueueError(f"lineup capture duplicates starting player {key}")
            result[key] = {**player, "fixture": {
                "first_league_fixture_date": club.get("first_league_fixture_date"),
                "lineup_source_url": club.get("lineup_source_url"),
                "source_match_id": club.get("source_match_id"),
            }}
    return result


def _index_person_evidence(
    evidence: Mapping[str, Any], *, lineup_capture_sha256: str,
) -> dict[tuple[tuple[str, str, str], str], dict[str, Any]]:
    if evidence.get("schema_version") != PERSON_EVIDENCE_SCHEMA:
        raise AdditionQueueError(f"person evidence must have schema {PERSON_EVIDENCE_SCHEMA}")
    if (evidence.get("source") or {}).get("lineup_capture_sha256") != lineup_capture_sha256:
        raise AdditionQueueError("person evidence is not bound to this exact lineup capture")
    result: dict[tuple[tuple[str, str, str], str], dict[str, Any]] = {}
    for player in evidence.get("players") or []:
        if not isinstance(player, dict) or not isinstance(player.get("source_selector"), dict):
            raise AdditionQueueError("person evidence has a malformed player")
        selector = _selector(player["source_selector"])
        player_id = str(player.get("source_player_id") or "").strip()
        if not player_id:
            raise AdditionQueueError("person evidence player lacks source_player_id")
        key = (selector, player_id)
        if key in result:
            raise AdditionQueueError(f"person evidence duplicates {key}")
        result[key] = dict(player)
    return result


def derive(
    *, source_capture_sha256: str, lineup_capture: Mapping[str, Any], lineup_capture_sha256: str,
    reconciliation: Mapping[str, Any], reconciliation_sha256: str,
    person_evidence: Mapping[str, Any], person_evidence_sha256: str,
) -> dict[str, Any]:
    """Create only first-XI players the reconciliation could not locate."""

    if reconciliation.get("schema_version") != RECONCILIATION_SCHEMA:
        raise AdditionQueueError(f"reconciliation must have schema {RECONCILIATION_SCHEMA}")
    sources = reconciliation.get("sources") or {}
    if sources.get("source_capture_sha256") != source_capture_sha256:
        raise AdditionQueueError("reconciliation is not bound to this exact squad source capture")
    if sources.get("lineup_capture_sha256") != lineup_capture_sha256:
        raise AdditionQueueError("reconciliation is not bound to this exact lineup capture")
    if sources.get("person_evidence_sha256") != person_evidence_sha256:
        raise AdditionQueueError("reconciliation is not bound to this exact person evidence")

    starters = _index_starting_players(lineup_capture)
    profiles = _index_person_evidence(person_evidence, lineup_capture_sha256=lineup_capture_sha256)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str, str], str]] = set()
    for club in reconciliation.get("clubs") or []:
        if not isinstance(club, dict) or not isinstance(club.get("source_selector"), dict):
            raise AdditionQueueError("reconciliation has a malformed club")
        selector = _selector(club["source_selector"])
        for failure in club.get("unresolved_first_fixture_players") or []:
            if not isinstance(failure, dict) or failure.get("reason") not in {
                "ambiguous-or-missing-dated-squad-player",
                "duplicate-resolved-player",
            }:
                continue
            player_id = str(failure.get("source_player_id") or "").strip()
            key = (selector, player_id)
            starter = starters.get(key)
            if starter is None:
                raise AdditionQueueError(f"unresolved first-fixture player is absent from lineup capture: {key}")
            if key in seen:
                raise AdditionQueueError(f"reconciliation duplicates unresolved first-fixture player: {key}")
            seen.add(key)
            profile = profiles.get(key)
            row = {
                "source_selector": dict(zip(("country_catalog", "competition_catalog", "club_name"), selector)),
                "source_player_id": player_id,
                "display_name": str(starter.get("display_name") or ""),
                "source_slug": str(starter.get("source_slug") or ""),
                "source_url": str(starter.get("source_url") or ""),
                "source_position_group": starter.get("source_position_group"),
                **starter["fixture"],
                "profile_status": "profile-facts-pending",
                "published_full_name": None,
                "published_birth_date": None,
                "published_nationality_label": None,
                "published_profile_position": None,
                "published_height_cm": None,
            }
            if profile is not None:
                row.update({
                    "profile_status": "opening-fixture-person-profiled",
                    "published_full_name": profile.get("published_full_name"),
                    "published_birth_date": profile.get("published_birth_date"),
                    "published_nationality_label": profile.get("published_nationality_label"),
                    "published_profile_position": profile.get("published_profile_position"),
                    "published_height_cm": profile.get("published_height_cm"),
                    "profile_url": profile.get("source_url"),
                })
            rows.append(row)
    rows.sort(key=lambda row: (
        str(row["source_selector"]["country_catalog"]), str(row["source_selector"]["competition_catalog"]),
        str(row["source_selector"]["club_name"]), str(row["source_player_id"]),
    ))
    profiled = sum(row["profile_status"] == "opening-fixture-person-profiled" for row in rows)
    return {
        "schema_version": SCHEMA,
        "purpose": "first-fixture starters absent from the dated squad-source capture; not a PM99 write or automatic roster replacement",
        "sources": {
            "source_capture_sha256": source_capture_sha256,
            "lineup_capture_sha256": lineup_capture_sha256,
            "reconciliation_sha256": reconciliation_sha256,
            "person_evidence_sha256": person_evidence_sha256,
        },
        "summary": {
            "opening_fixture_addition_count": len(rows),
            "club_count": len({tuple(row["source_selector"].values()) for row in rows}),
            "profiled_person_count": profiled,
            "profile_facts_pending_count": len(rows) - profiled,
        },
        "rows": rows,
        "remaining_requirements": [
            "A fixed-carrier allocation approved for the exact club and opening date.",
            "An authored PM99 rating, fine role, kit and portrait disposition for every allocated person.",
            "No queue row is a roster replacement until those independent gates pass.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-capture", required=True, type=Path)
    parser.add_argument("--lineup-capture", required=True, type=Path)
    parser.add_argument("--reconciliation", required=True, type=Path)
    parser.add_argument("--person-evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        _source_capture, source_capture_sha256 = _load(args.source_capture, label="squad source capture")
        lineup_capture, lineup_capture_sha256 = _load(args.lineup_capture, label="lineup capture")
        reconciliation, reconciliation_sha256 = _load(args.reconciliation, label="reconciliation")
        person_evidence, person_evidence_sha256 = _load(args.person_evidence, label="person evidence")
        result = derive(
            source_capture_sha256=source_capture_sha256, lineup_capture=lineup_capture,
            lineup_capture_sha256=lineup_capture_sha256, reconciliation=reconciliation,
            reconciliation_sha256=reconciliation_sha256, person_evidence=person_evidence,
            person_evidence_sha256=person_evidence_sha256,
        )
    except (OSError, AdditionQueueError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical_json_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
