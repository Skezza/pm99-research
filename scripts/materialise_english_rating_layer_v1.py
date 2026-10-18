#!/usr/bin/env python3
"""Build the English rating layer with the season-neutral editorial model."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_editorial_ratings_v1 as model  # noqa: E402
from scripts.season_english_fixed_carrier_authoring_v1 import COMPETITION_DIVISION


SCHEMA = "pm99-english-rating-layer-adapter-v1"
PREALLOCATION_SCHEMA = "pm99-opening-squad-preallocation-v1"
PRESEASON_STANDINGS_SCHEMA = "pm99-english-preseason-standings-v1"
POLICY_ID = "reviewed-editorial-english-preseason-strength-v2"
SOURCE_ID = "football-data-co-uk-england-results-csv-v1"
DIVISION_STRENGTH = {"Premier League": 74, "Championship": 66, "League One": 58, "League Two": 52}
DIVISION_SOURCE = {"Premier League": "E0", "Championship": "E1", "League One": "E2", "League Two": "E3"}
DIVISION_ORDER = {"E0": 0, "E1": 1, "E2": 2, "E3": 3}

# These are display aliases only.  Both the source CSV and the target-season
# roster are reduced to the same key; the historical club name retained in
# the recipe is never replaced.  The list covers long/short names used by the
# two sources, rather than a season-specific club judgement.
CLUB_ALIASES = {
    "afcbournemouth": "bournemouth", "bournemouth": "bournemouth",
    "brighton": "brightonhovealbion", "brightonhovealbion": "brightonhovealbion",
    "boston": "bostonunited", "bostonunited": "bostonunited",
    "burton": "burtonalbion", "burtonalbion": "burtonalbion",
    "carlisle": "carlisleunited", "carlisleunited": "carlisleunited",
    "crawley": "crawleytown", "crawleytown": "crawleytown",
    "dagenhamredbridge": "dagandred", "dagandred": "dagandred",
    "doncaster": "doncasterrovers", "doncasterrovers": "doncasterrovers",
    "derby": "derbycounty", "derbycounty": "derbycounty",
    "exeter": "exetercity", "exetercity": "exetercity",
    "forestgreen": "forestgreenrovers", "forestgreenrovers": "forestgreenrovers",
    "grimsby": "grimsbytown", "grimsbytown": "grimsbytown",
    "huddersfield": "huddersfieldtown", "huddersfieldtown": "huddersfieldtown",
    "ipswich": "ipswichtown", "ipswichtown": "ipswichtown",
    "kidderminster": "kidderminsterharriers", "kidderminsterharriers": "kidderminsterharriers",
    "leytonorient": "leytonorient", "leyton": "leytonorient",
    "manchestercity": "mancity", "mancity": "mancity",
    "manchesterunited": "manunited", "manunited": "manunited",
    "miltonkeynesdons": "mkdons", "mkdons": "mkdons",
    "newport": "newportcounty", "newportcounty": "newportcounty",
    "nottinghamforest": "nottmforest", "nottmforest": "nottmforest",
    "northampton": "northamptontown", "northamptontown": "northamptontown",
    "nottscounty": "nottscounty", "notts": "nottscounty",
    "oxford": "oxfordunited", "oxfordunited": "oxfordunited",
    "peterborough": "peterboro", "peterboroughunited": "peterboro", "peterboro": "peterboro",
    "plymouth": "plymouthargyle", "plymouthargyle": "plymouthargyle",
    "portvale": "portvale", "port": "portvale",
    "preston": "prestonnorthend", "prestonnorthend": "prestonnorthend",
    "qpr": "queensparkrangers", "queensparkrangers": "queensparkrangers",
    "rotherham": "rotherhamunited", "rotherhamunited": "rotherhamunited",
    "rushdend": "rushdenanddiamonds", "rushdendiamonds": "rushdenanddiamonds", "rushdenanddiamonds": "rushdenanddiamonds",
    "scunthorpe": "scunthorpeunited", "scunthorpeunited": "scunthorpeunited",
    "sheffutd": "sheffieldunited", "sheffieldunited": "sheffieldunited",
    "sheffwed": "sheffieldwednesday", "sheffieldwednesday": "sheffieldwednesday",
    "shrewsbury": "shrewsburytown", "shrewsburytown": "shrewsburytown",
    "stoke": "stokecity", "stokecity": "stokecity",
    "swansea": "swanseacity", "swanseacity": "swanseacity",
    "swindon": "swindontown", "swindontown": "swindontown",
    "westbrom": "westbromwichalbion", "westbromwichalbion": "westbromwichalbion",
    "wigan": "wiganathletic", "wiganathletic": "wiganathletic",
    "wycombe": "wycombewanderers", "wycombewanderers": "wycombewanderers",
    "wolverhamptonwanderers": "wolves", "wolves": "wolves",
}
_CLUB_SUFFIXES = (
    "northend", "athletic", "alexandra", "wanderers", "wednesday",
    "united", "rovers", "county", "albion", "hotspur", "stanley",
    "town", "city", "harriers", "fc",
)


class RatingLayerError(ValueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char.casefold() for char in text if char.isalnum() and not unicodedata.combining(char))


def _club_key(value: object) -> str:
    key = _normalise(value)
    return CLUB_ALIASES.get(key, key)


def _club_keys(value: object) -> set[str]:
    """Return safe long/short display-name matching candidates.

    Football-Data's result feeds use compact display names (for example
    ``Stoke`` and ``Cardiff``), whereas our squad source normally uses full
    names.  A stripped suffix is only accepted when it identifies one prior
    table row; collisions such as Bristol City/Rovers are left unresolved.
    """
    raw = _normalise(value)
    canonical = _club_key(value)
    result = {raw, canonical}
    for key in tuple(result):
        shortened = key
        changed = True
        while changed:
            changed = False
            for suffix in _CLUB_SUFFIXES:
                if shortened.endswith(suffix) and len(shortened) > len(suffix) + 2:
                    shortened = shortened[:-len(suffix)]
                    result.add(shortened)
                    changed = True
                    break
    return {key for key in result if key}


def _season_key(value: object) -> str:
    text = str(value or "")
    match = re.fullmatch(r"((?:19|20)\d{2})/(\d{2})", text)
    if match is None or (int(match.group(1)) + 1) % 100 != int(match.group(2)):
        raise RatingLayerError("preallocation has an invalid season label")
    return f"{match.group(1)}-{match.group(2)}"


def _standing_index(
    *, standings: Mapping[str, Any], season_key: str,
) -> dict[str, list[dict[str, Any]]]:
    if standings.get("schema_version") != PRESEASON_STANDINGS_SCHEMA:
        raise RatingLayerError(f"preseason standings must use {PRESEASON_STANDINGS_SCHEMA}")
    if standings.get("target_season") != season_key:
        raise RatingLayerError("preseason standings target season differs from preallocation")
    source = standings.get("source")
    if not isinstance(source, Mapping) or source.get("id") != SOURCE_ID:
        raise RatingLayerError("preseason standings have an unsupported source identity")
    competitions = standings.get("competitions")
    if not isinstance(competitions, list):
        raise RatingLayerError("preseason standings have no competitions")
    index: dict[str, list[dict[str, Any]]] = {}
    division_seen: set[str] = set()
    for competition in competitions:
        if not isinstance(competition, Mapping):
            raise RatingLayerError("preseason standings competition must be an object")
        division = str(competition.get("division") or "")
        rows = competition.get("standing")
        if division not in DIVISION_ORDER or division in division_seen or not isinstance(rows, list):
            raise RatingLayerError("preseason standings competition is invalid or duplicated")
        division_seen.add(division)
        for expected_rank, row in enumerate(rows, start=1):
            if not isinstance(row, Mapping):
                raise RatingLayerError("preseason standings row must be an object")
            rank = row.get("rank")
            keys = _club_keys(row.get("club"))
            if not keys or rank != expected_rank:
                raise RatingLayerError("preseason standings contain an invalid club or rank")
            record = {"division": division, "rank": rank, "club": str(row["club"])}
            for key in keys:
                index.setdefault(key, []).append(record)
    if division_seen != set(DIVISION_ORDER):
        raise RatingLayerError("preseason standings must contain E0 through E3 exactly once")
    return index


def _resolve_standing(
    *, index: Mapping[str, Sequence[Mapping[str, Any]]], club_name: str,
) -> tuple[dict[str, Any] | None, str | None]:
    # Prefer the explicit name/alias before considering safe shortened names.
    # Otherwise both Manchester clubs, for example, also generate the shared
    # fallback key ``man`` and would be incorrectly labelled ambiguous.
    primary = _club_key(club_name)
    primary_rows = index.get(primary, [])
    if len(primary_rows) == 1:
        return dict(primary_rows[0]), None
    if len(primary_rows) > 1:
        return None, "club-ambiguous-in-prior-english-standing"
    candidates: dict[tuple[str, int], Mapping[str, Any]] = {}
    for key in _club_keys(club_name):
        for row in index.get(key, []):
            candidates[(str(row["division"]), int(row["rank"]))] = row
    if not candidates:
        return None, "club-missing-from-prior-english-standing"
    if len(candidates) > 1:
        return None, "club-ambiguous-in-prior-english-standing"
    return dict(next(iter(candidates.values()))), None


def _preseason_strength(*, division: str, standing: Mapping[str, Any] | None) -> tuple[int, str]:
    """Map prior achievement to an intentionally reviewable PM99 strength.

    The current division supplies the normal level; the completed previous
    season determines whether the club is a title contender, established side,
    newcomer, or relegated club expected to challenge again.  This makes the
    game-engine objective input vary *within* each competition while retaining
    one deterministic policy for every season.
    """
    baseline = DIVISION_STRENGTH[division]
    current_source = DIVISION_SOURCE[division]
    if standing is None:
        return baseline - 12, "not-in-prior-four-english-divisions"
    prior_source = str(standing["division"])
    rank = int(standing["rank"])
    distance = DIVISION_ORDER[prior_source] - DIVISION_ORDER[current_source]
    if distance == 0:
        # The top four prior finishers get a visible confidence difference;
        # the rest taper smoothly through the existing division's range.
        return max(30, baseline + 16 - round(1.75 * (rank - 1))), "same-division-prior-finish"
    if distance < 0:
        # A club relegated from the higher division is usually expected to
        # compete near the top of its new division, not to inherit its raw
        # previous overall strength unchanged.
        return min(95, baseline + 10 - max(0, -distance - 1) * 4), "relegated-from-higher-division"
    if distance == 1:
        # Newly promoted clubs start lower even when they won the division
        # below.  This avoids promoting them directly to a title objective.
        return max(30, baseline - 7 - min(5, (rank - 1) // 4)), "promoted-from-lower-division"
    return max(30, baseline - 12), "promoted-from-outside-adjacent-division"


def _person_id(row: Mapping[str, Any]) -> str:
    source_id = str(row.get("opening_source_player_id") or "").strip()
    if source_id:
        return f"person-transfermarkt-{source_id}"
    row_sha = str(row.get("source_row_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", row_sha):
        raise RatingLayerError("player lacks a stable source-row identity")
    return f"person-source-{row_sha}"


def materialise(
    *, preallocation: Mapping[str, Any], preallocation_sha256: str,
    preseason_standings: Mapping[str, Any] | None = None,
    preseason_standings_sha256: str | None = None,
    squad_limit: int = 25,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if preallocation.get("schema_version") != PREALLOCATION_SCHEMA:
        raise RatingLayerError(f"preallocation must have schema {PREALLOCATION_SCHEMA}")
    if not 20 <= squad_limit <= 25:
        raise RatingLayerError("squad_limit must be between 20 and 25")
    season = preallocation.get("season")
    if not isinstance(season, Mapping) or not re.fullmatch(r"(?:19|20)\d{2}/\d{2}", str(season.get("label") or "")):
        raise RatingLayerError("preallocation must declare a YYYY/YY season")
    start_year = int(str(season["label"])[:4])
    season_key = _season_key(season["label"])
    standing_by_club = (
        _standing_index(standings=preseason_standings, season_key=season_key)
        if preseason_standings is not None else {}
    )
    english = []
    dates = []
    for club in preallocation.get("source_clubs") or []:
        selector = club.get("selector") or {}
        division = COMPETITION_DIVISION.get(str(selector.get("competition_catalog") or ""))
        if str(selector.get("country_catalog") or "") != "eng" or division is None:
            continue
        english.append((club, division))
        date = str(club.get("opening_fixture_date") or "")
        if date.startswith(f"{start_year:04d}-"):
            dates.append(date)
    snapshot_date = min(dates) if dates else f"{start_year:04d}-08-01"
    hierarchy = []
    candidate_players = []
    candidate_names: dict[str, tuple[str, str]] = {}
    gaps = []
    warnings = []
    strength_rows: list[dict[str, Any]] = []
    for club, division in sorted(english, key=lambda item: (_normalise(item[0]["selector"]["club_name"]), item[1])):
        selector = club["selector"]
        club_name = str(selector["club_name"])
        club_id = f"eng-{_normalise(selector['competition_catalog'])}-{_normalise(club_name)}"
        standing, standing_error = (
            _resolve_standing(index=standing_by_club, club_name=club_name)
            if preseason_standings is not None else (None, None)
        )
        strength, method = _preseason_strength(division=division, standing=standing)
        if preseason_standings is not None and standing_error is not None:
            gaps.append({
                "club": club_name, "division": division,
                "reason": standing_error,
                "fallback_strength": strength,
            })
        hierarchy.append({"club_id": club_id, "strength": strength, "source_ids": [POLICY_ID, SOURCE_ID]})
        strength_rows.append({
            "club": club_name, "current_division": division, "strength": strength,
            "method": method,
            "prior_division": standing.get("division") if standing is not None else None,
            "prior_rank": standing.get("rank") if standing is not None else None,
            "prior_club": standing.get("club") if standing is not None else None,
        })
        for row in list(club.get("players") or [])[:squad_limit]:
            facts = row.get("facts") or {}
            name = str(facts.get("name") or "").strip()
            position = str(facts.get("position") or "").upper()
            if position not in {"G", "D", "M", "F"}:
                position = "M"
                warnings.append({
                    "club": club_name, "player": name,
                    "source_row_sha256": row.get("source_row_sha256"),
                    "reason": "deterministic-editorial-primary-position-fallback",
                    "fallback_position": position,
                })
            person_id = _person_id(row)
            birth = facts.get("birth_date")
            if birth is not None:
                try:
                    parsed = dt.date.fromisoformat(str(birth))
                    if parsed > dt.date.fromisoformat(snapshot_date):
                        raise ValueError
                except ValueError:
                    warnings.append({"club": club_name, "player": name, "reason": "invalid-birth-date-omitted-from-rating-context", "value": birth})
                    birth = None
            player_id = f"rating-{hashlib.sha256(f'{person_id}|{club_id}'.encode()).hexdigest()[:24]}"
            candidate_names[f"{player_id}|{club_id}"] = (club_name, name)
            candidate_players.append({
                "player_id": player_id, "person_id": person_id, "club_id": club_id,
                "position": position, "birth_date": birth,
                "opening_fixture_date": str(club.get("opening_fixture_date") or ""),
                "height_cm": facts.get("height_cm") if isinstance(facts.get("height_cm"), int) and not isinstance(facts.get("height_cm"), bool) else None,
                "squad_status": "starting_xi" if isinstance(row.get("opening_xi_order"), int) else "opening_squad",
            })
    person_counts = Counter(row["person_id"] for row in candidate_players)
    representatives: dict[str, dict[str, Any]] = {}
    for row in candidate_players:
        current = representatives.get(row["person_id"])
        key = (row["opening_fixture_date"] or "9999-99-99", row["club_id"], row["player_id"])
        current_key = (
            current["opening_fixture_date"] or "9999-99-99", current["club_id"], current["player_id"]
        ) if current is not None else None
        if current_key is None or key < current_key:
            representatives[row["person_id"]] = row
    for person_id, count in sorted(person_counts.items()):
        if count > 1:
            representative = representatives[person_id]
            warnings.append({
                "person_id": person_id,
                "reason": "multiple-opening-squad-claims-rated-on-earliest-fixture-instance",
                "claim_count": count,
                "representative_club_id": representative["club_id"],
                "representative_fixture_date": representative["opening_fixture_date"],
            })
    players = []
    player_names: dict[str, tuple[str, str]] = {}
    for row in representatives.values():
        model_row = {key: value for key, value in row.items() if key != "opening_fixture_date"}
        players.append(model_row)
        player_names[row["player_id"]] = candidate_names[f"{row['player_id']}|{row['club_id']}"]
    rating_input = {
        "schema_version": model.INPUT_SCHEMA, "snapshot_date": snapshot_date,
        "hierarchy": {"schema_version": model.HIERARCHY_SCHEMA, "snapshot_date": snapshot_date, "clubs": hierarchy},
        "players": players,
    }
    output = model.build_rating_output(rating_input)
    by_club: dict[str, list[dict[str, Any]]] = {str(club[0]["selector"]["club_name"]): [] for club in english}
    rating_by_person = {row["person_id"]: row for row in output["player_ratings"]}
    for instance in candidate_players:
        row = rating_by_person[instance["person_id"]]
        club_name, player_name = candidate_names[f"{instance['player_id']}|{instance['club_id']}"]
        by_club[club_name].append({"player": player_name, "ratings": dict(row["ratings"]["values"]), "person_id": row["person_id"], "provenance": dict(row["ratings"]["provenance"])})
    layer = {"schema_version": "pm99-season-rating-layer-v1", "season": dict(season), "rows": [{"club": club, "players": rows} for club, rows in sorted(by_club.items(), key=lambda item: _normalise(item[0]))]}
    audit = {
        "schema_version": SCHEMA, "season": dict(season),
        "sources": {
            "preallocation_sha256": preallocation_sha256,
            "preseason_standings_sha256": preseason_standings_sha256,
            "rating_model_sha256": model.MODEL_SHA256,
            "policy_id": POLICY_ID,
        },
        "division_strengths": dict(DIVISION_STRENGTH),
        "club_strengths": sorted(strength_rows, key=lambda row: _normalise(row["club"])),
        "coverage": {
            "english_club_count": len(english), "rated_player_count": len(candidate_players),
            "unique_rated_person_count": len(players),
            "missing_primary_position_count": sum(row["reason"] == "primary-position-required-for-editorial-rating" for row in gaps),
            "stable_person_collision_count": sum(count > 1 for count in person_counts.values()),
            "gap_count": len(gaps), "warning_count": len(warnings),
        },
        "gaps": gaps, "warnings": warnings,
        "rating_layer_sha256": hashlib.sha256(canonical_json_bytes(layer)).hexdigest(),
    }
    return layer, audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preallocation", type=Path, required=True)
    parser.add_argument("--preseason-standings", type=Path)
    parser.add_argument("--squad-limit", type=int, default=25)
    parser.add_argument("--output-ratings", type=Path, required=True)
    parser.add_argument("--output-audit", type=Path, required=True)
    args = parser.parse_args()
    raw = args.preallocation.read_bytes()
    preallocation = json.loads(raw.decode("utf-8"))
    standings_raw = args.preseason_standings.read_bytes() if args.preseason_standings else None
    standings = json.loads(standings_raw.decode("utf-8")) if standings_raw is not None else None
    layer, audit = materialise(
        preallocation=preallocation, preallocation_sha256=hashlib.sha256(raw).hexdigest(),
        preseason_standings=standings,
        preseason_standings_sha256=hashlib.sha256(standings_raw).hexdigest() if standings_raw is not None else None,
        squad_limit=args.squad_limit,
    )
    for path, value in ((args.output_ratings, layer), (args.output_audit, audit)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(value))
    print(json.dumps(audit["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
