#!/usr/bin/env python3
"""Audit whether a duplicate-carrier replacement has dated source data.

The historical English source ledger began as a season roster.  It is useful
as a facts cache, but is not allowed to decide who occupied a club's reserve
carrier on the first day of the season: its own duplicate-person audit proves
that it contains later loans and transfers.  The only retained dated player
evidence is the certified first league fixture.

This tool deliberately does not write a package.  It produces a receipt for
every carrier that the opening-date identity resolution says must be replaced.
An identity becomes a *candidate* only where that player is named in the
first-fixture XI/bench, absent from the package roster, and present in the
facts ledger.  Even such a candidate still needs an editorial ratings/roles
record before it can be compiled.  All other slots remain explicitly pending
rather than being backfilled from an undated season roster.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_v2 as package_v2
from scripts.reconcile_opening_date_identities_v1 import (
    RESOLVED_SCHEMA,
    _club_key,
    _normalise,
)


SCHEMA = "pm99-opening-date-replacement-source-readiness-v1"


class SourceReadinessError(ValueError):
    """A source audit input lacks the small contract required for a receipt."""


def _canonical_bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceReadinessError(f"cannot read {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SourceReadinessError(f"{label} must be a JSON object")
    return value


def _opening_by_club(opening: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if opening.get("schema_version") != "pm99-2015-16-opening-lineup-reconciliation-v1":
        raise SourceReadinessError("opening lineups must use the certified reconciliation schema")
    if opening.get("failures"):
        raise SourceReadinessError("opening lineups contain unresolved identities")
    result: dict[str, list[dict[str, Any]]] = {}
    for club in opening.get("clubs", []):
        if not isinstance(club, dict) or not club.get("reconciled"):
            raise SourceReadinessError("opening lineup contains an uncertified club")
        name = club.get("club")
        if not isinstance(name, str) or not name:
            raise SourceReadinessError("opening lineup has an unnamed club")
        key = _club_key(name)
        if key in result:
            raise SourceReadinessError(f"opening lineup duplicates club {name!r}")
        players = [*(club.get("starting_xi") or []), *(club.get("substitutes") or [])]
        if not all(isinstance(player, dict) and isinstance(player.get("source_name"), str) for player in players):
            raise SourceReadinessError(f"opening lineup {name} contains unresolved player data")
        result[key] = players
    return result


def _facts_by_club(source_ledger: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    clubs = source_ledger.get("clubs")
    if not isinstance(clubs, list):
        raise SourceReadinessError("source ledger must contain clubs")
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for club in clubs:
        if not isinstance(club, dict) or not isinstance(club.get("club"), str):
            raise SourceReadinessError("source ledger has an unnamed club")
        key = _club_key(club["club"])
        if key in result:
            raise SourceReadinessError(f"source ledger duplicates club {club['club']!r}")
        players: dict[str, dict[str, Any]] = {}
        for player in club.get("players", []):
            if not isinstance(player, dict) or not isinstance(player.get("name"), str):
                raise SourceReadinessError(f"source ledger {club['club']} has an unnamed player")
            identity = _normalise(player["name"])
            if not identity or identity in players:
                raise SourceReadinessError(f"source ledger {club['club']} has ambiguous player {player.get('name')!r}")
            players[identity] = player
        result[key] = players
    return result


def build_readiness(
    package: dict[str, Any],
    resolution: dict[str, Any],
    opening: dict[str, Any],
    source_ledger: dict[str, Any],
) -> dict[str, Any]:
    """Return only source-supported first-fixture candidate rows.

    A candidate is *not* automatically allocated: two outgoing carrier slots
    can share one club and one candidate, and the source has no PM99 ratings or
    fine-role judgement.  Allocation belongs to a later authored package.
    """
    if resolution.get("schema_version") != RESOLVED_SCHEMA:
        raise SourceReadinessError(f"resolution.schema_version must be {RESOLVED_SCHEMA!r}")
    if resolution.get("package_id") != package.get("package_id"):
        raise SourceReadinessError("resolution belongs to a different package")

    clubs = {club["id"]: club for club in package["clubs"]}
    players = {player["id"]: player for player in package["players"]}
    roster_names: dict[str, set[str]] = defaultdict(set)
    for player in package["players"]:
        roster_names[player["club_id"]].add(_normalise(player["name"]))
    opening_by_club = _opening_by_club(opening)
    facts_by_club = _facts_by_club(source_ledger)

    rows: list[dict[str, Any]] = []
    candidate_identities: set[tuple[str, str]] = set()
    for group in resolution.get("rows", []):
        if not isinstance(group, dict) or not isinstance(group.get("resolution"), dict):
            raise SourceReadinessError("resolution has an invalid candidate row")
        replacements = group["resolution"].get("replace_player_ids")
        if not isinstance(replacements, list) or not all(isinstance(player_id, str) for player_id in replacements):
            raise SourceReadinessError("resolution replacement_player_ids must be a list of IDs")
        for player_id in replacements:
            player = players.get(player_id)
            if player is None:
                raise SourceReadinessError(f"resolution references absent player {player_id}")
            club = clubs.get(player["club_id"])
            if club is None:
                raise SourceReadinessError(f"player {player_id} has no package club")
            club_key = _club_key(str(club.get("full_name") or club["name"]))
            fixture_players = opening_by_club.get(club_key)
            source_players = facts_by_club.get(club_key)
            if fixture_players is None or source_players is None:
                raise SourceReadinessError(f"no retained opening evidence/facts ledger for {club['name']}")
            candidates: list[dict[str, Any]] = []
            for fixture_player in fixture_players:
                source_name = str(fixture_player["source_name"])
                identity = _normalise(source_name)
                # A person already in the package cannot fill a second carrier.
                if identity in roster_names[player["club_id"]]:
                    continue
                facts = source_players.get(identity)
                if facts is None:
                    continue
                candidates.append({
                    "name": facts["name"],
                    "source_name": source_name,
                    "birth_date_ddmmyy": facts.get("birth_date_ddmmyy"),
                    "nationality": facts.get("nationality"),
                    "position": facts.get("position"),
                    "height_cm": facts.get("height_cm"),
                    "weight_kg": facts.get("weight_kg"),
                    "shirt_number": fixture_player.get("shirt_number"),
                    "first_fixture_source_url": fixture_player.get("source_url"),
                })
                candidate_identities.add((club_key, identity))
            candidates.sort(key=lambda row: (_normalise(str(row["name"])), str(row.get("birth_date_ddmmyy") or "")))
            rows.append({
                "replacement_player_id": player_id,
                "carrier_id": player["carrier_id"],
                "club_id": club["id"],
                "club_name": club["name"],
                "outgoing_name": player["name"],
                "opening_fixture_identity_candidates": candidates,
                "status": "candidate-needs-editorial-ratings-and-unique-allocation" if candidates else "needs-dated-opening-roster-source",
            })
    rows.sort(key=lambda row: row["replacement_player_id"])
    slots_with_candidates = sum(bool(row["opening_fixture_identity_candidates"]) for row in rows)
    return {
        "schema_version": SCHEMA,
        "package_id": package["package_id"],
        "package_canonical_sha256": _hash(package),
        "resolution_canonical_sha256": _hash(resolution),
        "opening_lineup_canonical_sha256": _hash(opening),
        "source_ledger_canonical_sha256": _hash(source_ledger),
        "rows": rows,
        "summary": {
            "replacement_carriers_required": len(rows),
            "slots_with_retained_first_fixture_identity_candidates": slots_with_candidates,
            "unique_retained_first_fixture_identity_candidates": len(candidate_identities),
            "slots_needing_dated_opening_roster_source": len(rows) - slots_with_candidates,
            "strict_native_rebuild_ready": False,
        },
        "remaining_data_requirements": [
            "For every pending carrier: a source proving that named replacement player belonged to that club on the package snapshot date.",
            "For every replacement: name, date of birth, PM99 nationality, broad position, height, weight and opening shirt number.",
            "For every replacement: an authored PM99 rating/fine-role/portrait decision, bound to that dated identity source.",
        ],
        "policy": "The retained whole-season source ledger is a facts cache only. It must not select a replacement without separate opening-date membership evidence.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--resolution", required=True, type=Path)
    parser.add_argument("--opening-lineups", required=True, type=Path)
    parser.add_argument("--source-ledger", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        package = package_v2.read_canonical_package(args.package)
        package_v2.validate_package(package)
        resolution = _read_json(args.resolution, label="resolution")
        opening = _read_json(args.opening_lineups, label="opening lineups")
        source_ledger = _read_json(args.source_ledger, label="source ledger")
        output = build_readiness(package, resolution, opening, source_ledger)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(_canonical_bytes(output))
        print(json.dumps({"output": str(args.output), **output["summary"]}, sort_keys=True))
    except (SourceReadinessError, package_v2.PackageValidationError, OSError) as exc:
        print(f"opening-date replacement-source audit error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
