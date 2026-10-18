#!/usr/bin/env python3
"""Resolve world-2015 missing FIFA ratings with a deterministic editorial policy.

The input full-roster draft preserves complete FIFA16 candidate values where
they exist.  This tool fills only its explicit ``editorial-fallback-required``
rows, using a carrier/country hierarchy derived from those retained candidates,
dated opening-fixture role, source-squad-order band, age and broad position.
It produces source/package JSON only and never writes PM99 files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "pm99-world-2015-editorial-fallback-ratings-v1"
INPUT_SCHEMA = "pm99-world-2015-full-fixed-roster-carrier-drafts-v1"
RATING_KEYS = ("rating", "sprint_speed", "stamina", "aggression", "short_pass", "stand_tackle", "heading", "finishing", "dribbling", "gk_handling")
POSITION_DELTAS = {
    "G": {"sprint_speed": -21, "stamina": -14, "aggression": -11, "short_pass": -9, "stand_tackle": -25, "heading": -30, "finishing": -37, "dribbling": -31, "gk_handling": 0},
    "D": {"sprint_speed": -6, "stamina": 2, "aggression": 4, "short_pass": -4, "stand_tackle": 6, "heading": 5, "finishing": -19, "dribbling": -11, "gk_handling": -9},
    "M": {"sprint_speed": 2, "stamina": 6, "aggression": 1, "short_pass": 5, "stand_tackle": 1, "heading": -2, "finishing": -2, "dribbling": 3, "gk_handling": -9},
    "F": {"sprint_speed": 6, "stamina": 3, "aggression": 1, "short_pass": -1, "stand_tackle": -20, "heading": 2, "finishing": 9, "dribbling": 4, "gk_handling": -9},
}
ROLE_BONUS = {"starting_lineup": 5, "substitutes": 1, "source-squad-core": 0, "source-squad-depth": -4}


class EditorialFallbackError(ValueError):
    """The full-roster source draft cannot be safely transformed."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _read_canonical(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EditorialFallbackError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise EditorialFallbackError(f"{label} must be canonical JSON")
    return value, hashlib.sha256(raw).hexdigest()


def _clamp(value: int) -> int:
    return max(1, min(99, int(value)))


def _variation(*, carrier_id: int, player_id: int, field: str) -> int:
    digest = hashlib.sha256(f"world-2015-editorial-fallback-v1|{carrier_id}|{player_id}|{field}".encode()).digest()
    return int(digest[0] % 7) - 3


def _age(birth_date: object) -> int | None:
    try:
        year, month, day = (int(part) for part in str(birth_date).split("-"))
    except ValueError:
        # The full carrier remains source-blocked, but its rating can still
        # receive the deterministic non-age component.  Treating a missing
        # date as age zero would be worse than an explicit neutral adjustment.
        return None
    return 2015 - year - int((month, day) > (8, 8))


def _age_adjustment(age: int | None) -> int:
    if age is None:
        return 0
    return -5 if age <= 18 else (-3 if age <= 21 else (1 if 25 <= age <= 31 else (-2 if age >= 35 else 0)))


def _role(player: Mapping[str, Any]) -> str:
    opening = player.get("opening_fixture_presence")
    if isinstance(opening, dict) and opening.get("lineup_role") in {"starting_lineup", "substitutes"}:
        return str(opening["lineup_role"])
    index = player.get("source_squad_index")
    return "source-squad-core" if isinstance(index, int) and index <= 16 else "source-squad-depth"


def _known_values(draft: Mapping[str, Any]) -> tuple[dict[int, list[int]], dict[str, list[int]], list[int]]:
    by_carrier: dict[int, list[int]] = defaultdict(list)
    by_country: dict[str, list[int]] = defaultdict(list)
    all_values: list[int] = []
    for carrier in draft["carrier_drafts"]:
        club = carrier.get("club") or {}
        country = str((club.get("strict_identity") or {}).get("country_catalog") or "unknown")
        carrier_id = int(carrier["carrier_id"])
        for player in carrier["players"]:
            rating = player.get("rating_disposition") or {}
            if rating.get("status") != "fifa16-complete-candidate":
                continue
            value = (rating.get("values") or {}).get("rating")
            if not isinstance(value, int):
                raise EditorialFallbackError("complete FIFA16 candidate lacks quality value")
            by_carrier[carrier_id].append(value)
            by_country[country].append(value)
            all_values.append(value)
    if not all_values:
        raise EditorialFallbackError("full-roster draft has no retained FIFA16 hierarchy values")
    return by_carrier, by_country, all_values


def _hierarchy(values: list[int], fallback: list[int]) -> tuple[int, int, str]:
    source = values if len(values) >= 3 else fallback
    if not source:
        raise EditorialFallbackError("editorial hierarchy lacks fallback values")
    base = int(round(statistics.median(source)))
    ceiling = int(sorted(source)[max(0, int(round((len(source) - 1) * 0.9)))])
    return base, max(base + 4, ceiling), "carrier-retained-fifa16" if source is values else "country-or-global-retained-fifa16"


def _editorial_values(*, carrier_id: int, player: Mapping[str, Any], base: int, ceiling: int, hierarchy_source: str) -> dict[str, Any]:
    source = player.get("source_player")
    if not isinstance(source, dict):
        raise EditorialFallbackError("fallback player lacks source facts")
    position = source.get("position")
    if position not in POSITION_DELTAS:
        raise EditorialFallbackError(f"fallback player has invalid position: {position!r}")
    age = _age(source.get("birth_date"))
    role = _role(player)
    quality = _clamp(min(ceiling, base + ROLE_BONUS[role] + _age_adjustment(age) + _variation(carrier_id=carrier_id, player_id=int(player["player_carrier_id"]), field="quality")))
    height = int(source.get("height_cm") or 180)
    aerial = max(-4, min(7, (height - 180) // 3))
    values: dict[str, int] = {"rating": quality}
    for field in RATING_KEYS:
        if field == "rating":
            continue
        value = quality + POSITION_DELTAS[position][field] + _variation(carrier_id=carrier_id, player_id=int(player["player_carrier_id"]), field=field)
        if field == "heading":
            value += aerial
        if position == "G" and field == "gk_handling":
            value = max(value, max(35, quality - 12))
        values[field] = _clamp(value)
    return {
        "status": "editorial-fallback-applied",
        "values": values,
        "basis": {
            "policy_schema": SCHEMA,
            "policy_version": "v1",
            "source": "deterministic-editorial-context-transform; no FIFA16 value existed for this player",
            "hierarchy_source": hierarchy_source,
            "carrier_quality_baseline": base,
            "carrier_star_protection_ceiling": ceiling,
            "source_squad_role": role,
            "source_squad_role_bonus": ROLE_BONUS[role],
            "age_on_2015_08_08": age,
            "age_adjustment": _age_adjustment(age),
            "broad_position": position,
            "height_aerial_adjustment": aerial,
            "stable_separator": _variation(carrier_id=carrier_id, player_id=int(player["player_carrier_id"]), field="quality"),
        },
    }


def build_editorial_fallback_receipt(*, full_roster_draft: Mapping[str, Any]) -> dict[str, Any]:
    if full_roster_draft.get("schema_version") != INPUT_SCHEMA or not isinstance(full_roster_draft.get("carrier_drafts"), list):
        raise EditorialFallbackError("full-roster draft has the wrong schema")
    by_carrier, by_country, all_known = _known_values(full_roster_draft)
    output = json.loads(json.dumps(full_roster_draft))
    values: list[int] = []
    applied = 0
    retained = 0
    statuses: Counter[str] = Counter()
    for carrier in output["carrier_drafts"]:
        carrier_id = int(carrier["carrier_id"])
        country = str(((carrier.get("club") or {}).get("strict_identity") or {}).get("country_catalog") or "unknown")
        base, ceiling, hierarchy_source = _hierarchy(by_carrier.get(carrier_id, []), by_country.get(country, all_known))
        for player in carrier["players"]:
            rating = player.get("rating_disposition")
            if not isinstance(rating, dict):
                raise EditorialFallbackError("full-roster player lacks a rating disposition")
            if rating.get("status") == "editorial-fallback-required":
                requested = dict(rating)
                rating = _editorial_values(carrier_id=carrier_id, player=player, base=base, ceiling=ceiling, hierarchy_source=hierarchy_source)
                # Retain rejected FIFA candidates/reasons as proof that this
                # editorial value did not silently choose a wrong identity.
                if requested.get("candidate_fifa16_player_ids"):
                    rating["basis"]["fifa16_nonmatching_candidate_provenance"] = {
                        "fifa16_match_status": requested.get("fifa16_match_status"),
                        "candidate_fifa16_player_ids": requested["candidate_fifa16_player_ids"],
                        "reason": requested.get("reason"),
                        "identity_basis": requested.get("identity_basis"),
                    }
                player["rating_disposition"] = rating
                applied += 1
            elif rating.get("status") == "fifa16-complete-candidate":
                rating["basis"] = {"source": "retained-complete-fifa16-candidate; not editorially transformed"}
                retained += 1
            elif rating.get("status") == "identity-resolution-required":
                # An ambiguous FIFA identity is a source problem, not a
                # licence to give one of several people an editorial value.
                statuses["identity-resolution-required"] += 1
                continue
            else:
                raise EditorialFallbackError(f"unsupported rating disposition {rating.get('status')!r}")
            quality = (player["rating_disposition"].get("values") or {}).get("rating")
            if not isinstance(quality, int):
                raise EditorialFallbackError("resolved player rating has no quality")
            values.append(quality)
            statuses[str(player["rating_disposition"]["status"])] += 1
        carrier["blockers"] = [
            blocker for blocker in carrier["blockers"] if blocker != "player-rating-editorial-fallback-required"
        ]
    if len(set(values)) < 20 or max(values) - min(values) < 28:
        raise EditorialFallbackError("resolved rating distribution is implausibly flat")
    output["schema_version"] = SCHEMA
    output["sources"] = {
        "full_roster_draft_sha256": hashlib.sha256(canonical_json_bytes(full_roster_draft)).hexdigest(),
        "upstream_sources": full_roster_draft.get("sources"),
    }
    output["rating_policy"] = {
        "summary": "position-shaped deterministic editorial fallback using retained club/country FIFA16 hierarchy, source-squad role, age, height and stable separator; retained FIFA16 candidates are unchanged",
        "no_fabrication_policy": "only rows explicitly marked editorial-fallback-required are transformed; every output row records a basis",
    }
    output["coverage"] = {
        "strict_linked_carrier_count": len(output["carrier_drafts"]),
        "fixed_roster_slot_count": sum(len(row["players"]) for row in output["carrier_drafts"]),
        "retained_fifa16_candidate_count": retained,
        "editorial_fallback_applied_count": applied,
        "identity_resolution_required_count": statuses["identity-resolution-required"],
        "rating_status_counts": dict(sorted(statuses.items())),
        "quality_distribution": {"minimum": min(values), "maximum": max(values), "distinct_values": len(set(values)), "mean": round(sum(values) / len(values), 2), "elite_85_plus": sum(value >= 85 for value in values), "poor_52_or_less": sum(value <= 52 for value in values)},
        "compiler_package_ready_carrier_count": sum(row["status"] == "complete" for row in output["carrier_drafts"]),
        "compiler_package_blocked_carrier_count": sum(row["status"] == "blocked" for row in output["carrier_drafts"]),
    }
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-roster-draft", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    draft, _ = _read_canonical(args.full_roster_draft, label="full-roster draft")
    try:
        result = build_editorial_fallback_receipt(full_roster_draft=draft)
    except EditorialFallbackError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps(result["coverage"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
