#!/usr/bin/env python3
"""Turn duplicate player candidates into a dated, reviewable reconciliation queue.

Historic roster pages often describe a whole season.  A PM99 new-game database
needs one opening-date state: a real player cannot be in two clubs.  This tool
compares an already-built package with its captured first-fixture lineups.  It
can recommend removal of a duplicate only when exactly one existing package
record appears in that dated XI/bench.  Everything else is kept as a named
manual decision; it never guesses a transfer date or manufactures a player.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_v2 as package_v2


SCHEMA = "pm99-opening-date-identity-reconciliation-v1"
DECISIONS_SCHEMA = "pm99-opening-date-identity-decisions-v1"
RESOLVED_SCHEMA = "pm99-opening-date-identity-resolution-v1"


class ReconciliationError(ValueError):
    """The opening lineup source cannot safely reconcile package identities."""


def _require_id(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not package_v2.ID_RE.fullmatch(value):
        raise ReconciliationError(f"{label} must be a stable ID")
    return value


def _require_nonempty(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReconciliationError(f"{label} must be a non-empty string")
    return value


def _require_uri(value: Any, *, label: str) -> str:
    uri = _require_nonempty(value, label=label)
    if not uri.startswith(("https://", "http://")):
        raise ReconciliationError(f"{label} must be an HTTP(S) URI")
    return uri


def _canonical_bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _normalise(value: str) -> str:
    # NFKD does not decompose a small but important set of football-name
    # characters (notably Polish \u0142).  Source sites commonly preserve these
    # while the CP1252 PM99 package stores the readable transliteration.  Do
    # this before NFKD so a first-fixture name cannot be mistaken for a second,
    # missing player merely because its accent was not representable in PM99.
    text = str(value or "").translate(str.maketrans({
        "\u0141": "L", "\u0142": "l", "\u0110": "D", "\u0111": "d", "\u00d8": "O", "\u00f8": "o",
        "\u00de": "Th", "\u00fe": "th", "\u00c6": "AE", "\u00e6": "ae", "\u00d0": "D", "\u00f0": "d",
    }))
    text = unicodedata.normalize("NFKD", text)
    return "".join(char.casefold() for char in text if char.isalnum())


_CLUB_ALIASES = {
    "queensparkrangers": "qpr",
    "qpr": "qpr",
    "westbromwichalbion": "westbrom",
    "westbrom": "westbrom",
    "brightonhovealbion": "brighton",
    "brighton": "brighton",
    "nottinghamforest": "nottinghamforest",
    "nottmforest": "nottinghamforest",
    "sheffieldwednesday": "sheffwed",
    "sheffwed": "sheffwed",
    "sheffieldunited": "sheffutd",
    "sheffutd": "sheffutd",
    "miltonkeynesdons": "mkdons",
    "mkdons": "mkdons",
    "wolverhamptonwanderers": "wolves",
    "wolves": "wolves",
}


def _club_key(value: str) -> str:
    normalised = _normalise(value)
    normalised = normalised.removesuffix("footballclub").removesuffix("fc")
    return _CLUB_ALIASES.get(normalised, normalised)


def _candidate_key(player: dict[str, Any]) -> tuple[str, str, str] | None:
    facts = player.get("facts")
    if not isinstance(facts, dict) or not isinstance(player.get("name"), str):
        return None
    birth_date, nationality = facts.get("birth_date"), facts.get("nationality")
    if not isinstance(birth_date, str) or not isinstance(nationality, str):
        return None
    return (_normalise(player["name"]), birth_date, nationality)


def _read_canonical_package(path: Path) -> dict[str, Any]:
    package = package_v2.read_canonical_package(path)
    package_v2.validate_package(package)
    return package


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReconciliationError(f"cannot read {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReconciliationError(f"{label} must be a JSON object")
    return value


def _opening_evidence_by_club(opening: dict[str, Any]) -> tuple[dict[str, set[str]], dict[str, str]]:
    if opening.get("schema_version") != "pm99-2015-16-opening-lineup-reconciliation-v1":
        raise ReconciliationError("opening lineups must use the certified first-fixture reconciliation schema")
    if opening.get("failures"):
        raise ReconciliationError("opening lineups contain unresolved identities")
    result: dict[str, set[str]] = {}
    dates: dict[str, str] = {}
    for row in opening.get("clubs", []):
        if not isinstance(row, dict) or not row.get("reconciled"):
            raise ReconciliationError("opening lineups contain an uncertified club")
        club = row.get("club")
        if not isinstance(club, str) or not club:
            raise ReconciliationError("opening lineup has an unnamed club")
        names: set[str] = set()
        for player in [*(row.get("starting_xi") or []), *(row.get("substitutes") or [])]:
            if not isinstance(player, dict) or not isinstance(player.get("source_name"), str):
                raise ReconciliationError(f"opening lineup {club} has an unresolved player")
            names.add(_normalise(player["source_name"]))
        key = _club_key(club)
        if key in result:
            raise ReconciliationError(f"opening lineups duplicate club identity {club!r}")
        raw_date = row.get("first_league_fixture_date")
        if not isinstance(raw_date, str):
            raise ReconciliationError(f"opening lineup {club} has no first-fixture date")
        try:
            fixture_date = dt.datetime.strptime(raw_date, "%d/%m/%Y").date().isoformat()
        except ValueError as exc:
            raise ReconciliationError(f"opening lineup {club} has invalid first-fixture date {raw_date!r}") from exc
        result[key] = names
        dates[key] = fixture_date
    return result, dates


def build_reconciliation(package: dict[str, Any], opening: dict[str, Any]) -> dict[str, Any]:
    """Build only evidence-backed recommendations; make all other rows explicit."""
    clubs = {
        row["id"]: {
            "name": row["name"],
            "key": _club_key(str(row.get("full_name") or row["name"])),
        }
        for row in package["clubs"]
    }
    opening_names, opening_dates = _opening_evidence_by_club(opening)
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for player in package["players"]:
        key = _candidate_key(player)
        if key is not None:
            groups[key].append(player)

    rows: list[dict[str, Any]] = []
    auto_count = manual_count = 0
    for number, ((name, birth_date, nationality), players) in enumerate(sorted(groups.items()), start=1):
        if len(players) < 2:
            continue
        candidates = []
        dated_hits: list[dict[str, Any]] = []
        for player in sorted(players, key=lambda row: row["id"]):
            club = clubs.get(player["club_id"])
            if club is None:
                raise ReconciliationError(f"player {player['id']} has no package club")
            in_first_fixture = name in opening_names.get(club["key"], set())
            candidate = {
                "player_id": player["id"],
                "carrier_id": player["carrier_id"],
                "club_id": player["club_id"],
                "club_name": club["name"],
                "shirt_number": player["facts"]["shirt_number"],
                "in_first_fixture_xi_or_bench": in_first_fixture,
            }
            candidates.append(candidate)
            if in_first_fixture:
                dated_hits.append(candidate)
        if len(dated_hits) == 1:
            retained = dated_hits[0]
            disposition = "first-fixture-proven-retain-one-replace-others"
            auto_count += 1
            recommendation = {
                "retain_player_id": retained["player_id"],
                "replace_player_ids": [row["player_id"] for row in candidates if row["player_id"] != retained["player_id"]],
            }
        else:
            disposition = "manual-opening-date-membership-required"
            manual_count += 1
            recommendation = None
        rows.append({
            "id": f"candidate-{number:03d}",
            "person_candidate": {"normalised_name": name, "birth_date": birth_date, "nationality": nationality},
            "candidates": candidates,
            "disposition": disposition,
            "recommendation": recommendation,
        })
    return {
        "schema_version": SCHEMA,
        "package_id": package["package_id"],
        "package_canonical_sha256": _hash(package),
        "opening_lineup_canonical_sha256": _hash(opening),
        "snapshot_dates": sorted(set(opening_dates.values())),
        "rows": rows,
        "summary": {
            "duplicate_candidate_groups": len(rows),
            "first_fixture_proven_groups": auto_count,
            "manual_membership_groups": manual_count,
            "replacement_carriers_required": sum(
                len(row["recommendation"]["replace_player_ids"])
                for row in rows if row["recommendation"] is not None
            ),
        },
    }


def validate_decisions(decisions: dict[str, Any], reconciliation: dict[str, Any]) -> None:
    """Validate dated editorial choices against exactly this reconciliation queue.

    A decision identifies the existing carrier that retains the real person at
    the selected snapshot, or explicitly says that none of the available
    English carriers owns that person on that date.  It does *not* invent the
    replacement player.  That separate source-authoring job is kept visible.
    """
    if decisions.get("schema_version") != DECISIONS_SCHEMA:
        raise ReconciliationError(f"decisions.schema_version must be {DECISIONS_SCHEMA!r}")
    if decisions.get("reconciliation_canonical_sha256") != _hash(reconciliation):
        raise ReconciliationError("decisions are bound to a different reconciliation queue")
    rows = decisions.get("decisions")
    if not isinstance(rows, list):
        raise ReconciliationError("decisions.decisions must be a list")
    manual = {
        row["id"]: row for row in reconciliation["rows"]
        if row["disposition"] == "manual-opening-date-membership-required"
    }
    decision_ids: list[str] = []
    for index, decision in enumerate(rows):
        if not isinstance(decision, dict):
            raise ReconciliationError(f"decisions[{index}] must be an object")
        allowed = {
            "id", "action", "retain_player_id", "replace_player_ids",
            "snapshot_date", "reason", "sources",
        }
        if set(decision) != allowed:
            raise ReconciliationError(f"decisions[{index}] must contain exactly {sorted(allowed)}")
        identity = _require_id(decision.get("id"), label=f"decisions[{index}].id")
        decision_ids.append(identity)
        queue_row = manual.get(identity)
        if queue_row is None:
            raise ReconciliationError(f"decisions[{index}] is not a manual reconciliation candidate")
        action = decision.get("action")
        if action not in {"retain-one-replace-others", "replace-all"}:
            raise ReconciliationError(f"decisions[{index}].action is invalid")
        if decision.get("snapshot_date") not in reconciliation.get("snapshot_dates", []):
            raise ReconciliationError(
                f"decisions[{index}].snapshot_date must be one of the package opening snapshots "
                f"{reconciliation.get('snapshot_dates', [])}"
            )
        _require_nonempty(decision.get("reason"), label=f"decisions[{index}].reason")
        sources = decision.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ReconciliationError(f"decisions[{index}].sources must be a non-empty list")
        source_keys: list[str] = []
        for source_index, source in enumerate(sources):
            if not isinstance(source, dict) or set(source) != {"title", "uri"}:
                raise ReconciliationError(f"decisions[{index}].sources[{source_index}] must contain title and uri")
            title = _require_nonempty(source.get("title"), label=f"decisions[{index}].sources[{source_index}].title")
            uri = _require_uri(source.get("uri"), label=f"decisions[{index}].sources[{source_index}].uri")
            source_keys.append(f"{title}\u0000{uri}")
        if source_keys != sorted(set(source_keys)):
            raise ReconciliationError(f"decisions[{index}].sources must be sorted and unique")
        candidate_ids = sorted(candidate["player_id"] for candidate in queue_row["candidates"])
        replacement_ids = decision.get("replace_player_ids")
        if not isinstance(replacement_ids, list) or replacement_ids != sorted(set(replacement_ids)):
            raise ReconciliationError(f"decisions[{index}].replace_player_ids must be sorted and unique")
        if not all(isinstance(player_id, str) for player_id in replacement_ids):
            raise ReconciliationError(f"decisions[{index}].replace_player_ids must be strings")
        retained = decision.get("retain_player_id")
        if action == "retain-one-replace-others":
            if retained not in candidate_ids:
                raise ReconciliationError(f"decisions[{index}].retain_player_id is not a candidate carrier")
            expected_replacements = [player_id for player_id in candidate_ids if player_id != retained]
            if replacement_ids != expected_replacements:
                raise ReconciliationError(f"decisions[{index}].replace_player_ids must be every non-retained carrier")
        else:
            if retained is not None:
                raise ReconciliationError(f"decisions[{index}].replace-all must set retain_player_id to null")
            if replacement_ids != candidate_ids:
                raise ReconciliationError(f"decisions[{index}].replace-all must replace every candidate carrier")
    if decision_ids != sorted(decision_ids) or len(decision_ids) != len(set(decision_ids)):
        raise ReconciliationError("decision IDs must be sorted and unique")
    if set(decision_ids) != set(manual):
        raise ReconciliationError(
            "decisions must cover every manual candidate exactly once; "
            f"missing={sorted(set(manual) - set(decision_ids))}, extra={sorted(set(decision_ids) - set(manual))}"
        )


def apply_decisions(reconciliation: dict[str, Any], decisions: dict[str, Any]) -> dict[str, Any]:
    """Produce a receipt showing every carrier still needing source replacement."""
    validate_decisions(decisions, reconciliation)
    by_id = {row["id"]: row for row in decisions["decisions"]}
    rows: list[dict[str, Any]] = []
    replacements: list[str] = []
    manual_resolved = 0
    for row in reconciliation["rows"]:
        recommendation = row["recommendation"]
        if recommendation is not None:
            final = {
                "action": "retain-one-replace-others",
                "retain_player_id": recommendation["retain_player_id"],
                "replace_player_ids": recommendation["replace_player_ids"],
                "basis": "certified-first-fixture",
            }
        else:
            decision = by_id[row["id"]]
            final = {
                "action": decision["action"],
                "retain_player_id": decision["retain_player_id"],
                "replace_player_ids": decision["replace_player_ids"],
                "basis": "dated-editorial-source",
                "snapshot_date": decision["snapshot_date"],
                "reason": decision["reason"],
                "sources": decision["sources"],
            }
            manual_resolved += 1
        replacements.extend(final["replace_player_ids"])
        rows.append({
            "id": row["id"], "person_candidate": row["person_candidate"],
            "candidates": row["candidates"], "resolution": final,
        })
    return {
        "schema_version": RESOLVED_SCHEMA,
        "package_id": reconciliation["package_id"],
        "reconciliation_canonical_sha256": _hash(reconciliation),
        "decisions_canonical_sha256": _hash(decisions),
        "rows": rows,
        "summary": {
            "duplicate_candidate_groups": len(rows),
            "first_fixture_resolutions": reconciliation["summary"]["first_fixture_proven_groups"],
            "dated_editorial_resolutions": manual_resolved,
            "replacement_carriers_required": len(replacements),
            "unresolved_membership_groups": 0,
        },
    }
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--opening-lineups", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--decisions", type=Path, help="canonical manual membership decisions bound to this queue")
    args = parser.parse_args(argv)
    try:
        package = _read_canonical_package(args.package)
        opening = _read_json(args.opening_lineups, label="opening lineups")
        result = build_reconciliation(package, opening)
        if args.decisions is not None:
            decisions = _read_json(args.decisions, label="opening-date decisions")
            result = apply_decisions(result, decisions)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(_canonical_bytes(result))
        print(json.dumps({"output": str(args.output), **result["summary"]}, sort_keys=True))
    except (ReconciliationError, package_v2.PackageValidationError, OSError) as exc:
        print(f"opening-date identity reconciliation error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
