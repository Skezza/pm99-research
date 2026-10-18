#!/usr/bin/env python3
"""Generate deterministic, season-neutral PM99 editorial ratings.

The model is deliberately a transform of pinned inputs, not a source of
historical facts.  A caller supplies the season snapshot date, a reviewable
per-club strength hierarchy and stable person identities.  Complete sourced
ratings pass through unchanged; only players without them receive editorial
values.

Small separators are keyed by ``person_id``.  Carrier IDs, record slots, club
ordering and input ordering therefore cannot change a person's generated
attributes.  Every output row records canonical input hashes so a later edit
can be traced and reproduced.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


INPUT_SCHEMA = "pm99-season-editorial-rating-input-v1"
HIERARCHY_SCHEMA = "pm99-season-club-rating-hierarchy-v1"
OUTPUT_SCHEMA = "pm99-season-editorial-rating-output-v1"
MODEL_VERSION = "v1"
RATING_PROFILE = "pm99-visible-skills-v1"
RATING_FIELDS = (
    "quality", "speed", "stamina", "aggression", "passing", "tackling",
    "heading", "shooting", "dribbling", "handling",
)

_POSITIONS = {"G", "D", "M", "F"}
_STATUS_BONUS = {"starting_xi": 5, "substitute": 1, "opening_squad": -4}
_DELTAS = {
    "G": {"speed": -21, "stamina": -14, "aggression": -11, "passing": -9, "tackling": -25, "heading": -30, "shooting": -37, "dribbling": -31},
    "D": {"speed": -6, "stamina": 2, "aggression": 4, "passing": -4, "tackling": 6, "heading": 5, "shooting": -19, "dribbling": -11},
    "M": {"speed": 2, "stamina": 6, "aggression": 1, "passing": 5, "tackling": 1, "heading": -2, "shooting": -2, "dribbling": 3},
    "F": {"speed": 6, "stamina": 3, "aggression": 1, "passing": -1, "tackling": -20, "heading": 2, "shooting": 9, "dribbling": 4},
}


class EditorialRatingError(ValueError):
    """The pinned editorial-rating inputs are incomplete or inconsistent."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def document_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _policy_document() -> dict[str, Any]:
    """Return the declarative model inputs used for the policy fingerprint."""
    return {
        "model_version": MODEL_VERSION,
        "rating_profile": RATING_PROFILE,
        "rating_fields": list(RATING_FIELDS),
        "status_bonus": _STATUS_BONUS,
        "position_deltas": _DELTAS,
        "variation_range": [-2, 2],
        "outfield_handling_range": [1, 20],
        "goalkeeper_handling_floor": "max(35, quality - 12)",
    }


MODEL_SHA256 = document_sha256(_policy_document())


def _date(value: object, *, field: str) -> dt.date:
    try:
        parsed = dt.date.fromisoformat(str(value))
    except ValueError as exc:
        raise EditorialRatingError(f"{field} must be an ISO date") from exc
    if str(value) != parsed.isoformat():
        raise EditorialRatingError(f"{field} must be an ISO date")
    return parsed


def _age_on(birth_date: object, snapshot_date: dt.date) -> int | None:
    if birth_date in (None, ""):
        return None
    born = _date(birth_date, field="players[].birth_date")
    if born > snapshot_date:
        raise EditorialRatingError("players[].birth_date is after snapshot_date")
    return snapshot_date.year - born.year - ((snapshot_date.month, snapshot_date.day) < (born.month, born.day))


def _age_adjustment(age: int | None) -> int:
    if age is None:
        return 0
    if age <= 18:
        return -5
    if age <= 21:
        return -3
    if 25 <= age <= 31:
        return 1
    if age >= 35:
        return -2
    return 0


def _clamp(value: int, low: int = 1, high: int = 99) -> int:
    return max(low, min(high, int(value)))


def _variation(*, person_id: str, field: str) -> int:
    # person_id is the reconciled historical identity.  Do not add club,
    # carrier, slot, player row ID or snapshot date to this seed.
    digest = hashlib.sha256(f"pm99-season-editorial-ratings-v1|{person_id}|{field}".encode("utf-8")).digest()
    return int(digest[0] % 5) - 2


def _validate_rating_values(values: object, *, field: str) -> dict[str, int]:
    if not isinstance(values, Mapping) or set(values) != set(RATING_FIELDS):
        raise EditorialRatingError(f"{field} must contain exactly the ten PM99 visible ratings")
    result: dict[str, int] = {}
    for key in RATING_FIELDS:
        value = values[key]
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
            raise EditorialRatingError(f"{field}.{key} must be an integer in 0..100")
        result[key] = value
    return result


def _hierarchy_index(hierarchy: object, *, snapshot_date: str) -> tuple[dict[str, dict[str, Any]], str]:
    if not isinstance(hierarchy, Mapping) or hierarchy.get("schema_version") != HIERARCHY_SCHEMA:
        raise EditorialRatingError(f"hierarchy must use {HIERARCHY_SCHEMA}")
    if hierarchy.get("snapshot_date") != snapshot_date:
        raise EditorialRatingError("hierarchy.snapshot_date must equal snapshot_date")
    clubs = hierarchy.get("clubs")
    if not isinstance(clubs, list) or not clubs:
        raise EditorialRatingError("hierarchy.clubs must be a non-empty list")
    index: dict[str, dict[str, Any]] = {}
    for position, raw in enumerate(clubs):
        if not isinstance(raw, Mapping):
            raise EditorialRatingError(f"hierarchy.clubs[{position}] must be an object")
        club_id = str(raw.get("club_id") or "")
        strength = raw.get("strength")
        source_ids = raw.get("source_ids")
        if not club_id or club_id in index:
            raise EditorialRatingError("hierarchy club IDs must be present and unique")
        if not isinstance(strength, int) or isinstance(strength, bool) or not 30 <= strength <= 95:
            raise EditorialRatingError(f"hierarchy club {club_id!r} strength must be in 30..95")
        if not isinstance(source_ids, list) or not source_ids or any(not isinstance(value, str) or not value for value in source_ids):
            raise EditorialRatingError(f"hierarchy club {club_id!r} requires source_ids")
        index[club_id] = {"strength": strength, "source_ids": list(source_ids)}
    # JSON array order is not part of the hierarchy's meaning.  Fingerprint a
    # normalized projection so a viewer reordering clubs cannot invalidate all
    # generated player provenance.
    normalized = {
        "schema_version": HIERARCHY_SCHEMA,
        "snapshot_date": snapshot_date,
        "clubs": [
            {
                "club_id": club_id,
                "strength": index[club_id]["strength"],
                "source_ids": sorted(index[club_id]["source_ids"]),
            }
            for club_id in sorted(index)
        ],
    }
    return index, document_sha256(normalized)


def _editorial_ratings(
    *, player: Mapping[str, Any], snapshot: dt.date, club: Mapping[str, Any],
    hierarchy_sha256: str,
) -> dict[str, Any]:
    person_id = str(player["person_id"])
    position = str(player.get("position") or "")
    squad_status = str(player.get("squad_status") or "")
    if position not in _POSITIONS:
        raise EditorialRatingError(f"player {person_id!r} has unsupported position {position!r}")
    if squad_status not in _STATUS_BONUS:
        raise EditorialRatingError(f"player {person_id!r} has unsupported squad_status {squad_status!r}")
    age = _age_on(player.get("birth_date"), snapshot)
    adjustment = _age_adjustment(age)
    quality = _clamp(
        int(club["strength"]) + _STATUS_BONUS[squad_status] + adjustment
        + _variation(person_id=person_id, field="quality"),
        30,
        95,
    )
    height = player.get("height_cm")
    if height is not None and (not isinstance(height, int) or isinstance(height, bool) or not 140 <= height <= 220):
        raise EditorialRatingError(f"player {person_id!r} height_cm must be null or in 140..220")
    aerial = 0 if height is None else max(-4, min(7, (height - 180) // 3))
    values: dict[str, int] = {"quality": quality}
    for field, delta in _DELTAS[position].items():
        value = quality + delta + _variation(person_id=person_id, field=field)
        if field == "heading":
            value += aerial
        values[field] = _clamp(value)
    if position == "G":
        values["handling"] = max(
            max(35, quality - 12),
            _clamp(quality + _variation(person_id=person_id, field="handling")),
        )
    else:
        # Handling is goalkeeper technique, not general quality.  Tying this
        # to outfield quality made elite outfield players implausible keepers.
        values["handling"] = _clamp(8 + _variation(person_id=person_id, field="handling"), 1, 20)
    ordered_values = {field: values[field] for field in RATING_FIELDS}
    context = {
        "person_id": person_id,
        "club_id": str(player["club_id"]),
        "snapshot_date": snapshot.isoformat(),
        "position": position,
        "birth_date": player.get("birth_date"),
        "height_cm": height,
        "squad_status": squad_status,
        "club_strength": int(club["strength"]),
    }
    return {
        "profile": RATING_PROFILE,
        "values": ordered_values,
        "provenance": {
            "method": "deterministic editorial rating model v1",
            "proof_grade": "reviewed-editorial",
            "source_ids": list(club["source_ids"]),
            "model_sha256": MODEL_SHA256,
            "hierarchy_sha256": hierarchy_sha256,
            "player_context_sha256": document_sha256(context),
            "snapshot_date": snapshot.isoformat(),
            "person_id": person_id,
            "club_strength": int(club["strength"]),
            "squad_status": squad_status,
            "age_on_snapshot_date": age,
            "age_adjustment": adjustment,
            "position": position,
            "height_aerial_adjustment": aerial,
            "stable_separator": _variation(person_id=person_id, field="quality"),
        },
    }


def build_rating_output(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a pinned input and return stable package-overlay rating rows."""
    if payload.get("schema_version") != INPUT_SCHEMA:
        raise EditorialRatingError(f"input must use {INPUT_SCHEMA}")
    snapshot_text = str(payload.get("snapshot_date") or "")
    snapshot = _date(snapshot_text, field="snapshot_date")
    hierarchy, hierarchy_hash = _hierarchy_index(payload.get("hierarchy"), snapshot_date=snapshot_text)
    players = payload.get("players")
    if not isinstance(players, Sequence) or isinstance(players, (str, bytes)) or not players:
        raise EditorialRatingError("players must be a non-empty list")
    seen_players: set[str] = set()
    seen_people: set[str] = set()
    rows: list[dict[str, Any]] = []
    for offset, raw in enumerate(players):
        if not isinstance(raw, Mapping):
            raise EditorialRatingError(f"players[{offset}] must be an object")
        player_id = str(raw.get("player_id") or "")
        person_id = str(raw.get("person_id") or "")
        club_id = str(raw.get("club_id") or "")
        if not player_id or player_id in seen_players:
            raise EditorialRatingError("player IDs must be present and unique")
        if not person_id or person_id in seen_people:
            raise EditorialRatingError("immutable person IDs must be present and unique")
        if club_id not in hierarchy:
            raise EditorialRatingError(f"player {person_id!r} references unknown hierarchy club {club_id!r}")
        seen_players.add(player_id)
        seen_people.add(person_id)
        sourced = raw.get("sourced_ratings")
        if sourced is not None:
            if not isinstance(sourced, Mapping):
                raise EditorialRatingError(f"player {person_id!r} sourced_ratings must be an object")
            _validate_rating_values(sourced.get("values"), field=f"player {person_id!r} sourced_ratings.values")
            provenance = sourced.get("provenance")
            if not isinstance(provenance, Mapping) or not provenance.get("source_ids"):
                raise EditorialRatingError(f"player {person_id!r} sourced ratings require provenance.source_ids")
            ratings = copy.deepcopy(dict(sourced))
            resolution = {
                "status": "sourced-ratings-preserved",
                "sourced_ratings_sha256": document_sha256(sourced),
            }
        else:
            ratings = _editorial_ratings(
                player=raw,
                snapshot=snapshot,
                club=hierarchy[club_id],
                hierarchy_sha256=hierarchy_hash,
            )
            resolution = {
                "status": "editorial-ratings-generated",
                "model_sha256": MODEL_SHA256,
                "player_context_sha256": ratings["provenance"]["player_context_sha256"],
            }
        rows.append({"player_id": player_id, "person_id": person_id, "ratings": ratings, "resolution": resolution})
    rows.sort(key=lambda row: (row["person_id"], row["player_id"]))
    normalized_input = {
        "schema_version": INPUT_SCHEMA,
        "snapshot_date": snapshot_text,
        "hierarchy_sha256": hierarchy_hash,
        "players": [
            {
                "player_id": row["player_id"],
                "person_id": row["person_id"],
                "resolution": row["resolution"],
            }
            for row in rows
        ],
    }
    return {
        "schema_version": OUTPUT_SCHEMA,
        "snapshot_date": snapshot_text,
        "input_sha256": document_sha256(normalized_input),
        "hierarchy_sha256": hierarchy_hash,
        "model_sha256": MODEL_SHA256,
        "player_ratings": rows,
        "coverage": {
            "player_count": len(rows),
            "sourced_ratings_preserved_count": sum(row["resolution"]["status"] == "sourced-ratings-preserved" for row in rows),
            "editorial_ratings_generated_count": sum(row["resolution"]["status"] == "editorial-ratings-generated" for row in rows),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        output = build_rating_output(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, EditorialRatingError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(output))
    print(json.dumps(output["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
