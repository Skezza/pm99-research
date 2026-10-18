#!/usr/bin/env python3
"""Build pinned deterministic rating input from a season package draft.

This stage makes the agreed editorial fallback reproducible.  It rates only
source-authored players on allocated foreign carriers, derives squad status
from the independently captured opening-XI layer when available, and uses a
versioned country-strength table.  It does not claim those strengths are
historical source facts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_carrier_allocation_v1 as allocation_v1  # noqa: E402
from scripts import season_editorial_ratings_v1 as ratings_v1  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402


SCHEMA = "pm99-season-editorial-rating-input-build-v1"
POLICY_ID = "reviewed-editorial-country-strength-v1"

# Deliberately coarse and reviewable.  Player role, opening status, age and a
# stable person separator supply within-club variation in the downstream
# model.  Editing one entry changes only that country's clubs.
COUNTRY_STRENGTH = {
    "argentina": 72, "austria": 61, "belgium": 64, "brazil": 72,
    "bulgaria": 55, "chile": 61, "colombia": 62, "croatia": 60,
    "czechia": 59, "denmark": 60, "ecuador": 58, "finland": 51,
    "france": 70, "georgia": 48, "germany": 72, "greece": 62,
    "hungary": 54, "ireland": 49, "italy": 74, "netherlands": 68,
    "norway": 57, "paraguay": 59, "peru": 57, "poland": 57,
    "portugal": 67, "romania": 57, "russia": 64, "scotland": 61,
    "serbia": 58, "slovakia": 53, "slovenia": 53, "spain": 74,
    "sweden": 58, "switzerland": 58, "turkey": 64, "ukraine": 62,
    "uruguay": 61, "venezuela": 54,
}


class RatingInputBuildError(ValueError):
    pass


def _bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_bytes(dict(value))).hexdigest()


def _normalise(value: object) -> str:
    return "".join(char.casefold() for char in str(value or "") if char.isalnum())


def build_input(
    *, draft: Mapping[str, Any], allocation: Mapping[str, Any],
    opening: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    # The source bridge intentionally emits blocked drafts while legacy-tail
    # person collisions remain. Rating those source-authored rows is part of
    # resolving the draft; strict validation belongs to final integration.
    package_v2.validate_package(draft, strict=False)
    if allocation.get("schema_version") != allocation_v1.SCHEMA:
        raise RatingInputBuildError("unsupported carrier allocation")
    season = draft["season"]
    if allocation.get("season", {}).get("label") != season["label"]:
        raise RatingInputBuildError("allocation season differs from package")

    opening_by_selector: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    fixture_dates: list[str] = []
    if opening is not None:
        for row in opening.get("clubs", []):
            selector = row.get("source_selector", {})
            key = tuple(str(selector.get(field) or "") for field in (
                "country_catalog", "competition_catalog", "club_name"
            ))
            if not all(key) or key in opening_by_selector:
                raise RatingInputBuildError("opening layer has an invalid or duplicate selector")
            opening_by_selector[key] = row
            date = row.get("first_league_fixture_date")
            if isinstance(date, str) and date.startswith(f"{season['start_year']:04d}-"):
                fixture_dates.append(date)
    snapshot_date = min(fixture_dates) if fixture_dates else f"{season['start_year']:04d}-08-01"

    clubs = {int(row["carrier_id"]): row for row in draft["clubs"]}
    players = {str(row["id"]): row for row in draft["players"]}
    hierarchy: list[dict[str, Any]] = []
    rating_players: list[dict[str, Any]] = []
    missing_position_player_ids: list[str] = []
    invalid_birth_date_player_ids: list[str] = []
    missing_strength_carrier_ids: dict[str, list[int]] = {}
    missing_strength_player_ids: set[str] = set()
    xi_count = 0
    for assignment in allocation.get("assignments", []):
        carrier = int(assignment["carrier_id"])
        country = str(assignment["country_group"])
        club = clubs.get(carrier)
        if club is None:
            raise RatingInputBuildError(f"allocation carrier absent from package: {carrier}")
        source_players = [
            players[player_id] for player_id in club["roster_player_ids"]
            if str(players[player_id].get("person_id", "")).startswith("person-source-")
        ]
        if country not in COUNTRY_STRENGTH:
            # Do not manufacture a rating for a country group that has not
            # been added to the reviewed policy.  Retaining the other,
            # independently covered groups makes the outstanding policy work
            # explicit and reusable without presenting a partial output as
            # complete.
            missing_strength_carrier_ids.setdefault(country, []).append(carrier)
            missing_strength_player_ids.update(str(player["id"]) for player in source_players)
            continue
        hierarchy.append({
            "club_id": str(club["id"]),
            "strength": COUNTRY_STRENGTH[country],
            "source_ids": [POLICY_ID],
        })
        selector = assignment["source_selector"]
        key = (str(selector["country_catalog"]), str(selector["competition_catalog"]), str(assignment["club_name"]))
        opening_row = opening_by_selector.get(key)
        roster_by_name: dict[str, list[str]] = {}
        for player in source_players:
            roster_by_name.setdefault(
                _normalise(player.get("source_name", player["name"])), []
            ).append(str(player["id"]))
        joined_xi: list[str] = []
        for row in (opening_row or {}).get("starting_xi", []):
            candidates = roster_by_name.get(
                _normalise(row.get("source_name", row.get("display_name"))), []
            )
            if len(candidates) != 1:
                joined_xi = []
                break
            joined_xi.append(candidates[0])
        xi_player_ids = set(joined_xi) if len(joined_xi) == 11 and len(set(joined_xi)) == 11 else set()
        for player_id in club["roster_player_ids"]:
            player = players[player_id]
            if not str(player.get("person_id", "")).startswith("person-source-"):
                continue
            status = "starting_xi" if player_id in xi_player_ids else "opening_squad"
            facts = player.get("facts", {})
            birth = facts.get("birth_date")
            height = facts.get("height_cm")
            position = facts.get("primary_position")
            if not isinstance(position, str) or position not in {"G", "D", "M", "F"}:
                missing_position_player_ids.append(str(player_id))
                continue
            usable_birth: str | None = None
            if isinstance(birth, str):
                try:
                    parsed_birth = dt.date.fromisoformat(birth)
                    parsed_snapshot = dt.date.fromisoformat(snapshot_date)
                except ValueError:
                    invalid_birth_date_player_ids.append(str(player_id))
                else:
                    if parsed_birth <= parsed_snapshot:
                        usable_birth = birth
                    else:
                        invalid_birth_date_player_ids.append(str(player_id))
            xi_count += status == "starting_xi"
            rating_players.append({
                "player_id": player_id,
                "person_id": player["person_id"],
                "club_id": club["id"],
                "position": position,
                "birth_date": usable_birth,
                "height_cm": height if isinstance(height, int) and not isinstance(height, bool) else None,
                "squad_status": status,
            })

    hierarchy.sort(key=lambda row: row["club_id"])
    rating_players.sort(key=lambda row: (row["person_id"], row["player_id"]))
    payload = {
        "schema_version": ratings_v1.INPUT_SCHEMA,
        "snapshot_date": snapshot_date,
        "hierarchy": {
            "schema_version": ratings_v1.HIERARCHY_SCHEMA,
            "snapshot_date": snapshot_date,
            "clubs": hierarchy,
        },
        "players": rating_players,
    }
    # Validate by building the output; callers retain the input separately so
    # policy edits remain inspectable.
    ratings_v1.build_rating_output(payload)
    hard_blockers: list[dict[str, Any]] = []
    if missing_strength_carrier_ids:
        hard_blockers.append({
            "code": "country-strength-policy-required",
            "count": sum(len(carriers) for carriers in missing_strength_carrier_ids.values()),
            "country_groups": sorted(missing_strength_carrier_ids),
            "carrier_ids_by_country_group": {
                country: sorted(carriers)
                for country, carriers in sorted(missing_strength_carrier_ids.items())
            },
            "player_count": len(missing_strength_player_ids),
            "message": (
                "Allocated source players were left unrated because their country group "
                "has no reviewed editorial strength in this policy version."
            ),
        })
    if missing_position_player_ids:
        hard_blockers.append({
            "code": "source-player-primary-position-required-for-rating",
            "count": len(missing_position_player_ids),
            "player_ids": sorted(missing_position_player_ids),
        })
    audit = {
        "schema_version": SCHEMA,
        "season": dict(season),
        "inputs": {
            "draft_package_sha256": _digest(draft),
            "carrier_allocation_sha256": _digest(allocation),
            "opening_sha256": _digest(opening) if opening is not None else None,
        },
        "policy": {"id": POLICY_ID, "country_strength": dict(sorted(COUNTRY_STRENGTH.items()))},
        "coverage": {
            "club_count": len(hierarchy), "player_count": len(rating_players),
            "starting_xi_player_count": xi_count,
            "opening_squad_player_count": len(rating_players) - xi_count,
            "country_strength_missing_assignment_count": sum(
                len(carriers) for carriers in missing_strength_carrier_ids.values()
            ),
            "country_strength_missing_player_count": len(missing_strength_player_ids),
            "missing_primary_position_player_count": len(missing_position_player_ids),
            "invalid_birth_date_fallback_player_count": len(invalid_birth_date_player_ids),
        },
        "hard_blockers": hard_blockers,
        "non_blocking_warnings": ([{
            "code": "invalid-player-birth-date-fallback-logged",
            "count": len(invalid_birth_date_player_ids),
            "player_ids": sorted(invalid_birth_date_player_ids),
        }] if invalid_birth_date_player_ids else []),
        "output_sha256": _digest(payload),
    }
    return payload, audit


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RatingInputBuildError(f"input must be an object: {path}")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft-package", required=True, type=Path)
    parser.add_argument("--carrier-allocation", required=True, type=Path)
    parser.add_argument("--opening", type=Path)
    parser.add_argument("--output-input", required=True, type=Path)
    parser.add_argument("--output-ratings", required=True, type=Path)
    parser.add_argument("--output-audit", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        payload, audit = build_input(
            draft=_read(args.draft_package), allocation=_read(args.carrier_allocation),
            opening=_read(args.opening) if args.opening else None,
        )
        output = ratings_v1.build_rating_output(payload)
        for path, value in ((args.output_input, payload), (args.output_ratings, output), (args.output_audit, audit)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_bytes(value))
    except (OSError, ValueError, json.JSONDecodeError, package_v2.PackageValidationError) as exc:
        parser.error(str(exc))
    print(json.dumps(audit["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
